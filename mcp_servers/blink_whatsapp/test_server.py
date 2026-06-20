"""Pytest blink-whatsapp — Sprint 6."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from pydantic import ValidationError

from blink_whatsapp import server as s


@pytest.fixture
def mock_client(monkeypatch):
    c = MagicMock()
    s._set_client(c)
    monkeypatch.setattr(s, "WA_CLOUD_TOKEN", "fake-token")
    monkeypatch.setattr(s, "WA_PHONE_NUMBER_ID", "999999")
    monkeypatch.setattr(s, "EVOLUTION_BASE", "https://evo.test")
    monkeypatch.setattr(s, "EVOLUTION_INSTANCE", "blink")
    monkeypatch.setattr(s, "EVOLUTION_TOKEN", "evo-token")
    yield c


def test_enviar_texto_meta_cloud_padrao(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"messages": [{"id": "wamid.ABC"}]}
    mock_client.post.return_value = resp
    out = s.enviar_texto("5561999000000", "oi")
    assert out["ok"] is True
    assert out["canal_usado"] == "8133"
    assert out["foi_redirect"] is False


def test_enviar_texto_canal_0710_evolution(mock_client):
    resp = MagicMock(status_code=200)
    mock_client.post.return_value = resp
    out = s.enviar_texto("5561999000000", "oi", canal="0710")
    assert out["ok"] is True
    assert out["canal_usado"] == "0710"


def test_enviar_texto_veio_do_0710_eh_redirect(mock_client):
    """Quando flag veio_do_0710=True, força redirect sem importar canal pedido."""
    resp = MagicMock(status_code=200)
    mock_client.post.return_value = resp
    out = s.enviar_texto(
        "5561999000000",
        "Sua consulta confirmada para 24/06 às 09:30",  # conteúdo clínico
        veio_do_0710=True,
    )
    assert out["foi_redirect"] is True
    assert out["canal_usado"] == "0710"

    # Verifica que NÃO enviou o conteúdo clínico — enviou texto fixo de redirect
    args, kwargs = mock_client.post.call_args
    payload = kwargs["json"]
    texto = payload["text"]
    assert "consulta confirmada" not in texto  # NÃO repassou
    assert "wa.me" in texto  # tem link de redirect
    assert "canal oficial" in texto.lower()


def test_enviar_template_meta_ok(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"messages": [{"id": "wamid.XYZ"}]}
    mock_client.post.return_value = resp
    out = s.enviar_template_meta(
        "5561999000000",
        "1019_sem_convenio",
        ["Maria", "Asa Norte"],
    )
    assert out["ok"] is True
    assert out["message_id"] == "wamid.XYZ"


def test_enviar_template_com_body_params(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"messages": [{"id": "wamid"}]}
    mock_client.post.return_value = resp
    s.enviar_template_meta(
        "5561999000000",
        "confirmacao",
        ["Maria", "Karla", "24/06", "09:30"],
    )
    args, kwargs = mock_client.post.call_args
    components = kwargs["json"]["template"]["components"]
    assert len(components) == 1
    params = components[0]["parameters"]
    assert len(params) == 4
    assert params[0]["text"] == "Maria"


def test_enviar_template_http_error_retorna_erro(mock_client):
    mock_client.post.return_value = MagicMock(status_code=400, text="bad request")
    out = s.enviar_template_meta("5561999000000", "template_x")
    assert out["ok"] is False
    assert "400" in out["erro"]


def test_phone_curto_demais_rejeita():
    with pytest.raises(ValidationError):
        s.enviar_texto("123", "oi")


def test_texto_vazio_rejeita():
    with pytest.raises(ValidationError):
        s.enviar_texto("5561999000000", "")


def test_texto_alem_4096_rejeita():
    with pytest.raises(ValidationError):
        s.enviar_texto("5561999000000", "x" * 5000)


def test_resource_canais_inclui_oficial_e_legado():
    txt = s.resource_canais()
    assert "8133" in txt
    assert "0710" in txt
    assert s.NUMERO_OFICIAL in txt
