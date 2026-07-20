"""Bug C-61 — Anti-cobertura particular + handoff humano REAL (20/07/2026).

Origem: Fábio 20/07 — lead 24325544 (Patrícia/Maria bebê).
2 bugs simultâneos:
    (a) 'Sem Convênio é coberta com coparticipação' → filtro C-61 SEMPRE-ON
    (b) 'vou te conectar com equipe' mas IA continua respondendo → handoff FAKE

Pytest cobre:
    - _viola_cobertura_sem_convenio (várias variantes texto)
    - _gerar_fallback_particular (formato correto por médico)
    - detectar_pedido_humano (frases positivas + falsos negativos)
    - processar_handoff (mock kommo + validação chamadas)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent.handoff_humano import (
    STATUS_ATENDIMENTO_HUMANO,
    detectar_pedido_humano,
    processar_handoff,
    resposta_canonica_handoff,
)
from voice_agent.responder import (
    _convenio_particular_ou_sem,
    _gerar_fallback_particular,
    _viola_cobertura_sem_convenio,
)


# ═══════════════════════════════════════════════════════════════════════
# PARTE (a) — FILTRO ANTI-COBERTURA
# ═══════════════════════════════════════════════════════════════════════

class TestConvenioParticularOuSem:
    @pytest.mark.parametrize("valor", [
        "Sem Convênio", "sem convênio", "sem convenio",
        "Particular", "particular",
        "Não se aplica", "não se aplica",
    ])
    def test_convenios_que_devem_disparar(self, valor):
        ctx = {"known": {"convenio": valor}}
        assert _convenio_particular_ou_sem(ctx) is True

    @pytest.mark.parametrize("valor", [
        "Bacen", "Saúde Caixa", "Care Plus", "TJDFT",
    ])
    def test_convenios_aceitos_nao_disparam(self, valor):
        ctx = {"known": {"convenio": valor}}
        assert _convenio_particular_ou_sem(ctx) is False

    def test_ctx_vazio(self):
        assert _convenio_particular_ou_sem({}) is False
        assert _convenio_particular_ou_sem(None) is False


class TestFiltroCoberturaSemConvenio:
    def _ctx_particular(self):
        return {"known": {"convenio": "Sem Convênio"}}

    @pytest.mark.parametrize("texto", [
        "pelo seu convênio, a consulta é coberta",
        "está coberta pelo seu plano",
        "consulta é coberto pelo convênio",
        "pode ter coparticipação",
        "coparticipação dependendo do plano",
        "coparticipacao",
        "você não paga direto à clínica",
        "há reembolso pelo convênio",
        "depende do plano",
        "cobertura do convênio",
    ])
    def test_detecta_variantes(self, texto):
        assert _viola_cobertura_sem_convenio(texto, self._ctx_particular()) is True

    def test_texto_texto_real_lead_24325544(self):
        """Texto EXATO que Lia disse à Patrícia 20/07/2026 20:43:46."""
        texto = (
            "Maria, pelo seu convênio (Sem Convênio), a consulta com a Dra. "
            "Karla Delalíbera é coberta — você não paga direto à clínica "
            "(pode ter coparticipação dependendo do plano). Quer seguir?"
        )
        assert _viola_cobertura_sem_convenio(texto, self._ctx_particular()) is True

    def test_convenio_aceito_nao_dispara(self):
        # Se convenio é aceito, filtro NÃO deve interferir
        ctx = {"known": {"convenio": "Bacen"}}
        texto = "pelo seu convênio, está coberto"
        assert _viola_cobertura_sem_convenio(texto, ctx) is False

    def test_texto_normal_particular_nao_dispara(self):
        ctx = self._ctx_particular()
        texto = "A consulta é R$ 611 no Pix"
        assert _viola_cobertura_sem_convenio(texto, ctx) is False


class TestFallbackParticular:
    def test_gera_valor_karla_padrao(self):
        ctx = {"known": {"convenio": "Sem Convênio", "nome_paciente": "Ana Silva"}}
        texto = _gerar_fallback_particular(ctx)
        assert "Ana" in texto
        assert "R$ 611" in texto
        assert "R$ 670" in texto
        # Não pode ter cobertura/coparticipação
        assert "cobert" not in texto.lower()
        assert "coparticip" not in texto.lower()

    def test_gera_valor_apv(self):
        ctx = {"known": {"convenio": "Particular", "motivo": "Avaliação Processamento Visual"}}
        texto = _gerar_fallback_particular(ctx)
        assert "R$ 800" in texto
        assert "R$ 870" in texto

    def test_gera_valor_fabricio_catarata(self):
        ctx = {
            "known": {
                "convenio": "Sem Convênio",
                "motivo": "catarata",
                "medico": "Dr. Fabrício Freitas",
            },
        }
        texto = _gerar_fallback_particular(ctx)
        assert "R$ 445" in texto
        assert "R$ 470" in texto


# ═══════════════════════════════════════════════════════════════════════
# PARTE (b) — DETECTOR PEDIDO HUMANO
# ═══════════════════════════════════════════════════════════════════════

class TestDetectarPedidoHumano:
    @pytest.mark.parametrize("frase", [
        "Quero falar com um humano",
        "Prefiro atendente",
        "Me passa pra atendente",
        "Posso falar com alguém?",
        "Isso é robô?",
        "Cansei de falar com robô",
        "Prefiro humano",
        "Quero uma pessoa",
        "Não quero robô",
        "Tem alguém pra atender?",
        "Me transfere pra alguém",
    ])
    def test_detecta_pedido(self, frase):
        assert detectar_pedido_humano(frase) is True

    @pytest.mark.parametrize("frase", [
        "Quero agendar",
        "Bom dia",
        "Estou com dor",
        "Qual o valor?",
        "",
        "   ",
    ])
    def test_nao_dispara_em_texto_normal(self, frase):
        assert detectar_pedido_humano(frase) is False

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_HUMANO_ATIVADO", "0")
        assert detectar_pedido_humano("Quero falar com humano") is False


class TestProcessarHandoff:
    def _mock_kommo(self):
        m = MagicMock()
        m.atualizar_status_lead = MagicMock(return_value=True)
        m.update_lead_fields = MagicMock(return_value=True)
        m.add_note = MagicMock(return_value=True)
        return m

    def test_handoff_completo(self):
        km = self._mock_kommo()
        r = processar_handoff(km, 12345, motivo="paciente_pediu_humano")
        assert r["ok"] is True
        assert r["moveu_status"] is True
        assert r["desativou_ia"] is True
        assert r["gravou_nota"] is True

    def test_status_correto(self):
        km = self._mock_kommo()
        processar_handoff(km, 12345)
        # Deve ter chamado atualizar_status_lead com status 106563343
        km.atualizar_status_lead.assert_called_with(12345, STATUS_ATENDIMENTO_HUMANO)

    def test_desativa_ia_corretamente(self):
        km = self._mock_kommo()
        processar_handoff(km, 12345)
        km.update_lead_fields.assert_called_with(
            12345, {"ATIVADO IA?": "Desativado"},
        )

    def test_falha_em_um_step_continua_outros(self):
        km = self._mock_kommo()
        km.atualizar_status_lead = MagicMock(side_effect=Exception("boom"))
        r = processar_handoff(km, 12345)
        assert r["moveu_status"] is False
        assert r["desativou_ia"] is True  # ainda tentou
        assert r["gravou_nota"] is True

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_HUMANO_ATIVADO", "0")
        km = self._mock_kommo()
        r = processar_handoff(km, 12345)
        assert r["ok"] is False
        assert r["erro"] == "toggle_off"


class TestRespostaCanonica:
    def test_com_nome(self):
        r = resposta_canonica_handoff("Ana Silva")
        assert "Ana" in r
        assert "equipe" in r.lower() or "pessoa" in r.lower()

    def test_sem_nome(self):
        r = resposta_canonica_handoff(None)
        assert "equipe" in r.lower() or "pessoa" in r.lower()

    def test_mensagem_curta(self):
        # Handoff deve ser curto — não pode virar monólogo
        r = resposta_canonica_handoff("Paciente")
        assert len(r) < 250
