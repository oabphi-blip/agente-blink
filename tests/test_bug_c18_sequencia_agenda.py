"""
Bug C-18 (Fábio 10/06/2026) — Sequência obrigatória na oferta de agenda.

Lead 22779280 (Melissa de Almeida Ramos): Lia perguntou motivo+médico+unidade
antes de ofertar slot. Carga decisória demais. Paciente já tinha sugerido
"semana de 29/06". Lia DEVIA ter buscado Medware Karla Asa Norte naquela
semana e oferecido 2 slots imediatos.

Regra Fábio:
1. PASSO 1: oferta 2 slots concretos imediatamente
2. PASSO 2: se paciente RECUSAR os 2 → AÍ SIM pergunta dia+turno+período
   numa MENSAGEM SÓ (não 3 perguntas em 3 turnos)
3. Objetivo: agilidade. Não passar carga decisória pro paciente.
"""

import re

from voice_agent.responder import _agenda_block


# -----------------------------------------------------------------------------
# Cenário 1 — prompt menciona a sequência obrigatória
# -----------------------------------------------------------------------------

def test_prompt_menciona_sequencia_bug_c18():
    """O bloco AGENDA deve descrever a sequência PASSO 1 → PASSO 2 → PASSO 3."""
    ctx = {
        "agenda": [
            {"data": "2026-06-29", "hora_inicio": "09:00", "hora_fim": "09:30"},
            {"data": "2026-06-29", "hora_inicio": "14:00", "hora_fim": "14:30"},
        ],
        "known": {"medico": "Dra. Karla Delalíbera", "unidade": "Asa Norte"},
    }
    bloco = _agenda_block(ctx)
    assert "SEQUÊNCIA OBRIGATÓRIA" in bloco
    assert "Bug C-18" in bloco
    assert "PASSO 1" in bloco
    assert "PASSO 2" in bloco
    assert "PASSO 3" in bloco


def test_prompt_proibe_perguntar_antes_de_ofertar():
    """O prompt deve manter a proibição de perguntar turno/período antes de oferecer."""
    ctx = {
        "agenda": [{"data": "2026-06-29", "hora_inicio": "09:00", "hora_fim": "09:30"}],
        "known": {"medico": "Dra. Karla Delalíbera", "unidade": "Asa Norte"},
    }
    bloco = _agenda_block(ctx)
    # A proibição original continua válida
    assert "PROIBIDO perguntar 'qual turno'" in bloco
    assert "antes de oferecer" in bloco.lower()


# -----------------------------------------------------------------------------
# Cenário 2 — pergunta vinda DEPOIS de recusa deve ser UMA SÓ mensagem
# -----------------------------------------------------------------------------

def test_pergunta_pos_recusa_eh_uma_mensagem_so():
    """Na fase 2, a pergunta sobre dia+turno+período tem que ser CONJUNTA."""
    ctx = {
        "agenda": [{"data": "2026-06-29", "hora_inicio": "09:00", "hora_fim": "09:30"}],
        "known": {"medico": "Dra. Karla", "unidade": "Asa Norte"},
    }
    bloco = _agenda_block(ctx)
    # A pergunta de fallback deve estar formatada como UMA sentença que cobre
    # os 3 critérios juntos, não 3 perguntas separadas.
    assert "qual dia da semana" in bloco.lower()
    assert "qual turno" in bloco.lower()
    assert "qual período do turno" in bloco.lower()
    assert "manhã/tarde" in bloco
    assert "início, meio ou fim" in bloco


def test_pergunta_pos_recusa_no_contexto_certo():
    """A pergunta de fallback deve mencionar contexto (MÉDICO + UNIDADE)."""
    ctx = {
        "agenda": [{"data": "2026-06-29", "hora_inicio": "09:00", "hora_fim": "09:30"}],
        "known": {"medico": "Dra. Karla", "unidade": "Asa Norte"},
    }
    bloco = _agenda_block(ctx)
    # O prompt instrui a Lia a perguntar JÁ CONTEXTUALIZADO com médico+unidade
    assert "{{MÉDICO}}" in bloco
    assert "{{UNIDADE}}" in bloco


# -----------------------------------------------------------------------------
# Cenário 3 — objetivo "agilidade" sem indo e vindo
# -----------------------------------------------------------------------------

def test_objetivo_explicito_agilidade_sem_indo_e_vindo():
    """O prompt deve explicar POR QUE a sequência é assim (anti-prolixidade)."""
    ctx = {
        "agenda": [{"data": "2026-06-29", "hora_inicio": "09:00", "hora_fim": "09:30"}],
        "known": {"medico": "Dra. Karla", "unidade": "Asa Norte"},
    }
    bloco = _agenda_block(ctx)
    assert "AGILIDADE" in bloco
    assert "indo e vindo" in bloco.lower()
    # 3 decisões em 3 turnos = anti-padrão
    assert "3 decisões" in bloco or "carga" in bloco.lower()
