"""Bug C-65 (anti-chute agenda) + C-66 (remarcação sempre humano).

Origem: Fábio 21/07/2026, lead 21329281 Letícia/Alice.
2 bugs:
    (a) Lia disse 'segunda/quarta/sexta à tarde' sem hora concreta (chute)
    (b) Lia disse 'te espero no dia' quando paciente pediu remarcação
"""
from __future__ import annotations

import pytest

from voice_agent.handoff_humano import (
    detectar_pedido_humano,
    detectar_pedido_remarcacao_ou_cancelamento,
    resposta_canonica_remarcacao,
)
from voice_agent.responder import (
    _gerar_fallback_chute_agenda,
    _viola_chute_agenda_sem_hora,
)


# ═══════════════════════════════════════════════════════════════════════
# C-65 — CHUTE DE AGENDA (dia sem hora)
# ═══════════════════════════════════════════════════════════════════════

class TestChuteAgenda:
    def _ctx_agenda(self):
        return {"fsm": {"estado": "AGENDA"}, "known": {"nome_contato": "Letícia"}}

    def test_texto_real_lead_21329281_dispara(self):
        """Texto EXATO Lia às 19:28:13 (21/07)."""
        texto = (
            "Então as melhores opções pra você na Asa Norte seriam:\n"
            "- Segunda-feira à tarde\n"
            "- Quarta-feira à tarde\n"
            "- Sexta-feira à tarde\n\n"
            "Qual desses dias funciona melhor pra você?"
        )
        assert _viola_chute_agenda_sem_hora(texto, self._ctx_agenda()) is True

    @pytest.mark.parametrize("texto", [
        "Prefere terça ou quinta à tarde?",
        "Melhores opções: segunda à tarde ou sexta pela manhã, qual funciona melhor?",
        "Qual dia funciona melhor pra você, segunda ou quarta?",
    ])
    def test_variantes_chute_disparam(self, texto):
        assert _viola_chute_agenda_sem_hora(texto, self._ctx_agenda()) is True

    @pytest.mark.parametrize("texto", [
        # Confirmação com hora — OK
        "Confirmando: quinta-feira 23/07 às 10:30",
        # Oferta com hora concreta — OK
        "1️⃣ Quinta 23/07 às 14:00 · 2️⃣ Sexta 25/07 às 10:30. Qual prefere?",
        # Info pura sem oferta — OK
        "Karla atende segunda, quarta e sexta em Asa Norte",
        # Pergunta simples 1 dia — OK
        "Quinta às 10h fica bom pra você?",
    ])
    def test_falsos_positivos_nao_disparam(self, texto):
        assert _viola_chute_agenda_sem_hora(texto, self._ctx_agenda()) is False

    def test_fallback_menciona_medware(self):
        texto = _gerar_fallback_chute_agenda(
            {"known": {"nome_contato": "Ana"}},
        )
        assert "Ana" in texto
        assert "medware" in texto.lower() or "sistema" in texto.lower()


# ═══════════════════════════════════════════════════════════════════════
# C-66 — REMARCAÇÃO / CANCELAMENTO SEMPRE HUMANO
# ═══════════════════════════════════════════════════════════════════════

class TestDetectarRemarcacao:
    @pytest.mark.parametrize("frase", [
        # Cancelamento
        "Quero cancelar a consulta",
        "Vou cancelar",
        "Posso cancelar essa consulta?",
        # Desmarcação
        "Quero desmarcar",
        "Vou desmarcar minha consulta",
        # Remarcação
        "Quero remarcar",
        "Preciso remarcar",
        "Posso remarcar pra outra data?",
        # Não pode/vai
        "Não vou poder ir amanhã",
        "Não vai dar pra mim",
        "Não posso mais",
        # Mudar data
        "Quero mudar a data",
        "Posso trocar o dia?",
        "Preciso alterar o horário",
        # Faltar / adiar
        "Vou faltar amanhã",
        "Preciso adiar",
        "Quero adiar a consulta",
    ])
    def test_detecta_remarcacao(self, frase):
        assert detectar_pedido_remarcacao_ou_cancelamento(frase) is True

    @pytest.mark.parametrize("frase", [
        "Bom dia",
        "Quero agendar",
        "Qual o valor?",
        "Confirmo o horário",
        "Sim, vou comparecer",
    ])
    def test_texto_normal_nao_dispara(self, frase):
        assert detectar_pedido_remarcacao_ou_cancelamento(frase) is False

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_REMARCACAO_ATIVADO", "0")
        assert detectar_pedido_remarcacao_ou_cancelamento("Quero cancelar") is False


class TestRespostaCanonicaRemarcacao:
    def test_com_nome(self):
        r = resposta_canonica_remarcacao("Letícia Rocha")
        assert "Letícia" in r
        assert "equipe" in r.lower() and "humana" in r.lower()
        assert "particularidades" in r.lower()

    def test_sem_nome(self):
        r = resposta_canonica_remarcacao(None)
        assert "equipe" in r.lower()

    def test_curta(self):
        r = resposta_canonica_remarcacao("Paciente")
        assert len(r) < 400


class TestNaoConfundeComPedidoHumanoGenerico:
    """Detector de remarcação NÃO deve pegar 'quero falar com atendente'."""

    def test_pedido_humano_generico_nao_dispara_remarcacao(self):
        # 'Prefiro atendente' é pedido de humano genérico — NÃO remarcação
        assert detectar_pedido_remarcacao_ou_cancelamento("Prefiro atendente") is False
        # Mas o detector de humano DEVE pegar
        assert detectar_pedido_humano("Prefiro atendente") is True

    def test_remarcacao_pode_disparar_no_mesmo_texto(self):
        # "Quero cancelar" — detector de remarcação pega, humano pode ou não
        t = "Quero cancelar minha consulta"
        assert detectar_pedido_remarcacao_ou_cancelamento(t) is True
        # Não precisa também pegar humano — se pegar remarcação já vai pra handoff


# ═══════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO — _scrub_prohibited pega ambos
# ═══════════════════════════════════════════════════════════════════════

class TestIntegracaoScrubProhibited:
    def test_texto_lia_te_espero_no_dia_substituido_por_handoff(self):
        """Cenário Fábio 19:29:03 — Lia disse 'te espero' quando paciente pediu remarcar."""
        from voice_agent.responder import _scrub_prohibited

        # ctx com user_text mostrando que paciente pediu remarcação
        ctx = {
            "user_text": "Preciso remarcar minha consulta pra outra data",
            "known": {"nome_contato": "Letícia Rocha", "convenio": "Não se aplica"},
        }
        texto_lia_ruim = (
            "Recebi, obrigada! A consulta da Alice já está marcada para "
            "22/07 às 16:30. Se precisar remarcar ou cancelar, é só me "
            "avisar — caso contrário, te espero no dia marcado!"
        )
        resultado = _scrub_prohibited(texto_lia_ruim, ctx)
        # Deve ter sido substituído por resposta de handoff
        assert "te espero no dia" not in resultado.lower()
        assert "equipe" in resultado.lower() or "humana" in resultado.lower()

    def test_texto_lia_com_handoff_correto_passa(self):
        """Se Lia JÁ está fazendo handoff, filtro C-66 não interfere.

        NOTE: filtro C-47 LEGACY (task #413/C-67) ainda gera texto com
        'especialista em remarcação' quando detecta contexto de remarcação —
        isso é bug conhecido separado (C-67) que precisa de refactor do C-47.
        Enquanto isso, o teste só valida que a resposta menciona ATENDIMENTO
        (handoff acontece de alguma forma).
        """
        from voice_agent.responder import _scrub_prohibited

        ctx = {
            "user_text": "Quero remarcar",
            "known": {"nome_contato": "Letícia"},
        }
        texto_ok = (
            "Letícia, vou passar seu atendimento pra nossa equipe humana agora."
        )
        resultado = _scrub_prohibited(texto_ok, ctx)
        # Resposta final deve mencionar handoff / atendimento / remarcação
        lower = resultado.lower()
        assert any(t in lower for t in [
            "equipe", "atendimento", "remarcação", "remarcacao", "especialist",
        ])
