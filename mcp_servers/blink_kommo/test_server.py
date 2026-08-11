"""Pytest blink-kommo — Sprint 5."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock

from blink_kommo import server as s


@pytest.fixture
def mock_client(monkeypatch):
    c = MagicMock()
    s._set_client(c)
    yield c


def test_get_lead_ok(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": 24176164, "name": "Lead Teste"}
    mock_client.get.return_value = resp
    out = s.get_lead(24176164)
    assert out["id"] == 24176164


def test_get_lead_nao_encontrado_levanta(mock_client):
    mock_client.get.return_value = MagicMock(status_code=404)
    with pytest.raises(ValueError):
        s.get_lead(99999999)


def test_buscar_por_telefone_normaliza(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"_embedded": {"leads": [{"id": 100}, {"id": 200}]}}
    mock_client.get.return_value = resp
    out = s.buscar_leads_por_telefone("(61) 9 8133-1005")
    args, kwargs = mock_client.get.call_args
    assert kwargs["params"]["query"] == "61981331005"  # só dígitos
    assert len(out) == 2


def test_buscar_por_telefone_vazio(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"_embedded": {"leads": []}}
    mock_client.get.return_value = resp
    out = s.buscar_leads_por_telefone("9999")
    assert out == []


def test_atualizar_custom_field_confirma_via_get(mock_client):
    """Bug C-12: PATCH success NÃO basta — precisa GET para validar."""
    patch_resp = MagicMock(status_code=200)
    patch_resp.json.return_value = {"ok": True}

    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "custom_fields_values": [
            {"field_id": 1260817, "values": [{"value": "Ativado"}]}
        ]
    }

    # PATCH e depois GET
    mock_client.patch.return_value = patch_resp
    mock_client.get.return_value = get_resp

    out = s.atualizar_custom_field(24176164, 1260817, "Ativado")
    assert out["ok"] is True
    assert out["valor_gravado"] == "Ativado"


def test_atualizar_custom_field_NAO_CONFIRMOU_bug_c12(mock_client):
    """Bug C-12: PATCH retorna OK mas GET mostra que NÃO gravou."""
    patch_resp = MagicMock(status_code=200)
    patch_resp.json.return_value = {"ok": True}

    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "custom_fields_values": [
            {"field_id": 1260817, "values": []}  # vazio!
        ]
    }

    mock_client.patch.return_value = patch_resp
    mock_client.get.return_value = get_resp

    out = s.atualizar_custom_field(24176164, 1260817, "Ativado")
    assert out["ok"] is False
    assert out["erro"] == "campo_nao_confirmou"
    assert out["valor_pedido"] == "Ativado"


def test_atualizar_custom_field_patch_falha(mock_client):
    mock_client.patch.return_value = MagicMock(status_code=403, text="Forbidden")
    out = s.atualizar_custom_field(24176164, 1260817, "Ativado")
    assert out["ok"] is False
    assert "403" in out["erro"]


def test_anexar_nota_ok(mock_client):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "_embedded": {"notes": [{"id": 28997100}]}
    }
    mock_client.post.return_value = resp
    out = s.anexar_nota(24176164, "Nota teste")
    assert out["ok"] is True
    assert out["note_id"] == 28997100


def test_mover_etapa_normal(mock_client):
    """Move para etapa ativa — não desativa IA."""
    mock_client.patch.return_value = MagicMock(status_code=200)
    out = s.mover_etapa(24176164, 102560495)  # 3-AGENDAR
    assert out["ok"] is True


def test_mover_etapa_inativa_desativa_ia(mock_client):
    """Move para 1-ATENDIMENTO HUMANO — IA é desativada (Bug C-24a)."""
    patch_resp = MagicMock(status_code=200)
    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "custom_fields_values": [
            {"field_id": 1260817, "values": [{"value": "Desativado"}]}
        ]
    }
    mock_client.patch.return_value = patch_resp
    mock_client.get.return_value = get_resp

    out = s.mover_etapa(24176164, 106563343)  # 1-ATENDIMENTO HUMANO
    assert out["ok"] is True
    # Deve ter chamado PATCH 2x: mover + desativar IA
    assert mock_client.patch.call_count >= 2


def test_resource_etapas_inativas_lista_4():
    txt = s.resource_etapas_inativas()
    assert "106563343" in txt
    assert "106157139" in txt
    assert "106484343" in txt
    assert "106484347" in txt
