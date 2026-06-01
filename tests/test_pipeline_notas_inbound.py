"""Pytest da gravação de notas Kommo — APENAS Lia (outbound).

Histórico:
- 01/06/2026 manhã: introduzimos gravação dupla (paciente + Lia) pra
  facilitar auditoria de coerência (origem bug Diones 23742328).
- 01/06/2026 17:39 — Fábio decidiu reverter parcialmente: nota do
  paciente NÃO precisa virar nota Kommo (a mensagem já aparece no chat
  nativo). Mantemos APENAS a nota outbound da Lia, pra preservar
  observabilidade do agente sem poluir o feed.

Garantia: _sync_kommo_safely grava SOMENTE 1 nota por turno (a da Lia)
quando há `answer`. Não grava nada do `user_text`.
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
# Política nova: SOMENTE Lia em notas
# ----------------------------------------------------------------------

class TestNotasApenasLia:

    def test_user_text_e_answer_grava_so_lia(self):
        """Mesmo com user_text presente, NÃO grava nota inbound."""
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
        assert len(calls) == 1, (
            f"esperado 1 chamada add_note (só Lia), veio {len(calls)}"
        )
        nota = calls[0][0][1]
        assert "Lia" in nota
        assert "Olá!" in nota
        # NÃO pode conter o cabeçalho de paciente
        assert "Paciente" not in nota

    def test_user_text_vazio_so_grava_nota_lia(self):
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
        assert len(calls) == 1
        assert "Lia" in calls[0][0][1]

    def test_answer_vazio_NAO_grava_nada(self):
        """Sem answer, não há nada da Lia pra gravar — não grava NADA."""
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="",
            channel="81331005",
        )
        # Nenhuma nota: nem paciente (política), nem Lia (answer vazio)
        assert p.kommo.add_note.call_count == 0

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

    def test_add_note_outbound_falha_nao_bloqueia_sync(self):
        """Se a nota da Lia falhar (rede flaky), o resto do sync continua."""
        sync = _carregar_metodo()
        p = _FakePipeline()
        p.kommo.add_note.side_effect = RuntimeError("kommo flaky")
        # Não deve crashar — exception é capturada
        sync(
            p, phone="5561999999999",
            conversation_key="x",
            user_text="oi", answer="ola",
            channel="81331005",
        )
        # Tentou 1 vez (só a Lia)
        assert p.kommo.add_note.call_count == 1

    def test_nota_lia_NAO_contem_marca_paciente(self):
        """Sanity check: o texto da nota nunca pode vazar 'Paciente'."""
        sync = _carregar_metodo()
        p = _FakePipeline()
        sync(
            p, phone="5561x",
            conversation_key="x",
            user_text="texto qualquer do paciente",
            answer="resposta da Lia normal",
            channel="81331005",
        )
        calls = p.kommo.add_note.call_args_list
        assert len(calls) == 1
        # A única nota é da Lia — e ela NÃO carrega o texto do paciente
        nota = calls[0][0][1]
        assert "texto qualquer do paciente" not in nota
        assert "Lia" in nota
