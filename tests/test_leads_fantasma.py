"""Pytest do detector de leads-fantasma (Pilar #1)."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# _classifica_fantasma
# ----------------------------------------------------------------------

class TestClassifica:

    def test_lead_com_custom_fields_e_notas_NAO_eh_fantasma(self):
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 600,  # 10 min de idade
            "custom_fields": [
                {"values": [{"value": "Esther"}]},
                {"values": [{"value": "Karla"}]},
            ],
            "notes": [{"text": "oi"}],
        }
        assert _classifica_fantasma(lead, agora) is None

    def test_lead_recente_demais_pula(self):
        """Idade < 3 min = aguarda próximo tick."""
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 60,  # 1 min
            "custom_fields": [],
            "notes": [],
        }
        assert _classifica_fantasma(lead, agora) is None

    def test_lead_muito_velho_pula(self):
        """Idade > 30 min = não vale alertar (já passou)."""
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 3600,  # 1 hora
            "custom_fields": [],
            "notes": [],
        }
        assert _classifica_fantasma(lead, agora) is None

    def test_lead_vazio_idade_OK_eh_fantasma(self):
        """Caso 24057561 / 24060221: 10 min, nada preenchido."""
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 600,
            "custom_fields": [],
            "notes": [],
        }
        motivo = _classifica_fantasma(lead, agora)
        assert motivo is not None
        assert "custom_fields=0" in motivo
        assert "notas=0" in motivo

    def test_so_1_custom_field_eh_fantasma_borderline(self):
        """1 só CF = ainda suspeito (esperaria pelo menos motivo+nome)."""
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 600,
            "custom_fields": [{"values": [{"value": "Esther"}]}],
            "notes": [],
        }
        motivo = _classifica_fantasma(lead, agora)
        assert motivo is not None
        assert "custom_fields=1" in motivo

    def test_2_custom_fields_e_zero_notas_NAO_dispara(self):
        """2+ CF preenchidos = lead tá vivo, só não escreveu nota ainda."""
        from voice_agent.leads_fantasma import _classifica_fantasma
        agora = int(time.time())
        lead = {
            "_criado_ts": agora - 600,
            "custom_fields": [
                {"values": [{"value": "Esther"}]},
                {"values": [{"value": "Plan Assiste"}]},
            ],
            "notes": [],
        }
        assert _classifica_fantasma(lead, agora) is None

    def test_criado_at_iso_eh_parseado(self):
        from voice_agent.leads_fantasma import _classifica_fantasma
        # Lead criado há ~10 min, formato Kommo (Z)
        from datetime import datetime, timezone, timedelta
        criado = datetime.now(timezone.utc) - timedelta(minutes=10)
        lead = {
            "created_at": criado.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "custom_fields": [],
            "notes": [],
        }
        motivo = _classifica_fantasma(lead, int(time.time()))
        assert motivo is not None

    def test_sem_data_criacao_devolve_None(self):
        from voice_agent.leads_fantasma import _classifica_fantasma
        lead = {"custom_fields": [], "notes": []}
        assert _classifica_fantasma(lead, int(time.time())) is None

    def test_None_devolve_None(self):
        from voice_agent.leads_fantasma import _classifica_fantasma
        assert _classifica_fantasma(None, int(time.time())) is None
        assert _classifica_fantasma("string", int(time.time())) is None


# ----------------------------------------------------------------------
# tick + dedup
# ----------------------------------------------------------------------

class TestTick:

    def test_kommo_None_devolve_resultado_vazio(self):
        from voice_agent.leads_fantasma import tick
        res = tick(None, MagicMock())
        assert res.varridos == 0
        assert res.fantasmas_encontrados == 0

    def test_zero_leads_nao_alerta(self):
        from voice_agent.leads_fantasma import tick
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = []
        res = tick(kommo, MagicMock(), dry_run=True)
        assert res.varridos == 0

    def test_lead_fantasma_dry_run_NAO_envia(self, monkeypatch):
        from voice_agent.leads_fantasma import tick
        monkeypatch.setenv("SLACK_WEBHOOK_FANTASMA_URL", "http://x")
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = [{"id": 999}]
        agora = int(time.time())
        kommo.get_lead.return_value = {
            "id": 999,
            "name": "Lead #999",
            "status_id": 96441724,
            "created_at": _iso_ago(600),
            "custom_fields": [],
            "notes": [],
        }
        res = tick(kommo, MagicMock(), dry_run=True)
        assert res.varridos == 1
        assert res.fantasmas_encontrados == 1
        assert res.alertados == 0  # dry run

    def test_dedup_evita_alertar_duplicado(self, monkeypatch):
        from voice_agent.leads_fantasma import tick
        monkeypatch.setenv("SLACK_WEBHOOK_FANTASMA_URL", "http://x")
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = [{"id": 999}]
        kommo.get_lead.return_value = {
            "id": 999, "status_id": 96441724,
            "created_at": _iso_ago(600),
            "custom_fields": [], "notes": [],
        }
        redis = MagicMock()
        # Simula que esse lead JÁ foi alertado
        redis.exists.return_value = 1
        res = tick(kommo, redis, dry_run=False)
        assert res.fantasmas_encontrados == 1
        assert res.ja_alertados_dedup == 1
        assert res.alertados == 0

    def test_erro_get_lead_conta_como_erro(self):
        from voice_agent.leads_fantasma import tick
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = [{"id": 999}]
        kommo.get_lead.side_effect = RuntimeError("api down")
        res = tick(kommo, MagicMock(), dry_run=True)
        assert res.erros == 1


# ----------------------------------------------------------------------
# Habilitado / payload Slack
# ----------------------------------------------------------------------

class TestHabilitado:

    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LEADS_FANTASMA_ENABLED", raising=False)
        from voice_agent.leads_fantasma import esta_habilitado
        assert esta_habilitado() is False

    def test_on(self, monkeypatch):
        monkeypatch.setenv("LEADS_FANTASMA_ENABLED", "1")
        from voice_agent.leads_fantasma import esta_habilitado
        assert esta_habilitado() is True


class TestPayloadSlack:

    def test_payload_inclui_link_kommo(self):
        from voice_agent.leads_fantasma import (
            LeadFantasma, _payload_slack,
        )
        lf = LeadFantasma(
            lead_id=24057561, nome="Lead #X",
            status_id=96441724, criado_ts=0, idade_seg=600,
            motivo="custom_fields=0 + notas=0 (idade=600s)",
        )
        p = _payload_slack(lf)
        text = p["text"]
        assert "24057561" in text
        assert "fantasma" in text.lower()
        assert "univeja.kommo.com" in text


# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------

def _iso_ago(segundos: int) -> str:
    from datetime import datetime, timezone, timedelta
    return (
        datetime.now(timezone.utc) - timedelta(seconds=segundos)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
