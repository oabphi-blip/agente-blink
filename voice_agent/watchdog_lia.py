"""Watchdog "Lia muda" — Pilar #4 da fila de robustez.

Origem: Fábio 01/06/2026 — sintoma recorrente "Lia recebeu inbound
e não voltou". Hoje a única forma de detectar é o paciente reclamar
no WhatsApp. Esse cron 5 min varre o pipeline ATENDE procurando
leads onde:
- Última atualização foi um INBOUND do paciente (nota começa com
  "Paciente (WhatsApp):" / "💬" / contém número)
- Faz mais de SILENCIO_MAX_SEG (default 5 min) sem outbound da Lia
- IA está ATIVA (campo ATIVADO IA? != "Não ativado" / "Pausado")
- É horário comercial BRT (seg-sáb 8-18h)

Dispara alerta Slack com link Kommo. Não move o lead automaticamente
(princípio: tocar campo do lead = ação humana). Apenas alerta.

Liga via `WATCHDOG_LIA_ENABLED=1`. Webhook
`SLACK_WEBHOOK_WATCHDOG_URL` (ou fallback SLACK_WEBHOOK_URL).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

log = logging.getLogger(__name__)


# Pipeline ATENDE + status onde Lia deveria estar respondendo
PIPELINE_ATENDE = 8601819
STATUS_LIA_DEVE_RESPONDER = [
    96441724,    # 0-ETAPA ENTRADA
    106919911,   # 0-a classificar
    102560495,   # 3-AGENDAR
    106184631,   # 4-REAGENDAR
    106563343,   # 1-ATENDIMENTO HUMANO (caso IA volte a assumir)
]

SILENCIO_MAX_SEG = 5 * 60  # 5 min
SILENCIO_MAX_SEG_DEFAULT = SILENCIO_MAX_SEG

# Janela comercial BRT
HORA_INICIO = 8
HORA_FIM = 18  # exclusive

REDIS_DEDUP_PREFIX = "blink:watchdog:alertado:"
DEDUP_TTL = 30 * 60  # 30 min — pra alertar de novo se persistir


@dataclass
class WatchdogResultado:
    varridos: int = 0
    suspeitos: int = 0
    alertados: int = 0
    ja_alertados_dedup: int = 0
    fora_horario: int = 0
    ia_pausada: int = 0
    erros: int = 0
    detalhes: list[dict] = field(default_factory=list)


def esta_habilitado() -> bool:
    return os.getenv("WATCHDOG_LIA_ENABLED", "0") == "1"


def _webhook_url() -> str:
    return (
        os.getenv("SLACK_WEBHOOK_WATCHDOG_URL")
        or os.getenv("SLACK_WEBHOOK_URL")
        or ""
    )


def _silencio_max() -> int:
    try:
        return int(os.getenv("WATCHDOG_SILENCIO_MAX_SEG",
                             str(SILENCIO_MAX_SEG_DEFAULT)))
    except (TypeError, ValueError):
        return SILENCIO_MAX_SEG_DEFAULT


def _eh_horario_comercial(now: Optional[datetime] = None) -> bool:
    """Seg-Sáb, 8h-18h BRT (UTC-3)."""
    if now is None:
        brt = timezone(timedelta(hours=-3))
        now = datetime.now(brt)
    # Domingo = 6
    if now.weekday() == 6:
        return False
    return HORA_INICIO <= now.hour < HORA_FIM


def _ia_ativa(notas: list[dict]) -> bool:
    """Heurística: se a última nota relevante de status IA disse
    "Pausado" / "Desativado" / "Não ativado" → IA pausada (False).
    Caso contrário, presume ativa."""
    for nota in reversed(notas or []):
        texto = (nota.get("text") or "").lower()
        if "ia desativad" in texto or "ia pausad" in texto:
            return False
        if "ia ativad" in texto or "ativado_ia" in texto:
            return True
    return True


_RE_NOTA_INBOUND = re.compile(
    r"paciente\s*\(whatsapp\)|paciente\s*\(evolution\)|"
    r"\U0001F4AC|^paciente:",
    re.IGNORECASE,
)
_RE_NOTA_OUTBOUND = re.compile(
    r"lia\s*\(whatsapp\)|lia\s*\(evolution\)|\U0001F916|"
    r"^lia:|🤖|^assistente",
    re.IGNORECASE,
)


def _classifica_nota(texto: str) -> str:
    """Devolve 'inbound', 'outbound' ou 'outro'."""
    if not texto:
        return "outro"
    if _RE_NOTA_OUTBOUND.search(texto):
        return "outbound"
    if _RE_NOTA_INBOUND.search(texto):
        return "inbound"
    # Heurística leve: começa com "Paciente"
    head = texto.lstrip()[:30].lower()
    if head.startswith("paciente"):
        return "inbound"
    if head.startswith("lia") or head.startswith("🤖"):
        return "outbound"
    return "outro"


def _ultima_nota_relevante(notas: list[dict]) -> Optional[dict]:
    """Devolve a última nota classificada como inbound ou outbound."""
    for nota in reversed(notas or []):
        t = nota.get("text") or ""
        c = _classifica_nota(t)
        if c in ("inbound", "outbound"):
            n2 = dict(nota)
            n2["_classe"] = c
            return n2
    return None


def _nota_ts(nota: dict) -> int:
    """Extrai timestamp da nota (created_at em ISO ou epoch)."""
    if not nota:
        return 0
    ts = nota.get("created_at")
    if isinstance(ts, int):
        return ts
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:  # noqa: BLE001
            return 0
    return 0


def _classifica_lia_muda(
    lead: dict, agora_ts: int, silencio_max: int,
) -> Optional[str]:
    """True se: tem nota inbound como ÚLTIMA relevante, +
    idade > silencio_max + IA ativa. Devolve motivo ou None."""
    notas = lead.get("notes") or []
    ultima = _ultima_nota_relevante(notas)
    if not ultima or ultima.get("_classe") != "inbound":
        return None
    ts = _nota_ts(ultima)
    if not ts:
        return None
    idade = agora_ts - ts
    if idade < silencio_max:
        return None
    if not _ia_ativa(notas):
        return None
    return f"inbound há {idade}s sem resposta da Lia (limite={silencio_max}s)"


def _ja_alertado(redis_client: Any, lead_id: int) -> bool:
    if not redis_client:
        return False
    try:
        return bool(redis_client.exists(f"{REDIS_DEDUP_PREFIX}{lead_id}"))
    except Exception:  # noqa: BLE001
        return False


def _marca_alertado(redis_client: Any, lead_id: int) -> None:
    if not redis_client:
        return
    try:
        redis_client.setex(
            f"{REDIS_DEDUP_PREFIX}{lead_id}", DEDUP_TTL, int(time.time()),
        )
    except Exception:  # noqa: BLE001
        pass


def _payload_slack(lead_id: int, status_id: int, motivo: str) -> dict:
    return {
        "text": (
            f":mute: *Lia muda* — `{lead_id}` (status `{status_id}`)\n"
            f"• Motivo: {motivo}\n"
            f"• URL: https://univeja.kommo.com/leads/detail/{lead_id}\n"
            "Possíveis causas: Anthropic/OpenAI fora, fila travada, "
            "ctx envenenado, mensagem que entrou em loop. "
            "Recomendado: chamar `/admin/replay/{lead_id}` pra ver "
            "último turno."
        ),
    }


def _envia_slack(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        return False
    try:
        import httpx
        with httpx.Client(timeout=8.0) as c:
            r = c.post(webhook_url, json=payload)
        return 200 <= r.status_code < 300
    except Exception as e:  # noqa: BLE001
        log.warning("[WATCHDOG] erro slack: %s", e)
        return False


def tick(
    kommo: Any,
    redis_client: Any,
    *,
    pipeline_id: int = PIPELINE_ATENDE,
    statuses: Optional[list[int]] = None,
    silencio_max_seg: Optional[int] = None,
    dry_run: bool = False,
    now: Optional[datetime] = None,
    forcar_horario: bool = False,
) -> WatchdogResultado:
    """Roda 1 varredura. Devolve relatório."""
    res = WatchdogResultado()
    if not kommo:
        return res
    if not forcar_horario and not _eh_horario_comercial(now):
        res.fora_horario = 1
        return res
    sids = statuses or STATUS_LIA_DEVE_RESPONDER
    silencio = silencio_max_seg or _silencio_max()
    try:
        leads_basicos = kommo.list_leads_by_status(
            pipeline_id=pipeline_id, status_ids=sids,
            limit=100, page=1,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[WATCHDOG] erro list: %s", e)
        res.erros += 1
        return res
    agora_ts = int(time.time())
    webhook = _webhook_url()
    for ld in leads_basicos:
        res.varridos += 1
        lid = ld.get("id")
        if lid is None:
            continue
        try:
            detalhe = kommo.get_lead(lid) or {}
        except Exception:  # noqa: BLE001
            res.erros += 1
            continue
        motivo = _classifica_lia_muda(detalhe, agora_ts, silencio)
        if not motivo:
            # Conta caso IA pausada como flag pra log
            notas = detalhe.get("notes") or []
            if not _ia_ativa(notas):
                res.ia_pausada += 1
            continue
        res.suspeitos += 1
        if _ja_alertado(redis_client, lid):
            res.ja_alertados_dedup += 1
            continue
        res.detalhes.append({
            "lead_id": lid,
            "status_id": detalhe.get("status_id"),
            "motivo": motivo,
            "url": f"https://univeja.kommo.com/leads/detail/{lid}",
        })
        if dry_run:
            continue
        if webhook and _envia_slack(
            webhook, _payload_slack(lid, detalhe.get("status_id") or 0, motivo),
        ):
            res.alertados += 1
            _marca_alertado(redis_client, lid)
    return res
