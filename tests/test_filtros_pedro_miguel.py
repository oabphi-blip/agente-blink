"""Blindagem dos 2 filtros do bug Pedro Miguel 24102510 (tasks #224 e #226).

#226 — Cronologia: D+30 oferecido tendo D+7 disponível
#224 — Pergunta conceitual ignorada
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from voice_agent.filtros_pedro_miguel import (
    _viola_data_distante,
    _gerar_oferta_mais_proxima,
    _viola_ignorar_pergunta_conceitual,
    _gerar_explicacao_e_retoma,
    detectar_pergunta_conceitual,
    extrair_datas_oferecidas,
    menor_data_na_agenda,
)

_TZ_BR = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# #226 — Cronologia
# ---------------------------------------------------------------------------

def test_extrair_datas_dd_mm():
    out = extrair_datas_oferecidas("Você prefere 30/06 ou 02/07?")
    assert len(out) == 2


def test_extrair_datas_dd_mm_yyyy():
    out = extrair_datas_oferecidas("Marcamos 11/06/2026 às 14:30?")
    assert len(out) == 1


def test_extrair_datas_sem_data_devolve_vazio():
    out = extrair_datas_oferecidas("Oi, tudo bem?")
    assert out == []


def test_menor_data_agenda_formato_iso():
    agenda = [
        {"dia_iso": "2026-06-30", "hora": "14:30"},
        {"dia_iso": "2026-06-11", "hora": "10:00"},
        {"dia_iso": "2026-07-02", "hora": "15:00"},
    ]
    res = menor_data_na_agenda(agenda)
    assert res is not None
    assert res.day == 11 and res.month == 6


def test_menor_data_agenda_vazia():
    assert menor_data_na_agenda([]) is None
    assert menor_data_na_agenda(None) is None


@patch("voice_agent.filtros_pedro_miguel.datetime")
def test_viola_data_distante_caso_pedro(mock_dt):
    """Caso real: hoje 05/06, agenda tem 11/06 (D+6), Lia ofereceu 30/06 (D+25)."""
    fake_hoje = datetime(2026, 6, 5, 12, 0, tzinfo=_TZ_BR)
    mock_dt.now.return_value = fake_hoje
    mock_dt.fromisoformat.side_effect = datetime.fromisoformat
    mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
    mock_dt.side_effect = datetime  # construtor passa direto

    ctx = {
        "agenda": [
            {"dia_iso": "2026-06-11", "hora": "14:00"},
            {"dia_iso": "2026-06-11", "hora": "14:30"},
            {"dia_iso": "2026-06-11", "hora": "15:00"},
        ],
    }
    text = "Você prefere 30/06 ou 02/07?"
    assert _viola_data_distante(text, ctx, limite_dias_aceitavel=10) is True


@patch("voice_agent.filtros_pedro_miguel.datetime")
def test_viola_data_distante_aceita_se_agenda_so_tem_longe(mock_dt):
    """Se a agenda mais próxima já é D+15+, não tem como exigir mais perto."""
    fake_hoje = datetime(2026, 6, 5, 12, 0, tzinfo=_TZ_BR)
    mock_dt.now.return_value = fake_hoje
    mock_dt.fromisoformat.side_effect = datetime.fromisoformat
    mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp
    mock_dt.side_effect = datetime

    ctx = {"agenda": [{"dia_iso": "2026-07-01", "hora": "14:00"}]}
    text = "Tenho 01/07 ou 05/07."
    assert _viola_data_distante(text, ctx, limite_dias_aceitavel=10) is False


def test_viola_data_distante_sem_ctx_no_op():
    assert _viola_data_distante("30/06", None) is False
    assert _viola_data_distante("30/06", {}) is False


def test_viola_data_distante_sem_agenda_no_op():
    assert _viola_data_distante("30/06", {"agenda": []}) is False


def test_gerar_oferta_mais_proxima_com_agenda():
    ctx = {"agenda": [{"dia_iso": "2026-06-11", "hora": "14:00"}]}
    res = _gerar_oferta_mais_proxima(ctx)
    assert "11/06" in res
    assert "2 opções" in res or "2 op" in res


def test_gerar_oferta_sem_agenda_pede_reconsulta():
    res = _gerar_oferta_mais_proxima({"agenda": []})
    assert "reconsultar" in res.lower()


# ---------------------------------------------------------------------------
# #224 — Pergunta conceitual ignorada
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg_paciente,esperado", [
    ("o que é convênio?", "convenio"),
    ("o que é convenio", "convenio"),
    ("não entendi o que é sinal", "sinal"),
    ("como funciona o pix?", "pix"),
    ("me explica o que é particular", "particular"),
    ("ah ok obrigada", None),
    ("", None),
    ("qual a diferença pra particular?", "particular"),
])
def test_detectar_pergunta_conceitual(msg_paciente, esperado):
    assert detectar_pergunta_conceitual(msg_paciente) == esperado


def test_viola_quando_paciente_pergunta_e_lia_ignora():
    ctx = {"user_text": "o que é convênio?"}
    lia_resp = "Qual é o nome do seu convênio?"  # ignorou a pergunta
    viola, conceito = _viola_ignorar_pergunta_conceitual(lia_resp, ctx)
    assert viola is True
    assert conceito == "convenio"


def test_aceita_quando_lia_explicou():
    ctx = {"user_text": "o que é convênio?"}
    lia_resp = (
        "Convênio é o plano de saúde — tipo Saúde Caixa, Cassi, etc. "
        "Você tem algum?"
    )
    viola, _ = _viola_ignorar_pergunta_conceitual(lia_resp, ctx)
    assert viola is False


def test_aceita_quando_nao_houve_pergunta_conceitual():
    ctx = {"user_text": "agendar quarta-feira por favor"}
    lia_resp = "Perfeito! Tenho quarta 11/06 às 14:30. OK?"
    viola, _ = _viola_ignorar_pergunta_conceitual(lia_resp, ctx)
    assert viola is False


def test_gerar_explicacao_convenio_inclui_termo_chave():
    res = _gerar_explicacao_e_retoma("convenio")
    assert "plano de saúde" in res.lower() or "plano" in res.lower()


def test_gerar_explicacao_conceito_desconhecido_default():
    res = _gerar_explicacao_e_retoma("conceito_que_nao_existe")
    assert "explicar" in res.lower() or "rapidinho" in res.lower()
