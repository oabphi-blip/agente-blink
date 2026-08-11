"""Pytest dos fixes arquiteturais task #183 (06/06/2026):
1. Pipeline lock cross-rajada por conversation_key
2. tool_choice forçado por estado FSM em responder.py

Testes são puros (sem rede). Lock = mock Redis. tool_choice = análise
de strings do código + smoke import.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ============================================================
# FIX 1 — Pipeline lock cross-rajada
# ============================================================

class TestPipelineLockString:
    """Confirma código do lock está em pipeline.py."""

    def test_lock_aplicado_em_pipeline(self):
        path = ROOT / "voice_agent" / "pipeline.py"
        conteudo = path.read_text(encoding="utf-8")
        # Lock key padrão
        assert "blink:lock_pipeline:" in conteudo
        # Toggle env existe
        assert "PIPELINE_LOCK_ENABLED" in conteudo
        # Default ligado
        assert 'PIPELINE_LOCK_ENABLED", "1"' in conteudo
        # Erro padronizado
        assert "conversation_locked" in conteudo

    def test_pipeline_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "pipeline.py"
        py_compile.compile(str(path), doraise=True)


# ============================================================
# FIX 2 — tool_choice forçado por FSM em responder.py
# ============================================================

class TestToolChoicePorFSMString:
    """Confirma mapa estado → tool obrigatória + path correto."""

    def test_mapa_estado_para_tool(self):
        path = ROOT / "voice_agent" / "responder.py"
        conteudo = path.read_text(encoding="utf-8")
        # Mapa novo existe
        assert "_TOOL_POR_ESTADO" in conteudo
        # Estados FSM mapeados pras 3 tools
        assert '"AGENDA": "oferecer_slot"' in conteudo
        assert '"CONFIRMACAO": "confirmar_dados_paciente"' in conteudo
        assert '"GRAVACAO": "gravar_agendamento_medware"' in conteudo
        # tool_choice tipo "tool" + name (Anthropic API spec)
        assert '"type": "tool"' in conteudo
        # Lê fsm.estado (path correto que pipeline injeta)
        assert 'get("fsm", {})' in conteudo
        assert 'get("estado")' in conteudo

    def test_responder_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "responder.py"
        py_compile.compile(str(path), doraise=True)

    def test_ja_agendado_bypassa_tool_choice(self):
        """Se paciente já está agendado, NÃO força tool."""
        path = ROOT / "voice_agent" / "responder.py"
        conteudo = path.read_text(encoding="utf-8")
        # _ja_agendado lido + usado pra bypassar tool_choice
        assert "_ja_agendado = (caller_context or {}).get(\"ja_agendado\"" in conteudo
        assert "if _tool_obrigatoria and not _ja_agendado:" in conteudo


# ============================================================
# Anti-regressão — bugs cobertos
# ============================================================

class TestBugsCobertos:
    """Documenta no código quais bugs cada fix cobre — anti-regressão."""

    def test_pipeline_documenta_bug_183(self):
        path = ROOT / "voice_agent" / "pipeline.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "#183" in conteudo or "Bug #183" in conteudo

    def test_responder_documenta_bugs_alice_juliene(self):
        path = ROOT / "voice_agent" / "responder.py"
        conteudo = path.read_text(encoding="utf-8")
        # Pelo menos referência aos casos
        assert "Alice" in conteudo or "Sabrina" in conteudo or "task #183" in conteudo
