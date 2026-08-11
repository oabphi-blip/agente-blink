"""Bypass determinístico da mensagem de oferta de agenda.

Origem — Fábio 08/07/2026, lead Mariana 24273236.

BUG CRÔNICO (60+ dias): Lia (Sonnet 4.5) em FSM=AGENDA às vezes ignora
tool calling forçado e escreve texto livre — inventa frases:
    "reconferir com o calendário"     (Mariana, 08/07)
    "especialista em remarcação"      (Mariana, 08/07)
    "vou consultar e volto em 1 min"  (Alice, Sabrina, Sofia, Juliene, ...)
    "agenda fora do ar"               (Mariana, 08/07 — Medware ESTAVA UP)
    "retorno em horário comercial"    (Juliene, 02/06)

Filtros regex reativos (C-30, C-30A, C-31, C-33, C-36, C-37c) não fecham a
cauda longa — cada paciente novo escapa com frase diferente.

FIX ARQUITETURAL: retirar do LLM a decisão de escrever a mensagem de oferta.

Quando FSM=AGENDA + dados prontos + médico/unidade definidos:
    pipeline chama Medware direto (Python)
    │
    ├── Medware retorna slots → montar_texto_2_slots() devolve string canônica
    │                          (f-string pura — LLM NÃO é chamado)
    │
    └── Medware vazio/timeout → frase_escalacao_humano() devolve UMA frase
                                canônica + pipeline seta ATIVADO_IA=Solicitado
                                + move lead pra 1-ATENDIMENTO HUMANO

Contrato deste módulo:
    - montar_texto_2_slots(slots, ctx) SEMPRE contém as datas literais
    - montar_texto_2_slots(slots, ctx) NUNCA contém FRASES_BANIDAS
    - SEMPRE apresenta médico com nome+sobrenome (regra 06/2026)
    - dia da semana calculado por date.weekday() (bug C-35 blindado)
    - _assert_zero_frases_banidas() é sentinela final — se um dia
      alguém alterar template pra algo banido, fail-fast em runtime.

Toggle: AGENDA_DETERMINISTICA (default ON).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from voice_agent.checklist_dados_minimos import verificar_dados_minimos
from voice_agent.mensagens_ciclo import _DIAS_SEMANA_PT, _info_unidade

log = logging.getLogger(__name__)


# ===========================================================================
# Toggle — default ON
# ===========================================================================

def _ativado() -> bool:
    """Default ON. Setar AGENDA_DETERMINISTICA=0 desliga (rollback sem revert)."""
    return (os.getenv("AGENDA_DETERMINISTICA") or "1").lower() not in (
        "0", "false", "no", "off", "",
    )


# ===========================================================================
# Frases banidas — 60 dias de bug indexado
# ===========================================================================
# Se alguma dessas aparecer no texto de saída, é bug e AssertionError.
FRASES_BANIDAS: tuple[str, ...] = (
    # Bug Mariana 08/07/2026 lead 24273236 + Clarice 12/07/2026 lead 22544990
    "reconferir",
    "reconferir com o calendário",
    "reconferir com o calendario",
    "reconferir os horários",
    "reconferir os horarios",
    "especialista em remarcação",
    "especialista em remarcacao",
    "especialista em agendamento",
    "especialista em cancelamento",
    "especialista em remarcações",
    "especialista em remarcacoes",
    "nossa especialista em",
    "nosso especialista em",
    "equipe de remarcação",
    "equipe de remarcacao",
    "fora do ar",
    "não está retornando",
    "nao esta retornando",
    "vou encaminhar você para nossa",
    "vou encaminhar voce para nossa",
    "vou encaminhar você para nosso",
    "vou encaminhar voce para nosso",
    "vou encaminhar você",
    "vou encaminhar voce",
    # Bug Sofia 16/06, Alice 03/06, Sabrina/Kamila/Janeide/Iara/Keyla 02/06
    "reconsultar a agenda",
    "reconsultar os horários",
    "deixa eu consultar",
    "vou consultar",
    "volto em 1 minuto",
    "puxar a agenda",
    "ainda estou buscando",
    # Bug Juliene 02/06 lead 24053159
    "horário comercial",
    "horario comercial",
    "seg-sex 8",
    "retorno em horario",
    "retorno em horário",
    # Bug catalogado C-30 hesitação
    "aguarda só mais um pouquinho",
    "aguarda so mais um pouquinho",
    "verificar com a equipe",  # variante longa é permitida em escalação — abaixo
)


def _assert_zero_frases_banidas(texto: str) -> None:
    """Sentinela final — se algum dia template violar, fail-fast em runtime."""
    baixo = (texto or "").lower()
    for frase in FRASES_BANIDAS:
        if frase in baixo:
            raise AssertionError(
                f"[oferta_deterministica] texto viola frase banida "
                f"{frase!r} → texto: {texto[:200]!r}"
            )


# ===========================================================================
# Apresentação canônica do médico (regra 06/2026)
# ===========================================================================
_MEDICO_CANONICO: dict[str, str] = {
    "delalibera": "Dra. Karla Delalíbera",
    "delalíbera": "Dra. Karla Delalíbera",
    "karla": "Dra. Karla Delalíbera",
    "freitas": "Dr. Fabrício Freitas",
    "fabricio": "Dr. Fabrício Freitas",
    "fabrício": "Dr. Fabrício Freitas",
}


def _nome_medico_canonico(medico: Any) -> str:
    """Retorna sempre 'Dra. Karla Delalíbera' ou 'Dr. Fabrício Freitas'.
    Aceita string, lista (multiselect Kommo), ou vazio.
    """
    if isinstance(medico, (list, tuple)):
        medico = medico[0] if medico else ""
    m = (str(medico or "")).strip().lower()
    for chave, canonico in _MEDICO_CANONICO.items():
        if chave in m:
            return canonico
    # Sem match — retorna algo neutro que não seja "a médica" (poderia ser Kátia).
    return "a médica"


def _nome_paciente(ctx: Optional[dict]) -> str:
    """Primeiro nome do paciente pra abertura da mensagem."""
    known = (ctx or {}).get("known") or {}
    nome = (
        known.get("nome_paciente")
        or known.get("nome_completo_paciente")
        or known.get("nome")
        or ""
    )
    primeiro = str(nome).strip().split()[0] if str(nome).strip() else ""
    return primeiro or "Olá"


def _convenio_ou_pagamento(ctx: Optional[dict]) -> str:
    """Frase curta pro contexto de pagamento na mensagem."""
    known = (ctx or {}).get("known") or {}
    conv = str(known.get("convenio") or "").strip()
    conv_lower = conv.lower()
    if not conv or conv_lower in ("não se aplica", "nao se aplica", "particular", ""):
        return "no atendimento particular"
    return f"pelo {conv}"


def _get_unidade_str(ctx: Optional[dict]) -> str:
    """Extrai unidade do ctx.known — aceita string ou lista (Kommo multiselect)."""
    known = (ctx or {}).get("known") or {}
    u = known.get("unidade") or known.get("unidades") or ""
    if isinstance(u, (list, tuple)):
        u = u[0] if u else ""
    return str(u or "")


def _get_medico_str(ctx: Optional[dict]) -> str:
    """Extrai médico do ctx.known — aceita string ou lista (Kommo multiselect)."""
    known = (ctx or {}).get("known") or {}
    m = known.get("medico") or known.get("medicos") or ""
    if isinstance(m, (list, tuple)):
        m = m[0] if m else ""
    return str(m or "")


# ===========================================================================
# GATE — deve_ofertar_agora
# ===========================================================================

def deve_ofertar_agora(ctx: Optional[dict]) -> bool:
    """Retorna True SE E SOMENTE SE:
    - Toggle AGENDA_DETERMINISTICA está on
    - FSM.estado == 'AGENDA'
    - ctx.ja_agendado == False
    - ctx.known tem médico + unidade definidos
    - Checklist dados_minimos.pronto_para_oferecer_slot == True

    Se qualquer condição falha, o fluxo normal do LLM segue (coleta dados,
    responde dúvidas, etc). Só entramos no bypass quando é 100% seguro
    ofertar.
    """
    if not _ativado():
        return False
    if not ctx:
        return False

    # FSM
    fsm = ctx.get("fsm") or {}
    if (fsm.get("estado") or "").upper() != "AGENDA":
        return False

    # Não re-ofertar se já agendado (bug Esther 24060221, Sophia 23845330)
    if ctx.get("ja_agendado"):
        return False

    # Médico + unidade obrigatórios
    if not _get_medico_str(ctx):
        return False
    if not _get_unidade_str(ctx):
        return False

    # Dados mínimos completos
    known = ctx.get("known") or {}
    resultado = verificar_dados_minimos(known)
    return bool(resultado.pronto_para_oferecer_slot)


# ===========================================================================
# Formatação — data e hora canônicas
# ===========================================================================

def _formatar_data_com_dia_semana(data_iso: str) -> tuple[str, str]:
    """'2026-07-14' -> ('Terça-feira', '14/07')

    dia_semana é calculado por date.weekday() — blindado contra bug C-35
    ("Claude inventa dias da semana"). Sempre correto por construção.
    """
    dt = datetime.strptime(str(data_iso).strip()[:10], "%Y-%m-%d")
    dia_semana = _DIAS_SEMANA_PT[dt.weekday()].capitalize()
    return dia_semana, dt.strftime("%d/%m")


def _formatar_hora(hora: str) -> str:
    """'17:30' ou '17:30:00' -> '17h30'"""
    h = str(hora or "").strip()[:5]  # HH:MM
    if ":" not in h:
        return h
    partes = h.split(":", 1)
    return f"{partes[0]}h{partes[1]}"


# ===========================================================================
# Seleção dos 2 slots — 1 mais próximo + 1 alternativa (turno diferente se der)
# ===========================================================================

def selecionar_2_slots(slots: list[dict]) -> list[dict]:
    """Escolhe até 2 slots pra oferta.

    Regra:
      - slot 1 = mais próximo no tempo (primeiro item retornado por Medware)
      - slot 2 = próximo slot em DATA DIFERENTE, preferindo turno diferente
                 (manhã se slot 1 é tarde, tarde se slot 1 é manhã)
      - Se só houver slots do mesmo dia, devolve 2 desse mesmo dia
      - Se só houver 1 slot, devolve só 1

    Não filtra por preferência da paciente aqui — isso já é feito na
    janela_preferencia.py ao chamar Medware. Aqui é seleção pós-Medware.
    """
    if not slots:
        return []
    if len(slots) == 1:
        return [slots[0]]

    slot1 = slots[0]

    def _turno(s: dict) -> str:
        h = str(s.get("hora") or "")[:2]
        try:
            hh = int(h)
            return "manha" if hh < 12 else "tarde"
        except ValueError:
            return "manha"

    turno1 = _turno(slot1)
    data1 = str(slot1.get("data_iso") or "")

    # Preferência 1: slot em outra DATA e outro TURNO
    for s in slots[1:]:
        if str(s.get("data_iso") or "") != data1 and _turno(s) != turno1:
            return [slot1, s]
    # Preferência 2: slot em outra DATA
    for s in slots[1:]:
        if str(s.get("data_iso") or "") != data1:
            return [slot1, s]
    # Fallback: 2 primeiros do Medware
    return slots[:2]


# ===========================================================================
# Mensagem CANÔNICA — texto de oferta
# ===========================================================================

def montar_texto_2_slots(slots: list[dict], ctx: Optional[dict]) -> str:
    """Monta a mensagem de oferta de slot. F-string PURA.

    slots: lista com 1 ou 2 dicts contendo 'data_iso' e 'hora'.
    ctx: caller_context com known.nome_paciente/medico/unidade/convenio.

    Contrato:
        - Contém as datas literais no formato "(DD/MM)"
        - Contém horas no formato "HHhMM"
        - Contém nome+sobrenome do médico (regra 06/2026)
        - NUNCA contém FRASES_BANIDAS
        - Dia da semana calculado por weekday() — nunca inventa

    Se algo violar contrato, AssertionError é lançado (fail-fast).
    """
    if not slots:
        raise ValueError("montar_texto_2_slots exige pelo menos 1 slot")

    escolhidos = selecionar_2_slots(slots)
    slot1 = escolhidos[0]
    slot2 = escolhidos[1] if len(escolhidos) > 1 else None

    nome_pac = _nome_paciente(ctx)
    medico = _nome_medico_canonico(_get_medico_str(ctx))
    unidade_info = _info_unidade(_get_unidade_str(ctx))
    unidade_label = unidade_info["label"]
    pagamento = _convenio_ou_pagamento(ctx)

    dia1, data1 = _formatar_data_com_dia_semana(slot1["data_iso"])
    hora1 = _formatar_hora(slot1["hora"])

    linhas: list[str] = [
        f"{nome_pac}, encontrei estes horários com a {medico} "
        f"na unidade {unidade_label} {pagamento}:",
        "",
        f"1️⃣ {dia1} ({data1}) às {hora1}",
    ]

    if slot2:
        dia2, data2 = _formatar_data_com_dia_semana(slot2["data_iso"])
        hora2 = _formatar_hora(slot2["hora"])
        linhas.append(f"2️⃣ {dia2} ({data2}) às {hora2}")
        linhas.append("")
        linhas.append("Qual dos dois fica melhor?")
    else:
        linhas.append("")
        linhas.append("Este horário serve pra você?")

    texto = "\n".join(linhas)
    _assert_zero_frases_banidas(texto)
    return texto


# ===========================================================================
# Frase de escalação humano — Medware vazio/timeout
# ===========================================================================

def frase_escalacao_humano(ctx: Optional[dict]) -> str:
    """Fallback quando Medware retorna vazio 3x ou timeout.

    Uma única frase canônica (não 4 variantes como bug Mariana). Pipeline
    complementa desativando IA + movendo lead pra 1-ATENDIMENTO HUMANO +
    alerta Slack.
    """
    nome_pac = _nome_paciente(ctx)
    texto = (
        f"{nome_pac}, estou confirmando a disponibilidade com a nossa equipe "
        "aqui na Blink. Em instantes retorno com os horários exatos pra você. "
        "Obrigada pela paciência!"
    )
    _assert_zero_frases_banidas(texto)
    return texto
