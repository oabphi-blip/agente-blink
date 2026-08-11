"""Bug C-44 (Fábio 12/07/2026, lead Clarice 22544990).

Sintoma: Lia escreveu 4× em intervalos irregulares:
    "Entendi! Vou encaminhar você para nossa **especialista em
     remarcação**, que vai cuidar dessa alteração com você.
     Só um instante."

Papel inexistente na Blink. Prompt bumped (VERSAO_PROMPT 12/07) mas
cache Anthropic 5min TTL — durante janela de cache, Lia continuou.

Fix arquitetural:
    voice_agent/responder.py: _viola_papel_inventado + fallback SEMPRE-ON
    em _scrub_prohibited (linha 2799). Não depende de FSM nem de
    deve_ofertar_agora. Se text bate no regex → substitui pela frase
    canônica de handoff humano.

Este teste blinda contra regressão. Cada asserção é fato objetivo
(texto real do lead Clarice ou variante conhecida).
"""
from __future__ import annotations

import pytest

from voice_agent.responder import (
    _gerar_fallback_papel_inventado,
    _viola_papel_inventado,
)


# ═══════════════════════════════════════════════════════════════════════
# TEXTOS REAIS QUE APARECERAM NO CHAT DA CLARICE 22544990
# ═══════════════════════════════════════════════════════════════════════

TEXTO_LITERAL_CLARICE = (
    "Entendi! Vou encaminhar você para nossa **especialista em "
    "remarcação**, que vai cuidar dessa alteração com você. Só um "
    "instante."
)


class TestDetectaTextoLiteralClarice:
    """Texto exato que a Lia mandou 4× no chat da Clarice."""

    def test_detecta_texto_completo(self):
        assert _viola_papel_inventado(TEXTO_LITERAL_CLARICE) is True

    def test_detecta_sem_markdown(self):
        texto = (
            "Entendi! Vou encaminhar você para nossa especialista em "
            "remarcação, que vai cuidar dessa alteração com você."
        )
        assert _viola_papel_inventado(texto) is True


class TestVariantesEspecialistaEmX:
    """Todas as variantes de "especialista em [X]" que Lia pode inventar."""

    @pytest.mark.parametrize("frase", [
        "vou passar pra nossa especialista em remarcação",
        "nossa especialista em remarcações vai atender",
        "encaminho você pra especialista em agendamento",
        "nossa equipe tem especialista em cancelamento",
        "vou chamar a especialista em alteração",
        "especialista em mudança de horário te ajuda",
        "especialista em troca de data",
        "especialista em horários",
        "Nossa especialista em Remarcação",  # case-insensitive
    ])
    def test_detecta_variante(self, frase):
        assert _viola_papel_inventado(frase) is True, (
            f"NÃO detectou variante conhecida: {frase!r}"
        )


class TestEncaminharParaNossaX:
    """Padrões 'vou encaminhar você para nossa/nosso [X]'."""

    @pytest.mark.parametrize("frase", [
        "Vou encaminhar você para nossa especialista",
        "vou encaminhar voce para nosso especialista",
        "vou te encaminhar pra nossa equipe de remarcação",
        "vou encaminhar pra o departamento de agendamento",
        "Vou encaminhar você para a equipe de cancelamento",
    ])
    def test_detecta_encaminhamento_inventado(self, frase):
        assert _viola_papel_inventado(frase) is True


class TestPapeisReaisNaoDisparaFalsoPositivo:
    """Papéis reais da Blink NÃO devem disparar o filtro."""

    @pytest.mark.parametrize("frase_ok", [
        "A Dra. Karla Delalíbera vai te atender",
        "O Dr. Fabrício Freitas cuida disso",
        "Nossa equipe vai te ajudar",
        "Vou te conectar com nossa equipe",
        "A secretaria vai retornar",
        "Um atendente humano assume aqui",
        "Vou passar pra Dra. Karla",
        "Segundo horário disponível é às 15h",  # menciona "horário" mas sem cargo
        "Sua próxima consulta está agendada",
    ])
    def test_texto_valido_nao_dispara(self, frase_ok):
        assert _viola_papel_inventado(frase_ok) is False, (
            f"Falso positivo em frase válida: {frase_ok!r}"
        )


class TestFallbackFraseCanonica:
    """Fallback deve ser curto, sem cargo específico, sem alucinar."""

    def test_fallback_menciona_paciente_se_conhecido(self):
        ctx = {"known": {"nome_paciente": "Clarice Santos Brunelli"}}
        texto = _gerar_fallback_papel_inventado(ctx)
        assert "Clarice" in texto

    def test_fallback_menciona_equipe_nao_cargo_especifico(self):
        ctx = {"known": {"nome_paciente": "Clarice"}}
        texto = _gerar_fallback_papel_inventado(ctx)
        assert "nossa equipe" in texto.lower()

    def test_fallback_nao_contem_frase_banida(self):
        """O próprio fallback NÃO pode conter frase banida (loop infinito)."""
        ctx = {"known": {"nome_paciente": "Clarice"}}
        texto = _gerar_fallback_papel_inventado(ctx)
        assert _viola_papel_inventado(texto) is False, (
            f"Fallback contém padrão banido: {texto!r}"
        )

    def test_fallback_curto_e_honesto(self):
        ctx = {"known": {"nome_paciente": "Clarice"}}
        texto = _gerar_fallback_papel_inventado(ctx)
        assert len(texto) < 200
        # Não promete cargo específico
        for banido in ["especialista", "departamento", "setor"]:
            assert banido not in texto.lower()

    def test_fallback_sem_paciente_ainda_funciona(self):
        texto = _gerar_fallback_papel_inventado(None)
        assert "nossa equipe" in texto.lower()

    def test_fallback_sem_known_nome(self):
        texto = _gerar_fallback_papel_inventado({"known": {}})
        assert "nossa equipe" in texto.lower()


class TestIntegracaoScrubProhibited:
    """Confirma que _scrub_prohibited substitui o texto ruim."""

    def test_scrub_substitui_texto_clarice(self):
        from voice_agent.responder import _scrub_prohibited

        ctx = {"known": {"nome_paciente": "Clarice"}}
        resultado = _scrub_prohibited(TEXTO_LITERAL_CLARICE, ctx=ctx)

        # Não pode ter mais "especialista em remarcação"
        assert "especialista em remarcação" not in resultado.lower()
        assert "especialista em remarcacao" not in resultado.lower()

        # Tem que ter a frase de handoff canônica
        assert "nossa equipe" in resultado.lower()

    def test_scrub_deixa_passar_texto_valido(self):
        from voice_agent.responder import _scrub_prohibited

        texto_bom = (
            "Clarice, aqui estão os horários com a Dra. Karla "
            "Delalíbera na Asa Norte:\n\n"
            "1️⃣ Segunda-feira (13/07) às 17h30\n"
            "2️⃣ Quarta-feira (15/07) às 13h30\n\n"
            "Qual funciona pra você?"
        )
        resultado = _scrub_prohibited(texto_bom, ctx={})
        # Deve retornar praticamente igual
        assert "17h30" in resultado
        assert "13h30" in resultado
        assert "Dra. Karla Delalíbera" in resultado
