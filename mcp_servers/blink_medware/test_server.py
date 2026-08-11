"""Pytest blink-medware — Sprint 4 com httpx mock."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from pydantic import ValidationError

from blink_medware import server as s


@pytest.fixture
def mock_client(monkeypatch):
    """Mock httpx.Client."""
    client = MagicMock()
    s._set_client(client)
    yield client


def test_consultar_horarios_payload_correto(mock_client):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [
        {"data": "2026-06-22T00:00:00", "horario": "11:00:00",
         "codAgenda": 4, "codMedico": 12080, "codUnidade": 5},
    ]
    mock_client.get.return_value = resp
    out = s.consultar_horarios(
        medico="karla", unidade="Asa Norte", dias=14,
        hora_inicio="07:00", hora_fim="12:00",
        data_inicio="2026-06-22",
    )
    assert len(out) == 1
    args, kwargs = mock_client.get.call_args
    params = kwargs["params"]
    assert params["codMedico"] == 12080
    assert params["codUnidade"] == 5
    assert params["dataInicio"] == "22/06/2026"
    assert params["dataFim"] == "06/07/2026"  # +14
    assert params["horaInicio"] == "07:00"
    assert params["horaFim"] == "12:00"


def test_consultar_horarios_medico_fabricio(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    mock_client.get.return_value = resp
    s.consultar_horarios(medico="fabricio", unidade="Águas Claras")
    args, kwargs = mock_client.get.call_args
    assert kwargs["params"]["codMedico"] == 12081
    assert kwargs["params"]["codUnidade"] == 3


def test_consultar_horarios_unidade_sem_acento(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    mock_client.get.return_value = resp
    s.consultar_horarios(medico="karla", unidade="Aguas Claras")
    args, kwargs = mock_client.get.call_args
    assert kwargs["params"]["codUnidade"] == 3


def test_consultar_horarios_medico_invalido_levanta(mock_client):
    with pytest.raises(ValueError, match="Médico desconhecido"):
        s.consultar_horarios(medico="zezinho", unidade="Asa Norte")


def test_consultar_horarios_unidade_invalida_levanta(mock_client):
    with pytest.raises(ValueError, match="Unidade desconhecida"):
        s.consultar_horarios(medico="karla", unidade="Marte")


def test_consultar_horarios_dias_alem_30_rejeita(mock_client):
    with pytest.raises(ValidationError):
        s.consultar_horarios(medico="karla", unidade="Asa Norte", dias=60)


def test_consultar_horarios_hora_formato_errado_rejeita(mock_client):
    with pytest.raises(ValidationError):
        s.consultar_horarios(
            medico="karla", unidade="Asa Norte",
            hora_inicio="7h", hora_fim="12h",
        )


def test_consultar_horarios_timeout_retorna_vazio(mock_client):
    import httpx
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    out = s.consultar_horarios(medico="karla", unidade="Asa Norte")
    assert out == []


def test_consultar_paciente_cpf_limpa_formatacao(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"codPaciente": 999, "nome": "Maria"}
    mock_client.get.return_value = resp
    out = s.consultar_paciente_cpf("123.456.789-00")
    args, kwargs = mock_client.get.call_args
    assert kwargs["params"]["cpf"] == "12345678900"
    assert out["codPaciente"] == 999


def test_consultar_paciente_cpf_invalido_levanta(mock_client):
    with pytest.raises(ValueError, match="CPF inválido"):
        s.consultar_paciente_cpf("123")


def test_gravar_agendamento_valida_antes_de_chamar(mock_client):
    """Servidor é guardião — valida ANTES de chamar API (livro 4.5)."""
    with pytest.raises(ValidationError):
        s.gravar_agendamento(
            cod_agenda=4, cod_medico=12080, cod_unidade=5,
            data_iso="22/06/2026",  # formato BR, deve falhar
            hora="09:30",
            cpf="12345678900", nome_paciente="Maria",
            data_nasc_iso="1985-03-15", celular_e164="5561999",
        )


def test_gravar_agendamento_nome_curto_rejeita(mock_client):
    with pytest.raises(ValidationError):
        s.gravar_agendamento(
            cod_agenda=4, cod_medico=12080, cod_unidade=5,
            data_iso="2026-06-22", hora="09:30",
            cpf="12345678900", nome_paciente="Ma",  # < 3 chars
            data_nasc_iso="1985-03-15", celular_e164="5561999000000",
        )


def test_gravar_agendamento_payload_correto(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"codAgendamento": 555}
    mock_client.post.return_value = resp
    out = s.gravar_agendamento(
        cod_agenda=4, cod_medico=12080, cod_unidade=5,
        data_iso="2026-06-22", hora="09:30",
        cpf="123.456.789-00",
        nome_paciente="Maria Silva Santos",
        data_nasc_iso="1985-03-15",
        celular_e164="5561999000000",
        cod_plano=29,  # Saúde Caixa
    )
    assert out["ok"] is True
    assert out["cod_agendamento"] == 555
    args, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    assert payload["data"] == "22/06/2026"
    assert payload["dataNasc"] == "15/03/1985"
    assert payload["cpf"] == "12345678900"  # limpo
    assert payload["codPlano"] == 29


def test_gravar_agendamento_http_400_retorna_erro(mock_client):
    resp = MagicMock(status_code=400)
    resp.text = "Convênio inválido"
    mock_client.post.return_value = resp
    out = s.gravar_agendamento(
        cod_agenda=4, cod_medico=12080, cod_unidade=5,
        data_iso="2026-06-22", hora="09:30",
        cpf="12345678900", nome_paciente="Maria Silva",
        data_nasc_iso="1985-03-15", celular_e164="5561999000000",
    )
    assert out["ok"] is False
    assert "400" in out["erro"]


def test_resource_medicos_inclui_karla_e_fabricio():
    txt = s.resource_medicos()
    assert "karla: codMedico=12080" in txt
    assert "fabricio: codMedico=12081" in txt


def test_resource_unidades_inclui_codigos():
    txt = s.resource_unidades()
    assert "codUnidade=5" in txt  # Asa Norte
    assert "codUnidade=3" in txt  # Águas Claras
