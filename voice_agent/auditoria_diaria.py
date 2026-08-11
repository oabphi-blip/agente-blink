"""Auditoria diária retroativa — passa os turnos das últimas 24h pelo juiz
adversarial e gera relatório agregado.

Origem: sprint SRE 18/06/2026. Bugs C-30 a C-37 mostraram que sintomas só
aparecem quando paciente reclama. Precisamos descobrir ANTES via
auditoria automática.

Como funciona:

1. `varrer_conversas_24h()` faz SCAN em todas as keys `blink:trace:*` do
   Redis (lista FIFO por lead, populada pelo `tracing.TraceBuilder`).
   Cada item da lista é 1 turno serializado JSON. Filtra os que estão
   no intervalo das últimas 24h.
2. `auditar_turno()` chama `juiz_adversarial.JuizAdversarial.julgar()`
   passando (resposta_lia, ctx_resumo, user_text) — devolve um veredicto
   com risco/motivos/recomendado.
3. `agregar_sintomas()` agrupa por motivo (ex: "hesitacao_agenda": 4),
   ordena por frequência, e seleciona top 10 leads com maior risco.
4. `relatorio_diario()` orquestra tudo e devolve dict pro endpoint/cron.
5. `gerar_slack_message()` formata pra Slack (texto pronto pra `text:`).

Worker `_worker_auditoria_diaria_loop` (em `cron_interno.py`) chama
`relatorio_diario()` 1x/dia às 7h BRT e posta no Slack via
`SLACK_WEBHOOK_AUDITORIA_URL`. Dedup Redis garante 1 post/dia.

Custo: ~200 turnos/dia × ~$0.001/turno (Haiku) ≈ $0.20/dia.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)


# Prefixo das listas de tracing (deve casar com `tracing._redis_key`).
_TRACE_KEY_PATTERN = "blink:trace:*"

# URL base pro link `/admin/replay/{lead_id}` no Slack.
_REPLAY_URL_BASE_DEFAULT = "https://blink-agent.6prkfn.easypanel.host"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode(raw: Any) -> str:
    """Decoda bytes pra str. Tolera str puro."""
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""
    return str(raw) if raw is not None else ""


def _parse_lead_id_da_key(key: str) -> Optional[int]:
    """De `blink:trace:24168922` → 24168922. None se não casar."""
    if not key:
        return None
    parts = key.split(":")
    if len(parts) < 3:
        return None
    try:
        return int(parts[-1])
    except (TypeError, ValueError):
        return None


def _truncar(texto: str, limite: int = 300) -> str:
    if not texto:
        return ""
    s = str(texto)
    return s if len(s) <= limite else s[:limite] + "…"


# ---------------------------------------------------------------------------
# 1. Varredura Redis — últimos N turnos no intervalo 24h
# ---------------------------------------------------------------------------

def varrer_conversas_24h(
    redis_client: Any,
    *,
    agora_epoch: Optional[float] = None,
    janela_segundos: int = 24 * 3600,
    max_turnos_total: int = 5000,
) -> list[dict]:
    """Itera todas as keys `blink:trace:*` via SCAN, lê cada lista, filtra
    turnos com `ts_epoch >= agora - janela_segundos`.

    Devolve lista de dicts no formato:
        {lead_id, ts, prompt_truncated, resposta_lia, ctx_summary}

    `prompt_truncated` = user_text do paciente truncado a 300 chars.
    `resposta_lia` = output_final completo (o que foi enviado).
    `ctx_summary` = ctx_resumo do trace.

    `max_turnos_total` é safety-cap pra não estourar memória/custo.
    """
    if not redis_client:
        return []
    agora = agora_epoch if agora_epoch is not None else time.time()
    corte_min = agora - janela_segundos

    turnos: list[dict] = []
    try:
        # scan_iter retorna iterador de keys casando o pattern.
        keys_iter: Iterable[Any] = redis_client.scan_iter(
            match=_TRACE_KEY_PATTERN, count=200,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[AUDITORIA] scan_iter falhou: %s", e)
        return []

    for raw_key in keys_iter:
        if len(turnos) >= max_turnos_total:
            break
        key = _decode(raw_key)
        lead_id = _parse_lead_id_da_key(key)
        if lead_id is None:
            continue
        try:
            raw_list = redis_client.lrange(key, 0, -1) or []
        except Exception as e:  # noqa: BLE001
            log.warning("[AUDITORIA] lrange %s falhou: %s", key, e)
            continue
        for raw in raw_list:
            if len(turnos) >= max_turnos_total:
                break
            txt = _decode(raw)
            if not txt:
                continue
            try:
                d = json.loads(txt)
            except Exception:  # noqa: BLE001
                continue
            ts = d.get("ts_epoch") or 0
            try:
                ts_f = float(ts)
            except (TypeError, ValueError):
                ts_f = 0.0
            if ts_f < corte_min:
                continue
            turnos.append({
                "lead_id": lead_id,
                "ts": int(ts_f),
                "prompt_truncated": _truncar(d.get("user_text") or "", 300),
                "resposta_lia": d.get("output_final") or "",
                "ctx_summary": d.get("ctx_resumo") or {},
            })

    # Ordena por timestamp asc pra ter histórico estável.
    turnos.sort(key=lambda x: x.get("ts") or 0)
    return turnos


# ---------------------------------------------------------------------------
# 2. Auditar turno via juiz_adversarial
# ---------------------------------------------------------------------------

def auditar_turno(turno: dict, juiz: Any = None) -> dict:
    """Chama `juiz.julgar(lia_text, ctx, user_text)` e empacota o veredicto.

    Devolve:
        {lead_id, ts, risco, motivos, recomendacao}

    Em erro / juiz=None, devolve veredicto neutro (risco=0, recomendar=enviar).
    """
    lead_id = turno.get("lead_id")
    ts = turno.get("ts")
    resposta = turno.get("resposta_lia") or ""
    ctx = turno.get("ctx_summary") or {}
    user_text = turno.get("prompt_truncated") or ""

    # Sem resposta da Lia, sem o que auditar.
    if not resposta or not resposta.strip():
        return {
            "lead_id": lead_id, "ts": ts,
            "risco": 0, "motivos": [], "recomendacao": "enviar",
        }

    j = juiz
    if j is None:
        try:
            from voice_agent.juiz_adversarial import JuizAdversarial
            j = JuizAdversarial.from_env()
        except Exception as e:  # noqa: BLE001
            log.warning("[AUDITORIA] juiz indisponível: %s", e)
            j = None

    if j is None:
        return {
            "lead_id": lead_id, "ts": ts,
            "risco": 0, "motivos": [], "recomendacao": "enviar",
        }

    try:
        # Aceita tanto a chamada de método `julgar` (Anthropic Haiku real)
        # quanto um simulado `avaliar` (mocks em test). Compatível com ambos.
        if hasattr(j, "julgar"):
            v = j.julgar(lia_text=resposta, ctx=ctx, user_text=user_text)
        elif hasattr(j, "avaliar"):
            v = j.avaliar(lia_text=resposta, ctx=ctx, user_text=user_text)
        else:
            return {
                "lead_id": lead_id, "ts": ts,
                "risco": 0, "motivos": [], "recomendacao": "enviar",
            }
    except Exception as e:  # noqa: BLE001
        log.warning("[AUDITORIA] julgar falhou lead=%s ts=%s: %s",
                    lead_id, ts, e)
        return {
            "lead_id": lead_id, "ts": ts,
            "risco": 0, "motivos": ["erro_juiz"], "recomendacao": "enviar",
        }

    # Veredicto pode ser dataclass (VeredictoJuiz) ou dict — normaliza.
    if isinstance(v, dict):
        risco = int(v.get("risco", 0) or 0)
        motivos = list(v.get("motivos") or [])
        rec = str(v.get("recomendado", "enviar"))
    else:
        risco = int(getattr(v, "risco", 0) or 0)
        motivos = list(getattr(v, "motivos", []) or [])
        rec = str(getattr(v, "recomendado", "enviar"))

    return {
        "lead_id": lead_id, "ts": ts,
        "risco": risco, "motivos": motivos, "recomendacao": rec,
    }


# ---------------------------------------------------------------------------
# 3. Agregar sintomas
# ---------------------------------------------------------------------------

def agregar_sintomas(veredictos: list[dict]) -> dict:
    """Agrupa por motivo (string) → contagem, ordena desc.
    Lista top 10 leads com maior risco (último turno arriscado conta).

    Devolve:
        {
          "total_turnos": int,
          "total_risco_alto": int,        # risco >= 70
          "sintomas_top": {motivo: count, ...},  # top 10
          "leads_top": [
             {"lead_id": ..., "risco_max": ..., "motivos": [...]}
          ]  # top 10
        }
    """
    if not veredictos:
        return {
            "total_turnos": 0,
            "total_risco_alto": 0,
            "sintomas_top": {},
            "leads_top": [],
        }

    sintomas: dict[str, int] = {}
    por_lead: dict[Any, dict] = {}
    risco_alto = 0

    for v in veredictos:
        risco = int(v.get("risco", 0) or 0)
        motivos = list(v.get("motivos") or [])
        lead_id = v.get("lead_id")
        if risco >= 70:
            risco_alto += 1
        for m in motivos:
            if not m:
                continue
            sm = str(m).strip().lower().replace(" ", "_")
            sintomas[sm] = sintomas.get(sm, 0) + 1
        if lead_id is not None:
            prev = por_lead.get(lead_id)
            if prev is None or risco > prev["risco_max"]:
                por_lead[lead_id] = {
                    "lead_id": lead_id,
                    "risco_max": risco,
                    "motivos": [str(m) for m in motivos][:6],
                }

    # top 10 sintomas por count desc
    sintomas_ord = dict(
        sorted(sintomas.items(), key=lambda kv: kv[1], reverse=True)[:10]
    )
    # top 10 leads por risco desc
    leads_ord = sorted(
        por_lead.values(),
        key=lambda r: r.get("risco_max", 0),
        reverse=True,
    )[:10]

    return {
        "total_turnos": len(veredictos),
        "total_risco_alto": risco_alto,
        "sintomas_top": sintomas_ord,
        "leads_top": leads_ord,
    }


# ---------------------------------------------------------------------------
# 4. Orquestrador
# ---------------------------------------------------------------------------

def _periodo_iso(agora_epoch: float, janela_segundos: int) -> dict:
    from datetime import datetime, timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    fim = datetime.fromtimestamp(agora_epoch, tz=brt)
    ini = fim - timedelta(seconds=janela_segundos)
    return {
        "inicio_iso": ini.isoformat(timespec="seconds"),
        "fim_iso": fim.isoformat(timespec="seconds"),
    }


def relatorio_diario(
    redis_client: Any,
    *,
    juiz: Any = None,
    agora_epoch: Optional[float] = None,
    janela_segundos: int = 24 * 3600,
    max_turnos_total: int = 5000,
) -> dict:
    """Varre últimas 24h → audita → agrega → empacota.

    Devolve dict no formato:
        {
          "periodo": {"inicio_iso": ..., "fim_iso": ...},
          "total_turnos": int,
          "total_risco_alto": int,
          "sintomas_top": {...},
          "leads_top": [...]
        }
    """
    agora = agora_epoch if agora_epoch is not None else time.time()
    turnos = varrer_conversas_24h(
        redis_client,
        agora_epoch=agora,
        janela_segundos=janela_segundos,
        max_turnos_total=max_turnos_total,
    )
    veredictos = [auditar_turno(t, juiz=juiz) for t in turnos]
    agreg = agregar_sintomas(veredictos)
    return {
        "periodo": _periodo_iso(agora, janela_segundos),
        "total_turnos": agreg["total_turnos"],
        "total_risco_alto": agreg["total_risco_alto"],
        "sintomas_top": agreg["sintomas_top"],
        "leads_top": agreg["leads_top"],
    }


# ---------------------------------------------------------------------------
# 5. Formatador Slack
# ---------------------------------------------------------------------------

def gerar_slack_message(relatorio: dict) -> str:
    """Formata o relatório pra string pronta pro Slack (chave `text:`)."""
    if not isinstance(relatorio, dict):
        return ":mag: *Auditoria diária Lia* — relatório inválido."

    periodo = relatorio.get("periodo") or {}
    total = relatorio.get("total_turnos", 0)
    risco = relatorio.get("total_risco_alto", 0)
    sintomas = relatorio.get("sintomas_top") or {}
    leads = relatorio.get("leads_top") or []

    base = (
        os.environ.get("BLINK_REPLAY_BASE_URL")
        or _REPLAY_URL_BASE_DEFAULT
    ).rstrip("/")

    if total == 0:
        return (
            f":mag: *Auditoria diária Lia* "
            f"({periodo.get('inicio_iso', '?')} → "
            f"{periodo.get('fim_iso', '?')})\n"
            f"Sem turnos auditáveis nas últimas 24h. "
            f"(Tracing ativo?)"
        )

    emoji = ":white_check_mark:" if risco == 0 else ":rotating_light:"
    linhas = [
        f"{emoji} *Auditoria diária Lia* "
        f"({periodo.get('inicio_iso', '?')} → "
        f"{periodo.get('fim_iso', '?')})",
        f"Turnos auditados: *{total}* · "
        f"Risco alto (>=70): *{risco}*",
    ]

    if sintomas:
        linhas.append("")
        linhas.append("*Top sintomas:*")
        for i, (motivo, count) in enumerate(list(sintomas.items())[:5], 1):
            linhas.append(f"  {i}. `{motivo}` — {count}x")

    # Top 3 piores leads com link de replay.
    if leads:
        linhas.append("")
        linhas.append("*Top 3 piores leads (replay):*")
        for r in leads[:3]:
            lid = r.get("lead_id")
            rmax = r.get("risco_max", 0)
            mot = ", ".join(r.get("motivos") or [])[:120] or "—"
            url = f"{base}/admin/replay/{lid}"
            linhas.append(
                f"  • lead `{lid}` risco={rmax} motivos=_{mot}_\n"
                f"    {url}"
            )

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Helpers pro worker (toggle + dedup)
# ---------------------------------------------------------------------------

def auditoria_diaria_habilitada() -> bool:
    """Default ON. Pra desligar: AUDITORIA_DIARIA_ENABLED=0 explicitamente."""
    val = (os.environ.get("AUDITORIA_DIARIA_ENABLED") or "1").lower().strip()
    return val not in ("0", "false", "no", "off", "")


def chave_dedup_dia(agora_epoch: Optional[float] = None) -> str:
    """`blink:auditoria_diaria:YYYY-MM-DD` em BRT."""
    from datetime import datetime, timedelta, timezone
    agora = agora_epoch if agora_epoch is not None else time.time()
    brt = timezone(timedelta(hours=-3))
    return (
        "blink:auditoria_diaria:"
        + datetime.fromtimestamp(agora, tz=brt).strftime("%Y-%m-%d")
    )
