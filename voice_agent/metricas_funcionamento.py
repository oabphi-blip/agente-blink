"""Métricas live de funcionamento do pipeline Lia (06/06/2026, task #260).

Objetivo: trocar "achismo" por NÚMERO.

Sem infra nova. Counters Redis simples (INCR + EXPIRE) por dia.
Endpoint /admin/funcionamento lê e calcula taxas.

Eventos rastreados:
- tool:<nome>:ok       — tool chamada com sucesso (oferecer_slot, gravar_agendamento, etc)
- tool:<nome>:fail     — tool chamada com erro
- fsm:<estado>:enter   — pipeline.py registra cada transição FSM
- fsm:<estado>:complete — estado FOI COMPLETADO (passou pra próximo no caminho feliz)
- abandono:detectado   — /admin/leads-abandonados encontrou >= 1 abandono na varredura

Chave Redis: `blink:metric:<evento>:<YYYY-MM-DD>` → INCR + EXPIRE 30 dias.

Taxas calculadas (target):
- agenda_para_oferecer_slot = tool:oferecer_slot:ok ÷ fsm:AGENDA:enter   (>= 80%)
- gravacao_sucesso = tool:gravar_agendamento_medware:ok ÷ (ok+fail)      (>= 95%)
- circuit_breaker_acionado = fsm:GRAVACAO:fail ÷ fsm:GRAVACAO:enter      (<= 10%)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

_TTL_DIAS = 30
_TTL_SEG = _TTL_DIAS * 86400


def _today_str() -> str:
    return date.today().isoformat()


def _key(evento: str, dia: Optional[str] = None) -> str:
    dia = dia or _today_str()
    return f"blink:metric:{evento}:{dia}"


def incrementar(
    redis_client, evento: str, valor: int = 1, dia: Optional[str] = None,
) -> None:
    """Registra +N pra um evento. Best-effort: nunca quebra pipeline.

    Exemplo:
        incrementar(redis, "tool:oferecer_slot:ok")
        incrementar(redis, "fsm:AGENDA:enter")
    """
    if redis_client is None:
        return
    try:
        k = _key(evento, dia)
        redis_client.incrby(k, valor)
        redis_client.expire(k, _TTL_SEG)
    except Exception as e:  # noqa: BLE001
        log.warning("[metric] incr %s falhou: %s", evento, e)


def get_contador(
    redis_client, evento: str, dia: Optional[str] = None,
) -> int:
    """Lê valor do contador, 0 se vazio/erro."""
    if redis_client is None:
        return 0
    try:
        v = redis_client.get(_key(evento, dia))
        if v is None:
            return 0
        if isinstance(v, bytes):
            v = v.decode()
        return int(v)
    except Exception:  # noqa: BLE001
        return 0


def funcionamento_hoje(redis_client) -> dict:
    """Snapshot completo do dia: contadores brutos + taxas calculadas.

    Retorna dict pronto pra resposta JSON do endpoint /admin/funcionamento.
    """
    if redis_client is None:
        return {"erro": "redis_indisponivel", "ts": int(time.time())}

    # Eventos rastreados
    eventos_tool = [
        "tool:oferecer_slot:ok", "tool:oferecer_slot:fail",
        "tool:confirmar_dados_paciente:ok", "tool:confirmar_dados_paciente:fail",
        "tool:gravar_agendamento_medware:ok", "tool:gravar_agendamento_medware:fail",
    ]
    eventos_fsm = [
        "fsm:TRIAGEM:enter", "fsm:DADOS:enter", "fsm:CONVENIO:enter",
        "fsm:AGENDA:enter", "fsm:CONFIRMACAO:enter", "fsm:GRAVACAO:enter",
        "fsm:POS_GRAVACAO:enter",
    ]
    outros = ["abandono:detectado", "pipeline:lock_acionado"]

    contadores: dict[str, int] = {}
    for ev in eventos_tool + eventos_fsm + outros:
        contadores[ev] = get_contador(redis_client, ev)

    # Taxas calculadas
    agenda_enter = contadores.get("fsm:AGENDA:enter", 0)
    oferta_ok = contadores.get("tool:oferecer_slot:ok", 0)
    taxa_agenda_para_slot = (
        round(100.0 * oferta_ok / agenda_enter, 1)
        if agenda_enter > 0 else None
    )

    grav_ok = contadores.get("tool:gravar_agendamento_medware:ok", 0)
    grav_fail = contadores.get("tool:gravar_agendamento_medware:fail", 0)
    grav_total = grav_ok + grav_fail
    taxa_gravacao_sucesso = (
        round(100.0 * grav_ok / grav_total, 1)
        if grav_total > 0 else None
    )

    return {
        "dia": _today_str(),
        "ts": int(time.time()),
        "contadores": contadores,
        "taxas": {
            "agenda_para_oferecer_slot_pct": taxa_agenda_para_slot,
            "gravacao_sucesso_pct": taxa_gravacao_sucesso,
            "target_agenda_para_slot": 80.0,
            "target_gravacao_sucesso": 95.0,
        },
        "alarmes_ativos": _alarmes_ativos(taxa_agenda_para_slot, taxa_gravacao_sucesso),
    }


def _alarmes_ativos(
    taxa_agenda: Optional[float], taxa_grav: Optional[float],
) -> list[str]:
    """Lista de alarmes baseado nas taxas. Vazio = tudo OK."""
    alarmes: list[str] = []
    if taxa_agenda is not None and taxa_agenda < 80.0:
        alarmes.append(
            f"AGENDA→oferecer_slot caiu pra {taxa_agenda}% (target 80%)"
        )
    if taxa_grav is not None and taxa_grav < 95.0:
        alarmes.append(
            f"Gravação Medware caiu pra {taxa_grav}% (target 95%)"
        )
    return alarmes


def funcionamento_ultimos_n_dias(redis_client, n: int = 7) -> dict:
    """Histórico de N dias pra ver tendência."""
    if redis_client is None:
        return {"erro": "redis_indisponivel"}
    hoje = date.today()
    serie = []
    for i in range(n):
        d = (hoje - timedelta(days=i)).isoformat()
        agenda = get_contador(redis_client, "fsm:AGENDA:enter", d)
        oferta = get_contador(redis_client, "tool:oferecer_slot:ok", d)
        grav_ok = get_contador(redis_client, "tool:gravar_agendamento_medware:ok", d)
        grav_fail = get_contador(redis_client, "tool:gravar_agendamento_medware:fail", d)
        serie.append({
            "dia": d,
            "agenda_enter": agenda,
            "oferecer_slot_ok": oferta,
            "gravacao_ok": grav_ok,
            "gravacao_fail": grav_fail,
            "taxa_agenda_para_slot_pct": (
                round(100.0 * oferta / agenda, 1) if agenda > 0 else None
            ),
        })
    return {"dias": list(reversed(serie)), "ts": int(time.time())}
