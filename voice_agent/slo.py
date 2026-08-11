"""SLO Board — Observabilidade SRE da Lia.

Origem: discussão Fábio 18/06/2026 noite — 12 bugs novos (C-30…C-37c) em 30
dias todos foram descobertos pelo PACIENTE reclamando. Faltava painel que
revelasse instabilidade ANTES da queixa. Este módulo agrega os 4 sinais
mais críticos de qualidade do agente, em janelas 24h e 7d, e calcula o
"error budget" contra metas pré-acordadas.

ALVOS DE SLO (configuráveis via env):
    hallucination_rate    <  1%   (% turnos com qualquer filtro `_viola_*`)
    response_latency_p99  < 8000 ms
    tool_call_success     > 95%
    message_delivery_rate > 95%
    agent_uptime_pct      > 99%

LEITURA DOS DADOS:
- Tracing estruturado (`voice_agent/tracing.py`) — `blink:trace:{lead_id}` lista
  Redis com TTL 30d. Cada item JSON tem `ts_epoch`, `filtros_disparados`,
  `tools_chamadas`, `elapsed_ms`, `output_final`. Usamos `redis.keys("blink:trace:*")`
  + `lrange(key, 0, -1)` em modo defensivo (skips em erro).
- Counters do módulo `metricas_funcionamento` — `blink:func:health:{YYYYMMDD}:ok|fail`
  pra agent_uptime.
- Counters wamid Meta — `blink:wamid:status:{wamid}` setado pelo webhook do Meta
  com status delivered/sent/failed. Lemos via `redis.scan_iter`.
- Kommo `list_leads_by_status` pra contar leads movidos pra ATENDIMENTO HUMANO
  nas últimas 24h (proxy de "escalations").

Quando algum dado não existe (Redis vazio, Kommo down), retornamos `None` em
vez de zero. O dashboard sinaliza "sem dados" em vez de mentir.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------

# Pipeline ATENDE no Kommo (Bug C-29: usar status_ids: list[int] plural)
PIPELINE_ATENDE = 8601819
STATUS_ATENDIMENTO_HUMANO = 106563343

# Janelas
JANELA_24H_SEG = 24 * 3600
JANELA_7D_SEG = 7 * 24 * 3600

# Alvos SLO (defaults — overridable via env)
SLO_HALLUCINATION_PCT_MAX = float(os.getenv("SLO_HALLUCINATION_PCT_MAX", "1.0"))
SLO_UPTIME_PCT_MIN = float(os.getenv("SLO_UPTIME_PCT_MIN", "99.0"))
SLO_LATENCY_P99_MS_MAX = float(os.getenv("SLO_LATENCY_P99_MS_MAX", "8000"))
SLO_DELIVERY_PCT_MIN = float(os.getenv("SLO_DELIVERY_PCT_MIN", "95.0"))
SLO_TOOL_SUCCESS_PCT_MIN = float(os.getenv("SLO_TOOL_SUCCESS_PCT_MIN", "95.0"))


# -----------------------------------------------------------------------
# Helpers utilitários
# -----------------------------------------------------------------------

def _agora_epoch() -> int:
    return int(time.time())


def _agora_brt_iso() -> str:
    brt = timezone(timedelta(hours=-3))
    return datetime.now(brt).isoformat(timespec="seconds")


def _scan_iter(redis_client: Any, match: str) -> Iterable[str]:
    """Wrapper defensivo pra `scan_iter` — tolera mocks/dicts."""
    if redis_client is None:
        return []
    try:
        out = redis_client.scan_iter(match=match)
        return out or []
    except Exception:  # noqa: BLE001
        return []


def _decode(v: Any) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v) if v is not None else ""


def _safe_lrange(redis_client: Any, key: str) -> list[str]:
    """Lê toda a lista. Retorna [] em qualquer erro."""
    try:
        raw = redis_client.lrange(key, 0, -1) or []
        return [_decode(r) for r in raw]
    except Exception:  # noqa: BLE001
        return []


def _safe_get(redis_client: Any, key: str) -> Optional[str]:
    try:
        v = redis_client.get(key)
        return _decode(v) if v is not None else None
    except Exception:  # noqa: BLE001
        return None


def _percentile(values: list[float], pct: float) -> Optional[float]:
    """Percentil nearest-rank (NIST). None se vazio.

    Para n valores, índice = ceil(pct/100 * n) - 1 (zero-based). Garante que
    p99 sobre 100 amostras pega de fato o 99º elemento — semantica padrão
    SRE (Prometheus, Datadog), que considera o pior caso "razoável".
    """
    if not values:
        return None
    import math
    arr = sorted(values)
    n = len(arr)
    idx = int(math.ceil((pct / 100.0) * n)) - 1
    idx = max(0, min(idx, n - 1))
    return float(arr[idx])


# -----------------------------------------------------------------------
# Coleta de turnos do tracing
# -----------------------------------------------------------------------

def _iter_traces_em_janela(
    redis_client: Any,
    janela_seg: int,
    limite_keys: int = 5000,
) -> Iterable[dict]:
    """Itera por TODOS os traces gravados em janela `janela_seg`.

    Lê todas as chaves `blink:trace:*` (cap em `limite_keys` pra não estourar)
    e ignora turnos com `ts_epoch` fora da janela.
    """
    if redis_client is None:
        return
    corte = _agora_epoch() - int(janela_seg)
    keys_lidas = 0
    for key in _scan_iter(redis_client, "blink:trace:*"):
        if keys_lidas >= limite_keys:
            break
        keys_lidas += 1
        key_str = _decode(key)
        for raw in _safe_lrange(redis_client, key_str):
            try:
                t = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(t, dict):
                continue
            ts = int(t.get("ts_epoch") or 0)
            if ts < corte:
                continue
            yield t


# -----------------------------------------------------------------------
# Cálculo dos SLOs
# -----------------------------------------------------------------------

def _calcular_slos(
    redis_client: Any,
    kommo_client: Any,
    janela_seg: int,
) -> dict:
    """Núcleo de cálculo. Retorna dict com todas as métricas."""
    total_turnos = 0
    turnos_com_filtro = 0
    latencias_ms: list[float] = []
    tool_total = 0
    tool_ok = 0

    for t in _iter_traces_em_janela(redis_client, janela_seg):
        total_turnos += 1
        filtros = t.get("filtros_disparados") or []
        if isinstance(filtros, list) and len(filtros) > 0:
            turnos_com_filtro += 1
        try:
            el = int(t.get("elapsed_ms") or 0)
            if el > 0:
                latencias_ms.append(float(el))
        except (TypeError, ValueError):
            pass
        tools = t.get("tools_chamadas") or []
        if isinstance(tools, list):
            for call in tools:
                if not isinstance(call, dict):
                    continue
                tool_total += 1
                if bool(call.get("ok")):
                    tool_ok += 1

    # Hallucination rate (proxy: % turnos onde algum _viola_* disparou)
    if total_turnos > 0:
        hallucination_rate = round(
            100.0 * turnos_com_filtro / total_turnos, 3,
        )
    else:
        hallucination_rate = None

    # Latency p99
    latency_p99 = _percentile(latencias_ms, 99.0)

    # Tool call success
    if tool_total > 0:
        tool_call_success_rate = round(100.0 * tool_ok / tool_total, 3)
    else:
        tool_call_success_rate = None

    # Delivery rate (varre `blink:wamid:status:*` em até `limite` chaves)
    delivered = 0
    failed = 0
    other = 0
    keys_wamid = 0
    for key in _scan_iter(redis_client, "blink:wamid:status:*"):
        keys_wamid += 1
        if keys_wamid > 5000:
            break
        st = (_safe_get(redis_client, _decode(key)) or "").lower()
        if st in ("delivered", "read"):
            delivered += 1
        elif st in ("failed", "undelivered", "error"):
            failed += 1
        else:
            other += 1
    total_wamid = delivered + failed + other
    if total_wamid > 0:
        message_delivery_rate = round(100.0 * delivered / total_wamid, 3)
    else:
        message_delivery_rate = None

    # Uptime: counters diários `blink:func:health:YYYYMMDD:ok` e `:fail`
    dias = max(1, int(janela_seg // 86400))
    hoje = datetime.now(timezone(timedelta(hours=-3)))
    ok_total = 0
    fail_total = 0
    for d in range(dias):
        dia = (hoje - timedelta(days=d)).strftime("%Y%m%d")
        ok_total += int(_safe_get(redis_client, f"blink:func:health:{dia}:ok") or 0)
        fail_total += int(_safe_get(redis_client, f"blink:func:health:{dia}:fail") or 0)
    tot_health = ok_total + fail_total
    if tot_health > 0:
        agent_uptime_pct = round(100.0 * ok_total / tot_health, 3)
    else:
        agent_uptime_pct = None

    # Escalations: count leads em ATENDIMENTO HUMANO com updated_at na janela
    escalations_to_human = 0
    if kommo_client is not None:
        try:
            corte = _agora_epoch() - int(janela_seg)
            leads = kommo_client.list_leads_by_status(
                pipeline_id=PIPELINE_ATENDE,
                status_ids=[STATUS_ATENDIMENTO_HUMANO],
                limit=250,
            ) or []
            for lead in leads:
                if not isinstance(lead, dict):
                    continue
                # se a API não voltar updated_at, considera todos
                upd = lead.get("updated_at")
                if upd is None or int(upd) >= corte:
                    escalations_to_human += 1
        except Exception as e:  # noqa: BLE001
            log.warning("[SLO] erro ao contar escalations: %s", e)
            escalations_to_human = None
    else:
        escalations_to_human = None

    return {
        "janela_seg": int(janela_seg),
        "janela_label": (
            "24h" if janela_seg == JANELA_24H_SEG
            else "7d" if janela_seg == JANELA_7D_SEG
            else f"{janela_seg}s"
        ),
        "hallucination_rate": hallucination_rate,
        "response_latency_p99": (
            int(latency_p99) if latency_p99 is not None else None
        ),
        "tool_call_success_rate": tool_call_success_rate,
        "message_delivery_rate": message_delivery_rate,
        "agent_uptime_pct": agent_uptime_pct,
        "conversations_total_24h": (
            total_turnos if janela_seg == JANELA_24H_SEG else None
        ),
        "conversations_total": total_turnos,
        "escalations_to_human": escalations_to_human,
        "turnos_com_filtro": turnos_com_filtro,
        "tool_total": tool_total,
        "tool_ok": tool_ok,
        "wamid_total": total_wamid,
        "wamid_delivered": delivered,
        "wamid_failed": failed,
        "ts_brt": _agora_brt_iso(),
    }


def calcular_slos_24h(
    redis_client: Any = None,
    kommo_client: Any = None,
) -> dict:
    """SLOs janela últimas 24h."""
    return _calcular_slos(redis_client, kommo_client, JANELA_24H_SEG)


def calcular_slos_7d(
    redis_client: Any = None,
    kommo_client: Any = None,
) -> dict:
    """SLOs janela últimos 7 dias rolling."""
    return _calcular_slos(redis_client, kommo_client, JANELA_7D_SEG)


# -----------------------------------------------------------------------
# Error budget
# -----------------------------------------------------------------------

def _classificar(metrica: Optional[float], alvo: float, lower_better: bool) -> str:
    """Devolve 'healthy', 'warning', 'burnt' ou 'no_data'."""
    if metrica is None:
        return "no_data"
    if lower_better:
        if metrica <= alvo:
            return "healthy"
        if metrica <= alvo * 2.0:
            return "warning"
        return "burnt"
    # higher better
    if metrica >= alvo:
        return "healthy"
    delta_alarm = (100.0 - alvo) * 2.0  # tolerância 2x distância pro alvo
    if metrica >= max(0.0, alvo - delta_alarm):
        return "warning"
    return "burnt"


def error_budget_status(
    redis_client: Any = None,
    kommo_client: Any = None,
    slos: Optional[dict] = None,
) -> dict:
    """Compara SLOs (janela 24h) com alvos e devolve burn rate.

    `burn_rate` aqui é heurístico: razão entre erro real vs erro permitido.
    Burn rate > 1.0 = consumindo budget mais rápido que o aceitável.
    """
    s = slos if slos is not None else calcular_slos_24h(redis_client, kommo_client)

    hall = s.get("hallucination_rate")
    uptime = s.get("agent_uptime_pct")
    lat = s.get("response_latency_p99")
    delivery = s.get("message_delivery_rate")
    tool_ok = s.get("tool_call_success_rate")

    classes = {
        "hallucination": _classificar(hall, SLO_HALLUCINATION_PCT_MAX, lower_better=True),
        "uptime": _classificar(uptime, SLO_UPTIME_PCT_MIN, lower_better=False),
        "latency": _classificar(lat, SLO_LATENCY_P99_MS_MAX, lower_better=True),
        "delivery": _classificar(delivery, SLO_DELIVERY_PCT_MIN, lower_better=False),
        "tool_success": _classificar(tool_ok, SLO_TOOL_SUCCESS_PCT_MIN, lower_better=False),
    }

    # status global = pior das dimensões com dado
    ordem = {"healthy": 0, "no_data": 1, "warning": 2, "burnt": 3}
    pior = "healthy"
    for v in classes.values():
        if ordem[v] > ordem[pior]:
            pior = v

    # burn rate na dimensão hallucination (a mais ligada a bugs)
    if hall is None or SLO_HALLUCINATION_PCT_MAX <= 0:
        burn_rate = 0.0
    else:
        burn_rate = round(hall / SLO_HALLUCINATION_PCT_MAX, 3)

    # minutos até queimar o budget na janela 24h (estimativa simples):
    # se taxa atual continua, em quanto tempo cobrimos 100% do budget mensal?
    # Budget mensal = 30 dias * (1 - alvo/100) = 30 * 0.99 = 29.7 "dias-bons"
    # Burn = quanto a taxa de erro EXCEDE o alvo
    if hall is None:
        minutos_ate_burn = None
    elif hall <= SLO_HALLUCINATION_PCT_MAX:
        minutos_ate_burn = 60 * 24 * 30  # >= 30 dias = saudável
    else:
        # excesso (em pontos pct)
        excesso = hall - SLO_HALLUCINATION_PCT_MAX
        # budget restante = 30 dias × alvo
        budget_min = 30 * 24 * 60 * (SLO_HALLUCINATION_PCT_MAX / 100.0)
        # tempo até consumir tudo nessa taxa de excesso
        try:
            minutos_ate_burn = int(budget_min / (excesso / 100.0))
        except ZeroDivisionError:
            minutos_ate_burn = 60 * 24 * 30

    return {
        "status": pior,
        "burn_rate": burn_rate,
        "minutos_ate_burn": minutos_ate_burn,
        "dimensoes": classes,
        "alvos": {
            "hallucination_rate_max_pct": SLO_HALLUCINATION_PCT_MAX,
            "agent_uptime_min_pct": SLO_UPTIME_PCT_MIN,
            "response_latency_p99_max_ms": SLO_LATENCY_P99_MS_MAX,
            "message_delivery_min_pct": SLO_DELIVERY_PCT_MIN,
            "tool_call_success_min_pct": SLO_TOOL_SUCCESS_PCT_MIN,
        },
        "ts_brt": _agora_brt_iso(),
    }


# -----------------------------------------------------------------------
# Renderizador HTML
# -----------------------------------------------------------------------

def _cor_status(status: str) -> str:
    return {
        "healthy": "#1b8a3a",
        "warning": "#c98300",
        "burnt": "#b3271a",
        "no_data": "#6b7280",
    }.get(status, "#6b7280")


def _fmt(v: Any, suffix: str = "") -> str:
    if v is None:
        return "<span style='color:#6b7280'>sem dados</span>"
    return f"{v}{suffix}"


def _card(titulo: str, valor_html: str, status: str, sub: str = "") -> str:
    cor = _cor_status(status)
    return (
        f"<div style='background:#fff;border-left:6px solid {cor};"
        f"border-radius:6px;padding:14px 18px;margin:8px 0;"
        f"box-shadow:0 1px 3px rgba(0,0,0,0.08);min-width:220px;'>"
        f"<div style='font-size:12px;color:#6b7280;text-transform:uppercase;"
        f"letter-spacing:.04em;'>{titulo}</div>"
        f"<div style='font-size:24px;font-weight:600;margin-top:4px;'>"
        f"{valor_html}</div>"
        f"<div style='font-size:11px;color:#6b7280;margin-top:6px;'>{sub}</div>"
        f"</div>"
    )


def _bloco_janela(titulo: str, s: dict, eb_dims: dict) -> str:
    cards = []
    cards.append(_card(
        "Hallucination rate",
        _fmt(s.get("hallucination_rate"), "%"),
        eb_dims.get("hallucination", "no_data"),
        f"alvo &lt; {SLO_HALLUCINATION_PCT_MAX}% · "
        f"{s.get('turnos_com_filtro', 0)} turnos com filtro / "
        f"{s.get('conversations_total', 0)} totais",
    ))
    cards.append(_card(
        "Response latency p99",
        _fmt(s.get("response_latency_p99"), " ms"),
        eb_dims.get("latency", "no_data"),
        f"alvo &lt; {int(SLO_LATENCY_P99_MS_MAX)} ms",
    ))
    cards.append(_card(
        "Tool call success",
        _fmt(s.get("tool_call_success_rate"), "%"),
        eb_dims.get("tool_success", "no_data"),
        f"alvo &gt; {SLO_TOOL_SUCCESS_PCT_MIN}% · "
        f"{s.get('tool_ok', 0)} ok / {s.get('tool_total', 0)} chamadas",
    ))
    cards.append(_card(
        "Message delivery rate",
        _fmt(s.get("message_delivery_rate"), "%"),
        eb_dims.get("delivery", "no_data"),
        f"alvo &gt; {SLO_DELIVERY_PCT_MIN}% · "
        f"{s.get('wamid_delivered', 0)} entregues / "
        f"{s.get('wamid_total', 0)} wamid",
    ))
    cards.append(_card(
        "Agent uptime",
        _fmt(s.get("agent_uptime_pct"), "%"),
        eb_dims.get("uptime", "no_data"),
        f"alvo &gt; {SLO_UPTIME_PCT_MIN}%",
    ))
    cards.append(_card(
        "Conversas (janela)",
        _fmt(s.get("conversations_total")),
        "healthy" if s.get("conversations_total") else "no_data",
        f"turnos gravados no tracing",
    ))
    cards.append(_card(
        "Escalations a humano",
        _fmt(s.get("escalations_to_human")),
        "warning" if (s.get("escalations_to_human") or 0) > 0 else "healthy",
        f"leads em ATENDIMENTO HUMANO",
    ))

    return (
        f"<section style='margin-bottom:24px;'>"
        f"<h2 style='margin:0 0 8px 0;color:#1f2937;'>Janela {titulo}</h2>"
        f"<div style='display:flex;flex-wrap:wrap;gap:12px;'>{''.join(cards)}</div>"
        f"</section>"
    )


def render_html(slos_24h: dict, slos_7d: dict, eb: dict) -> str:
    """Renderiza dashboard simples sem framework."""
    cor_top = _cor_status(eb.get("status", "no_data"))
    burn = eb.get("burn_rate")
    minutos = eb.get("minutos_ate_burn")
    minutos_label = (
        "indeterminado" if minutos is None
        else f"{minutos // 60}h {minutos % 60}min"
        if minutos < 60 * 24 * 7
        else f"{minutos // (60*24)} dias"
    )
    eb_dims = eb.get("dimensoes", {})

    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>SLO Board — Lia Blink</title>"
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "sans-serif;background:#f3f4f6;color:#111827;margin:0;padding:24px;}"
        "h1{margin:0 0 4px 0;}"
        "h2{font-size:16px;text-transform:uppercase;letter-spacing:.05em;"
        "color:#6b7280;}"
        ".banner{padding:18px 22px;border-radius:8px;color:#fff;margin-bottom:24px;"
        "box-shadow:0 1px 4px rgba(0,0,0,0.1);}"
        ".small{font-size:12px;opacity:.85;}"
        ".legend{font-size:12px;color:#6b7280;margin-top:24px;}"
        "</style></head><body>"
        f"<h1>SLO Board — Lia Blink</h1>"
        f"<div class='small' style='color:#6b7280;margin-bottom:16px;'>"
        f"Atualizado em {slos_24h.get('ts_brt', '')} (BRT). "
        "Atualize a página pra recarregar.</div>"
        f"<div class='banner' style='background:{cor_top};'>"
        f"<div style='font-size:14px;text-transform:uppercase;letter-spacing:.05em;'>"
        f"Error budget</div>"
        f"<div style='font-size:28px;font-weight:700;margin-top:4px;'>"
        f"{eb.get('status', 'no_data').upper()}</div>"
        f"<div class='small'>burn rate: {burn} · "
        f"queima total estimada em: {minutos_label}</div>"
        f"</div>"
        f"{_bloco_janela('24h', slos_24h, eb_dims)}"
        f"{_bloco_janela('7 dias', slos_7d, eb_dims)}"
        "<section class='legend'>"
        "<strong>Como interpretar:</strong> verde = dentro do SLO; amarelo = "
        "warning (dobro de tolerância); vermelho = budget queimado. "
        "Hallucination rate é o % de turnos em que ao menos 1 filtro "
        "<code>_viola_*</code> disparou no <code>responder.py</code>. "
        "P99 lê <code>elapsed_ms</code> dos traces. "
        "Delivery rate vem de <code>blink:wamid:status:*</code>. "
        "Uptime vem de <code>blink:func:health:YYYYMMDD:ok|fail</code>."
        "</section>"
        "</body></html>"
    )
