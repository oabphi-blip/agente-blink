"""Blindagem das partes 1+3 do plano autônomo (04/06/2026).

PARTE 1 (task #218) — Cron interno semanal:
  - Worker dispara categoria R/E/C automaticamente toda segunda 9h BRT
  - Toggle via env CAMPANHA_SEMANAL_ENABLED=1
  - Dedup Redis evita re-disparo no mesmo dia

PARTE 3 (task #219) — Endpoint /admin/kommo-trigger-disparar:
  - Aceita JSON {lead_id, template, body_params}
  - Aceita form-urlencoded do Kommo Automation (leads[update][0][id])
"""
import os
from unittest.mock import patch


# ---------------------------------------------------------------------------
# PARTE 1 — Toggles e helpers de campanha semanal
# ---------------------------------------------------------------------------

def test_campanha_semanal_default_desligada():
    """Sem env, default = false. Não dispara nada."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CAMPANHA_SEMANAL_ENABLED", None)
        from voice_agent.cron_interno import _campanha_semanal_enabled
        assert _campanha_semanal_enabled() is False


def test_campanha_semanal_ligada_com_env_1():
    with patch.dict(os.environ, {"CAMPANHA_SEMANAL_ENABLED": "1"}):
        from voice_agent.cron_interno import _campanha_semanal_enabled
        assert _campanha_semanal_enabled() is True


def test_campanha_semanal_categoria_default_R():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CAMPANHA_SEMANAL_CATEGORIA", None)
        from voice_agent.cron_interno import _campanha_semanal_categoria
        assert _campanha_semanal_categoria() == "R"


def test_campanha_semanal_categoria_customizada():
    with patch.dict(os.environ, {"CAMPANHA_SEMANAL_CATEGORIA": "e"}):
        from voice_agent.cron_interno import _campanha_semanal_categoria
        # uppercase automático
        assert _campanha_semanal_categoria() == "E"


def test_campanha_semanal_max_default_20():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CAMPANHA_SEMANAL_MAX", None)
        from voice_agent.cron_interno import _campanha_semanal_max_leads
        assert _campanha_semanal_max_leads() == 20


def test_campanha_semanal_max_limite_200():
    """Tentativa de setar 500 vira 200 (cap de segurança)."""
    with patch.dict(os.environ, {"CAMPANHA_SEMANAL_MAX": "500"}):
        from voice_agent.cron_interno import _campanha_semanal_max_leads
        assert _campanha_semanal_max_leads() == 200


def test_campanha_semanal_max_invalido_cai_no_default():
    with patch.dict(os.environ, {"CAMPANHA_SEMANAL_MAX": "abc"}):
        from voice_agent.cron_interno import _campanha_semanal_max_leads
        assert _campanha_semanal_max_leads() == 20


# ---------------------------------------------------------------------------
# PARTE 1 — Função _eh_segunda_feira_9h_brt
# ---------------------------------------------------------------------------

def test_eh_segunda_feira_9h_brt_funcao_existe_e_roda():
    """Sanity check: função existe e devolve bool sem exception."""
    from voice_agent.cron_interno import _eh_segunda_feira_9h_brt
    result = _eh_segunda_feira_9h_brt()
    assert isinstance(result, bool)
