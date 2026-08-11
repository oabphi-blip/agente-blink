"""Pytest — Bug C-104 (11/08/2026): FAQ convênio aceito + valor enriquecido.

Origens:
  - Python deve responder "vocês aceitam X?" ANTES do LLM usando ctx.known.convenio_aceito
    já derivado por C-103 (enriquecimento_ctx).
  - deve_responder_valor agora usa ctx.known.valor_consulta (C-103) quando disponível.

Módulo testado: voice_agent/blindagens_deterministicas.py
  - deve_responder_faq_convenio_aceito(ctx, user_text)
  - deve_responder_valor(ctx, user_text) — fast path com valor_precomputado

Cobertura (20 cenários):
  - Convênio aceito via ctx.known.convenio_aceito=True → "sim, atendemos"
  - Convênio não aceito via ctx.known.convenio_aceito=False → "não está na rede"
  - Convênio aceito via ctx.known.convenio (sem convenio_aceito) → deriva inline
  - Convênio mencionado no user_text → extrai e deriva
  - Convênio desconhecido → retorna None (LLM continua)
  - Toggle BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO=0 → None
  - deve_responder_valor com valor_precomputado=None (coberto) → "coberto pelo plano"
  - deve_responder_valor com valor_precomputado tuple → resposta formatada
  - deve_responder_valor sem valor_precomputado → fallback inference normal
  - Integração: tentar_bypass_deterministico usa faq_convenio_aceito
"""
from __future__ import annotations

import os
import pytest

from voice_agent.blindagens_deterministicas import (
    deve_responder_faq_convenio_aceito,
    deve_responder_valor,
    tentar_bypass_deterministico,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(convenio: str = "", convenio_aceito=None, medico: str = "Karla",
         valor_consulta=None, nome: str = "Ana") -> dict:
    known: dict = {"nome": nome, "medico": medico}
    if convenio:
        known["convenio"] = convenio
    if convenio_aceito is not None:
        known["convenio_aceito"] = convenio_aceito
    if valor_consulta is not None or valor_consulta == ():
        known["valor_consulta"] = valor_consulta
    return {"known": known}


def _ctx_com_valor(medico: str, val_tuple, nome: str = "Carlos") -> dict:
    """ctx com valor_consulta já derivado + convenio_aceito=False (particular)."""
    return {
        "known": {
            "nome": nome,
            "medico": medico,
            "convenio": "Não se aplica",
            "convenio_aceito": False,
            "valor_consulta": val_tuple,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# C-104a — deve_responder_faq_convenio_aceito: fonte 1 (ctx.known.convenio_aceito)
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_aceito_via_known_true():
    """ctx.known.convenio_aceito=True → resposta imediata positiva."""
    ctx = _ctx(convenio="Bacen", convenio_aceito=True)
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam o meu convênio?")
    assert r is not None
    assert "sim, atendemos" in r.lower() or "sim" in r.lower()
    assert "Bacen" in r


def test_c104_nao_aceito_via_known_false():
    """ctx.known.convenio_aceito=False → resposta imediata negativa + particular."""
    ctx = _ctx(convenio="Unimed", convenio_aceito=False)
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam Unimed?")
    assert r is not None
    assert "não está na nossa rede" in r.lower() or "não" in r.lower()
    assert "particular" in r.lower()
    assert "Unimed" in r


def test_c104_aceito_saude_caixa():
    """Saúde Caixa é convênio aceito — resposta positiva."""
    ctx = _ctx(convenio="Saúde Caixa", convenio_aceito=True)
    r = deve_responder_faq_convenio_aceito(ctx, "funciona com meu plano?")
    assert r is not None
    assert "sim" in r.lower()
    assert "Saúde Caixa" in r


def test_c104_nao_aceito_gdf():
    """GDF não aceito — resposta negativa com oferta particular."""
    ctx = _ctx(convenio="GDF", convenio_aceito=False)
    r = deve_responder_faq_convenio_aceito(ctx, "atendem pelo GDF?")
    assert r is not None
    assert "não" in r.lower()
    assert "611" in r or "particular" in r.lower()


# ─────────────────────────────────────────────────────────────────────────────
# C-104b — fonte 2: ctx.known.convenio sem convenio_aceito (deriva inline)
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_deriva_inline_convenio_aceito():
    """ctx tem convenio mas NÃO tem convenio_aceito — função deriva inline."""
    ctx = _ctx(convenio="Serpro")  # aceito mas sem convenio_aceito no known
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam convênio?")
    assert r is not None
    assert "sim" in r.lower()
    assert "Serpro" in r


def test_c104_deriva_inline_nao_aceito():
    """ctx tem convenio Amil sem convenio_aceito — deriva inline → nega."""
    ctx = _ctx(convenio="Amil")
    r = deve_responder_faq_convenio_aceito(ctx, "aceita Amil?")
    assert r is not None
    assert "não" in r.lower()


# ─────────────────────────────────────────────────────────────────────────────
# C-104c — fonte 3: extrai convênio do user_text
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_extrai_nome_do_user_text_aceito():
    """Convênio Bacen só no user_text — extrai e responde positivo."""
    ctx = {"known": {"nome": "Pedro", "medico": "Karla"}}
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam convênio Bacen?")
    assert r is not None
    assert "sim" in r.lower()


def test_c104_extrai_nome_do_user_text_nao_aceito():
    """Convênio Amil só no user_text — extrai e nega."""
    ctx = {"known": {}}
    r = deve_responder_faq_convenio_aceito(ctx, "aceitam convênio Amil?")
    assert r is not None
    assert "não" in r.lower()


# ─────────────────────────────────────────────────────────────────────────────
# C-104d — convênio desconhecido → None (LLM continua)
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_desconhecido_retorna_none():
    """Convênio não mapeado → None (falha aberta, LLM continua)."""
    ctx = _ctx(convenio="ConvênioXYZ2000")
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam meu plano?")
    assert r is None


def test_c104_sem_convenio_sem_user_text_none():
    """Sem convênio em nenhuma fonte → None."""
    ctx = {"known": {}}
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam convênio?")
    assert r is None


# ─────────────────────────────────────────────────────────────────────────────
# C-104e — user_text não é pergunta de convênio → None
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_user_text_irrelevante_none():
    """user_text sobre agendamento — NÃO interceptado."""
    ctx = _ctx(convenio="Bacen", convenio_aceito=True)
    r = deve_responder_faq_convenio_aceito(ctx, "quero marcar uma consulta")
    assert r is None


def test_c104_user_text_valor_none():
    """user_text sobre valor — NÃO interceptado por faq_convenio_aceito."""
    ctx = _ctx(convenio="Bacen", convenio_aceito=True)
    r = deve_responder_faq_convenio_aceito(ctx, "quanto custa a consulta?")
    assert r is None


# ─────────────────────────────────────────────────────────────────────────────
# C-104f — toggle OFF
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_toggle_off(monkeypatch):
    """BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO=0 → None."""
    monkeypatch.setenv("BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO", "0")
    ctx = _ctx(convenio="Bacen", convenio_aceito=True)
    r = deve_responder_faq_convenio_aceito(ctx, "vocês aceitam o Bacen?")
    assert r is None


# ─────────────────────────────────────────────────────────────────────────────
# C-104g — deve_responder_valor fast path com valor_precomputado (C-103)
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_valor_precomputado_tuple():
    """valor_consulta já derivado → deve_responder_valor usa sem reprocessar."""
    ctx = _ctx_com_valor("Karla", (611.0, 670.0, 335.0))
    r = deve_responder_valor(ctx, "quanto custa?")
    assert r is not None
    assert "611" in r
    assert "670" in r


def test_c104_valor_precomputado_coberto_by_convenio():
    """valor_consulta=None (coberto) + convenio_aceito=True → resposta de cobertura."""
    ctx = {
        "known": {
            "nome": "Renata",
            "medico": "Karla",
            "convenio": "Saúde Caixa",
            "convenio_aceito": True,
            "valor_consulta": None,
        }
    }
    r = deve_responder_valor(ctx, "qual o valor?")
    assert r is not None
    assert "coberta" in r.lower() or "plano" in r.lower() or "saúde caixa" in r.lower()


def test_c104_valor_fabricio_precomputado():
    """Valor Fabrício pré-computado (445 Pix)."""
    ctx = _ctx_com_valor("Fabrício", (445.0, 470.0, 235.0), nome="Marcos")
    r = deve_responder_valor(ctx, "qual o preço da consulta?")
    assert r is not None
    assert "445" in r


def test_c104_valor_sem_precomputado_usa_inference():
    """Sem valor_consulta no known → fallback para inference normal."""
    ctx = {"known": {"nome": "Bia", "medico": "Karla"}}
    r = deve_responder_valor(ctx, "quanto custa?")
    # deve responder (inference normal também responde)
    assert r is not None
    assert "611" in r or "800" in r or "R$" in r.upper().replace("R$ ", "R$")


# ─────────────────────────────────────────────────────────────────────────────
# C-104h — integração: tentar_bypass_deterministico roteia faq_convenio_aceito
# ─────────────────────────────────────────────────────────────────────────────

def test_c104_chain_roteia_convenio_aceito():
    """tentar_bypass_deterministico retorna ('faq_convenio_aceito', texto)."""
    ctx = _ctx(convenio="Bacen", convenio_aceito=True)
    result = tentar_bypass_deterministico(ctx, "vocês aceitam convênio?")
    assert result is not None
    nome_bypass, texto = result
    assert nome_bypass == "faq_convenio_aceito"
    assert "sim" in texto.lower()


def test_c104_chain_nao_aceito_bypass():
    """tentar_bypass_deterministico pega GDF (não aceito) via faq_convenio_aceito."""
    ctx = _ctx(convenio="GDF", convenio_aceito=False)
    result = tentar_bypass_deterministico(ctx, "atendem GDF?")
    assert result is not None
    nome_bypass, texto = result
    # pode ser convenio (classificador_convenio) ou faq_convenio_aceito
    assert nome_bypass in ("faq_convenio_aceito", "convenio")
    assert "não" in texto.lower()
