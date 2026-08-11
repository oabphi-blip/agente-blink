"""Pytest do anti-envenenamento de MÉDICO/UNIDADE/CONVÊNIO no Kommo.

Origem: bug Diones 23742328 (01/06/2026). Lia alucinou Fabrício quando
ctx tinha Karla. extract_lead_fields detectou 'Fabrício' no histórico.
Pipeline gravou MÉDICOS=Fabrício no Kommo, sobrescrevendo Karla. Próximo
turn: ctx.known.medico=Fabrício, TRAVA MÉDICO defende o errado. Loop
de envenenamento.

Fix: MÉDICO/UNIDADE/CONVÊNIO só gravam se o lead AINDA NÃO TEM valor.
Atendente humano pode alterar manualmente pelo Kommo (não passa por aqui).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


class _FakePipeline:
    def __init__(self, known=None, status_id=102560495):
        self.kommo = MagicMock()
        self.kommo.find_lead_id_by_phone.return_value = 23742328
        self.kommo.get_caller_context_by_lead.return_value = {
            "known": known or {},
            "status_id": status_id,
        }
        self.kommo.update_lead_fields = MagicMock()
        self.kommo.update_lead_status = MagicMock()
        self.kommo.add_note = MagicMock()
        # extract_lead_fields será mockado por teste específico
        self.responder = MagicMock()
        self.responder.extract_lead_fields = MagicMock()


def _carregar_sync():
    from voice_agent.pipeline import VoicePipeline
    return VoicePipeline._sync_kommo_safely


class TestAntiEnvenenamento:

    def test_medico_diferente_bloqueia_sobrescrita(self):
        """Cenário Diones exato."""
        sync = _carregar_sync()
        p = _FakePipeline(known={"medico": "Dra. Karla Delalibera"})
        # extract_lead_fields detectou Fabricio no histórico
        p.responder.extract_lead_fields.return_value = {
            "medico": "Dr. Fabrício Freitas",
            "convenio": "Não se aplica",  # campo OK manter
            "name": "Diones",  # outros campos OK
        }
        sync(p, phone="5561X", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        # update_lead_fields foi chamado SEM 'medico'
        chamada = p.kommo.update_lead_fields.call_args
        fields_gravados = chamada[0][1]
        assert "medico" not in fields_gravados
        # Outros campos foram preservados
        assert fields_gravados.get("name") == "Diones"

    def test_unidade_diferente_bloqueia_sobrescrita(self):
        sync = _carregar_sync()
        p = _FakePipeline(known={"unidade": "Águas Claras"})
        p.responder.extract_lead_fields.return_value = {
            "unidade": "Asa Norte",  # tentativa de troca
            "ativado_ia": "ATIVADO",  # OK manter
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        assert "unidade" not in fields

    def test_convenio_diferente_bloqueia_sobrescrita(self):
        sync = _carregar_sync()
        p = _FakePipeline(known={"convenio": "STF-Med"})
        p.responder.extract_lead_fields.return_value = {
            "convenio": "Amil",  # tentativa de troca
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        assert "convenio" not in fields

    def test_medico_igual_NAO_bloqueia(self):
        """Reescrever pelo MESMO valor (ex: extract devolveu 'karla'
        e ctx tem 'Dra. Karla') é OK — não é envenenamento."""
        sync = _carregar_sync()
        p = _FakePipeline(known={"medico": "Dra. Karla Delalibera"})
        p.responder.extract_lead_fields.return_value = {
            "medico": "Dra. Karla Delalibera",
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        # medico tá presente porque é igual (idempotente)
        assert fields.get("medico") == "Dra. Karla Delalibera"

    def test_medico_vazio_no_ctx_permite_gravar_pela_primeira_vez(self):
        """Lead NOVO sem médico ainda — pipeline pode gravar."""
        sync = _carregar_sync()
        p = _FakePipeline(known={})  # vazio
        p.responder.extract_lead_fields.return_value = {
            "medico": "Dra. Karla Delalibera",
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        assert fields.get("medico") == "Dra. Karla Delalibera"

    def test_unidade_vazia_no_ctx_permite_gravar(self):
        sync = _carregar_sync()
        p = _FakePipeline(known={"medico": "Dra. Karla Delalibera"})
        p.responder.extract_lead_fields.return_value = {
            "unidade": "Águas Claras",  # ainda não tinha
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        assert fields.get("unidade") == "Águas Claras"

    def test_comparacao_case_insensitive(self):
        """'Karla' vs 'KARLA' não conta como mudança."""
        sync = _carregar_sync()
        p = _FakePipeline(known={"medico": "Dra. Karla Delalibera"})
        p.responder.extract_lead_fields.return_value = {
            "medico": "DRA. KARLA DELALIBERA",  # maiúscula
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        # Igualdade case-insensitive → permanece
        assert "medico" in fields

    def test_outros_campos_sem_protecao_podem_atualizar(self):
        """nome, motivo, dia_turno, etc seguem podendo atualizar."""
        sync = _carregar_sync()
        p = _FakePipeline(known={
            "medico": "Dra. Karla Delalibera",
            "motivo": "rotina",
        })
        p.responder.extract_lead_fields.return_value = {
            "reason": "estrabismo do filho",  # motivo MUDOU mas não está protegido
            "dia_turno_periodo": "Quarta tarde",
        }
        sync(p, phone="x", conversation_key="x",
             user_text="oi", answer="ok", channel="81331005")
        fields = p.kommo.update_lead_fields.call_args[0][1]
        assert fields.get("reason") == "estrabismo do filho"
        assert fields.get("dia_turno_periodo") == "Quarta tarde"
