"""
Pytest Bug C-103 — LLM pergunta convênio quando ctx.known.convenio já está preenchido

Gerado automaticamente por scripts/bug_history_analyzer.py em 11/08/2026.
"""
import pytest
# from voice_agent.blindagens_deterministicas import _viola_bug_c_103
# TODO: mover _viola_bug_c_103 para blindagens_deterministicas.py antes de rodar


# ── Deve bloquear frases proibidas ───────────────────────────────────────────

class TestBloqueiaFrasesProibidas:

    def test_bloqueia_1(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("Atendimento será por convênio", ctx)
        assert r is not None, "Bug C-103: frase não bloqueada: 'Atendimento será por convênio'"

    def test_bloqueia_2(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("atendimento sem convênio", ctx)
        assert r is not None, "Bug C-103: frase não bloqueada: 'atendimento sem convênio'"

    def test_bloqueia_3(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("qual convênio você utiliza", ctx)
        assert r is not None, "Bug C-103: frase não bloqueada: 'qual convênio você utiliza'"

    def test_bloqueia_4(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("convênio ou particular", ctx)
        assert r is not None, "Bug C-103: frase não bloqueada: 'convênio ou particular'"


# ── Não deve bloquear frases normais ─────────────────────────────────────────

class TestNaoBloqueiaFrasesNormais:

    def test_frase_ok_1(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("Tenho 2 horários disponíveis para você", ctx)
        assert r is None, "Frase normal foi bloqueada incorretamente"

    def test_frase_ok_2(self):
        ctx = {"found": True, "known": {}}
        r = _viola_bug_c_103("Qual o melhor horário para você?", ctx)
        assert r is None