"""Blindagem dos campos de acompanhamento (task #231).

Origem: Fábio 05/06/2026 — adicionou colunas STATUS CONVERSA, ULTIMA MSG
OUTBOUND, PROXIMA ACAO e ÚLTIMA MENSAGEM (date_time) na lista do funil
ATENDE. Lia preenche a cada turno via _sync_kommo_safely.
"""
import pytest

from voice_agent.campos_acompanhamento import (
    FIELD_STATUS_CONVERSA, FIELD_PROXIMA_ACAO,
    FIELD_ULTIMA_MSG_OUTBOUND, FIELD_TS_ULTIMA_MSG_ENVIADA,
    formatar_ultima_msg_outbound, mapear_status_e_proxima,
    montar_dict_campos,
)


# ---------------------------------------------------------------------------
# Field IDs corretos
# ---------------------------------------------------------------------------

def test_field_ids_confirmados():
    assert FIELD_STATUS_CONVERSA[0] == 1260854
    assert FIELD_ULTIMA_MSG_OUTBOUND == 1260856
    assert FIELD_PROXIMA_ACAO[0] == 1260858
    assert FIELD_TS_ULTIMA_MSG_ENVIADA == 1260860


def test_enums_status_conversa_completos():
    """15 enums confirmados via API Kommo 05/06/2026."""
    table = FIELD_STATUS_CONVERSA[1]
    assert len(table) == 15
    # Sample checks dos críticos
    assert table["aguardando_paciente_responder"] == 927048
    assert table["agenda_oferecida"] == 927056
    assert table["agendado_aguarda_consulta"] == 927064
    assert table["convenio_nao_aceito"] == 927074


def test_enums_proxima_acao_completos():
    table = FIELD_PROXIMA_ACAO[1]
    assert len(table) == 12
    assert table["aguardar_resposta_paciente"] == 927078
    assert table["oferecer_agenda"] == 927082
    assert table["escalar_humano"] == 927094


# ---------------------------------------------------------------------------
# Formatador da ULTIMA MSG OUTBOUND
# ---------------------------------------------------------------------------

def test_formatar_inclui_autor_e_horario():
    res = formatar_ultima_msg_outbound(
        "Você prefere 9h ou 14h?",
        autor="LIA",
        ts_unix=1717612200,  # 05/06/2024 ~17:30 BRT
    )
    assert res.startswith("[LIA")
    assert "Você prefere 9h ou 14h?" in res


def test_formatar_humano_diferente_de_lia():
    res = formatar_ultima_msg_outbound(
        "Bom dia! Recebi seu áudio.", autor="HUMANO", ts_unix=1717612200,
    )
    assert res.startswith("[HUMANO")


def test_formatar_texto_vazio_devolve_vazio():
    assert formatar_ultima_msg_outbound("") == ""
    assert formatar_ultima_msg_outbound(None) == ""  # type: ignore[arg-type]


def test_formatar_trunca_texto_longo():
    longo = "a" * 1000
    res = formatar_ultima_msg_outbound(longo, ts_unix=1717612200)
    assert len(res) <= 510  # 500 max + prefixo curto
    assert res.endswith("…")


def test_formatar_collapsa_whitespace():
    res = formatar_ultima_msg_outbound(
        "linha 1\n\n\n   linha 2", ts_unix=1717612200,
    )
    assert "\n" not in res
    assert "   " not in res


# ---------------------------------------------------------------------------
# Mapeamento FSM → enums
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("estado_fsm,status_esperado,proxima_esperada", [
    ("TRIAGEM", "coletando_dados", "coletar_dados_minimos"),
    ("DADOS", "coletando_dados", "coletar_dados_minimos"),
    ("CONVENIO", "validando_convenio", "validar_convenio"),
    ("AGENDA", "agenda_oferecida", "aguardar_resposta_paciente"),
    ("CONFIRMACAO", "confirmando_horario", "aguardar_resposta_paciente"),
    ("GRAVACAO", "gravando_medware", "aguardar_resposta_paciente"),
    ("POS_GRAVACAO", "agendado_aguarda_consulta", "confirmar_horario_d-1"),
])
def test_mapeamento_caminho_feliz(
    estado_fsm, status_esperado, proxima_esperada,
):
    s, p = mapear_status_e_proxima(estado_fsm)
    assert s == status_esperado
    assert p == proxima_esperada


def test_mapeamento_ja_agendado_vence_fsm():
    """Mesmo estado FSM=TRIAGEM, ja_agendado=True força status final."""
    s, p = mapear_status_e_proxima("TRIAGEM", ja_agendado=True)
    assert s == "agendado_aguarda_consulta"
    assert p == "confirmar_horario_d-1"


def test_mapeamento_convenio_nao_aceito_vence_tudo():
    s, p = mapear_status_e_proxima(
        "AGENDA", convenio_nao_aceito=True, ja_agendado=False,
    )
    assert s == "convenio_nao_aceito"
    assert p == "escalar_humano"


def test_mapeamento_desistiu_vence_qualquer():
    s, p = mapear_status_e_proxima(
        "CONFIRMACAO", paciente_desistiu=True, ja_agendado=True,
    )
    assert s == "desistiu_explicito"
    assert p == "desativar_lead"


def test_mapeamento_cobrar_sinal_apos_oferta():
    s, p = mapear_status_e_proxima("CONFIRMACAO", cobrar_sinal=True)
    assert s == "aguardando_sinal_pix"
    assert p == "cobrar_sinal_pix"


def test_mapeamento_estado_desconhecido_devolve_none():
    s, p = mapear_status_e_proxima("ESTADO_QUE_NAO_EXISTE")
    assert s is None
    assert p is None


def test_mapeamento_none_devolve_none():
    s, p = mapear_status_e_proxima(None)
    assert s is None
    assert p is None


def test_mapeamento_lowercase_funciona():
    s, p = mapear_status_e_proxima("agenda")
    assert s == "agenda_oferecida"


# ---------------------------------------------------------------------------
# Montar dict completo
# ---------------------------------------------------------------------------

def test_montar_dict_sem_estado_so_msg():
    out = montar_dict_campos(
        answer="Oi!", estado_fsm=None, ts_unix=1717612200,
    )
    assert "ultima_msg_outbound" in out
    assert "status_conversa" not in out
    assert "proxima_acao" not in out


def test_montar_dict_estado_agenda_traz_3_chaves():
    out = montar_dict_campos(
        answer="Tenho 9h ou 14h", estado_fsm="AGENDA", ts_unix=1717612200,
    )
    assert out["status_conversa"] == "agenda_oferecida"
    assert out["proxima_acao"] == "aguardar_resposta_paciente"
    assert "ultima_msg_outbound" in out


def test_montar_dict_ja_agendado_pos_consulta():
    out = montar_dict_campos(
        answer="Te espero terça.", estado_fsm="POS_GRAVACAO",
        ja_agendado=True, ts_unix=1717612200,
    )
    assert out["status_conversa"] == "agendado_aguarda_consulta"
    assert out["proxima_acao"] == "confirmar_horario_d-1"


def test_montar_dict_answer_vazio_pula_msg():
    out = montar_dict_campos(answer="", estado_fsm="AGENDA")
    assert "ultima_msg_outbound" not in out
    # status/proxima continuam (são úteis mesmo sem texto novo)
    assert out["status_conversa"] == "agenda_oferecida"
