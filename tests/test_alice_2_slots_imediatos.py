"""Blindagem do bug Alice lead 21256807 — 03/06/2026 22:09.

Tudo já preenchido no ctx (nome, idade, médico, unidade, convênio, motivo)
+ agenda real disponível → Lia perguntou "Manhã ou Tarde? Início, Meio ou
Fim do turno?" em vez de OFERECER 2 slots concretos.

Fluxo aprovado por Fábio (03/06/2026 noite):
  1. Lia oferece 2 slots mais próximos (1 manhã + 1 tarde quando possível)
  2. Paciente pode aceitar, pedir dia/hora específicos, ou recusar
  3. Se recusar SEM especificar → AÍ SIM Lia pergunta dia/turno/período

Filtros e helpers cobertos:
  - _viola_pergunta_turno_periodo_com_agenda(text, ctx)
  - _selecionar_2_slots_inteligente(agenda)
  - _gerar_oferta_2_slots(ctx)
"""
from voice_agent.responder import (
    _viola_pergunta_turno_periodo_com_agenda,
    _selecionar_2_slots_inteligente,
    _gerar_oferta_2_slots,
)


# Agenda Medware-like usada nos testes
AGENDA_REAL_KARLA_ASA_NORTE = [
    {"data_br": "05/06/2026", "hora": "09:00", "dia_semana": "quinta-feira"},
    {"data_br": "05/06/2026", "hora": "14:30", "dia_semana": "quinta-feira"},
    {"data_br": "06/06/2026", "hora": "10:00", "dia_semana": "sexta-feira"},
    {"data_br": "10/06/2026", "hora": "15:00", "dia_semana": "terça-feira"},
]


def _ctx_alice() -> dict:
    """Reproduz o ctx do lead 21256807 no momento da pergunta de turno."""
    return {
        "found": True,
        "known": {
            "nome_paciente": "Alice Rocha Nascimento Morais",
            "motivo": "retorno/pós-operatório",
            "convenio": "Saúde Caixa",
            "unidade": "Asa Norte",
            "medico": "Dra. Karla Delalibera",
            "especialidade": "Oftalmopediatria",
        },
        "medico": "Dra. Karla Delalibera",
        "agenda": AGENDA_REAL_KARLA_ASA_NORTE,
    }


# ---------------------------------------------------------------------------
# Caso real Alice (regressão direta)
# ---------------------------------------------------------------------------

def test_alice_pergunta_turno_periodo_com_agenda_eh_violacao():
    """A mensagem exata enviada às 22:09 do dia 03/06."""
    txt = (
        "Perfeito! Alice tem 5 anos. Então vamos agendar uma consulta de "
        "retorno/acompanhamento pós-operatório com a Dra. Karla na Asa Norte "
        "pelo Saúde Caixa.\n\n"
        "Qual sua preferência de turno e período?\n"
        "- Turno: Manhã ou Tarde?\n"
        "- Período: Início, Meio ou Fim?"
    )
    assert _viola_pergunta_turno_periodo_com_agenda(txt, _ctx_alice()) is True


def test_pergunta_manha_ou_tarde_simples_eh_violacao():
    txt = "Você prefere manhã ou tarde?"
    assert _viola_pergunta_turno_periodo_com_agenda(txt, _ctx_alice()) is True


def test_pergunta_inicio_meio_fim_eh_violacao():
    txt = "Período: Início, Meio ou Fim?"
    assert _viola_pergunta_turno_periodo_com_agenda(txt, _ctx_alice()) is True


def test_pergunta_qual_turno_eh_violacao():
    txt = "Pra eu organizar — qual é o seu turno preferido?"
    assert _viola_pergunta_turno_periodo_com_agenda(txt, _ctx_alice()) is True


# ---------------------------------------------------------------------------
# Não deve violar quando NÃO há agenda
# ---------------------------------------------------------------------------

def test_pergunta_turno_SEM_agenda_NAO_eh_violacao():
    """Sem agenda no ctx, perguntar preferência ainda é OK (vamos buscar Medware)."""
    txt = "Você prefere manhã ou tarde?"
    ctx_sem_agenda = {**_ctx_alice(), "agenda": []}
    assert _viola_pergunta_turno_periodo_com_agenda(txt, ctx_sem_agenda) is False


def test_oferta_concreta_NAO_eh_violacao():
    """Quando Lia OFERECE slot, não viola — o que viola é PERGUNTAR turno."""
    txt = (
        "Tenho 2 horários abertos: 1️⃣ quinta-feira (05/06) às 09:00 ou "
        "2️⃣ quinta-feira (05/06) às 14:30. Qual fica melhor?"
    )
    assert _viola_pergunta_turno_periodo_com_agenda(txt, _ctx_alice()) is False


# ---------------------------------------------------------------------------
# Seleção inteligente — 1 manhã + 1 tarde
# ---------------------------------------------------------------------------

def test_selecionar_pega_1_manha_e_1_tarde_quando_ambos_existem():
    """Caso ideal: agenda tem manhã e tarde → escolhe 1 de cada."""
    dois = _selecionar_2_slots_inteligente(AGENDA_REAL_KARLA_ASA_NORTE)
    assert len(dois) == 2
    horas = [int(s["hora"][:2]) for s in dois]
    assert horas[0] < 12  # 1º = manhã
    assert horas[1] >= 12  # 2º = tarde


def test_selecionar_so_manha_se_so_tem_manha():
    agenda_so_manha = [
        {"data_br": "05/06/2026", "hora": "09:00", "dia_semana": "quinta-feira"},
        {"data_br": "05/06/2026", "hora": "10:30", "dia_semana": "quinta-feira"},
        {"data_br": "06/06/2026", "hora": "11:00", "dia_semana": "sexta-feira"},
    ]
    dois = _selecionar_2_slots_inteligente(agenda_so_manha)
    assert len(dois) == 2
    assert dois[0]["hora"] == "09:00"
    assert dois[1]["hora"] == "10:30"


def test_selecionar_so_tarde_se_so_tem_tarde():
    agenda_so_tarde = [
        {"data_br": "05/06/2026", "hora": "14:00", "dia_semana": "quinta-feira"},
        {"data_br": "05/06/2026", "hora": "15:30", "dia_semana": "quinta-feira"},
    ]
    dois = _selecionar_2_slots_inteligente(agenda_so_tarde)
    assert len(dois) == 2
    assert all(int(s["hora"][:2]) >= 12 for s in dois)


def test_selecionar_agenda_vazia_retorna_lista_vazia():
    assert _selecionar_2_slots_inteligente([]) == []


def test_selecionar_1_slot_retorna_so_ele():
    agenda = [{"data_br": "05/06/2026", "hora": "09:00", "dia_semana": "quinta-feira"}]
    dois = _selecionar_2_slots_inteligente(agenda)
    assert len(dois) == 1


# ---------------------------------------------------------------------------
# Mensagem gerada
# ---------------------------------------------------------------------------

def test_gerar_oferta_2_slots_tem_emoji_1_e_2():
    msg = _gerar_oferta_2_slots(_ctx_alice())
    assert "1️⃣" in msg
    assert "2️⃣" in msg


def test_gerar_oferta_2_slots_menciona_medico_completo():
    msg = _gerar_oferta_2_slots(_ctx_alice())
    assert "Dra. Karla Delalibera" in msg


def test_gerar_oferta_2_slots_menciona_unidade():
    msg = _gerar_oferta_2_slots(_ctx_alice())
    assert "Asa Norte" in msg


def test_gerar_oferta_2_slots_tem_horarios_concretos():
    msg = _gerar_oferta_2_slots(_ctx_alice())
    # 1 manhã + 1 tarde escolhidos do AGENDA_REAL_KARLA_ASA_NORTE
    assert "09:00" in msg
    assert "14:30" in msg


def test_gerar_oferta_2_slots_oferece_alternativa():
    """Se paciente não gostar, mensagem deve oferecer caminho de fala livre."""
    msg = _gerar_oferta_2_slots(_ctx_alice())
    assert "outro" in msg.lower() or "preferir" in msg.lower()


def test_gerar_oferta_2_slots_NAO_pergunta_turno():
    """Crítico: a mensagem gerada NÃO pode reintroduzir a pergunta de turno."""
    msg = _gerar_oferta_2_slots(_ctx_alice())
    assert "turno" not in msg.lower()
    assert "manhã ou tarde" not in msg.lower()
    assert "início, meio" not in msg.lower()


def test_gerar_oferta_2_slots_agenda_vazia_pede_minuto():
    """Se agenda vazia (Medware indisponível), fallback honesto."""
    msg = _gerar_oferta_2_slots({"agenda": []})
    assert "1 minuto" in msg or "volto" in msg.lower()
