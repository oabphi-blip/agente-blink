"""Pytest Bug C-16 — Lia disse "Atendemos INAS GDF" (lead 24117314, 08/06/2026).

Cobre:
1. Detector `_detectar_convenio_nao_aceito_no_texto` reconhece variantes
   (INAS, INAS GDF, gdf inas, etc) + outros convênios KB 18.
2. `_viola_disse_atende_convenio_nao_aceito` retorna nome quando combina
   afirmação positiva + convênio não aceito.
3. NÃO dispara em frases negativas ("não atendemos Inas").
4. `_gerar_script_convenio_nao_aceito` produz mensagem do artigo 18 KB.
5. _scrub_prohibited substitui a frase original pela mensagem corrigida.

Caso real (replica frase 1:1 do lead 24117314):
    "Perfeito! Atendemos o INAS GDF.\n\nAgora, para eu já solicitar..."
"""
from __future__ import annotations

import pytest

from voice_agent.responder import (
    _detectar_convenio_nao_aceito_no_texto,
    _gerar_script_convenio_nao_aceito,
    _viola_disse_atende_convenio_nao_aceito,
)


class TestDetectorConvenioNaoAceito:
    @pytest.mark.parametrize("frase, esperado", [
        ("Atendemos o INAS GDF", "inas"),
        ("Cobrimos o GDF Saúde", "gdf saúde"),
        ("Sim, aceitamos Cassi sem problemas", "cassi"),
        ("Bradesco está na nossa rede credenciada", "bradesco"),
        ("Hap Vida está coberto", "hap vida"),
        ("Atendemos Sul América sim", "sul américa"),
        ("Cobrimos Unimed perfeitamente", "unimed"),
    ])
    def test_detecta_convenios_kb18(self, frase, esperado):
        result = _detectar_convenio_nao_aceito_no_texto(frase)
        assert result == esperado, f"frase={frase!r} → got {result!r}"

    @pytest.mark.parametrize("frase", [
        "Atendemos Saúde Caixa sem restrição",  # KB 17 aceito
        "Cobrimos Pro ser STJ",  # KB 17 aceito
        "Atendemos TRF Pró-Social",  # KB 17 aceito
        "Sem convênio: R$ 611",  # particular
        "",
        None,
    ])
    def test_nao_dispara_em_convenios_aceitos(self, frase):
        result = _detectar_convenio_nao_aceito_no_texto(frase or "")
        assert result is None, f"falso positivo em frase={frase!r} → {result!r}"


class TestViolaAfirmacaoConvenioNaoAceito:
    def test_caso_real_lead_24117314_inas(self):
        """Frase EXATA da Lia em 08/06/2026 11:41 BRT."""
        frase = (
            "Perfeito!  Atendemos o INAS GDF.\n\n"
            "Agora, para eu já solicitar a autorização do convênio antes "
            "do dia da consulta, preciso confirmar:\n\n"
            "**Qual é a data de nascimento completa da Maria?** "
        )
        result = _viola_disse_atende_convenio_nao_aceito(frase, ctx=None)
        assert result == "inas"

    @pytest.mark.parametrize("frase, esperado", [
        ("Atendemos Bradesco sim", "bradesco"),
        ("Cobrimos Cassi", "cassi"),
        ("Aceitamos Sul América", "sul américa"),
        ("Credenciamos Notre Dame", "notre dame"),
        ("Hap Vida está na nossa rede", "hap vida"),
    ])
    def test_dispara_em_afirmacao_positiva(self, frase, esperado):
        result = _viola_disse_atende_convenio_nao_aceito(frase, ctx=None)
        assert result == esperado

    @pytest.mark.parametrize("frase", [
        "Infelizmente NÃO atendemos Inas GDF",
        "A Blink não cobre Bradesco",
        "Cassi não está credenciada na nossa rede",
        "Não aceitamos Unimed",
        "Sul América não cobre — só seguir sem convênio",
    ])
    def test_nao_dispara_em_negacao(self, frase):
        """Negações são CORRETAS — não devem disparar o filtro."""
        result = _viola_disse_atende_convenio_nao_aceito(frase, ctx=None)
        assert result is None, f"falso positivo em frase negativa: {frase!r}"

    def test_nao_dispara_em_texto_sem_convenio(self):
        frase = "Perfeito! Vou agendar pra você. Qual sua preferência?"
        assert _viola_disse_atende_convenio_nao_aceito(frase, ctx=None) is None

    def test_nao_dispara_em_convenio_aceito(self):
        frase = "Atendemos Saúde Caixa sim, posso agendar"
        assert _viola_disse_atende_convenio_nao_aceito(frase, ctx=None) is None


class TestGerarScript:
    def test_mensagem_contem_nao_credenciado(self):
        msg = _gerar_script_convenio_nao_aceito("inas", ctx=None)
        assert "não está credenciado" in msg.lower()

    def test_mensagem_contem_2_opcoes(self):
        msg = _gerar_script_convenio_nao_aceito("inas", ctx=None)
        assert "1️⃣" in msg
        assert "2️⃣" in msg
        assert "sem convênio" in msg.lower()

    def test_personaliza_com_nome(self):
        ctx = {"known": {"nome_paciente": "Maria Agostini Ferraz"}}
        msg = _gerar_script_convenio_nao_aceito("inas", ctx=ctx)
        assert "Maria" in msg
        assert "Agostini" not in msg, "Só primeiro nome"

    def test_nao_promete_excecao(self):
        msg = _gerar_script_convenio_nao_aceito("inas", ctx=None)
        proibidas = ["infelizmente", "talvez", "vou verificar", "pode ser que"]
        low = msg.lower()
        for p in proibidas:
            assert p not in low, f"frase proibida {p!r} na mensagem"

    def test_label_convenio_inas_uppercase(self):
        msg = _gerar_script_convenio_nao_aceito("inas", ctx=None)
        assert "INAS" in msg

    def test_label_convenio_longo_title_case(self):
        msg = _gerar_script_convenio_nao_aceito("bradesco", ctx=None)
        assert "Bradesco" in msg


class TestIntegracaoScrubProhibited:
    def test_scrub_substitui_afirmacao_inas(self):
        from voice_agent.responder import _scrub_prohibited
        frase_lia = "Perfeito! Atendemos o INAS GDF. Qual a data?"
        result = _scrub_prohibited(frase_lia, ctx=None)
        assert result != frase_lia, "scrub não substituiu"
        assert "não está credenciado" in result.lower()
        assert "INAS" in result

    def test_scrub_preserva_frase_correta(self):
        from voice_agent.responder import _scrub_prohibited
        frase_lia = "Vamos agendar sua consulta para Águas Claras"
        result = _scrub_prohibited(frase_lia, ctx=None)
        assert result == frase_lia
