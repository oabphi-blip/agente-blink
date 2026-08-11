"""Pytest do juiz adversarial Haiku.

Cobre:
1. Parsing JSON do veredicto (raw → dataclass)
2. Resumo de ctx pro juiz
3. Threshold de substituição (>= limiar)
4. Erro Haiku não bloqueia (devolve enviar)
5. from_env desligado / sem chave / com chave
6. Gravação no Redis (mock)

Não chama API real (mock do client Anthropic). Os 4 casos canônicos
(Esther, Adelia, Juliene, Diones) ficam no test_juiz_adversarial_e2e.py
que rodam contra API real quando JUIZ_HAIKU_E2E=1 (caro, opt-in).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# _resumir_ctx_pro_juiz
# ----------------------------------------------------------------------

class TestResumirCtx:

    def test_ctx_None_devolve_string_sem_contexto(self):
        from voice_agent.juiz_adversarial import _resumir_ctx_pro_juiz
        out = _resumir_ctx_pro_juiz(None)
        assert "sem contexto" in out.lower()

    def test_ctx_vazio_devolve_basico(self):
        from voice_agent.juiz_adversarial import _resumir_ctx_pro_juiz
        out = _resumir_ctx_pro_juiz({})
        assert "ja_agendado: False" in out
        assert "agenda_disponivel: False" in out

    def test_ctx_esther_completo(self):
        """Cenário Esther 24060221."""
        from voice_agent.juiz_adversarial import _resumir_ctx_pro_juiz
        ctx = {
            "ja_agendado": True,
            "agenda": [{"x": 1}],
            "etapa": "5-AGENDADO",
            "known": {
                "nome_paciente": "Esther Dias Guimarães",
                "dia_consulta_iso": "2026-06-09T18:30:00-03:00",
                "medico": "Dra. Karla Delalibera",
                "unidade": "Águas Claras",
            },
        }
        out = _resumir_ctx_pro_juiz(ctx)
        assert "ja_agendado: True" in out
        assert "5-AGENDADO" in out
        assert "Esther" in out
        assert "2026-06-09" in out
        assert "Karla" in out
        assert "Águas Claras" in out


# ----------------------------------------------------------------------
# _extrair_json
# ----------------------------------------------------------------------

class TestExtrairJson:

    def test_json_puro(self):
        from voice_agent.juiz_adversarial import _extrair_json
        txt = '{"risco": 85, "motivos": ["oferta apos agendado"], ' \
              '"recomendado": "substituir"}'
        out = _extrair_json(txt)
        assert out["risco"] == 85
        assert out["recomendado"] == "substituir"

    def test_json_em_markdown_fence(self):
        from voice_agent.juiz_adversarial import _extrair_json
        txt = '```json\n{"risco": 10, "recomendado": "enviar"}\n```'
        out = _extrair_json(txt)
        assert out["risco"] == 10
        assert out["recomendado"] == "enviar"

    def test_json_com_texto_antes_e_depois(self):
        from voice_agent.juiz_adversarial import _extrair_json
        txt = 'Analisei. Resultado: {"risco":50,"motivos":[]} pronto.'
        out = _extrair_json(txt)
        assert out["risco"] == 50

    def test_string_invalida_devolve_dict_vazio(self):
        from voice_agent.juiz_adversarial import _extrair_json
        assert _extrair_json("") == {}
        assert _extrair_json("não é JSON") == {}
        # JSON mal formado
        assert _extrair_json("{ risco: 50 }") == {}


# ----------------------------------------------------------------------
# JuizAdversarial.julgar (com mock do client)
# ----------------------------------------------------------------------

class _MockBlock:
    def __init__(self, text):
        self.text = text


class _MockResp:
    def __init__(self, text):
        self.content = [_MockBlock(text)]


@pytest.fixture
def juiz_mockado():
    """JuizAdversarial com client Anthropic mockado — não bate na API.

    Constrói a instância via __new__ pra pular o __init__ (que faria
    `Anthropic(api_key=...)` real). Injeta um MagicMock no _client.
    """
    from voice_agent.juiz_adversarial import JuizAdversarial
    j = JuizAdversarial.__new__(JuizAdversarial)
    j._client = MagicMock()
    j.model = "claude-haiku-4-5-20251001"
    j.timeout = 8.0
    j.limiar = 70
    j.max_tokens = 200
    return j


class TestJulgar:

    def test_resposta_normal_baixo_risco_envia(self, juiz_mockado):
        juiz_mockado._client.messages.create.return_value = _MockResp(
            '{"risco": 10, "motivos": [], "recomendado": "enviar"}'
        )
        v = juiz_mockado.julgar(
            lia_text="Olá Esther! Posso te ajudar?",
            ctx={"ja_agendado": False},
            user_text="oi",
        )
        assert v.risco == 10
        assert v.recomendado == "enviar"
        assert not v.deve_substituir

    def test_resposta_violadora_alto_risco_substitui(self, juiz_mockado):
        juiz_mockado._client.messages.create.return_value = _MockResp(
            '{"risco": 90, "motivos": ["oferta apos agendado"], '
            '"recomendado": "substituir"}'
        )
        v = juiz_mockado.julgar(
            lia_text="Deixa eu trazer os horários da Dra. Karla pra você",
            ctx={"ja_agendado": True},
            user_text="...",
        )
        assert v.risco == 90
        assert v.deve_substituir
        assert "oferta apos agendado" in v.motivos

    def test_risco_acima_limiar_mesmo_com_recomendado_enviar(self, juiz_mockado):
        """Se Haiku marcar risco=80 mas disser 'enviar' por engano, força
        substituir (defesa em profundidade)."""
        juiz_mockado._client.messages.create.return_value = _MockResp(
            '{"risco": 80, "motivos": ["dubio"], "recomendado": "enviar"}'
        )
        v = juiz_mockado.julgar(lia_text="x", ctx={}, user_text="x")
        assert v.deve_substituir

    def test_lia_text_vazio_devolve_neutro(self, juiz_mockado):
        v = juiz_mockado.julgar(lia_text="", ctx={}, user_text="oi")
        assert v.recomendado == "enviar"
        # Não chamou a API
        juiz_mockado._client.messages.create.assert_not_called()

    def test_erro_api_nao_bloqueia(self, juiz_mockado):
        juiz_mockado._client.messages.create.side_effect = RuntimeError(
            "timeout"
        )
        v = juiz_mockado.julgar(lia_text="ok", ctx={}, user_text="x")
        assert v.recomendado == "enviar"
        assert v.erro is not None
        assert "timeout" in v.erro.lower()

    def test_json_invalido_da_haiku_nao_bloqueia(self, juiz_mockado):
        juiz_mockado._client.messages.create.return_value = _MockResp(
            "resposta sem JSON nenhum"
        )
        v = juiz_mockado.julgar(lia_text="ok", ctx={}, user_text="x")
        # Parser não achou JSON → risco=0, recomendado=enviar
        assert v.recomendado == "enviar"
        assert v.risco == 0


# ----------------------------------------------------------------------
# from_env
# ----------------------------------------------------------------------

class TestFromEnv:

    def test_desligado_devolve_None(self, monkeypatch):
        monkeypatch.delenv("JUIZ_HAIKU_ENABLED", raising=False)
        from voice_agent.juiz_adversarial import JuizAdversarial
        assert JuizAdversarial.from_env() is None

    def test_ligado_sem_chave_devolve_None(self, monkeypatch):
        monkeypatch.setenv("JUIZ_HAIKU_ENABLED", "1")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from voice_agent.juiz_adversarial import JuizAdversarial
        assert JuizAdversarial.from_env() is None

    def test_ligado_com_chave_devolve_instancia(self, monkeypatch):
        monkeypatch.setenv("JUIZ_HAIKU_ENABLED", "1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        from voice_agent.juiz_adversarial import JuizAdversarial
        j = JuizAdversarial.from_env()
        assert j is not None
        assert j.model.startswith("claude-haiku")

    def test_limiar_customizado_via_env(self, monkeypatch):
        monkeypatch.setenv("JUIZ_HAIKU_ENABLED", "1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("JUIZ_HAIKU_LIMIAR", "50")
        from voice_agent.juiz_adversarial import JuizAdversarial
        j = JuizAdversarial.from_env()
        assert j.limiar == 50

    def test_limiar_invalido_volta_default(self, monkeypatch):
        monkeypatch.setenv("JUIZ_HAIKU_ENABLED", "1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("JUIZ_HAIKU_LIMIAR", "abc")
        from voice_agent.juiz_adversarial import JuizAdversarial, LIMIAR_DEFAULT
        j = JuizAdversarial.from_env()
        assert j.limiar == LIMIAR_DEFAULT


# ----------------------------------------------------------------------
# gravar_veredicto_redis
# ----------------------------------------------------------------------

class TestGravarRedis:

    def test_grava_payload_serializavel(self):
        from voice_agent.juiz_adversarial import (
            gravar_veredicto_redis, VeredictoJuiz,
        )
        redis = MagicMock()
        v = VeredictoJuiz(
            risco=85, motivos=["oferta apos agendado"],
            recomendado="substituir", elapsed_ms=523,
        )
        gravar_veredicto_redis(redis, 24060221, v, "Lia disse algo aqui")
        # Foi chamado uma vez
        assert redis.setex.call_count == 1
        chave, ttl, valor = redis.setex.call_args[0]
        assert "blink:juiz:veredicto:24060221:" in chave
        assert ttl == 7 * 24 * 3600
        # Valor é JSON parseável e tem os campos
        payload = json.loads(valor)
        assert payload["risco"] == 85
        assert payload["motivos"] == ["oferta apos agendado"]
        assert payload["recomendado"] == "substituir"
        assert "Lia disse algo aqui" in payload["lia_text_preview"]

    def test_redis_None_nao_levanta(self):
        from voice_agent.juiz_adversarial import (
            gravar_veredicto_redis, VeredictoJuiz,
        )
        # Não deve crashar
        gravar_veredicto_redis(None, 1, VeredictoJuiz(), "x")

    def test_redis_falha_nao_levanta(self):
        from voice_agent.juiz_adversarial import (
            gravar_veredicto_redis, VeredictoJuiz,
        )
        redis = MagicMock()
        redis.setex.side_effect = RuntimeError("redis down")
        # Não deve crashar
        gravar_veredicto_redis(redis, 1, VeredictoJuiz(), "x")


# ----------------------------------------------------------------------
# VeredictoJuiz.deve_substituir
# ----------------------------------------------------------------------

class TestVeredictoFlag:

    def test_recomendado_substituir_eh_True(self):
        from voice_agent.juiz_adversarial import VeredictoJuiz
        v = VeredictoJuiz(recomendado="substituir")
        assert v.deve_substituir is True

    def test_recomendado_enviar_eh_False(self):
        from voice_agent.juiz_adversarial import VeredictoJuiz
        v = VeredictoJuiz(recomendado="enviar")
        assert v.deve_substituir is False
