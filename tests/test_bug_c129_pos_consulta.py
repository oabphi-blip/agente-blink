"""Bug C-129 (12/08/2026) — Pós-consulta: escalar para atendimento humano.

Caso real: lead 14230149 Luciana consultou em 10/08/2026. Perguntou
"recibo de pagamento" → Lia respondeu com tabela de preços + "Gostaria de agendar?".

Fix: bypass deve_escalar_pos_consulta() detecta pedidos de documento/administrativo
(Camada A) e ctx.a_fazer_pos_consulta=True + msg geral (Camada B) → retorna
mensagem de escalada → pipeline move lead para 1-ATENDIMENTO HUMANO.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from voice_agent.pos_consulta import (
    deve_escalar_pos_consulta,
    _RE_PEDIDO_DOCUMENTO_C129,
    _RE_INTENT_NOVO_AGENDAMENTO_C129,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _ctx(a_fazer_pos_consulta: bool = False, lead_id: int = 14230149) -> dict:
    known: dict = {"lead_id": lead_id}
    if a_fazer_pos_consulta:
        known["a_fazer_pos_consulta"] = True
    return {"known": known}


# ── Camada A: pedido de documento ─────────────────────────────────────────────

class TestCamadaA:
    """Deve escalar independente de ctx quando paciente pede documento/adm."""

    def test_recibo(self):
        r = deve_escalar_pos_consulta(None, "preciso do recibo da consulta")
        assert r is not None
        assert "equipe" in r.lower() or "atendente" in r.lower() or "Blink" in r

    def test_nota_fiscal(self):
        r = deve_escalar_pos_consulta(None, "podem me enviar a nota fiscal?")
        assert r is not None

    def test_reembolso(self):
        r = deve_escalar_pos_consulta(None, "quero solicitar reembolso pelo plano")
        assert r is not None

    def test_comprovante_pagamento(self):
        r = deve_escalar_pos_consulta(None, "me mandam o comprovante de pagamento")
        assert r is not None

    def test_atestado(self):
        r = deve_escalar_pos_consulta(None, "Dra. Karla pode me dar um atestado?")
        assert r is not None

    def test_atestado_medico(self):
        r = deve_escalar_pos_consulta(None, "preciso de atestado médico para a escola")
        assert r is not None

    def test_laudo(self):
        r = deve_escalar_pos_consulta(None, "quando sai o laudo?")
        assert r is not None

    def test_laudo_medico(self):
        r = deve_escalar_pos_consulta(None, "quero pegar o laudo médico")
        assert r is not None

    def test_resultado_exame(self):
        r = deve_escalar_pos_consulta(None, "resultado do exame ficou pronto?")
        assert r is not None

    def test_receita_medica(self):
        r = deve_escalar_pos_consulta(None, "a doutora passou uma receita médica, como recebo?")
        assert r is not None

    def test_prontuario(self):
        r = deve_escalar_pos_consulta(None, "quero meu prontuário")
        assert r is not None

    def test_segunda_via(self):
        r = deve_escalar_pos_consulta(None, "podem me enviar segunda via do recibo?")
        assert r is not None

    def test_declaracao_comparecimento(self):
        r = deve_escalar_pos_consulta(None, "preciso de declaração de comparecimento")
        assert r is not None

    def test_case_real_luciana(self):
        """Caso real: lead 14230149 Luciana — 'recibo de pagamento'."""
        r = deve_escalar_pos_consulta(None, "recibo de pagamento")
        assert r is not None

    def test_ctx_none_nao_importa_camada_a(self):
        """Camada A escala mesmo sem ctx (ctx=None)."""
        r = deve_escalar_pos_consulta(None, "quero o reembolso do plano")
        assert r is not None


# ── Camada A: falso positivo — NÃO deve escalar ───────────────────────────────

class TestCamadaANaoEscala:
    """Mensagens que NÃO são pedidos de documento."""

    def test_quero_agendar(self):
        r = deve_escalar_pos_consulta(None, "quero agendar uma consulta")
        assert r is None

    def test_quanto_custa(self):
        r = deve_escalar_pos_consulta(None, "quanto custa a consulta?")
        assert r is None

    def test_oi(self):
        r = deve_escalar_pos_consulta(None, "oi, boa tarde")
        assert r is None

    def test_horario(self):
        r = deve_escalar_pos_consulta(None, "qual o horário de atendimento?")
        assert r is None

    def test_convenio(self):
        r = deve_escalar_pos_consulta(None, "vocês aceitam Bacen?")
        assert r is None


# ── Camada B: a_fazer_pos_consulta=True ───────────────────────────────────────

class TestCamadaB:
    """Com a_fazer_pos_consulta=True, escala msg geral mas não novo agendamento."""

    def test_msg_generica_escala(self):
        ctx = _ctx(a_fazer_pos_consulta=True)
        r = deve_escalar_pos_consulta(ctx, "oi, tudo bem?")
        assert r is not None

    def test_pergunta_generica_escala(self):
        ctx = _ctx(a_fazer_pos_consulta=True)
        r = deve_escalar_pos_consulta(ctx, "como ficou a consulta da Luciana?")
        assert r is not None

    def test_novo_agendamento_nao_escala(self):
        """Quer marcar nova consulta — não escalar, deixar fluxo de agendamento."""
        ctx = _ctx(a_fazer_pos_consulta=True)
        r = deve_escalar_pos_consulta(ctx, "quero agendar uma nova consulta")
        assert r is None

    def test_marcar_retorno_nao_escala(self):
        ctx = _ctx(a_fazer_pos_consulta=True)
        r = deve_escalar_pos_consulta(ctx, "gostaria de marcar um retorno com a Dra. Karla")
        assert r is None

    def test_proxima_consulta_nao_escala(self):
        ctx = _ctx(a_fazer_pos_consulta=True)
        r = deve_escalar_pos_consulta(ctx, "quando posso fazer a próxima consulta?")
        assert r is None

    def test_sem_a_fazer_pos_consulta_msg_generica_nao_escala(self):
        """Sem flag, msg genérica não escala pela Camada B."""
        ctx = _ctx(a_fazer_pos_consulta=False)
        r = deve_escalar_pos_consulta(ctx, "oi, tudo bem?")
        assert r is None

    def test_ctx_none_sem_documento_nao_escala(self):
        r = deve_escalar_pos_consulta(None, "olá")
        assert r is None


# ── Toggle ─────────────────────────────────────────────────────────────────────

class TestToggle:
    def test_toggle_off_suprime_camada_a(self):
        with patch.dict("os.environ", {"POS_CONSULTA_ATIVADO": "0"}):
            r = deve_escalar_pos_consulta(None, "preciso do recibo")
            assert r is None

    def test_toggle_off_suprime_camada_b(self):
        with patch.dict("os.environ", {"POS_CONSULTA_ATIVADO": "0"}):
            ctx = _ctx(a_fazer_pos_consulta=True)
            r = deve_escalar_pos_consulta(ctx, "oi")
            assert r is None

    def test_toggle_on_default(self):
        """Sem env, toggle é ON."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("POS_CONSULTA_ATIVADO", None)
            r = deve_escalar_pos_consulta(None, "preciso do reembolso")
            assert r is not None


# ── Mensagem canônica ──────────────────────────────────────────────────────────

class TestMensagemCanonica:
    def test_mensagem_menciona_equipe(self):
        r = deve_escalar_pos_consulta(None, "quero o recibo")
        assert r is not None
        lower = r.lower()
        assert "equipe" in lower or "atendente" in lower or "blink" in lower

    def test_mensagem_nao_menciona_particular(self):
        """Mensagem de escalada não deve usar termo 'particular'."""
        r = deve_escalar_pos_consulta(None, "quero o reembolso")
        assert r is not None
        assert "particular" not in r.lower()

    def test_mensagem_nao_menciona_sdp(self):
        """Mensagem não deve mencionar 'SDP'."""
        r = deve_escalar_pos_consulta(None, "quero laudo médico")
        assert r is not None
        assert "sdp" not in r.lower()

    def test_fail_open_user_text_vazio(self):
        r = deve_escalar_pos_consulta(None, "")
        assert r is None

    def test_fail_open_user_text_none(self):
        r = deve_escalar_pos_consulta(None, None)  # type: ignore
        assert r is None


# ── Regex direta ───────────────────────────────────────────────────────────────

class TestRegex:
    def test_re_documento_recibo(self):
        assert _RE_PEDIDO_DOCUMENTO_C129.search("preciso do recibo")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("Recibo")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("reembolso pelo plano")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("nota fiscal")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("resultado do exame")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("LAUDO MÉDICO")
        assert _RE_PEDIDO_DOCUMENTO_C129.search("atestado médico")

    def test_re_documento_nao_casa_agendamento(self):
        assert not _RE_PEDIDO_DOCUMENTO_C129.search("quero agendar")
        assert not _RE_PEDIDO_DOCUMENTO_C129.search("quanto custa?")
        assert not _RE_PEDIDO_DOCUMENTO_C129.search("oi")

    def test_re_agendamento_casos(self):
        assert _RE_INTENT_NOVO_AGENDAMENTO_C129.search("quero agendar uma consulta")
        assert _RE_INTENT_NOVO_AGENDAMENTO_C129.search("marcar retorno com a Dra.")
        assert _RE_INTENT_NOVO_AGENDAMENTO_C129.search("nova consulta")
        assert _RE_INTENT_NOVO_AGENDAMENTO_C129.search("próxima consulta")

    def test_re_agendamento_nao_casa_doc(self):
        assert not _RE_INTENT_NOVO_AGENDAMENTO_C129.search("recibo")
        assert not _RE_INTENT_NOVO_AGENDAMENTO_C129.search("reembolso")
        assert not _RE_INTENT_NOVO_AGENDAMENTO_C129.search("oi")
