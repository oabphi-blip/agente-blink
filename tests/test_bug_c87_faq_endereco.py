"""
Bug C-87 (05/08/2026) — FAQ endereço determinístico.

Cobre:
- Detecção dos padrões principais de "onde fica"
- Unidade Asa Norte → endereço certo
- Unidade Águas Claras → endereço certo
- Sem unidade → mostra as duas + pergunta qual é mais perto
- Toggle OFF → None
- Fail-open (ctx None, user_text None)
- Nome do paciente na saudação
- Integração no chain tentar_bypass_deterministico
"""
import os
import pytest
from unittest.mock import patch

from voice_agent.blindagens_deterministicas import (
    deve_responder_faq_endereco,
    tentar_bypass_deterministico,
)

# ── helpers ──────────────────────────────────────────────────────────────────

def ctx_com_unidade(unidade: str, nome: str = "Juliana") -> dict:
    return {"known": {"unidade": unidade, "nome_paciente": nome}}


def ctx_sem_unidade(nome: str = "") -> dict:
    return {"known": {"nome_paciente": nome}}


# ── detecção de padrão ───────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "onde fica a clínica?",
    "Onde fica?",
    "qual o endereço?",
    "qual é o endereço",
    "fica no felicittá?",
    "fica no felicitta?",
    "felicittá shopping",
    "qual a localização?",
    "como chegar?",
    "como chego lá",
    "tem estacionamento?",
    "qual é a unidade?",
    "onde fica o consultório?",
    "endereço da clínica",
    "shin qi",
    "lago norte",
])
def test_detecta_pergunta_endereco(texto):
    ctx = ctx_sem_unidade()
    result = deve_responder_faq_endereco(ctx, texto)
    assert result is not None, f"Deveria detectar: {texto!r}"


@pytest.mark.parametrize("texto", [
    "quero agendar",
    "qual o valor?",
    "qual médico atende",
    "boa tarde",
    "",
    "meu filho tem 5 anos",
])
def test_nao_detecta_fora_do_escopo(texto):
    ctx = ctx_sem_unidade()
    result = deve_responder_faq_endereco(ctx, texto)
    assert result is None, f"Não deveria detectar: {texto!r}"


# ── resposta por unidade ─────────────────────────────────────────────────────

def test_asa_norte_retorna_endereco_asa_norte():
    ctx = ctx_com_unidade("Asa Norte")
    result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert result is not None
    assert "SHIN QI 5" in result
    assert "Lago Norte" in result
    assert "maps.app.goo.gl/jPfjSsXA1bHhsyw56" in result
    # não deve conter endereço de Águas Claras
    assert "Felicittá" not in result


def test_aguas_claras_retorna_endereco_aguas_claras():
    ctx = ctx_com_unidade("Águas Claras")
    result = deve_responder_faq_endereco(ctx, "qual o endereço?")
    assert result is not None
    assert "Felicittá" in result
    assert "maps.app.goo.gl/FRbkUtg4U4xG55q18" in result
    # não deve conter endereço de Asa Norte
    assert "SHIN QI" not in result


def test_aguas_claras_variante_sem_acento():
    ctx = ctx_com_unidade("Aguas Claras")
    result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert result is not None
    assert "Felicittá" in result


def test_sem_unidade_mostra_ambas():
    ctx = ctx_sem_unidade()
    result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert result is not None
    assert "Asa Norte" in result
    assert "Águas Claras" in result
    assert "maps.app.goo.gl/jPfjSsXA1bHhsyw56" in result
    assert "maps.app.goo.gl/FRbkUtg4U4xG55q18" in result
    assert "mais perto" in result.lower()


def test_ctx_none_mostra_ambas():
    result = deve_responder_faq_endereco(None, "onde fica?")
    assert result is not None
    assert "Asa Norte" in result
    assert "Águas Claras" in result


# ── saudação com nome ─────────────────────────────────────────────────────────

def test_nome_paciente_na_saudacao_asa_norte():
    ctx = ctx_com_unidade("Asa Norte", nome="Carlos")
    result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert result.startswith("Carlos, ")


def test_nome_paciente_na_saudacao_ambas():
    ctx = ctx_sem_unidade(nome="Ana")
    result = deve_responder_faq_endereco(ctx, "endereço?")
    assert "Ana" in result


def test_sem_nome_sem_virgula():
    ctx = ctx_sem_unidade(nome="")
    result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert not result.startswith(", ")


# ── toggle OFF ───────────────────────────────────────────────────────────────

def test_toggle_off_retorna_none():
    ctx = ctx_com_unidade("Asa Norte")
    with patch.dict(os.environ, {"BLINDAGEM_FAQ_ENDERECO_ATIVADO": "0"}):
        result = deve_responder_faq_endereco(ctx, "onde fica?")
    assert result is None


def test_toggle_false_retorna_none():
    ctx = ctx_com_unidade("Águas Claras")
    with patch.dict(os.environ, {"BLINDAGEM_FAQ_ENDERECO_ATIVADO": "false"}):
        result = deve_responder_faq_endereco(ctx, "endereço?")
    assert result is None


# ── fail-open ────────────────────────────────────────────────────────────────

def test_user_text_none_retorna_none():
    ctx = ctx_com_unidade("Asa Norte")
    result = deve_responder_faq_endereco(ctx, None)  # type: ignore
    assert result is None


# ── integração no chain ───────────────────────────────────────────────────────

def test_chain_retorna_faq_endereco_asa_norte():
    ctx = ctx_com_unidade("Asa Norte")
    resultado = tentar_bypass_deterministico(ctx, "onde fica?")
    assert resultado is not None
    nome_bypass, texto = resultado
    assert nome_bypass == "faq_endereco"
    assert "SHIN QI 5" in texto


def test_chain_retorna_faq_endereco_aguas_claras():
    ctx = ctx_com_unidade("Águas Claras")
    resultado = tentar_bypass_deterministico(ctx, "qual o endereço?")
    assert resultado is not None
    nome_bypass, texto = resultado
    assert nome_bypass == "faq_endereco"
    assert "Felicittá" in texto


def test_chain_retorna_faq_endereco_sem_unidade():
    ctx = ctx_sem_unidade()
    resultado = tentar_bypass_deterministico(ctx, "fica no felicittá?")
    assert resultado is not None
    nome_bypass, texto = resultado
    assert nome_bypass == "faq_endereco"
    assert "Asa Norte" in texto
    assert "Águas Claras" in texto


def test_chain_nao_retorna_faq_endereco_pra_pergunta_agendar():
    ctx = ctx_sem_unidade()
    resultado = tentar_bypass_deterministico(ctx, "quero agendar consulta")
    # pode retornar outro bypass ou None, mas nunca "faq_endereco"
    if resultado is not None:
        assert resultado[0] != "faq_endereco"
