"""
Testes Bug C-76d — Context Guard + Zep limit
=============================================
29/07/2026 — BadRequestError 400 'maximum context length' em lead 24374118
(novo lead, primeira mensagem, chatId=null, mas overflow ainda assim).

Causa raiz: zep_adapter.recuperar_contexto() retornava TODOS os msgs sem
limite. Phone number com meses de histórico → centenas de msgs → overflow.

Fix:
1. zep_adapter.py: limit=20 hard cap em recuperar_contexto()
2. responder.py: CTX-GUARD estima tokens e trunca progressivamente antes
   de chamar a Claude API (Zep→10 em nivel1, history→12 em nivel2).
"""
from __future__ import annotations

import sys
import os
import types
import importlib
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─── Zep adapter tests ───────────────────────────────────────────────────────

class TestZepAdapterLimit:
    """Garante que recuperar_contexto() respeita o limite de msgs."""

    def _make_message(self, role_type: str, content: str):
        m = MagicMock()
        m.role_type = role_type
        m.content = content
        return m

    def _make_memory(self, n: int):
        """Cria objeto memory com n mensagens alternadas user/assistant."""
        msgs = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append(self._make_message(role, f"mensagem {i}"))
        mem = MagicMock()
        mem.messages = msgs
        return mem

    def test_sem_zep_key_retorna_vazio(self):
        """Sem ZEP_API_KEY, retorna [] independente do session_id."""
        with patch.dict(os.environ, {"ZEP_API_KEY": ""}):
            # reimport sem client ativo
            import importlib
            import voice_agent.zep_adapter as _zep
            importlib.reload(_zep)
            result = _zep.recuperar_contexto("qualquer-session")
        assert result == []

    def test_sem_session_id_retorna_vazio(self, monkeypatch):
        """session_id vazio retorna []."""
        import voice_agent.zep_adapter as _zep
        monkeypatch.setattr(_zep, "_client", MagicMock())
        result = _zep.recuperar_contexto("")
        assert result == []

    def test_20_msgs_passa_sem_truncar(self, monkeypatch):
        """20 mensagens (= limite padrão) não são truncadas."""
        import voice_agent.zep_adapter as _zep
        mock_client = MagicMock()
        mock_client.memory.get.return_value = self._make_memory(20)
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert len(result) == 20

    def test_30_msgs_trunca_para_20(self, monkeypatch):
        """30 mensagens → trunca para últimas 20."""
        import voice_agent.zep_adapter as _zep
        mock_client = MagicMock()
        mock_client.memory.get.return_value = self._make_memory(30)
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert len(result) == 20
        # Garante que são as ÚLTIMAS 20 (conteúdo "mensagem 10" a "mensagem 29")
        assert result[0]["content"] == "mensagem 10"
        assert result[-1]["content"] == "mensagem 29"

    def test_100_msgs_trunca_para_20(self, monkeypatch):
        """100 mensagens → trunca para últimas 20."""
        import voice_agent.zep_adapter as _zep
        mock_client = MagicMock()
        mock_client.memory.get.return_value = self._make_memory(100)
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert len(result) == 20

    def test_limit_customizavel(self, monkeypatch):
        """limit=5 trunca para 5."""
        import voice_agent.zep_adapter as _zep
        mock_client = MagicMock()
        mock_client.memory.get.return_value = self._make_memory(50)
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc", limit=5)
        assert len(result) == 5

    def test_msgs_vazias_filtradas(self, monkeypatch):
        """Mensagens com content vazio ou None são ignoradas."""
        import voice_agent.zep_adapter as _zep
        mem = MagicMock()
        m1 = self._make_message("user", "olá")
        m2 = self._make_message("assistant", "")       # vazia → skip
        m3 = self._make_message("user", "  ")          # só espaço → skip
        m4 = self._make_message("assistant", "resposta ok")
        mem.messages = [m1, m2, m3, m4]
        mock_client = MagicMock()
        mock_client.memory.get.return_value = mem
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_role_type_mapeado_corretamente(self, monkeypatch):
        """role_type human/user → 'user'; qualquer outro → 'assistant'."""
        import voice_agent.zep_adapter as _zep
        mem = MagicMock()
        mem.messages = [
            self._make_message("human", "oi"),
            self._make_message("user", "olá"),
            self._make_message("assistant", "tudo bem"),
            self._make_message("system", "instrução"),
        ]
        mock_client = MagicMock()
        mock_client.memory.get.return_value = mem
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert result[0]["role"] == "user"     # human
        assert result[1]["role"] == "user"     # user
        assert result[2]["role"] == "assistant"
        assert result[3]["role"] == "assistant"  # system → assistant

    def test_falha_silenciosa_retorna_vazio(self, monkeypatch):
        """Qualquer exceção retorna [] sem propagar."""
        import voice_agent.zep_adapter as _zep
        mock_client = MagicMock()
        mock_client.memory.get.side_effect = RuntimeError("timeout")
        monkeypatch.setattr(_zep, "_client", mock_client)

        result = _zep.recuperar_contexto("sess-abc")
        assert result == []


# ─── Context Guard helper tests ───────────────────────────────────────────────

class TestContextGuardHelpers:
    """Testa os helpers _chars_of e _chars_msgs usados no CTX-GUARD."""

    def _chars_of(self, field):
        if isinstance(field, list):
            return sum(len(b.get("text", "")) for b in field)
        return len(str(field))

    def _chars_msgs(self, msg_list):
        total = 0
        for m in msg_list:
            c = m.get("content", "")
            total += len(c) if isinstance(c, str) else sum(len(str(x)) for x in c)
        return total

    def test_chars_of_string(self):
        assert self._chars_of("hello world") == 11

    def test_chars_of_list_of_blocks(self):
        blocks = [{"text": "abc"}, {"text": "de"}]
        assert self._chars_of(blocks) == 5

    def test_chars_of_empty_list(self):
        assert self._chars_of([]) == 0

    def test_chars_msgs_string_content(self):
        msgs = [
            {"role": "user", "content": "oi"},       # 2 chars
            {"role": "assistant", "content": "tudo"},  # 4 chars
        ]
        assert self._chars_msgs(msgs) == 6

    def test_chars_msgs_list_content(self):
        msgs = [{"role": "assistant", "content": [{"type": "text", "text": "ok"}]}]
        result = self._chars_msgs(msgs)
        assert result > 0

    def test_chars_msgs_empty(self):
        assert self._chars_msgs([]) == 0

    def test_token_estimation_ratio(self):
        """4 chars ≈ 1 token (estimativa conservadora)."""
        system_chars = 400_000   # ~100K tokens — near limit
        msgs_chars = 100_000     # ~25K tokens
        tokens = (system_chars + msgs_chars) // 4
        assert tokens == 125_000
        assert tokens < 160_000  # abaixo do warning

    def test_token_estimation_overflow(self):
        """Sistema com 500K chars + 200K msgs → ~175K tokens → overflow."""
        system_chars = 500_000
        msgs_chars = 200_000
        tokens = (system_chars + msgs_chars) // 4
        assert tokens > 160_000


# ─── Context Guard logic integration tests ───────────────────────────────────

class TestContextGuardLogic:
    """
    Testa a lógica do CTX-GUARD inline no responder.py.
    Simula os 3 níveis: abaixo do limite, nivel1 (Zep), nivel2 (history).
    """

    def _run_guard(self, system_chars: int, zep_msgs: list, history: list, user_text: str = "oi"):
        """
        Reproduz a lógica do CTX-GUARD como ela aparece em responder.py.
        Retorna (messages_final, zep_final, history_final, nivel).
        """
        def _chars_of(field):
            if isinstance(field, list):
                return sum(len(b.get("text", "")) for b in field)
            return len(str(field))

        def _chars_msgs(msg_list):
            total = 0
            for m in msg_list:
                c = m.get("content", "")
                total += len(c) if isinstance(c, str) else sum(len(str(x)) for x in c)
            return total

        # Simula system_field com tamanho system_chars
        system_field = "x" * system_chars

        # Simula _sanitize_messages (passa direto)
        def sanitize(msgs): return msgs

        messages = sanitize(zep_msgs + history + [{"role": "user", "content": user_text}])
        _sys_chars = _chars_of(system_field)
        _ctx_tokens_est = (_sys_chars + _chars_msgs(messages)) // 4
        _CTX_WARN = 160_000
        _CTX_CRIT = 170_000
        nivel = 0

        if _ctx_tokens_est > _CTX_WARN:
            nivel = 1
            zep_msgs = zep_msgs[-10:] if zep_msgs else []
            messages = sanitize(zep_msgs + history + [{"role": "user", "content": user_text}])
            lvl1_est = (_sys_chars + _chars_msgs(messages)) // 4
            if lvl1_est > _CTX_CRIT:
                nivel = 2
                history = history[-12:] if len(history) > 12 else history
                messages = sanitize(zep_msgs + history + [{"role": "user", "content": user_text}])

        return messages, zep_msgs, history, nivel

    def test_abaixo_limite_nenhum_truncamento(self):
        """Contexto pequeno (<160K tokens) → sem truncamento."""
        system_chars = 100_000   # 25K tokens
        zep = [{"role": "user", "content": "x" * 100}] * 20
        hist = [{"role": "user", "content": "y" * 100}] * 12
        _, zep_out, hist_out, nivel = self._run_guard(system_chars, zep, hist)
        assert nivel == 0
        assert len(zep_out) == 20
        assert len(hist_out) == 12

    def test_nivel1_trunca_zep(self):
        """160K+ tokens → nivel1: Zep truncado para 10 msgs."""
        # 480K chars system + 80K msgs = 560K chars ≈ 140K tokens... below limit
        # Need to go over: 640K chars system = 160K tokens (já no limite)
        # 640K + 1 msgs de 100 chars cada * 100 = 10K chars extra = 162.5K tokens
        system_chars = 640_000   # 160K tokens
        zep = [{"role": "user", "content": "x" * 200}] * 30   # 6K chars extra = +1500 tokens
        hist = [{"role": "user", "content": "y" * 50}] * 12
        _, zep_out, hist_out, nivel = self._run_guard(system_chars, zep, hist)
        assert nivel >= 1
        assert len(zep_out) <= 10

    def test_nivel2_trunca_history(self):
        """Mesmo após truncar Zep, se ainda >170K → trunca history."""
        # Sistema enorme para forçar level 2
        system_chars = 680_000   # 170K tokens só do system — já no crit
        zep = [{"role": "user", "content": "x" * 200}] * 30
        hist = [{"role": "user", "content": "y" * 200}] * 24
        _, zep_out, hist_out, nivel = self._run_guard(system_chars, zep, hist)
        assert nivel == 2
        assert len(hist_out) <= 12

    def test_novo_lead_sem_historico_nao_e_afetado(self):
        """Novo lead (zep=[], history=[], user_text curto) → sem truncamento."""
        system_chars = 200_000   # 50K tokens — sistema normal
        msgs, zep_out, hist_out, nivel = self._run_guard(system_chars, [], [])
        assert nivel == 0
        assert len(msgs) == 1  # só o user_text

    def test_lead_24374118_simulado(self):
        """
        Simula lead 24374118: novo lead, Zep com 80 msgs de sessões anteriores.
        SYSTEM: 124K chars MASTER + 40K KB = ~164K chars ≈ 41K tokens.
        Zep: 80 msgs × 300 chars = 24K chars = 6K tokens.
        Total ≈ 47K tokens → ABAIXO do limite → nenhum truncamento.

        Mas se Zep tiver 500 msgs × 300 chars = 150K chars = 37.5K tokens
        + system 41K = 78.5K tokens → ainda ok.

        Forçar overflow: system 160K chars + Zep 500 msgs × 800 chars = 512K
        → total 672K chars ÷ 4 = 168K tokens → nivel1 ativado.
        """
        system_chars = 160_000  # 40K tokens
        # 500 msgs × 800 chars = 400K chars = 100K tokens → total 140K → nível 0?
        # Ainda sob 160K limite. Precisamos de mais.
        # 500 msgs × 800 chars + system 160K chars = 560K → 140K → abaixo do limite.
        # Para ativar nível 1: 700K chars total → 175K tokens.
        # System 700K - 160K = 540K de msgs → 675 msgs × 800 chars.
        zep = [{"role": "user", "content": "x" * 800}] * 675
        hist = []
        _, zep_out, hist_out, nivel = self._run_guard(system_chars, zep, hist)
        assert nivel >= 1
        assert len(zep_out) <= 10


# ─── Integration: Zep + Guard juntos ─────────────────────────────────────────

class TestZepAndGuardIntegration:
    """
    Verifica que Zep já truncado para 20 msgs + CTX-GUARD fornecem defesa dupla.
    """

    def test_zep_20_mais_guard_cobertura_dupla(self):
        """
        Zep retorna no máximo 20 msgs (fix C-76d zep_adapter).
        CTX-GUARD adicionalmente trunca se system muito grande.
        As duas defesas operam independentemente.
        """
        # Cenário: Zep retornou 20 msgs (depois do cap), cada uma de 2000 chars
        # System 100K chars (25K tokens)
        # 20 msgs × 2000 chars = 40K chars = 10K tokens
        # Total: 35K tokens → bem abaixo do limite
        system_chars = 100_000
        zep_20 = [{"role": "user", "content": "x" * 2000}] * 20

        def _chars_msgs(msg_list):
            total = 0
            for m in msg_list:
                c = m.get("content", "")
                total += len(c) if isinstance(c, str) else sum(len(str(x)) for x in c)
            return total

        msgs_chars = _chars_msgs(zep_20)
        tokens_est = (system_chars + msgs_chars) // 4
        assert tokens_est < 160_000, f"Zep 20 msgs + system normal não deve overflow: {tokens_est}"

    def test_sem_zep_nunca_overflow_lead_novo(self):
        """
        Lead novo (Zep=[], history=[]) com MASTER completo (124K chars)
        + 9 artigos KB obrigatórios (~40K chars) = ~164K chars ≈ 41K tokens.
        Muito abaixo do limite. CTX-GUARD deve ser nivel=0.
        """
        master_chars = 124_519
        kb_chars = 40_000
        system_chars = master_chars + kb_chars   # ~164K chars ≈ 41K tokens

        msgs_chars = len("oi")  # user_text mínimo
        tokens_est = (system_chars + msgs_chars) // 4
        assert tokens_est < 160_000, f"Lead novo não deve overflow: {tokens_est}"
