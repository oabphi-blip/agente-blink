"""Pytest do filtro _viola_pergunta_redundante_convenio.

Origem: lead 24063769 Adriana (02/06/2026). Convênio já no ctx
("Não se aplica") mas Lia perguntou 4 vezes seguidas: "com ou sem
convênio?", "é por convênio?", "será sem convênio?". Triagem
redundante que enrola paciente.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# Detector
# ----------------------------------------------------------------------

class TestDetector:

    def test_lia_pergunta_com_ou_sem_quando_ctx_tem_DISPARA(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {"convenio": "Não se aplica"}}
        resp = "Será por convênio ou sem convênio?"
        assert _viola_pergunta_redundante_convenio(resp, ctx) is True

    def test_caso_adriana_exato(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {"convenio": "Não se aplica"}}
        # Mensagem real da Lia no lead 24063769
        resp = (
            "Agora me confirma: **será por convênio ou sem convênio?**"
        )
        assert _viola_pergunta_redundante_convenio(resp, ctx) is True

    def test_caso_adriana_segunda_repergunta(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {"convenio": "Não se aplica"}}
        resp = (
            "Para o exame completo sem convênio, preciso saber qual é "
            "o motivo da consulta para te passar o valor exato."
        )
        # "sem convênio" como afirmação não é pergunta — não dispara
        # MAS a regex de pergunta normal pega "sem convênio?" com ?
        # Aqui é afirmação, vamos só validar que NÃO dispara erradamente
        assert _viola_pergunta_redundante_convenio(resp, ctx) is False

    def test_ctx_convenio_real_lia_repergunta_DISPARA(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {"convenio": "STF-Med"}}
        resp = "Você vai usar convênio?"
        assert _viola_pergunta_redundante_convenio(resp, ctx) is True

    def test_ctx_sem_convenio_pergunta_NORMAL_NAO_dispara(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {}}  # ctx vazio — pode perguntar
        resp = "Será por convênio ou sem convênio?"
        assert _viola_pergunta_redundante_convenio(resp, ctx) is False

    def test_ctx_None_NAO_dispara(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        resp = "Será por convênio ou sem convênio?"
        assert _viola_pergunta_redundante_convenio(resp, None) is False

    def test_lia_pergunta_outra_coisa_NAO_dispara(self):
        from voice_agent.responder import _viola_pergunta_redundante_convenio
        ctx = {"known": {"convenio": "Não se aplica"}}
        resp = "Qual seu motivo da consulta?"
        assert _viola_pergunta_redundante_convenio(resp, ctx) is False


# ----------------------------------------------------------------------
# Fallback gerador
# ----------------------------------------------------------------------

class TestFallbackGerador:

    def test_karla_particular_oferece_R611(self):
        from voice_agent.responder import _gerar_resposta_valor_sem_repergunta
        ctx = {"known": {
            "medico": "Dra. Karla Delalibera",
            "convenio": "Não se aplica",
            "especialidade": "Oftalmologia Geral",
        }}
        out = _gerar_resposta_valor_sem_repergunta(ctx)
        assert "611" in out
        assert "Karla" in out
        # Não pergunta convênio
        assert "convênio ou sem" not in out.lower()

    def test_fabricio_catarata_oferece_R297(self):
        from voice_agent.responder import _gerar_resposta_valor_sem_repergunta
        ctx = {"known": {
            "medico": "Dr. Fabrício Freitas",
            "especialidade": "Catarata",
            "convenio": "Não se aplica",
        }}
        out = _gerar_resposta_valor_sem_repergunta(ctx)
        assert "297" in out
        assert "Fabr" in out

    def test_sdp_oferece_R800(self):
        from voice_agent.responder import _gerar_resposta_valor_sem_repergunta
        ctx = {"known": {
            "especialidade": "SDP",
            "convenio": "Não se aplica",
        }}
        out = _gerar_resposta_valor_sem_repergunta(ctx)
        assert "800" in out
        assert "SDP" in out or "prend" in out.lower()

    def test_sem_medico_no_ctx_responde_tabela_completa(self):
        from voice_agent.responder import _gerar_resposta_valor_sem_repergunta
        ctx = {"known": {}}
        out = _gerar_resposta_valor_sem_repergunta(ctx)
        # Tem os 3 valores
        assert "611" in out
        assert "297" in out
        assert "800" in out

    def test_convenio_aceito_diz_coberto(self):
        from voice_agent.responder import _gerar_resposta_valor_sem_repergunta
        ctx = {"known": {
            "medico": "Dra. Karla",
            "convenio": "STF-Med",
        }}
        out = _gerar_resposta_valor_sem_repergunta(ctx)
        assert "coberta" in out.lower() or "convênio" in out.lower()
        assert "STF" in out


# ----------------------------------------------------------------------
# Integração _scrub_prohibited
# ----------------------------------------------------------------------

class TestIntegracaoScrub:

    def test_scrub_substitui_pergunta_redundante_Adriana(self):
        from voice_agent.responder import _scrub_prohibited
        ctx = {"known": {
            "convenio": "Não se aplica",
            "medico": "Dra. Karla Delalibera",
            "especialidade": "Oftalmologia Geral",
        }}
        buggy = (
            "Para te passar o valor exato do exame completo, preciso "
            "de algumas informações:\n"
            "1️⃣ Quem vai ser atendido?\n"
            "2️⃣ Será por convênio ou sem convênio?"
        )
        out = _scrub_prohibited(buggy, ctx=ctx)
        # Resposta nova vai ter R$ 611 (Karla particular) e SEM
        # repergunta "convênio ou sem"
        assert "611" in out
        assert "convênio ou sem" not in out.lower()
