"""Error budget — alvos SLO + detecção de queima + alerta Slack.

SLOs operacionais da Lia (calibrados em 18/06/2026 com base nos 30 dias
anteriores):

  hallucination_rate ≤ 1%   (Lia inventar dado vs total turns)
  agent_uptime       ≥ 99%  (healthz 200 OK)
  delivery_rate      ≥ 95%  (Meta status=delivered / accepted)
  synthetic_pass_rate ≥ 95% (cenários sintéticos passando)

Worker `_worker_error_budget_loop` em cron_interno.py roda a cada 15min,
chama `disparar_alerta_se_necessario()`. Posta no `SLACK_WEBHOOK_ALERTAS_URL`
quando houver violation. Dedup 1h por Redis key
`blink:error_budget_alert:{YYYY-MM-DD-HH}` pra evitar spam.

Toggle `ERROR_BUDGET_ALERTS_ENABLED=1` (default ON, rollback sem deploy).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_TZ_BRT = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Alvos
# ---------------------------------------------------------------------------

ERROR_BUDGET_TARGETS: dict[str, float] = {
    "hallucination_rate": 0.01,    # MENOR-OU-IGUAL é bom
    "agent_uptime": 0.99,          # MAIOR-OU-IGUAL é bom
    "delivery_rate": 0.95,         # MAIOR-OU-IGUAL é bom
    "synthetic_pass_rate": 0.95,   # MAIOR-OU-IGUAL é bom
}

# Métricas onde menor = melhor (invertem comparação)
_METRICAS_MENOR_MELHOR: frozenset[str] = frozenset({"hallucination_rate"})


# ---------------------------------------------------------------------------
# Burn rate
# ---------------------------------------------------------------------------

def _calcular_burn_rate(metrica: str, alvo: float, atual: float) -> float:
    """Quanto do orçamento já queimou.

    Pra métricas "maior é melhor" (uptime=0.99 alvo):
        budget total = 1 - alvo = 0.01 (1% de erro permitido)
        consumido = 1 - atual
        burn = consumido / budget

    Pra "menor é melhor" (hallucination=0.01 alvo):
        budget = alvo
        consumido = atual
        burn = atual / alvo

    Retorna 1.0 = budget esgotado. > 1.0 = estourou. <1.0 = dentro.
    """
    if metrica in _METRICAS_MENOR_MELHOR:
        if alvo <= 0:
            return float("inf") if atual > 0 else 0.0
        return atual / alvo
    # maior é melhor
    budget = 1.0 - alvo
    if budget <= 0:
        # alvo 100% — qualquer falha estoura
        return float("inf") if atual < alvo else 0.0
    consumido = 1.0 - atual
    return consumido / budget


def _severidade(burn_rate: float) -> str:
    if burn_rate >= 2.0:
        return "critical"
    if burn_rate >= 1.0:
        return "critical"
    if burn_rate >= 0.5:
        return "warning"
    return "ok"


def verificar_burn(slos_atuais: dict) -> list[dict]:
    """Compara SLOs atuais × alvos. Retorna list[violation].

    Violation = dict {metrica, alvo, atual, burn_rate, severidade}.
    Só inclui métricas em estado warning OU critical.
    """
    violations: list[dict] = []
    for metrica, alvo in ERROR_BUDGET_TARGETS.items():
        if metrica not in slos_atuais:
            continue
        try:
            atual = float(slos_atuais[metrica])
        except (TypeError, ValueError):
            continue
        burn = _calcular_burn_rate(metrica, alvo, atual)
        sev = _severidade(burn)
        if sev == "ok":
            continue
        violations.append({
            "metrica": metrica,
            "alvo": alvo,
            "atual": atual,
            "burn_rate": round(burn, 3),
            "severidade": sev,
        })
    # Ordena pior primeiro (maior burn rate)
    violations.sort(key=lambda v: -v["burn_rate"])
    return violations


# ---------------------------------------------------------------------------
# Alerta Slack
# ---------------------------------------------------------------------------

def _admin_slo_url() -> str:
    return (
        os.environ.get("ADMIN_SLO_URL")
        or "https://blink-agent.6prkfn.easypanel.host/admin/slo"
    )


def gerar_alerta_slack(violations: list[dict]) -> str:
    """Formata mensagem Slack com top 3 violations.

    Inclui emoji por severidade, link pro painel, contagem total.
    Retorna string vazia se nenhuma violation.
    """
    if not violations:
        return ""
    crit = [v for v in violations if v["severidade"] == "critical"]
    warn = [v for v in violations if v["severidade"] == "warning"]
    emoji = ":rotating_light:" if crit else ":warning:"
    titulo = (
        f"{emoji} *Error Budget — Lia* — "
        f"{len(crit)} crítico, {len(warn)} aviso"
    )
    top = violations[:3]
    linhas = []
    for v in top:
        flecha = ":arrow_down:" if (
            v["metrica"] in _METRICAS_MENOR_MELHOR and v["atual"] > v["alvo"]
        ) else ":arrow_up:"
        if v["metrica"] not in _METRICAS_MENOR_MELHOR:
            # uptime/delivery/synthetic: atual ABAIXO do alvo = problema
            flecha = ":arrow_down:"
        sev_emoji = ":fire:" if v["severidade"] == "critical" else ":warning:"
        linhas.append(
            f"{sev_emoji} *{v['metrica']}* — atual={v['atual']:.3f} "
            f"alvo={v['alvo']:.3f} burn={v['burn_rate']:.2f} {flecha}"
        )
    rodape = f":mag: detalhes: {_admin_slo_url()}"
    return "\n".join([titulo, *linhas, rodape])


# ---------------------------------------------------------------------------
# Coleta dos SLOs (delegada — módulo não força fonte)
# ---------------------------------------------------------------------------

def coletar_slos_atuais() -> dict:
    """Tenta coletar SLOs dos módulos existentes.

    Falhas individuais NÃO derrubam — métrica fica ausente, alvo ignorado.
    Toda métrica é float 0..1 (taxa).
    """
    slos: dict[str, float] = {}

    # 1. synthetic_pass_rate — última execução cached em Redis
    try:
        synthetic_taxa = float(
            os.environ.get("SYNTHETIC_LAST_PASS_RATE") or "1.0"
        )
        slos["synthetic_pass_rate"] = synthetic_taxa
    except (TypeError, ValueError):
        pass

    # 2. delivery_rate / agent_uptime / hallucination_rate
    # Lê do metricas_funcionamento se disponível
    try:
        from voice_agent import metricas_funcionamento as mf
        snap = mf.funcionamento_hoje(None) or {}
        taxas = snap.get("taxas") or {}
        for k, v in taxas.items():
            if k in ERROR_BUDGET_TARGETS:
                try:
                    slos[k] = float(v)
                except (TypeError, ValueError):
                    pass
    except Exception:  # noqa: BLE001
        pass

    return slos


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------

def _alerts_habilitado() -> bool:
    # Default ON (rollback explícito)
    raw = (os.environ.get("ERROR_BUDGET_ALERTS_ENABLED") or "1").lower()
    return raw not in ("0", "false", "no", "off", "")


def _slack_webhook_url() -> Optional[str]:
    return (os.environ.get("SLACK_WEBHOOK_ALERTAS_URL") or "").strip() or None


def _dedup_key_atual() -> str:
    """Chave dedup por hora (YYYY-MM-DD-HH BRT)."""
    h = datetime.now(_TZ_BRT).strftime("%Y-%m-%d-%H")
    return f"blink:error_budget_alert:{h}"


def disparar_alerta_se_necessario(
    redis_client=None,
    slos_atuais: Optional[dict] = None,
    http_client: Optional[httpx.Client] = None,
) -> dict:
    """Pipeline completo: coleta SLOs → verifica burn → posta Slack se preciso.

    Args:
        redis_client: Redis pra dedup (opcional).
        slos_atuais: override de coleta (testes).
        http_client: httpx.Client (testes mockam).

    Retorna `{enviou, violations, motivo}`.
    """
    if not _alerts_habilitado():
        return {"enviou": False, "violations": [], "motivo": "disabled"}

    slos = slos_atuais if slos_atuais is not None else coletar_slos_atuais()
    violations = verificar_burn(slos)

    if not violations:
        return {"enviou": False, "violations": [], "motivo": "no_violation"}

    # Dedup por hora (não spammar mesmo alerta a cada 15min)
    dedup_key = _dedup_key_atual()
    if redis_client is not None:
        try:
            ja = redis_client.get(dedup_key)
            if ja:
                return {
                    "enviou": False, "violations": violations,
                    "motivo": "dedup_hit",
                }
        except Exception as e:  # noqa: BLE001
            log.warning("[ERROR_BUDGET] redis dedup falhou: %s", e)

    url = _slack_webhook_url()
    if not url:
        # Sem webhook configurado, registra mas não estoura
        log.warning(
            "[ERROR_BUDGET] %d violations mas SLACK_WEBHOOK_ALERTAS_URL "
            "ausente: %s",
            len(violations), violations[:3],
        )
        return {
            "enviou": False, "violations": violations,
            "motivo": "no_webhook",
        }

    texto = gerar_alerta_slack(violations)
    try:
        cli = http_client or httpx.Client(timeout=10.0)
        cli.post(url, json={"text": texto})
        if http_client is None:
            cli.close()
        log.warning(
            "[ERROR_BUDGET] alerta postado — %d violations",
            len(violations),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[ERROR_BUDGET] slack post falhou: %s", e)
        return {
            "enviou": False, "violations": violations,
            "motivo": f"slack_error: {e}"[:200],
        }

    # Grava dedup só se posta com sucesso
    if redis_client is not None:
        try:
            redis_client.setex(dedup_key, 3600, "1")
        except Exception as e:  # noqa: BLE001
            log.warning("[ERROR_BUDGET] redis setex falhou: %s", e)

    return {"enviou": True, "violations": violations, "motivo": "ok"}
