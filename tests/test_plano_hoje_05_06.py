"""Pytest do "Plano Hoje" aplicado 05/06/2026 — sem mais documento.

3 fixes coberto:
1. kommo.py User-Agent (Bug #240)
2. kommo.patch_custom_fields_raw com GET validação (Bug C-12)
3. /admin/leads-abandonados (caso lead 24107106)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ============================================================
# FIX 1 — Bug #240 User-Agent
# ============================================================

class TestUserAgentKommo:
    """Confirma User-Agent identificável vai em todo header."""

    def test_user_agent_presente(self):
        from voice_agent.kommo import KommoClient
        c = KommoClient(subdomain="x", token="tok-test")
        h = c._headers
        assert "User-Agent" in h
        assert "blink-agent" in h["User-Agent"]
        assert "blinkoftalmologia" in h["User-Agent"]

    def test_authorization_continua_correto(self):
        from voice_agent.kommo import KommoClient
        c = KommoClient(subdomain="x", token="tok-test")
        h = c._headers
        assert h["Authorization"] == "Bearer tok-test"
        assert h["Content-Type"] == "application/json"
        assert h["Accept"] == "application/json"


# ============================================================
# FIX 2 — Bug C-12 patch_custom_fields_raw
# ============================================================

class TestPatchCustomFieldsRaw:
    """Função PATCH + GET de validação anti-MCP-mentiroso."""

    def test_assinatura_funcao_existe(self):
        from voice_agent.kommo import KommoClient
        assert hasattr(KommoClient, "patch_custom_fields_raw")

    def test_patch_2xx_e_get_confirma_grava_campo(self):
        from voice_agent.kommo import KommoClient
        c = KommoClient(subdomain="x", token="t")
        cfs = [{"field_id": 1260860, "values": [{"value": 1780000000}]}]

        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 200
        mock_patch_resp.json.return_value = {"id": 999}

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "custom_fields_values": [
                {"field_id": 1260860, "values": [{"value": 1780000000}]},
            ]
        }

        mock_httpx_client = MagicMock()
        mock_httpx_client.__enter__.return_value = mock_httpx_client
        mock_httpx_client.__exit__.return_value = None
        mock_httpx_client.patch.return_value = mock_patch_resp
        mock_httpx_client.get.return_value = mock_get_resp

        with patch("voice_agent.kommo.httpx.Client", return_value=mock_httpx_client):
            ok, body = c.patch_custom_fields_raw(999, cfs)
        assert ok is True

    def test_patch_2xx_mas_get_mostra_campo_nao_gravado_detecta_bug_C12(self):
        """O coração do Bug C-12: API retorna 2xx mas custom_fields_values fica vazio."""
        from voice_agent.kommo import KommoClient
        c = KommoClient(subdomain="x", token="t")
        cfs = [{"field_id": 1260860, "values": [{"value": 1780000000}]}]

        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 200
        mock_patch_resp.json.return_value = {"id": 999}

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"custom_fields_values": []}  # MENTIRA

        mock_httpx_client = MagicMock()
        mock_httpx_client.__enter__.return_value = mock_httpx_client
        mock_httpx_client.__exit__.return_value = None
        mock_httpx_client.patch.return_value = mock_patch_resp
        mock_httpx_client.get.return_value = mock_get_resp

        with patch("voice_agent.kommo.httpx.Client", return_value=mock_httpx_client):
            ok, body = c.patch_custom_fields_raw(999, cfs)
        assert ok is False
        assert body.get("bug") == "C-12"
        assert 1260860 in body.get("missing", [])

    def test_patch_403_retorna_false(self):
        from voice_agent.kommo import KommoClient
        c = KommoClient(subdomain="x", token="t")
        cfs = [{"field_id": 1260860, "values": [{"value": 1}]}]

        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 403
        mock_patch_resp.json.return_value = {"detail": "forbidden"}

        mock_httpx_client = MagicMock()
        mock_httpx_client.__enter__.return_value = mock_httpx_client
        mock_httpx_client.__exit__.return_value = None
        mock_httpx_client.patch.return_value = mock_patch_resp

        with patch("voice_agent.kommo.httpx.Client", return_value=mock_httpx_client):
            ok, body = c.patch_custom_fields_raw(999, cfs)
        assert ok is False
        assert body.get("status") == 403


# ============================================================
# FIX 3 — /admin/leads-abandonados (caso 24107106)
# ============================================================

class TestLeadsAbandonadosEndpoint:
    """Detecta o "promete e some" — Lia disse 'volto em 1min' e sumiu.

    Smoke test puro de syntax do webhook.py (sem importar pipeline pesado
    que dá deadlock no sandbox). Vale como gate de regressão sintática.
    """

    def test_webhook_py_compila(self):
        import py_compile
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "voice_agent" / "webhook.py"
        # py_compile lança PyCompileError se houver erro de sintaxe
        py_compile.compile(str(path), doraise=True)

    def test_endpoint_string_existe_no_arquivo(self):
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "voice_agent" / "webhook.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "/admin/leads-abandonados" in conteudo
        assert "admin_leads_abandonados" in conteudo
        # Critério de detecção: usa field_id 1260817 (ATIVADO IA?) + 1260860 (ÚLTIMA MENS LIA)
        assert "1260817" in conteudo
        assert "1260860" in conteudo
