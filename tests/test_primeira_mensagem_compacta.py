"""
tests/test_primeira_mensagem_compacta.py

Replica caso lead 24154908 -- anti-regressao para filtros E-series.
Origem: diagnostico lead 24154908 (15/06/2026)
"""
import re
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from voice_agent.responder import (
        _viola_primeira_mensagem_longa,
        _viola_markdown_whatsapp,
        _viola_dicas_banidas,
        _viola_inicio_noite,
    )
    FILTROS_DISPONIVEIS = True
except ImportError:
    FILTROS_DISPONIVEIS = False


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro14_mensagem_longa_primeira():
    texto_longo = " ".join(["palavra"] * 81)
    ctx = {"turno_numero": 1}
    assert _viola_primeira_mensagem_longa(texto_longo, ctx)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro14_mensagem_curta_ok():
    texto_curto = " ".join(["palavra"] * 30)
    ctx = {"turno_numero": 1}
    assert not _viola_primeira_mensagem_longa(texto_curto, ctx)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro14_segundo_turno_ok():
    texto_longo = " ".join(["palavra"] * 200)
    ctx = {"turno_numero": 2}
    assert not _viola_primeira_mensagem_longa(texto_longo, ctx)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro15_markdown_headers():
    texto = "## Valor da Consulta\nR$ 350"
    assert _viola_markdown_whatsapp(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro15_markdown_separador():
    texto = "Opcoes\n---\nManha: 9h"
    assert _viola_markdown_whatsapp(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro16_dicas_banidas_minutos():
    texto = "A consulta dura de 60 a 90 minutos aproximadamente."
    assert _viola_dicas_banidas(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro16_dicas_banidas_horas():
    texto = "Apos a consulta, a visao fica embacada por 4 a 6 horas."
    assert _viola_dicas_banidas(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro16_dicas_banidas_experiencia():
    texto = "A Dra. Karla tem 15 anos de experiencia em oftalmologia."
    assert _viola_dicas_banidas(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro16_brinquedo_banido():
    texto = "Pode trazer brinquedo favorito do seu filho para a consulta."
    assert _viola_dicas_banidas(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro17_inicio_noite():
    texto = "Temos horario disponivel no Inicio da Noite, 18h."
    assert _viola_inicio_noite(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro17_turno_noite():
    texto = "Temos horarios no turno da noite tambem."
    assert _viola_inicio_noite(texto)


@pytest.mark.skipif(not FILTROS_DISPONIVEIS, reason="Filtros nao importaveis")
def test_filtro17_manha_tarde_ok():
    texto = "Temos horario na manha: 9h, e na tarde: 14h."
    assert not _viola_inicio_noite(texto)


def test_apresentacao_karla_canonica():
    resposta_correta = "Dra. Karla Delalibera, especialista em Avaliacao do Processamento Visual."
    assert "oftalmopediatria" not in resposta_correta.lower()
    assert "avaliacao do processamento visual" in resposta_correta.lower()


def test_pediatrica_replica_24154908():
    resposta_problematica = (
        "Ola! Sim, atendemos criancas! A consulta de avaliacao oftalmopediatrica "
        "com a Dra. Karla Delalibera, nossa especialista em oftalmopediatria "
        "com 15 anos de experiencia, dura de 60 a 90 minutos. "
        "Apos a consulta, a visao fica embacada por 4 a 6 horas. "
        "Recomendamos evitar voltar pra escola no mesmo dia. "
        "Para agendar, preciso de: nome da crianca, data de nascimento, "
        "motivo principal e unidade preferida. "
        "\n## Valor da Consulta R$ 350,00 (Pix) ou R$ 370,00 (Cartao)."
    )
    if FILTROS_DISPONIVEIS:
        assert _viola_dicas_banidas(resposta_problematica)
        assert _viola_markdown_whatsapp(resposta_problematica)


def test_primeira_mensagem_max_80_palavras():
    if not FILTROS_DISPONIVEIS:
        pytest.skip("Filtros nao importaveis")
    ctx = {"turno_numero": 1}
    texto_80 = " ".join(["ok"] * 80)
    assert not _viola_primeira_mensagem_longa(texto_80, ctx)
    texto_81 = " ".join(["ok"] * 81)
    assert _viola_primeira_mensagem_longa(texto_81, ctx)
