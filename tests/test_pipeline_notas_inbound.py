"""Pytest da gravação dupla de notas Kommo (paciente + Lia).

Origem: lead 23742328 Diones Alves Santos (01/06/2026). Notas do Kommo
mostravam apenas "Lia (WhatsApp):" — respostas do paciente sumiam, virando
monólogo impossível de auditar.

Garantia: TODA chamada ao _sync_kommo_safely com user_text não vazio grava
ANTES uma nota "💬 Paciente (WhatsApp):" + DEPOIS a nota da Lia.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


class _FakePipeline:
    """Stub minimalista pra exercitar _sync_kommo_safely sem cliente real."""

    def __init__(self):
        self.kommo = MagicMock()
        self.kommo.find_lead_id_by_phone.return_value = 23742328
        self.kommo.get_caller_context_by_lead.return_value = {}
        self.kommo.update_lead_fields = MagicMock()
        # responder.extract_lead_fields vazio (sem features)
        self.responder = MagicMock()
        self.responder.extract_lead_fields.return_value = {}


def _carregar_metodo():
    """Importa _sync_kommo_safely como função desacoplada do contexto da
    classe Pipeline (que pega muitos imports pesados). Usa unbound."""
    from voice_agent.pipeline import VoicePipeline
    return VoicePipeline._sync_kommo_safely


# ----------------------------------------------------------------------
# Casos
# ----------------------------------------------------------------------

class TestNotasInbound:

    def test_grava_nota_paciente_antes_nota_lia(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p,
            phone="5561999999999",
            conversation_key="556199999999",
            user_text="oi, quero agendar consulta",
            answer="Olá! Sou a Lia da Blink.",
            channel="81331005",
        )
        calls = p.kommo.add_note.call_args_list
        # Deve ter 2 chamadas: 1 do paciente + 1 da Lia
        assert len(calls) == 2, f"esperado 2 chamadas add_note, veio {len(calls)}"
        # Primeira = paciente
        primeira_text = calls[0][0][1]
        assert "Paciente" in primeira_text
        assert "oi, quero agendar consulta" in primeira_text
        # Segunda = Lia
        segunda_text = calls[1][0][1]
        assert "Lia" in segunda_text
        assert "Olá!" in segunda_text

    def test_user_text_vazio_so_grava_nota_lia(self):
        """Quando user_text é None ou vazio, NÃO grava nota inbound."""
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p,
            phone="5561999999999",
            conversation_key="x",
            user_text=None,
            answer="Lia disse algo",
            channel="81331005",
        )
        calls = p.kommo.add_note.call_args_list
        assert len(calls) == 1
        assert "Lia" in calls[0][0][1]

    def test_user_text_whitespace_so_grava_nota_lia(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p,
            phone="5561999999999",
            conversation_key="x",
            user_text="   \n  ",
            answer="resp",
            channel="81331005",
        )
        calls = p.kommo.add_note.call_args_list
        # só a Lia
        assert len(calls) == 1
        assert "Lia" in calls[0][0][1]

    def test_user_text_longo_e_truncado_em_3000(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        longo = "x" * 4000
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text=longo, answer="ok",
            channel="81331005",
        )
        primeira = p.kommo.add_note.call_args_list[0][0][1]
        # Cabeçalho + corpo truncado + reticências
        assert "Paciente" in primeira
        assert len(primeira) < 3100
        assert "…" in primeira

    def test_answer_vazio_so_grava_nota_paciente(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="",
            channel="81331005",
        )
        calls = p.kommo.add_note.call_args_list
        assert len(calls) == 1
        assert "Paciente" in calls[0][0][1]

    def test_lead_nao_encontrado_nao_grava_nada(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        p.kommo.find_lead_id_by_phone.return_value = None
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="ola",
            channel="81331005",
        )
        assert p.kommo.add_note.call_count == 0

    def test_kommo_none_nao_levanta(self):
        sync = _carregar_metodo()
        p = _FakePipeline()
        p.kommo = None
        # Não deve crashar
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="ola",
            channel="81331005",
        )

    def test_add_note_inbound_falha_nao_bloqueia_lia(self):
        """Se nota do paciente falhar (rede flaky), a da Lia ainda grava."""
        sync = _carregar_metodo()
        p = _FakePipeline()
        # primeira chamada: exception; segunda: ok
        p.kommo.add_note.side_effect = [
            RuntimeError("kommo flaky"),
            True,
        ]
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="ola",
            channel="81331005",
        )
        # Foi tentado 2 vezes (paciente E Lia)
        assert p.kommo.add_note.call_count == 2
