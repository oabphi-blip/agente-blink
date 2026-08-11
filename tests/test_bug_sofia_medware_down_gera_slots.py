"""
Bug Sofia 22843522 (11/07/2026) — Medware down → Lia disse "agenda fora do ar".

Fábio: 200h rodando sem evolução real. Fix mínimo, autônomo, sem worker
nem cache Redis:

Camada C — quando Medware DOWN + fallback Kommo vazio, gera 2 slots
plausíveis a partir do calendar_atendimento.json (dias que o médico
atende naquela unidade). Karla AC → próxima terça 10h + próxima quinta
14h. Karla AN → próxima seg/qua/sex. Fabrício AC → próxima ter/qui.

Não é slot Medware real. É pré-reserva sujeita a confirmação humana —
mesmo padrão que a equipe humana usa quando o Medware oscila.

Elimina 100% dos "agenda fora do ar" quando temos médico+unidade no ctx.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from voice_agent.responder import (
    _gerar_resposta_honesta_medware_down,
    _gerar_slots_do_calendario_json,
)

_TZ = ZoneInfo("America/Sao_Paulo")


# ---------- _gerar_slots_do_calendario_json ----------

def test_karla_aguas_claras_retorna_2_slots_ter_qui():
    ctx = {"known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"}}
    slots = _gerar_slots_do_calendario_json(ctx)
    assert len(slots) == 2
    dias_da_semana = {s["dia_semana"].lower() for s in slots}
    # deve ter só terça ou quinta
    for dia in dias_da_semana:
        assert dia in ("terça-feira", "quinta-feira"), f"Dia inválido: {dia}"


def test_karla_asa_norte_retorna_2_slots_seg_qua_sex():
    ctx = {"known": {"medico": "Karla Delalibera", "unidade": "Asa Norte"}}
    slots = _gerar_slots_do_calendario_json(ctx)
    assert len(slots) == 2
    for s in slots:
        assert s["dia_semana"].lower() in (
            "segunda-feira", "quarta-feira", "sexta-feira",
        ), f"Dia inválido pra Karla AN: {s['dia_semana']}"


def test_fabricio_aguas_claras_retorna_2_slots_ter_qui():
    ctx = {"known": {"medico": "Dr. Fabricio Freitas", "unidade": "Águas Claras"}}
    slots = _gerar_slots_do_calendario_json(ctx)
    assert len(slots) == 2
    for s in slots:
        assert s["dia"].lower() in ("terça-feira", "quinta-feira")


def test_slots_gerados_sao_futuros():
    """Nenhum slot pode ser hoje ou passado."""
    ctx = {"known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"}}
    slots = _gerar_slots_do_calendario_json(ctx)
    hoje = datetime.now(_TZ).date()
    for s in slots:
        d, m, y = s["data"].split("/")
        data = datetime(int(y), int(m), int(d)).date()
        assert data > hoje, f"Slot {s['data']} não é futuro"


def test_slots_horarios_padrao_10h_14h():
    """Primeiro slot 10:00 (manhã), segundo 14:00 (tarde)."""
    ctx = {"known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"}}
    slots = _gerar_slots_do_calendario_json(ctx)
    assert slots[0]["hora"] == "10:00"
    assert slots[1]["hora"] == "14:00"


def test_sem_medico_ou_unidade_retorna_vazio():
    """Sem contexto suficiente, não chuta."""
    assert _gerar_slots_do_calendario_json({}) == []
    assert _gerar_slots_do_calendario_json({"known": {"medico": "Karla"}}) == []
    assert _gerar_slots_do_calendario_json({"known": {"unidade": "AC"}}) == []


def test_medico_desconhecido_retorna_vazio():
    ctx = {"known": {"medico": "Dr. Fulano", "unidade": "Asa Norte"}}
    assert _gerar_slots_do_calendario_json(ctx) == []


def test_katia_em_pausa_retorna_vazio():
    """Kátia está em pausa — nunca gera slot."""
    ctx = {"known": {"medico": "Kátia Delalibera", "unidade": "Asa Norte"}}
    assert _gerar_slots_do_calendario_json(ctx) == []


# ---------- Integração: _gerar_resposta_honesta_medware_down ----------

def test_sofia_karla_asa_norte_NAO_diz_agenda_fora_do_ar():
    """Reproduz caso Sofia 22843522: Karla AN, Medware down, Kommo vazio.

    Com Camada C ativa, Lia deve OFERECER 2 slots plausíveis em vez do
    fallback 'agenda fora do ar neste exato momento'.
    """
    ctx = {
        "known": {
            "medico": "Karla Delalibera",
            "unidade": "Asa Norte",
            "nome_paciente": "Sofia",
        },
        "agenda": [],
    }
    resposta = _gerar_resposta_honesta_medware_down(ctx)
    assert "fora do ar" not in resposta.lower(), (
        f"Camada C não ativou pra Karla AN. Resposta: {resposta!r}"
    )
    assert "Karla" in resposta or "karla" in resposta.lower()


def test_karla_aguas_claras_medware_down_gera_oferta():
    ctx = {
        "known": {
            "medico": "Karla Delalibera",
            "unidade": "Águas Claras",
            "nome_contato": "Fábio",
        },
        "agenda": [],
    }
    resposta = _gerar_resposta_honesta_medware_down(ctx)
    assert "fora do ar" not in resposta.lower()
    # Deve mencionar terça ou quinta (dias Karla AC)
    r_low = resposta.lower()
    assert any(d in r_low for d in ("terça", "quinta")), (
        f"Deve mencionar ter/qui. Resposta: {resposta!r}"
    )


def test_sem_medico_medware_down_mantem_fallback_honesto():
    """Sem médico definido, Camada C não age → fallback honesto original."""
    ctx = {"known": {"nome_contato": "João"}, "agenda": []}
    resposta = _gerar_resposta_honesta_medware_down(ctx)
    assert "fora do ar" in resposta.lower()


def test_fabricio_aguas_claras_medware_down_gera_oferta():
    ctx = {
        "known": {
            "medico": "Fabrício Freitas",
            "unidade": "Águas Claras",
            "nome_contato": "Maria",
        },
        "agenda": [],
    }
    resposta = _gerar_resposta_honesta_medware_down(ctx)
    assert "fora do ar" not in resposta.lower()


def test_ctx_agenda_com_slots_medware_ok_ainda_e_prioridade_1():
    """Se Medware respondeu (ctx.agenda tem slots), Camada C NÃO deve
    substituir — prioridade 1 sempre vence."""
    slot_medware_real = {
        "data": "13/08/2026", "hora": "09:30", "dia": "quinta-feira",
        "cod_agenda": 12345,
    }
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"},
        "agenda": [slot_medware_real],
    }
    resposta = _gerar_resposta_honesta_medware_down(ctx)
    # Deve conter o slot Medware, não os do JSON
    assert "13/08" in resposta or "09:30" in resposta
