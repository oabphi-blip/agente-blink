"""Bug C-73 — anti-repetição de pergunta de perfil (Fábio 14/08/2026).

Caso real: lead 24456676. Paciente disse "Criança", Lia perguntou de novo
com nova taxonomia.
"""
from __future__ import annotations

import pytest

from voice_agent.anti_repeticao_perfil import (
    _classificar_inbound,
    _outbound_repete_pergunta_perfil,
    _perfil_do_ctx,
    _refinamento_por_categoria,
    validar_nao_repetir_pergunta_perfil,
)


class TestOutboundRepete:
    def test_padrao_v1_bebe_crianca_adolescente_adulto(self):
        t = "é para um bebê, criança, adolescente ou adulto?"
        assert _outbound_repete_pergunta_perfil(t) is True

    def test_padrao_v2_bebe_crianca_pequena_escolar(self):
        t = "é para um bebê, criança pequena, escolar ou adolescente?"
        assert _outbound_repete_pergunta_perfil(t) is True

    def test_texto_normal_passa(self):
        assert _outbound_repete_pergunta_perfil("Bom dia!") is False


class TestClassificarInbound:
    def test_crianca(self):
        assert _classificar_inbound("Criança") == "crianca"

    def test_bebe(self):
        assert _classificar_inbound("Bebê") == "bebe"

    def test_bebe_por_meses(self):
        assert _classificar_inbound("Meu filho tem 8 meses") == "bebe"

    def test_adolescente(self):
        assert _classificar_inbound("adolescente") == "adolescente"

    def test_adulto_para_mim(self):
        assert _classificar_inbound("Para mim mesmo") == "adulto"

    def test_sem_categoria(self):
        assert _classificar_inbound("Oi, tudo bem?") is None


class TestPerfilDoCtx:
    def test_ctx_crianca(self):
        ctx = {"known": {"perfil_paciente": "criança"}}
        assert _perfil_do_ctx(ctx) == "crianca"

    def test_ctx_bebe(self):
        ctx = {"known": {"perfil_paciente": "bebê"}}
        assert _perfil_do_ctx(ctx) == "bebe"

    def test_ctx_vazio(self):
        assert _perfil_do_ctx({}) is None

    def test_ctx_none(self):
        assert _perfil_do_ctx(None) is None


class TestRefinamento:
    def test_bebe_pergunta_meses(self):
        r = _refinamento_por_categoria("bebe")
        assert "meses" in r.lower()

    def test_crianca_pergunta_idade(self):
        r = _refinamento_por_categoria("crianca")
        assert "idade" in r.lower()

    def test_com_nome_saudacao(self):
        r = _refinamento_por_categoria("crianca", "Maria")
        assert "Maria" in r


class TestValidarNaoRepetirPergunta:
    def test_caso_real_lead_24456676(self):
        """Reproduz exatamente o caso do lead."""
        text = (
            "Posso te ajudar com o agendamento de consulta oftalmológica "
            "para a criança.\n\nPara eu te direcionar certo, pode me contar: "
            "é para um bebê, criança pequena, escolar ou adolescente?"
        )
        ctx = {"user_text": "Criança", "known": {}, "lead_id": "24456676"}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is True
        assert "idade" in txt.lower()  # refinamento correto

    def test_categoria_conhecida_via_ctx(self):
        text = "é para um bebê, criança, adolescente ou adulto?"
        ctx = {"user_text": "", "known": {"perfil_paciente": "bebê"}}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is True
        assert "meses" in txt.lower()

    def test_primeira_pergunta_sem_ctx_passa(self):
        """Primeira vez que pergunta, sem categoria conhecida — passa."""
        text = "é para um bebê, criança, adolescente ou adulto?"
        ctx = {"user_text": "Oi, quero agendar", "known": {}}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is False

    def test_texto_sem_pergunta_perfil_passa(self):
        text = "Bom dia, tudo bem?"
        ctx = {"user_text": "Criança", "known": {}}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is False

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("ANTI_REPETICAO_PERFIL_ATIVADO", "0")
        text = "é para um bebê, criança, adolescente ou adulto?"
        ctx = {"user_text": "Criança"}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is False

    def test_bebe_categoria(self):
        text = "é para um bebê, criança, adolescente ou adulto?"
        ctx = {"user_text": "Bebê de 3 meses"}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is True
        assert "meses" in txt.lower()

    def test_adulto_pergunta_nome(self):
        text = "é para um bebê, criança, adolescente ou adulto?"
        ctx = {"user_text": "Para mim mesmo"}
        txt, foi = validar_nao_repetir_pergunta_perfil(text, ctx)
        assert foi is True
        assert "nome" in txt.lower()
