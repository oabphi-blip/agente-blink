"""Blindagem do método get_lead_main_contact (task #212 / 04/06/2026).

Adicionado pra suportar endpoint /admin/disparar-lead/{lead_id} que
dispensa input manual de telefone/nome — busca tudo do Kommo.
"""
from unittest.mock import MagicMock, patch


def _kommo_instance():
    """Cria stub KommoClient com config mínima pra testes unit."""
    from voice_agent.kommo import KommoClient
    return KommoClient(subdomain="test", token="test_token")


def test_get_lead_main_contact_retorna_telefone_nome_status():
    k = _kommo_instance()

    fake_lead_response = MagicMock()
    fake_lead_response.status_code = 200
    fake_lead_response.json.return_value = {
        "id": 12345,
        "status_id": 101508307,
        "_embedded": {
            "contacts": [
                {"id": 999, "is_main": True},
            ],
        },
    }

    fake_contact_response = MagicMock()
    fake_contact_response.status_code = 200
    fake_contact_response.json.return_value = {
        "id": 999,
        "name": "Noah Pereira Vieira",
        "custom_fields_values": [
            {
                "field_code": "PHONE",
                "values": [{"value": "+5561999998888"}],
            },
        ],
    }

    with patch("voice_agent.kommo.httpx.Client") as mock_client_cls:
        client = MagicMock()
        client.get.side_effect = [fake_lead_response, fake_contact_response]
        mock_client_cls.return_value.__enter__.return_value = client

        result = k.get_lead_main_contact(12345)

    assert result is not None
    assert result["telefone"] == "5561999998888"  # só dígitos
    assert result["nome"] == "Noah Pereira Vieira"
    assert result["status_id"] == 101508307


def test_get_lead_main_contact_sem_contato_retorna_None():
    k = _kommo_instance()
    fake_lead_response = MagicMock()
    fake_lead_response.status_code = 200
    fake_lead_response.json.return_value = {
        "id": 12345,
        "status_id": 142,
        "_embedded": {"contacts": []},
    }
    with patch("voice_agent.kommo.httpx.Client") as mock_client_cls:
        client = MagicMock()
        client.get.return_value = fake_lead_response
        mock_client_cls.return_value.__enter__.return_value = client

        result = k.get_lead_main_contact(12345)

    assert result is None


def test_get_lead_main_contact_lead_inexistente():
    k = _kommo_instance()
    fake_resp = MagicMock()
    fake_resp.status_code = 404

    with patch("voice_agent.kommo.httpx.Client") as mock_client_cls:
        client = MagicMock()
        client.get.return_value = fake_resp
        mock_client_cls.return_value.__enter__.return_value = client

        result = k.get_lead_main_contact(99999)

    assert result is None


def test_get_lead_main_phone_usa_get_lead_main_contact():
    """get_lead_main_phone deve ser wrapper sobre get_lead_main_contact."""
    k = _kommo_instance()
    k.get_lead_main_contact = MagicMock(return_value={
        "telefone": "5561999998888",
        "nome": "Test",
        "status_id": 1,
    })
    assert k.get_lead_main_phone(123) == "5561999998888"


def test_get_lead_main_phone_sem_contato_retorna_None():
    k = _kommo_instance()
    k.get_lead_main_contact = MagicMock(return_value=None)
    assert k.get_lead_main_phone(123) is None


def test_get_lead_main_phone_contato_sem_telefone():
    k = _kommo_instance()
    k.get_lead_main_contact = MagicMock(return_value={
        "telefone": None, "nome": "Test", "status_id": 1,
    })
    assert k.get_lead_main_phone(123) is None
