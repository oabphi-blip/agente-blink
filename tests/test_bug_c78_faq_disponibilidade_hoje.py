"""Pytest — Bug C-78 (01/08/2026): FAQ disponibilidade hoje.

Causa raiz lead 23456132 (João, 8-REALIZADO):
  - Paciente perguntou "A Dra Karla está atendendo hj?" num sábado.
  - Bot foi ao Medware → vazio (sábado = sem agenda) → ctx.agenda=[] →
    C-30 não disparou (has_agenda=False) → C-30A disse "Medware instável" (ERRADO)
    → LLM entrou em loop stall 3x "reconferir os horários exatos".

Fix: `deve_responder_faq_disponibilidade_hoje()` em `blindagens_deterministicas.py`
intercept ANTES de chegar ao Medware. Resposta baseada em dia-da-semana
e escala dos médicos. Zero LLM, zero Medware.

Cobre:
  - Sábado/domingo → não atende (Karla e Fabrício)
  - Dia útil sem atendimento (ex. ter-qui para Karla Asa Norte) → próxima data
  - Dia útil com atendimento → confirma + pede dados
  - Médico desconhecido → pass-through (None)
  - Toggle OFF → None
  - Integração com chain tentar_bypass_deterministico
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

# ── importar módulo ────────────────────────────────────────────────────────────
from voice_agent.blindagens_deterministicas import (
    _FAQ_DISP_HOJE,
    _KARLA_ASA_NORTE_DIAS,
    _KARLA_AGUAS_CLARAS_DIAS,
    _FABRICIO_DIAS,
    _NOMES_DIAS_PT,
    _proxima_data_no_plano,
    deve_responder_faq_disponibilidade_hoje,
    tentar_bypass_deterministico,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ctx_karla_asa_norte():
    return {"known": {"medico": "Dra. Karla Delalíbera", "unidade": "Asa Norte"}}

def _ctx_karla_aguas_claras():
    return {"known": {"medico": "Dra. Karla Delalíbera", "unidade": "Águas Claras"}}

def _ctx_karla_sem_unidade():
    return {"known": {"medico": "Dra. Karla Delalíbera"}}

def _ctx_fabricio():
    return {"known": {"medico": "Dr. Fabrício Freitas", "unidade": "Asa Norte"}}

def _ctx_sem_medico():
    return {"known": {}}

def _mock_hoje(weekday: int):
    """Retorna um date fictício com o weekday desejado."""
    # Encontra data real com o weekday certo
    base = date(2026, 8, 1)   # sábado (weekday=5)
    delta = (weekday - base.weekday()) % 7
    return base + timedelta(days=delta)


# ══════════════════════════════════════════════════════════════════════════════
# 1. REGEX _FAQ_DISP_HOJE — cobertura de padrões
# ══════════════════════════════════════════════════════════════════════════════

FRASES_QUE_DEVEM_CASAR = [
    "A Dra Karla está atendendo hj?",
    "está atendendo hoje?",
    "tem horário hoje?",
    "tem vaga hoje",
    "atende hoje?",
    "hoje tem consulta?",
    "hoje está atendendo?",
    "atende sábado?",
    "atende domingo?",
    "tem horário sábado?",
    "tem vaga domingo",
    "sábado tem atendimento?",
    "tem horário amanhã?",
]

FRASES_QUE_NAO_DEVEM_CASAR = [
    "quero agendar para a próxima semana",
    "qual o valor da consulta",
    "tem oftalmologista pediátrico?",
    "meu filho tem estrabismo",
    "oi boa tarde",
    "pode me confirmar o horário?",
]

@pytest.mark.parametrize("frase", FRASES_QUE_DEVEM_CASAR)
def test_regex_casa(frase: str):
    assert _FAQ_DISP_HOJE.search(frase), f"Regex deveria casar: {frase!r}"


@pytest.mark.parametrize("frase", FRASES_QUE_NAO_DEVEM_CASAR)
def test_regex_nao_casa(frase: str):
    assert not _FAQ_DISP_HOJE.search(frase), f"Regex NÃO deveria casar: {frase!r}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. _proxima_data_no_plano — cálculo correto
# ══════════════════════════════════════════════════════════════════════════════

def test_proxima_data_karla_asa_norte_de_sabado():
    sabado = _mock_hoje(5)  # sábado
    prox, nome = _proxima_data_no_plano(sabado, _KARLA_ASA_NORTE_DIAS)
    assert prox.weekday() == 0, "Próxima Karla Asa Norte após sábado deve ser segunda"
    assert "segunda" in nome

def test_proxima_data_karla_aguas_claras_de_sabado():
    sabado = _mock_hoje(5)
    prox, nome = _proxima_data_no_plano(sabado, _KARLA_AGUAS_CLARAS_DIAS)
    assert prox.weekday() == 1, "Próxima Karla Águas Claras após sábado deve ser terça"
    assert "terça" in nome

def test_proxima_data_fabricio_de_quarta():
    quarta = _mock_hoje(2)
    prox, nome = _proxima_data_no_plano(quarta, _FABRICIO_DIAS)
    assert prox.weekday() == 3, "Próximo Fabrício após quarta deve ser quinta"
    assert "quinta" in nome


# ══════════════════════════════════════════════════════════════════════════════
# 3. deve_responder_faq_disponibilidade_hoje — cenários principais
# ══════════════════════════════════════════════════════════════════════════════

def test_sabado_karla_asa_norte_nao_atende():
    """Bug C-78 original: sábado → não atende → mostra próxima (segunda)."""
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_asa_norte(), "A Dra Karla está atendendo hj?"
        )
    assert resp is not None
    assert "sábado" in resp.lower()
    assert "não tem atendimento" in resp.lower() or "não atende" in resp.lower() or "não tem" in resp.lower()
    assert "segunda" in resp.lower() or "segunda-feira" in resp.lower()


def test_domingo_karla_aguas_claras_nao_atende():
    domingo = _mock_hoje(6)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = domingo
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_aguas_claras(), "tem horário hoje?"
        )
    assert resp is not None
    assert "domingo" in resp.lower()


def test_segunda_karla_asa_norte_atende():
    """Segunda = dia de Karla Asa Norte → confirma atendimento."""
    segunda = _mock_hoje(0)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = segunda
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_asa_norte(), "atende hoje?"
        )
    assert resp is not None
    assert "sim" in resp.lower()
    assert "segunda" in resp.lower()
    assert "asa norte" in resp.lower()


def test_terca_karla_asa_norte_nao_atende_mostra_quarta():
    """Terça = Karla Asa Norte NÃO atende (é dia de Águas Claras)."""
    terca = _mock_hoje(1)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = terca
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_asa_norte(), "tem horário hoje?"
        )
    assert resp is not None
    assert "quarta" in resp.lower(), f"Esperava 'quarta' na resposta: {resp}"


def test_terca_karla_aguas_claras_atende():
    """Terça = dia de Karla Águas Claras → confirma."""
    terca = _mock_hoje(1)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = terca
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_aguas_claras(), "está atendendo hj?"
        )
    assert resp is not None
    assert "sim" in resp.lower()
    assert "águas claras" in resp.lower() or "aguas claras" in resp.lower()


def test_karla_sem_unidade_sabado_mostra_ambas():
    """Sem unidade definida + sábado → mostra Asa Norte E Águas Claras."""
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_karla_sem_unidade(), "atende hoje?"
        )
    assert resp is not None
    assert "asa norte" in resp.lower()
    assert "águas claras" in resp.lower() or "aguas claras" in resp.lower()


def test_fabricio_sabado_nao_atende():
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_fabricio(), "tem horário hoje?"
        )
    assert resp is not None
    assert "fabrício" in resp.lower() or "fabricio" in resp.lower()
    assert "terça" in resp.lower()


def test_medico_desconhecido_retorna_none():
    """Sem médico definido → pass-through (None)."""
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        resp = deve_responder_faq_disponibilidade_hoje(
            _ctx_sem_medico(), "atende hoje?"
        )
    assert resp is None


def test_pergunta_generica_nao_dispara():
    """Perguntas genéricas não devem disparar a FAQ."""
    resp = deve_responder_faq_disponibilidade_hoje(
        _ctx_karla_asa_norte(), "quando a clínica fica fechada?"
    )
    assert resp is None


def test_toggle_off_retorna_none():
    """Toggle BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO=0 → None."""
    sabado = _mock_hoje(5)
    with patch.dict(os.environ, {"BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO": "0"}):
        with patch("voice_agent.blindagens_deterministicas.datetime") as m:
            m.now.return_value.date.return_value = sabado
            resp = deve_responder_faq_disponibilidade_hoje(
                _ctx_karla_asa_norte(), "atende hoje?"
            )
    assert resp is None


def test_texto_vazio_retorna_none():
    resp = deve_responder_faq_disponibilidade_hoje(_ctx_karla_asa_norte(), "")
    assert resp is None

def test_ctx_none_retorna_none_ou_resposta_sem_unidade():
    """ctx=None não deve lançar exceção."""
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        # Sem ctx → médico desconhecido → None (fail-open)
        resp = deve_responder_faq_disponibilidade_hoje(None, "atende hoje?")
    assert resp is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. Integração com chain tentar_bypass_deterministico
# ══════════════════════════════════════════════════════════════════════════════

def test_chain_retorna_faq_disponibilidade_hoje():
    """tentar_bypass_deterministico deve chamar C-78 antes de faq_especialidade."""
    sabado = _mock_hoje(5)
    with patch("voice_agent.blindagens_deterministicas.datetime") as m:
        m.now.return_value.date.return_value = sabado
        resultado = tentar_bypass_deterministico(
            _ctx_karla_asa_norte(), "A Dra Karla está atendendo hj?"
        )
    assert resultado is not None
    nome_bypass, texto = resultado
    assert nome_bypass == "faq_disponibilidade_hoje"
    assert "sábado" in texto.lower()


def test_chain_nao_interfere_em_outras_perguntas():
    """Perguntas de especialidade ainda passam pelo chain normalmente."""
    resultado = tentar_bypass_deterministico(
        _ctx_karla_asa_norte(), "tem oftalmologista pediátrico?"
    )
    # Deve retornar faq_especialidade, não faq_disponibilidade_hoje
    if resultado is not None:
        nome_bypass, _ = resultado
        assert nome_bypass != "faq_disponibilidade_hoje"


# ══════════════════════════════════════════════════════════════════════════════
# 5. Stall regex em responder.py — variante "corretas" (Bug C-78b)
# ══════════════════════════════════════════════════════════════════════════════

def test_stall_regex_pega_corretAs():
    """Regex no _FAKE_AGENDA_LOOKUP deve pegar 'opções corretas'."""
    from voice_agent.responder import _FAKE_AGENDA_LOOKUP
    frase = "deixa eu reconferir os horários exatos com a agenda do Medware pra te passar as opções corretas"
    assert any(p.search(frase) for p in _FAKE_AGENDA_LOOKUP), (
        "Nenhum padrão em _FAKE_AGENDA_LOOKUP casou com a frase stall de C-78"
    )

def test_stall_regex_pega_reconferir_medware():
    from voice_agent.responder import _FAKE_AGENDA_LOOKUP
    frase = "reconferir os horários com a agenda do Medware"
    assert any(p.search(frase) for p in _FAKE_AGENDA_LOOKUP)

def test_stall_regex_nao_falso_positivo_confirmacao():
    """Confirmação legítima não deve ser pega pelo stall filter."""
    from voice_agent.responder import _FAKE_AGENDA_LOOKUP
    frase = "Sua consulta está confirmada para sexta-feira (14/08) às 09:30 na Asa Norte."
    assert not any(p.search(frase) for p in _FAKE_AGENDA_LOOKUP)
