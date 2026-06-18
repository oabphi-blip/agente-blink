"""Pytest da Camada 2 — endpoint /admin/gerar-oferta-slots/{lead_id}.

Testa as funções puras (parser de preferência, filtro de slots, seleção
dos 2 slots, montagem da mensagem canônica) + integração end-to-end com
mocks de KommoClient e MedwareClient.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from voice_agent.gerar_oferta_slots import (
    parsear_preferencia,
    filtrar_slots_por_preferencia,
    selecionar_2_slots,
    formatar_slot,
    montar_mensagem,
    gerar_oferta_para_lead,
    _apresentacao_medico,
    _primeiro_nome,
)


# ─────────────────────────────────────────────────────────────────────
# 1. parsear_preferencia
# ─────────────────────────────────────────────────────────────────────


def test_parser_segunda_manha_inicio():
    p = parsear_preferencia("Segunda-feira — manhã — início (8h-9h)")
    assert p["dia_semana"] == 0
    assert p["turno"] == "manha"
    assert p["periodo"] == "inicio"
    assert "segunda-feira" in p["texto_descritivo"]
    assert "manhã" in p["texto_descritivo"]
    assert "início" in p["texto_descritivo"]


def test_parser_quarta_tarde_fim():
    p = parsear_preferencia("Quarta tarde fim")
    assert p["dia_semana"] == 2
    assert p["turno"] == "tarde"
    assert p["periodo"] == "fim"


def test_parser_vazio_retorna_none():
    p = parsear_preferencia("")
    assert p["dia_semana"] is None
    assert p["turno"] is None
    assert p["periodo"] is None
    assert p["texto_descritivo"] == ""


def test_parser_amanha_sem_dia_especifico():
    p = parsear_preferencia("Amanhã (preferência não especificada)")
    # 'Amanhã' não casa com dia da semana → None
    assert p["dia_semana"] is None


def test_parser_sexta_manha():
    p = parsear_preferencia("sexta de manhã")
    assert p["dia_semana"] == 4
    assert p["turno"] == "manha"


def test_parser_noite_vira_tarde():
    # Blink não atende noite — cai pra tarde
    p = parsear_preferencia("quinta noite")
    assert p["dia_semana"] == 3
    assert p["turno"] == "tarde"


# ─────────────────────────────────────────────────────────────────────
# 2. filtrar_slots_por_preferencia
# ─────────────────────────────────────────────────────────────────────


def _mk_slot(data_iso, hora):
    return {"data_iso": data_iso, "hora": hora,
            "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5}


def test_filtro_dia_da_semana():
    slots = [
        _mk_slot("2026-06-22", "11:00:00"),  # segunda
        _mk_slot("2026-06-24", "08:30:00"),  # quarta
        _mk_slot("2026-06-29", "09:00:00"),  # segunda
    ]
    pref = {"dia_semana": 0, "turno": None, "periodo": None}
    out = filtrar_slots_por_preferencia(slots, pref)
    assert len(out) == 2
    assert all(s["_weekday"] == 0 for s in out)


def test_filtro_turno_manha():
    slots = [
        _mk_slot("2026-06-22", "09:00:00"),  # manhã
        _mk_slot("2026-06-22", "14:30:00"),  # tarde
        _mk_slot("2026-06-22", "11:00:00"),  # manhã
    ]
    pref = {"dia_semana": None, "turno": "manha", "periodo": None}
    out = filtrar_slots_por_preferencia(slots, pref)
    assert len(out) == 2
    assert all(s["_hora_int"] < 12 for s in out)


def test_filtro_periodo_inicio_ordena_por_proximidade():
    # Manhã início = ideal 8h. Quanto mais perto de 8h, melhor.
    slots = [
        _mk_slot("2026-06-22", "11:00:00"),
        _mk_slot("2026-06-22", "08:30:00"),
        _mk_slot("2026-06-22", "09:00:00"),
    ]
    pref = {"dia_semana": None, "turno": "manha", "periodo": "inicio"}
    out = filtrar_slots_por_preferencia(slots, pref)
    # 08:30 (mais perto de 8) vem primeiro
    assert out[0]["_hora_int"] == 8


def test_filtro_sem_preferencia_retorna_tudo():
    slots = [
        _mk_slot("2026-06-22", "09:00:00"),
        _mk_slot("2026-06-23", "14:00:00"),
    ]
    pref = {"dia_semana": None, "turno": None, "periodo": None}
    out = filtrar_slots_por_preferencia(slots, pref)
    assert len(out) == 2


# ─────────────────────────────────────────────────────────────────────
# 3. selecionar_2_slots
# ─────────────────────────────────────────────────────────────────────


def test_selecionar_2_pega_primeiros_quando_tem_2_ou_mais():
    filtrados = [
        _mk_slot("2026-06-29", "09:00:00"),
        _mk_slot("2026-06-29", "09:30:00"),
        _mk_slot("2026-07-06", "09:00:00"),
    ]
    out = selecionar_2_slots(filtrados, [])
    assert len(out) == 2
    assert out[0]["hora"] == "09:00:00"
    assert out[1]["hora"] == "09:30:00"


def test_selecionar_2_relaxa_para_lista_completa_se_vazio():
    filtrados = []
    sem_pref = [
        _mk_slot("2026-06-22", "11:00:00"),
        _mk_slot("2026-06-24", "08:30:00"),
    ]
    out = selecionar_2_slots(filtrados, sem_pref)
    assert len(out) == 2


def test_selecionar_2_completa_com_lista_relaxada_quando_so_tem_1():
    filtrados = [_mk_slot("2026-06-29", "09:00:00")]
    sem_pref = [
        _mk_slot("2026-06-22", "11:00:00"),
        _mk_slot("2026-06-29", "09:00:00"),  # já tá nos filtrados
        _mk_slot("2026-06-24", "08:30:00"),
    ]
    out = selecionar_2_slots(filtrados, sem_pref)
    assert len(out) == 2
    assert out[0]["hora"] == "09:00:00"


# ─────────────────────────────────────────────────────────────────────
# 4. formatar_slot
# ─────────────────────────────────────────────────────────────────────


def test_formatar_slot_basico():
    raw = {"data_iso": "2026-06-29", "hora": "09:00:00",
           "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5}
    out = formatar_slot(raw)
    assert out["data"] == "29/06"
    assert out["dia_semana"] == "segunda-feira"
    assert out["hora"] == "09:00"
    assert out["codAgenda"] == 4


def test_formatar_slot_aceita_formato_raw_medware():
    raw = {"data": "2026-06-22T00:00:00", "horario": "11:30:00",
           "codAgenda": 4}
    out = formatar_slot(raw)
    assert out["data"] == "22/06"
    assert out["dia_semana"] == "segunda-feira"
    assert out["hora"] == "11:30"


# ─────────────────────────────────────────────────────────────────────
# 5. montar_mensagem
# ─────────────────────────────────────────────────────────────────────


def test_mensagem_formato_canonico():
    slot1 = {"data": "29/06", "dia_semana": "segunda-feira", "hora": "09:00"}
    slot2 = {"data": "29/06", "dia_semana": "segunda-feira", "hora": "09:30"}
    msg = montar_mensagem(
        "Fábio", "Dra. Karla Delalíbera", "Asa Norte",
        "segunda-feira manhã início", slot1, slot2,
    )
    assert "Fábio!" in msg
    assert "Dra. Karla Delalíbera" in msg
    assert "Asa Norte" in msg
    assert "segunda-feira manhã início" in msg
    assert "1️⃣ segunda-feira, 29/06 às 09:00" in msg
    assert "2️⃣ segunda-feira, 29/06 às 09:30" in msg
    assert "Qual prefere?" in msg


def test_mensagem_sem_preferencia_omite_descritivo():
    slot1 = {"data": "22/06", "dia_semana": "segunda-feira", "hora": "11:00"}
    slot2 = {"data": "24/06", "dia_semana": "quarta-feira", "hora": "08:30"}
    msg = montar_mensagem(
        "Maria", "Dra. Karla Delalíbera", "Águas Claras",
        "", slot1, slot2,
    )
    # Sem vírgula antes do ":" porque não tem pref
    assert "na Águas Claras:" in msg
    assert "Maria!" in msg


# ─────────────────────────────────────────────────────────────────────
# 6. Helpers
# ─────────────────────────────────────────────────────────────────────


def test_primeiro_nome():
    assert _primeiro_nome("Fábio Philipe Costa Martins") == "Fábio"
    assert _primeiro_nome("maria  silva") == "Maria"
    assert _primeiro_nome("") == ""
    assert _primeiro_nome(None) == ""


def test_apresentacao_medico_karla():
    assert _apresentacao_medico("Dra. Karla Delalibera") == "Dra. Karla Delalíbera"
    assert _apresentacao_medico("karla") == "Dra. Karla Delalíbera"
    assert _apresentacao_medico(None) == "Dra. Karla Delalíbera"


def test_apresentacao_medico_fabricio():
    assert _apresentacao_medico("Dr. Fabricio Freitas") == "Dr. Fabrício Freitas"
    assert _apresentacao_medico("fabricio") == "Dr. Fabrício Freitas"


# ─────────────────────────────────────────────────────────────────────
# 7. Integração — gerar_oferta_para_lead com mocks
# ─────────────────────────────────────────────────────────────────────


def _lead_fabio_philipe():
    """Mimica o lead 24113652 (Fábio Philipe) usado no debug real."""
    return {
        "id": 24113652,
        "name": "AGENDAR_ Fábio Philipe segunda manhã",
        "custom_fields_values": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Fábio Philipe Costa Martins"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_name": "UNIDADE",
             "values": [{"value": "Asa Norte"}]},
            {"field_name": "DIA/TURNO/PERIODO ⚠️",
             "values": [{"value": "Segunda-feira — manhã — início (8h-9h)"}]},
        ],
    }


def test_gerar_oferta_fabio_philipe_completo():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    kommo.add_note.return_value = {"note_id": 99999}

    medware = MagicMock()
    medware.horarios_para_agente.return_value = [
        {"data_iso": "2026-06-22", "hora": "11:00:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
        {"data_iso": "2026-06-29", "hora": "09:00:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
        {"data_iso": "2026-06-29", "hora": "09:30:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
        {"data_iso": "2026-07-06", "hora": "08:30:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
    ]

    out = gerar_oferta_para_lead(
        lead_id=24113652,
        kommo_client=kommo,
        medware_client=medware,
        postar_nota=True,
    )

    assert out["ok"] is True
    assert out["paciente"] == "Fábio Philipe Costa Martins"
    assert out["medico"] == "Dra. Karla Delalíbera"
    assert out["unidade"] == "Asa Norte"
    assert len(out["slots"]) == 2
    # preferência: segunda manhã início → 29/06 09:00 deve estar no topo
    # (08:30 do 06/07 está mais perto de 8h mas é outra semana)
    assert all(s["dia_semana"] == "segunda-feira" for s in out["slots"])
    assert all("manhã" in out["mensagem_pronta"].lower() or
               "manh" in out["mensagem_pronta"] for _ in [0])
    # 1️⃣ e 2️⃣ na mensagem
    assert "1️⃣" in out["mensagem_pronta"]
    assert "2️⃣" in out["mensagem_pronta"]
    # Nota foi postada
    assert out["nota_kommo_id"] == 99999
    kommo.add_note.assert_called_once()


def test_gerar_oferta_lead_inexistente():
    kommo = MagicMock()
    kommo.get_lead.return_value = None
    medware = MagicMock()

    out = gerar_oferta_para_lead(99999999, kommo, medware)

    assert out["ok"] is False
    assert out["error"] == "lead_nao_encontrado"


def test_gerar_oferta_medware_vazio():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    medware = MagicMock()
    medware.horarios_para_agente.return_value = []

    out = gerar_oferta_para_lead(24113652, kommo, medware)

    assert out["ok"] is False
    assert out["error"] == "sem_slots"


def test_gerar_oferta_medware_exception():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    medware = MagicMock()
    medware.horarios_para_agente.side_effect = RuntimeError("ReadTimeout")

    out = gerar_oferta_para_lead(24113652, kommo, medware)

    assert out["ok"] is False
    assert out["error"] == "medware_indisponivel"
    assert "ReadTimeout" in out["detail"]


def test_gerar_oferta_override_medico():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    medware = MagicMock()
    medware.horarios_para_agente.return_value = [
        {"data_iso": "2026-06-23", "hora": "09:00:00",
         "cod_agenda": 4, "cod_medico": 12081, "cod_unidade": 3},
        {"data_iso": "2026-06-25", "hora": "10:00:00",
         "cod_agenda": 4, "cod_medico": 12081, "cod_unidade": 3},
    ]

    out = gerar_oferta_para_lead(
        24113652, kommo, medware,
        override_medico="Dr. Fabrício Freitas",
        override_unidade="Águas Claras",
    )

    # Override venceu o ctx do lead
    assert out["ok"] is True
    assert out["medico"] == "Dr. Fabrício Freitas"
    assert out["unidade"] == "Águas Claras"


def test_gerar_oferta_nao_posta_nota_quando_postar_nota_false():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    medware = MagicMock()
    medware.horarios_para_agente.return_value = [
        {"data_iso": "2026-06-29", "hora": "09:00:00", "cod_agenda": 4},
        {"data_iso": "2026-06-29", "hora": "09:30:00", "cod_agenda": 4},
    ]

    out = gerar_oferta_para_lead(
        24113652, kommo, medware, postar_nota=False,
    )

    assert out["ok"] is True
    assert out["nota_kommo_id"] is None
    kommo.add_note.assert_not_called()


def test_gerar_oferta_janela_dias_cap_em_14():
    kommo = MagicMock()
    kommo.get_lead.return_value = _lead_fabio_philipe()
    medware = MagicMock()
    medware.horarios_para_agente.return_value = [
        {"data_iso": "2026-06-29", "hora": "09:00:00", "cod_agenda": 4},
        {"data_iso": "2026-06-29", "hora": "09:30:00", "cod_agenda": 4},
    ]

    # Pedimos 60 dias — função deve capar em 14
    out = gerar_oferta_para_lead(
        24113652, kommo, medware, janela_dias=60,
    )

    assert out["ok"] is True
    assert out["janela_dias"] == 14


def test_gerar_oferta_lead_sem_preferencia_funciona():
    """Lead sem campo DIA/TURNO/PERIODO ainda deve receber 2 slots."""
    lead = {
        "id": 100,
        "name": "Paciente Novo",
        "custom_fields_values": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Maria Silva"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_name": "UNIDADE",
             "values": [{"value": "Asa Norte"}]},
            # SEM DIA/TURNO/PERIODO
        ],
    }
    kommo = MagicMock()
    kommo.get_lead.return_value = lead
    medware = MagicMock()
    medware.horarios_para_agente.return_value = [
        {"data_iso": "2026-06-22", "hora": "11:00:00", "cod_agenda": 4},
        {"data_iso": "2026-06-24", "hora": "08:30:00", "cod_agenda": 4},
    ]

    out = gerar_oferta_para_lead(100, kommo, medware, postar_nota=False)

    assert out["ok"] is True
    assert out["paciente"] == "Maria Silva"
    assert len(out["slots"]) == 2
    assert out["preferencia"]["dia_semana"] is None
