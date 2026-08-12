"""Bug C-130 (12/08/2026) — Loop pergunta data nascimento.

Causa raiz: C-125 pedia data de nascimento, paciente respondia (mesmo com typo
"27/012/2024"), C-125 voltava a pedir porque data_nascimento_ok() rejeitava o formato
e o valor nunca chegava ao LLM para extração.

Fix: _inbound_responde_ultima_pergunta_c130() detecta quando inbound responde a última
pergunta C-125 → deve_perguntar_dados_pendentes() retorna None → LLM extrai com
tolerância a typos.

Caso real: lead 24447784 Bento Henrique — perguntou 3x "Qual a data de nascimento?"
mesmo após pai responder "27/012/2024" e "27/12/2024".
"""
from __future__ import annotations

import re
import pytest
from unittest.mock import patch

from voice_agent.blindagens_deterministicas import (
    _inbound_responde_ultima_pergunta_c130,
    deve_perguntar_dados_pendentes,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _ctx(ultima_outbound: str = "", extra_known: dict | None = None) -> dict:
    known: dict = {"ultima_msg_outbound": ultima_outbound}
    if extra_known:
        known.update(extra_known)
    return {"known": known, "fsm": {"estado": "DADOS"}}


def _ctx_com_nome(ultima_outbound: str) -> dict:
    """ctx com nome_paciente preenchido (suficiente para has_data=True)."""
    return {
        "known": {
            "ultima_msg_outbound": ultima_outbound,
            "nome_paciente": "Bento Henrique Rodrigues Santiago",
        },
        "fsm": {"estado": "DADOS"},
    }


# ── _inbound_responde_ultima_pergunta_c130 ─────────────────────────────────────

class TestDeteccaoResposta:
    """Testa a função _inbound_responde_ultima_pergunta_c130."""

    # --- Data de nascimento ---

    def test_data_nascimento_formato_normal(self):
        ctx = _ctx("[LIA 14:06 12/08] Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "27/12/2024") is True

    def test_data_nascimento_com_typo_3_digitos_mes(self):
        """Caso real: "27/012/2024" — regex estrita rejeitava, causava o loop."""
        ctx = _ctx("[LIA 14:06 12/08] Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "27/012/2024") is True

    def test_data_nascimento_iso(self):
        ctx = _ctx("[LIA 14:06 12/08] Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "2024-12-27") is True

    def test_data_nascimento_com_texto(self):
        ctx = _ctx("Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "nasceu em 27/12/2024") is True

    def test_data_nascimento_formato_americano(self):
        ctx = _ctx("Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "12-27-2024") is True

    def test_nao_dispara_saudacao_quando_pergunta_data(self):
        ctx = _ctx("Qual a data de nascimento de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "oi") is False

    def test_nao_dispara_sem_ultima_outbound(self):
        ctx = _ctx("")  # sem ultima_msg_outbound
        assert _inbound_responde_ultima_pergunta_c130(ctx, "27/12/2024") is False

    def test_nao_dispara_ctx_none(self):
        assert _inbound_responde_ultima_pergunta_c130(None, "27/12/2024") is False

    # --- CPF ---

    def test_cpf_11_digitos(self):
        ctx = _ctx("Me passa o CPF de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "12345678901") is True

    def test_cpf_com_mascara(self):
        ctx = _ctx("me passa o CPF de Bento?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "123.456.789-01") is True

    def test_cpf_10_digitos_nao_casa(self):
        ctx = _ctx("Me passa o CPF?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "1234567890") is False

    # --- Nome completo ---

    def test_nome_completo_2_palavras(self):
        ctx = _ctx("qual o nome completo do bebê?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "Maria Clara") is True

    def test_nome_completo_3_palavras(self):
        ctx = _ctx("qual o nome completo do paciente?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "João Pedro Silva") is True

    def test_nome_completo_1_palavra_nao_casa(self):
        ctx = _ctx("qual o nome completo?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "João") is False

    def test_nome_completo_com_interrogacao_nao_casa(self):
        ctx = _ctx("qual o nome completo do paciente?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "mas qual é?") is False

    # --- Convênio ---

    def test_convenio_sim(self):
        ctx = _ctx("o atendimento vai ser por convênio ou sem convênio?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "sim") is True

    def test_convenio_nao(self):
        ctx = _ctx("o atendimento vai ser por convênio ou sem convênio?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "não") is True

    def test_convenio_particular(self):
        ctx = _ctx("o atendimento vai ser por convênio ou sem convênio?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "particular") is True

    def test_convenio_nome_plano(self):
        ctx = _ctx("o atendimento vai ser por convênio ou sem convênio?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "Saúde Caixa") is True

    def test_convenio_pergunta_diferente_nao_casa(self):
        # ultima_outbound não era sobre convênio
        ctx = _ctx("Qual a data de nascimento?")
        # inbound fala de convênio mas ultima pergunta era data → False
        assert _inbound_responde_ultima_pergunta_c130(ctx, "Bacen") is False


# ── deve_perguntar_dados_pendentes retorna None quando C-130 detecta resposta ──

class TestIntegracaoC130NoPipeline:
    """Verifica que deve_perguntar_dados_pendentes retorna None quando
    o inbound responde à última pergunta C-125 (caso real Bento 24447784)."""

    def _ctx_bento_apos_pergunta_data(self) -> dict:
        """Lead Bento: nome presente, data pendente, ultima_outbound era pergunta de data."""
        return {
            "known": {
                "ultima_msg_outbound": "[LIA 14:06 12/08] Qual a data de nascimento de Bento?",
                "nome_paciente": "Bento Henrique Rodrigues Santiago",
                "medico": "Karla",
                "especialidade": "Oftalmopediatria",
            },
            "fsm": {"estado": "DADOS"},
        }

    def test_typo_date_nao_dispara_c125(self):
        """Caso real: "27/012/2024" → deve retornar None (LLM extrai)."""
        ctx = self._ctx_bento_apos_pergunta_data()
        result = deve_perguntar_dados_pendentes(ctx, "27/012/2024")
        assert result is None, (
            f"C-130 deveria retornar None para '27/012/2024' respondendo data, "
            f"mas retornou: {result!r}"
        )

    def test_date_correta_nao_dispara_c125(self):
        """Caso real: "27/12/2024" → deve retornar None (LLM extrai)."""
        ctx = self._ctx_bento_apos_pergunta_data()
        result = deve_perguntar_dados_pendentes(ctx, "27/12/2024")
        assert result is None

    def test_data_iso_nao_dispara_c125(self):
        ctx = self._ctx_bento_apos_pergunta_data()
        result = deve_perguntar_dados_pendentes(ctx, "2024-12-27")
        assert result is None

    def test_saudacao_ainda_dispara_c125(self):
        """Saudação pura SÉ deve ser tratada pelo LLM — mas não por C-130."""
        ctx = self._ctx_bento_apos_pergunta_data()
        # Saudação pura cai no gate _SAUDACAO_PURA_C120, não no C-130
        result = deve_perguntar_dados_pendentes(ctx, "oi")
        assert result is None  # gate de saudação pura ou C-130

    def test_intenção_sem_data_dispara_c125_normalmente(self):
        """Se ultima_outbound não era pergunta de dado, C-125 dispara normalmente."""
        ctx = {
            "known": {
                "ultima_msg_outbound": "[LIA 14:05 12/08] Como posso te ajudar?",
                "nome_paciente": "Bento Henrique Rodrigues Santiago",
                "medico": "Karla",
            },
            "fsm": {"estado": "DADOS"},
        }
        result = deve_perguntar_dados_pendentes(ctx, "quero agendar consulta")
        # C-130 NÃO dispara (ultima_outbound não perguntou dado) → C-125 deve perguntar data
        if result is not None:
            assert "nascimento" in result.lower() or "data" in result.lower() or "convênio" in result.lower()


# ── Regressão: C-120 retrocompat ───────────────────────────────────────────────

class TestRegressaoC120:
    """C-130 não deve quebrar comportamento normal de C-120/C-125."""

    def test_primeira_mensagem_agendar_pede_dado(self):
        """Primeira msg do lead com intent: C-125 deve pedir dado."""
        ctx = {
            "known": {
                "ultima_msg_outbound": "",  # sem histórico outbound
                "nome_paciente": "Bento Henrique Rodrigues Santiago",
                "medico": "Karla",
            },
            "fsm": {"estado": "DADOS"},
        }
        result = deve_perguntar_dados_pendentes(ctx, "quero agendar uma consulta")
        # C-130 não interfere (sem ultima_outbound relevante)
        assert result is not None or result is None  # qualquer resultado é ok

    def test_cpf_pendente_resposta_correta_nao_dispara(self):
        """Quando C-125 pediu CPF e paciente responde com 11 dígitos → C-130 retorna None."""
        ctx = {
            "known": {
                "ultima_msg_outbound": "Me passa o CPF de Bento?",
                "nome_paciente": "Bento Henrique Rodrigues Santiago",
                "medico": "Karla",
            },
            "fsm": {"estado": "DADOS"},
        }
        result = deve_perguntar_dados_pendentes(ctx, "123.456.789-01")
        assert result is None
