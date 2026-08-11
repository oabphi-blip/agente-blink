"""Blindagem do método ensure_custom_field do KommoClient (task #216).

Implementado pra setup automático dos 3 campos de ACOMPANHAMENTO LIA:
  - STATUS CONVERSA (select, 15 valores)
  - ULTIMA MSG OUTBOUND (textarea)
  - PROXIMA ACAO (select, 12 valores)

Idempotente: chamando 2x não duplica.
"""
from unittest.mock import MagicMock, patch


def _kommo():
    from voice_agent.kommo import KommoClient
    return KommoClient(subdomain="test", token="test_token")


# ---------------------------------------------------------------------------
# list_custom_fields
# ---------------------------------------------------------------------------

def test_list_custom_fields_retorna_lista_paginada():
    k = _kommo()
    pagina_1 = MagicMock()
    pagina_1.status_code = 200
    pagina_1.json.return_value = {
        "_embedded": {
            "custom_fields": [
                {"id": 100, "name": "ATIVADO IA?", "type": "select"},
                {"id": 200, "name": "CONVÊNIO", "type": "select"},
            ],
        },
    }
    pagina_2 = MagicMock()
    pagina_2.status_code = 204

    with patch("voice_agent.kommo.httpx.Client") as mc:
        client = MagicMock()
        client.get.side_effect = [pagina_1, pagina_2]
        mc.return_value.__enter__.return_value = client
        result = k.list_custom_fields()

    assert len(result) == 2
    assert result[0]["name"] == "ATIVADO IA?"


# ---------------------------------------------------------------------------
# create_custom_field
# ---------------------------------------------------------------------------

def test_create_custom_field_textarea_payload_minimo():
    k = _kommo()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "_embedded": {
            "custom_fields": [
                {"id": 999, "name": "ULTIMA MSG OUTBOUND", "type": "textarea"},
            ],
        },
    }

    with patch("voice_agent.kommo.httpx.Client") as mc:
        client = MagicMock()
        client.post.return_value = fake_resp
        mc.return_value.__enter__.return_value = client
        res = k.create_custom_field(
            name="ULTIMA MSG OUTBOUND",
            field_type="textarea",
        )

    assert res is not None
    assert res["id"] == 999
    # Confirma que enviou payload correto
    body = client.post.call_args.kwargs["json"]
    assert body[0]["name"] == "ULTIMA MSG OUTBOUND"
    assert body[0]["type"] == "textarea"
    assert "enums" not in body[0]


def test_create_custom_field_select_com_enums():
    k = _kommo()
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "_embedded": {
            "custom_fields": [
                {"id": 1234, "name": "STATUS CONVERSA", "type": "select",
                 "enums": [{"id": 99001, "value": "aguardando_paciente_responder"}]},
            ],
        },
    }

    with patch("voice_agent.kommo.httpx.Client") as mc:
        client = MagicMock()
        client.post.return_value = fake_resp
        mc.return_value.__enter__.return_value = client
        res = k.create_custom_field(
            name="STATUS CONVERSA",
            field_type="select",
            enums=["aguardando_paciente_responder", "agenda_oferecida"],
        )

    assert res is not None
    assert res["id"] == 1234
    body = client.post.call_args.kwargs["json"]
    assert body[0]["type"] == "select"
    assert len(body[0]["enums"]) == 2
    assert body[0]["enums"][0]["value"] == "aguardando_paciente_responder"
    assert body[0]["enums"][0]["sort"] == 1


def test_create_custom_field_falha_4xx_retorna_None():
    k = _kommo()
    fake_resp = MagicMock()
    fake_resp.status_code = 400
    fake_resp.text = '{"validation-errors": [...]}'

    with patch("voice_agent.kommo.httpx.Client") as mc:
        client = MagicMock()
        client.post.return_value = fake_resp
        mc.return_value.__enter__.return_value = client
        res = k.create_custom_field(name="X", field_type="text")

    assert res is None


# ---------------------------------------------------------------------------
# ensure_custom_field (idempotente)
# ---------------------------------------------------------------------------

def test_ensure_custom_field_ja_existe_devolve_exists():
    k = _kommo()
    k.list_custom_fields = MagicMock(return_value=[
        {"id": 5555, "name": "STATUS CONVERSA", "type": "select"},
    ])
    k.create_custom_field = MagicMock()

    res = k.ensure_custom_field(
        name="STATUS CONVERSA", field_type="select",
        enums=["a", "b"],
    )

    assert res["action"] == "exists"
    assert res["field"]["id"] == 5555
    k.create_custom_field.assert_not_called()


def test_ensure_custom_field_nao_existe_cria():
    k = _kommo()
    k.list_custom_fields = MagicMock(return_value=[
        {"id": 1, "name": "OUTRO", "type": "text"},
    ])
    k.create_custom_field = MagicMock(return_value={
        "id": 7777, "name": "STATUS CONVERSA", "type": "select",
    })

    res = k.ensure_custom_field(
        name="STATUS CONVERSA", field_type="select",
        enums=["a", "b"],
    )

    assert res["action"] == "created"
    assert res["field"]["id"] == 7777
    k.create_custom_field.assert_called_once()


def test_ensure_custom_field_case_insensitive():
    """Match de nome ignora case (STATUS CONVERSA == Status Conversa)."""
    k = _kommo()
    k.list_custom_fields = MagicMock(return_value=[
        {"id": 333, "name": "Status Conversa", "type": "select"},
    ])
    k.create_custom_field = MagicMock()

    res = k.ensure_custom_field(name="STATUS CONVERSA", field_type="select")

    assert res["action"] == "exists"
    assert res["field"]["id"] == 333


def test_ensure_custom_field_falha_create_retorna_failed():
    k = _kommo()
    k.list_custom_fields = MagicMock(return_value=[])
    k.create_custom_field = MagicMock(return_value=None)

    res = k.ensure_custom_field(name="NOVO", field_type="text")

    assert res["action"] == "failed"
    assert res["field"] is None
