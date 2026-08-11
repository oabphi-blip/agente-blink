"""Pytest — Bug C-105 (11/08/2026): Python seleciona slots; LLM só humaniza.

Antes: LLM recebia agenda inteira e DECIDIA quais slots mostrar.
Depois: Python pré-seleciona os 3 melhores; LLM só formata.

Módulos testados:
  voice_agent/oferta_slot_deterministico.py
    - selecionar_slots(agenda, turno_pref, ja_ofertados) -> list[dict]
    - formatar_slots_para_prompt(slots, medico, unidade) -> str
    - formatar_oferta_humana(slots, medico, unidade, nome) -> str
  voice_agent/enriquecimento_ctx.py  (step 11)
    - enriquecer_known injeta slots_selecionados em ctx.known
  voice_agent/responder.py
    - _agenda_block usa slots pré-selecionados quando presentes
    - _gerar_oferta_3_slots prefere ctx.known.slots_selecionados

Cobertura (20 cenários):
  selecionar_slots:
    - sem preferência: 1 manhã + 1 tarde + 1 alternativo
    - turno_pref="manhã": 3 slots de manhã
    - turno_pref="tarde": 3 slots de tarde
    - só manhã disponível: 2 slots de manhã
    - só tarde disponível: 2 slots de tarde
    - agenda vazia: []
    - ja_ofertados filtra corretamente
    - todos ofertados: usa agenda completa (sem retorno vazio)
    - toggle OFF: retorna []
  formatar_slots_para_prompt:
    - contém REGRA C-105 e "USE EXATAMENTE ESTES"
    - contém dados reais dos slots
  formatar_oferta_humana:
    - formato 1️⃣/2️⃣/3️⃣ correto
    - inclui nome do paciente quando fornecido
  enriquecimento_ctx step 11:
    - agenda disponível → slots_selecionados injetado
    - agenda vazia → slots_selecionados não injetado
    - respeita turno_pref do known
  responder._agenda_block:
    - com slots_selecionados → usa formatar_slots_para_prompt
    - sem slots_selecionados → usa lógica existente (backward compat)
  responder._gerar_oferta_3_slots:
    - com slots_selecionados → usa pre-selecionados
    - sem slots_selecionados → fallback normal
"""
from __future__ import annotations

import os
import pytest

from voice_agent.oferta_slot_deterministico import (
    selecionar_slots,
    formatar_slots_para_prompt,
    formatar_oferta_humana,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _slot(data_iso: str, hora: str, dia_semana: str = "Quarta-feira",
          data_br: str = "13/08") -> dict:
    return {
        "data_iso": data_iso,
        "data_br": data_br,
        "dia_semana": dia_semana,
        "hora": hora,
        "cod_agenda": 1,
        "cod_medico": 12080,
        "cod_unidade": 5,
    }


# Agenda realista com manhã e tarde
_AGENDA_MISTA = [
    _slot("2026-08-13", "08:30", "Quarta-feira", "13/08"),
    _slot("2026-08-13", "09:00", "Quarta-feira", "13/08"),
    _slot("2026-08-13", "14:00", "Quarta-feira", "13/08"),
    _slot("2026-08-13", "16:30", "Quarta-feira", "13/08"),
    _slot("2026-08-14", "10:00", "Quinta-feira",  "14/08"),
    _slot("2026-08-14", "15:00", "Quinta-feira",  "14/08"),
]

_AGENDA_SO_MANHA = [
    _slot("2026-08-13", "08:00", "Quarta-feira", "13/08"),
    _slot("2026-08-13", "09:30", "Quarta-feira", "13/08"),
    _slot("2026-08-14", "10:00", "Quinta-feira",  "14/08"),
]

_AGENDA_SO_TARDE = [
    _slot("2026-08-13", "14:00", "Quarta-feira", "13/08"),
    _slot("2026-08-13", "16:00", "Quarta-feira", "13/08"),
    _slot("2026-08-14", "15:30", "Quinta-feira",  "14/08"),
]


# ─────────────────────────────────────────────────────────────────────────────
# selecionar_slots — lógica central
# ─────────────────────────────────────────────────────────────────────────────

def test_c105_sem_preferencia_retorna_1_manha_1_tarde():
    """Sem turno_pref: primeiro slot é manhã, segundo é tarde."""
    slots = selecionar_slots(_AGENDA_MISTA)
    assert len(slots) >= 2
    horas = [int(s["hora"][:2]) for s in slots[:2]]
    assert horas[0] < 12, "primeiro slot deve ser manhã"
    assert horas[1] >= 12, "segundo slot deve ser tarde"


def test_c105_turno_manha_retorna_ate_3_manha():
    """turno_pref='manhã' → todos os slots selecionados são de manhã."""
    slots = selecionar_slots(_AGENDA_MISTA, turno_pref="manhã")
    assert len(slots) >= 1
    for s in slots:
        assert int(s["hora"][:2]) < 12, f"slot {s['hora']} não é manhã"


def test_c105_turno_tarde_retorna_ate_3_tarde():
    """turno_pref='tarde' → slots de tarde prioritários."""
    slots = selecionar_slots(_AGENDA_MISTA, turno_pref="tarde")
    assert len(slots) >= 1
    for s in slots[:2]:
        assert int(s["hora"][:2]) >= 12, f"slot {s['hora']} não é tarde"


def test_c105_so_manha_disponivel():
    """Só manhã na agenda → retorna manhã sem reclamar."""
    slots = selecionar_slots(_AGENDA_SO_MANHA)
    assert len(slots) >= 2
    for s in slots:
        assert int(s["hora"][:2]) < 12


def test_c105_so_tarde_disponivel():
    """Só tarde na agenda → retorna tarde sem reclamar."""
    slots = selecionar_slots(_AGENDA_SO_TARDE)
    assert len(slots) >= 2
    for s in slots:
        assert int(s["hora"][:2]) >= 12


def test_c105_agenda_vazia_retorna_lista_vazia():
    """Agenda vazia → retorna []."""
    assert selecionar_slots([]) == []


def test_c105_retorna_no_maximo_3_slots():
    """Nunca retorna mais de 3 slots."""
    slots = selecionar_slots(_AGENDA_MISTA)
    assert len(slots) <= 3


def test_c105_ja_ofertados_filtrado():
    """Slots já ofertados ao lead (E6-B) são excluídos."""
    ja_ofertados = {"2026-08-13_08:30", "2026-08-13_09:00"}
    slots = selecionar_slots(_AGENDA_MISTA, ja_ofertados=ja_ofertados)
    ids_sel = {f"{s['data_iso']}_{s['hora']}" for s in slots}
    assert "2026-08-13_08:30" not in ids_sel
    assert "2026-08-13_09:00" not in ids_sel


def test_c105_todos_ofertados_usa_agenda_completa():
    """Se todos já ofertados → usa agenda inteira (evita retorno vazio)."""
    todos = {f"{s['data_iso']}_{s['hora']}" for s in _AGENDA_MISTA}
    slots = selecionar_slots(_AGENDA_MISTA, ja_ofertados=todos)
    assert len(slots) >= 1  # não vazio


def test_c105_toggle_off_retorna_vazio(monkeypatch):
    """OFERTA_SLOT_DETERMINISTICO=0 → retorna [] (rollback seguro).

    Usa monkeypatch.setattr para não corromper estado do módulo entre testes.
    """
    import voice_agent.oferta_slot_deterministico as m
    monkeypatch.setattr(m, "_ATIVADO", False)
    slots = m.selecionar_slots(_AGENDA_MISTA)
    assert slots == []


# ─────────────────────────────────────────────────────────────────────────────
# formatar_slots_para_prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_c105_prompt_contem_regra_inviolavel():
    """formatar_slots_para_prompt inclui instrução C-105."""
    # Usa slots hardcoded para não depender do toggle (test isolation)
    slots = [_slot("2026-08-13", "09:30"), _slot("2026-08-13", "14:00")]
    texto = formatar_slots_para_prompt(slots, medico="Dra. Karla", unidade="Asa Norte")
    assert "C-105" in texto or "USE EXATAMENTE" in texto


def test_c105_prompt_contem_dados_reais():
    """Prompt contém dados dos slots reais."""
    slots = [_slot("2026-08-13", "09:30", "Quarta-feira", "13/08")]
    texto = formatar_slots_para_prompt(slots, medico="Karla", unidade="Asa Norte")
    assert "09:30" in texto
    assert "13/08" in texto or "Quarta" in texto


def test_c105_prompt_vazio_para_slots_vazios():
    """Sem slots → retorna string vazia (não gera prompt com dados errados)."""
    assert formatar_slots_para_prompt([]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# formatar_oferta_humana
# ─────────────────────────────────────────────────────────────────────────────

def test_c105_oferta_humana_formato_emoji():
    """Mensagem de oferta usa emojis 1️⃣/2️⃣/3️⃣."""
    slots = [_slot("2026-08-13", "09:30"), _slot("2026-08-13", "14:00")]
    texto = formatar_oferta_humana(slots, medico="Dra. Karla", unidade="Asa Norte")
    assert "1️⃣" in texto
    assert "Qual fica melhor" in texto


def test_c105_oferta_humana_com_nome():
    """Nome do paciente aparece no início."""
    slots = [_slot("2026-08-13", "09:30")]
    texto = formatar_oferta_humana(slots, medico="Karla", unidade="Asa Norte",
                                   nome_paciente="Ana")
    assert texto.startswith("Ana,")


def test_c105_oferta_humana_vazia_para_slots_vazios():
    """Sem slots → string vazia (não envia mensagem sem dados)."""
    assert formatar_oferta_humana([]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# enriquecimento_ctx step 11
# ─────────────────────────────────────────────────────────────────────────────

def test_c105_enriquecimento_injeta_slots_selecionados():
    """enriquecer_known injeta slots_selecionados quando agenda presente."""
    from voice_agent.enriquecimento_ctx import enriquecer_known
    ctx = {
        "found": True,
        "agenda": _AGENDA_MISTA,
        "known": {"medico": "Karla"},
    }
    result = enriquecer_known(ctx)
    known = result.get("known", {})
    assert "slots_selecionados" in known
    assert len(known["slots_selecionados"]) >= 1


def test_c105_enriquecimento_nao_injeta_sem_agenda():
    """Sem agenda → slots_selecionados NÃO é injetado."""
    from voice_agent.enriquecimento_ctx import enriquecer_known
    ctx = {
        "found": True,
        "known": {"medico": "Karla"},
    }
    result = enriquecer_known(ctx)
    assert "slots_selecionados" not in result.get("known", {})


def test_c105_enriquecimento_respeita_turno_pref():
    """turno_pref='tarde' no known → slots de tarde pré-selecionados."""
    from voice_agent.enriquecimento_ctx import enriquecer_known
    ctx = {
        "found": True,
        "agenda": _AGENDA_MISTA,
        "known": {"medico": "Karla", "turno_preferido": "tarde"},
    }
    result = enriquecer_known(ctx)
    slots = result.get("known", {}).get("slots_selecionados", [])
    assert len(slots) >= 1
    # Primeiro slot deve ser tarde
    assert int(slots[0]["hora"][:2]) >= 12


# ─────────────────────────────────────────────────────────────────────────────
# responder._agenda_block e _gerar_oferta_3_slots
# ─────────────────────────────────────────────────────────────────────────────

def test_c105_agenda_block_usa_slots_selecionados():
    """_agenda_block com slots_selecionados no known → usa C-105 (não expõe agenda inteira)."""
    from voice_agent.responder import _agenda_block
    slots_sel = [_slot("2026-08-13", "09:30")]
    ctx = {
        "agenda": _AGENDA_MISTA,
        "known": {"medico": "Karla", "unidade": "Asa Norte",
                  "slots_selecionados": slots_sel},
    }
    texto = _agenda_block(ctx)
    # Deve conter a instrução C-105 (não a instrução legada "OFERTA IMEDIATA DE 3 SLOTS")
    assert "C-105" in texto or "PRÉ-SELECIONADOS" in texto
    # NÃO deve expor horários da agenda inteira que não foram selecionados
    assert "16:30" not in texto  # slot da agenda que não foi pré-selecionado


def test_c105_agenda_block_sem_slots_usa_logica_legada():
    """_agenda_block sem slots_selecionados → comportamento legado inalterado."""
    from voice_agent.responder import _agenda_block
    ctx = {
        "agenda": _AGENDA_MISTA,
        "known": {"medico": "Karla"},
    }
    texto = _agenda_block(ctx)
    # Deve conter a instrução legada
    assert "AGENDA REAL" in texto or "HORÁRIOS" in texto.upper()


def test_c105_gerar_oferta_prefere_slots_selecionados():
    """_gerar_oferta_3_slots usa known.slots_selecionados se disponível."""
    from voice_agent.responder import _gerar_oferta_3_slots
    slot_fixo = _slot("2026-08-20", "11:00", "Quinta-feira", "20/08")
    ctx = {
        "agenda": _AGENDA_MISTA,  # agenda maior, mas deve usar só slot_fixo
        "known": {"medico": "Karla", "unidade": "Asa Norte",
                  "slots_selecionados": [slot_fixo]},
    }
    texto = _gerar_oferta_3_slots(ctx)
    assert "11:00" in texto
    assert "20/08" in texto
    # Não deve citar slots da agenda original que não foram selecionados
    assert "08:30" not in texto
