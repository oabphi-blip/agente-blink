"""Pytest do watchdog "Lia muda" (Pilar #4)."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def _iso_ago(segundos: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=segundos)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ----------------------------------------------------------------------
# _eh_horario_comercial
# ----------------------------------------------------------------------

class TestHorarioComercial:

    def test_segunda_meio_dia_eh_comercial(self):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        brt = timezone(timedelta(hours=-3))
        # 02/06/2026 segunda 12:00 BRT
        seg = datetime(2026, 6, 2, 12, 0, tzinfo=brt)
        assert _eh_horario_comercial(seg) is True

    def test_sabado_10h_eh_comercial(self):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        brt = timezone(timedelta(hours=-3))
        sab = datetime(2026, 6, 6, 10, 0, tzinfo=brt)
        assert _eh_horario_comercial(sab) is True

    def test_domingo_NAO_eh_comercial(self):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        brt = timezone(timedelta(hours=-3))
        dom = datetime(2026, 6, 7, 12, 0, tzinfo=brt)
        assert _eh_horario_comercial(dom) is False

    def test_19h_NAO_eh_comercial(self):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        brt = timezone(timedelta(hours=-3))
        noite = datetime(2026, 6, 2, 19, 0, tzinfo=brt)
        assert _eh_horario_comercial(noite) is False

    def test_7h_NAO_eh_comercial(self):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        brt = timezone(timedelta(hours=-3))
        cedo = datetime(2026, 6, 2, 7, 0, tzinfo=brt)
        assert _eh_horario_comercial(cedo) is False


# ----------------------------------------------------------------------
# _classifica_nota
# ----------------------------------------------------------------------

class TestClassificaNota:

    def test_paciente_whatsapp_eh_inbound(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("Paciente (WhatsApp):\noi") == "inbound"

    def test_paciente_evolution_eh_inbound(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("Paciente (Evolution):\noi") == "inbound"

    def test_lia_whatsapp_eh_outbound(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("Lia (WhatsApp):\nolá!") == "outbound"

    def test_robo_emoji_eh_outbound(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("🤖 Lia: oi") == "outbound"

    def test_texto_aleatorio_eh_outro(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("status alterado") == "outro"

    def test_vazio_eh_outro(self):
        from voice_agent.watchdog_lia import _classifica_nota
        assert _classifica_nota("") == "outro"


# ----------------------------------------------------------------------
# _ia_ativa
# ----------------------------------------------------------------------

class TestIaAtiva:

    def test_sem_notas_presume_ativa(self):
        from voice_agent.watchdog_lia import _ia_ativa
        assert _ia_ativa([]) is True

    def test_nota_pausado_inativa(self):
        from voice_agent.watchdog_lia import _ia_ativa
        assert _ia_ativa([{"text": "IA pausada pelo atendente"}]) is False

    def test_ultima_decisao_vence(self):
        from voice_agent.watchdog_lia import _ia_ativa
        # Primeiro pausada, depois reativada — vence a última
        notas = [
            {"text": "IA pausada"},
            {"text": "IA ativada de novo"},
        ]
        assert _ia_ativa(notas) is True


# ----------------------------------------------------------------------
# _classifica_lia_muda
# ----------------------------------------------------------------------

class TestClassificaLiaMuda:

    def test_inbound_antigo_sem_outbound_eh_suspeito(self):
        from voice_agent.watchdog_lia import _classifica_lia_muda
        agora = int(time.time())
        lead = {
            "notes": [
                {
                    "created_at": _iso_ago(600),
                    "text": "Paciente (WhatsApp):\nquero agendar",
                }
            ],
        }
        motivo = _classifica_lia_muda(lead, agora, 300)
        assert motivo is not None
        assert "sem resposta" in motivo.lower()

    def test_inbound_recente_NAO_dispara(self):
        from voice_agent.watchdog_lia import _classifica_lia_muda
        agora = int(time.time())
        lead = {
            "notes": [
                {
                    "created_at": _iso_ago(60),
                    "text": "Paciente (WhatsApp):\noi",
                }
            ],
        }
        assert _classifica_lia_muda(lead, agora, 300) is None

    def test_ultima_outbound_NAO_dispara(self):
        """Lia já respondeu = OK."""
        from voice_agent.watchdog_lia import _classifica_lia_muda
        agora = int(time.time())
        lead = {
            "notes": [
                {
                    "created_at": _iso_ago(800),
                    "text": "Paciente (WhatsApp):\noi",
                },
                {
                    "created_at": _iso_ago(400),
                    "text": "Lia (WhatsApp):\nolá!",
                },
            ],
        }
        assert _classifica_lia_muda(lead, agora, 300) is None

    def test_ia_pausada_NAO_dispara(self):
        from voice_agent.watchdog_lia import _classifica_lia_muda
        agora = int(time.time())
        lead = {
            "notes": [
                {
                    "created_at": _iso_ago(600),
                    "text": "Paciente (WhatsApp):\nteste",
                },
                {
                    "created_at": _iso_ago(550),
                    "text": "IA pausada pelo atendente humano",
                },
            ],
        }
        assert _classifica_lia_muda(lead, agora, 300) is None

    def test_lead_sem_notas_devolve_None(self):
        from voice_agent.watchdog_lia import _classifica_lia_muda
        assert _classifica_lia_muda({}, int(time.time()), 300) is None


# ----------------------------------------------------------------------
# tick (forcar_horario=True pra evitar dep de relógio)
# ----------------------------------------------------------------------

class TestTick:

    def test_kommo_None_devolve_vazio(self):
        from voice_agent.watchdog_lia import tick
        res = tick(None, MagicMock(), forcar_horario=True)
        assert res.varridos == 0

    def test_fora_de_horario_NAO_varre(self):
        from voice_agent.watchdog_lia import tick
        brt = timezone(timedelta(hours=-3))
        dom = datetime(2026, 6, 7, 12, 0, tzinfo=brt)
        kommo = MagicMock()
        res = tick(kommo, MagicMock(), now=dom, forcar_horario=False)
        assert res.fora_horario == 1
        kommo.list_leads_by_status.assert_not_called()

    def test_dry_run_NAO_envia(self, monkeypatch):
        from voice_agent.watchdog_lia import tick
        monkeypatch.setenv("SLACK_WEBHOOK_WATCHDOG_URL", "http://x")
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = [{"id": 1}]
        kommo.get_lead.return_value = {
            "id": 1, "status_id": 96441724,
            "notes": [{
                "created_at": _iso_ago(600),
                "text": "Paciente (WhatsApp):\noi",
            }],
        }
        res = tick(
            kommo, MagicMock(), silencio_max_seg=300,
            dry_run=True, forcar_horario=True,
        )
        assert res.suspeitos == 1
        assert res.alertados == 0

    def test_dedup_evita_duplicado(self, monkeypatch):
        from voice_agent.watchdog_lia import tick
        monkeypatch.setenv("SLACK_WEBHOOK_WATCHDOG_URL", "http://x")
        kommo = MagicMock()
        kommo.list_leads_by_status.return_value = [{"id": 1}]
        kommo.get_lead.return_value = {
            "id": 1, "status_id": 96441724,
            "notes": [{
                "created_at": _iso_ago(600),
                "text": "Paciente (WhatsApp):\noi",
            }],
        }
        redis = MagicMock()
        redis.exists.return_value = 1  # já alertado
        res = tick(
            kommo, redis, silencio_max_seg=300,
            dry_run=False, forcar_horario=True,
        )
        assert res.suspeitos == 1
        assert res.ja_alertados_dedup == 1
        assert res.alertados == 0


# ----------------------------------------------------------------------
# esta_habilitado
# ----------------------------------------------------------------------

class TestHabilitado:

    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("WATCHDOG_LIA_ENABLED", raising=False)
        from voice_agent.watchdog_lia import esta_habilitado
        assert esta_habilitado() is False

    def test_on(self, monkeypatch):
        monkeypatch.setenv("WATCHDOG_LIA_ENABLED", "1")
        from voice_agent.watchdog_lia import esta_habilitado
        assert esta_habilitado() is True

    def test_silencio_custom_env(self, monkeypatch):
        monkeypatch.setenv("WATCHDOG_SILENCIO_MAX_SEG", "120")
        from voice_agent.watchdog_lia import _silencio_max
        assert _silencio_max() == 120

    def test_silencio_invalido_volta_default(self, monkeypatch):
        monkeypatch.setenv("WATCHDOG_SILENCIO_MAX_SEG", "abc")
        from voice_agent.watchdog_lia import _silencio_max, SILENCIO_MAX_SEG_DEFAULT
        assert _silencio_max() == SILENCIO_MAX_SEG_DEFAULT
