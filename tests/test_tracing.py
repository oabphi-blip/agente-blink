"""Pytest do tracing estruturado de turnos.

Cobre:
- _resumir_ctx (None, vazio, completo)
- TraceTurno (to_dict / from_dict round-trip)
- TraceBuilder (chainable, captura tools/juiz/filtros/output/erro)
- gravar_trace (rpush + ltrim + expire)
- carregar_traces (lrange + parse)
- esta_habilitado (env on/off)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# _resumir_ctx
# ----------------------------------------------------------------------

class TestResumirCtx:

    def test_ctx_None_devolve_dict_vazio(self):
        from voice_agent.tracing import _resumir_ctx
        assert _resumir_ctx(None) == {}

    def test_ctx_nao_dict_devolve_vazio(self):
        from voice_agent.tracing import _resumir_ctx
        assert _resumir_ctx("string") == {}
        assert _resumir_ctx([1, 2]) == {}

    def test_ctx_vazio_devolve_flags_basicas(self):
        from voice_agent.tracing import _resumir_ctx
        out = _resumir_ctx({})
        assert out["ja_agendado"] is False
        assert out["agenda_disponivel"] is False
        assert out["etapa"] == ""
        assert out["status_id"] is None

    def test_ctx_esther_completo(self):
        from voice_agent.tracing import _resumir_ctx
        ctx = {
            "ja_agendado": True,
            "agenda": [{"x": 1}],
            "etapa": "5-AGENDADO",
            "status_id": 101507507,
            "known": {
                "nome_paciente": "Esther Dias Guimarães",
                "medico": "Dra. Karla Delalibera",
                "unidade": "Águas Claras",
                "convenio": "Plan Assiste - MPF (MPU)",
                "dia_consulta_iso": "2026-06-09T18:30:00-03:00",
            },
        }
        out = _resumir_ctx(ctx)
        assert out["ja_agendado"] is True
        assert out["agenda_disponivel"] is True
        assert out["etapa"] == "5-AGENDADO"
        assert out["status_id"] == 101507507
        assert out["nome_paciente"] == "Esther Dias Guimarães"
        assert "Karla" in out["medico"]
        assert out["unidade"] == "Águas Claras"
        assert out["dia_consulta_iso"].startswith("2026-06-09")

    def test_ctx_campos_nao_conhecidos_ignorados(self):
        """Campos extras em ctx.known não vazam pro trace."""
        from voice_agent.tracing import _resumir_ctx
        ctx = {"known": {"campo_estranho_qualquer": "x"}}
        out = _resumir_ctx(ctx)
        assert "campo_estranho_qualquer" not in out


# ----------------------------------------------------------------------
# TraceTurno round-trip
# ----------------------------------------------------------------------

class TestRoundTrip:

    def test_to_from_dict_preserva_campos(self):
        from voice_agent.tracing import TraceTurno
        t = TraceTurno(
            ts_iso="2026-06-02T00:30:00-03:00",
            ts_epoch=1780359000,
            lead_id=24060221,
            phone="5561992589767",
            user_text="oi",
            ctx_resumo={"ja_agendado": True},
            tools_chamadas=[{"name": "oferecer_slot", "ok": True}],
            juiz_veredict={"risco": 85, "motivos": ["x"]},
            output_final="resposta",
            filtros_disparados=["juiz_haiku"],
            elapsed_ms=1234,
        )
        d = t.to_dict()
        assert d["lead_id"] == 24060221
        assert d["ctx_resumo"]["ja_agendado"] is True
        t2 = TraceTurno.from_dict(d)
        assert t2.lead_id == t.lead_id
        assert t2.juiz_veredict == t.juiz_veredict
        assert t2.tools_chamadas == t.tools_chamadas

    def test_from_dict_ignora_campos_desconhecidos(self):
        from voice_agent.tracing import TraceTurno
        d = {
            "lead_id": 1,
            "phone": "x",
            "campo_que_nao_existe": "ignora",
        }
        t = TraceTurno.from_dict(d)
        assert t.lead_id == 1
        assert t.phone == "x"
        assert not hasattr(t, "campo_que_nao_existe")


# ----------------------------------------------------------------------
# TraceBuilder
# ----------------------------------------------------------------------

class TestBuilder:

    def test_chainable_e_acumula(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(
            lead_id=24060221, phone="556199x",
            conversation_key="k", channel="81331005",
        )
        out = (
            b.set_user_text("oi quero agendar")
             .set_ctx({"ja_agendado": True, "known": {
                 "nome_paciente": "Esther"
             }})
             .add_tool("oferecer_slot", ok=True, detail="2 slots")
             .add_tool("gravar_agendamento", ok=False, detail="medware 500")
             .set_juiz({"risco": 75, "motivos": ["x"], "recomendado": "substituir"})
             .set_memoria_bugs("esther_oferta_pos_agendado_imagem", 0.93)
             .add_filtro("_viola_oferta_apos_agendado")
             .add_filtro("juiz_haiku")
             .set_output("Anotei aqui...")
             .finalizar()
        )
        assert out.lead_id == 24060221
        assert out.user_text == "oi quero agendar"
        assert out.ctx_resumo["ja_agendado"] is True
        assert out.ctx_resumo["nome_paciente"] == "Esther"
        assert len(out.tools_chamadas) == 2
        assert out.tools_chamadas[1]["ok"] is False
        assert out.juiz_veredict["risco"] == 75
        assert out.memoria_bugs_match["bug_id"].startswith("esther")
        assert "_viola_oferta_apos_agendado" in out.filtros_disparados
        assert out.elapsed_ms >= 0

    def test_user_text_longo_truncado_2000(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(lead_id=1)
        b.set_user_text("x" * 3000)
        assert len(b.trace.user_text) == 2000

    def test_output_longo_truncado_3000(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(lead_id=1)
        b.set_output("y" * 5000)
        assert len(b.trace.output_final) == 3000

    def test_juiz_normaliza_motivos_max_5(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(lead_id=1)
        b.set_juiz({
            "risco": 50,
            "motivos": ["a", "b", "c", "d", "e", "f", "g"],
            "recomendado": "enviar",
        })
        assert len(b.trace.juiz_veredict["motivos"]) == 5

    def test_set_erro(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(lead_id=1)
        b.set_erro("timeout medware")
        assert b.trace.erro == "timeout medware"

    def test_finalizar_calcula_elapsed(self):
        from voice_agent.tracing import TraceBuilder
        b = TraceBuilder(lead_id=1)
        time.sleep(0.01)
        t = b.finalizar()
        assert t.elapsed_ms >= 10


# ----------------------------------------------------------------------
# Persistência Redis (mockado)
# ----------------------------------------------------------------------

class TestGravarTrace:

    def test_grava_rpush_ltrim_expire(self):
        from voice_agent.tracing import (
            gravar_trace, TraceTurno, _redis_key, TTL_DEFAULT,
        )
        redis = MagicMock()
        t = TraceTurno(lead_id=42, phone="x", output_final="resp")
        ok = gravar_trace(redis, t)
        assert ok is True
        # rpush foi chamado com chave correta
        chave_esperada = _redis_key(42)
        redis.rpush.assert_called_once()
        args = redis.rpush.call_args[0]
        assert args[0] == chave_esperada
        # Payload é JSON parseável
        payload = json.loads(args[1])
        assert payload["lead_id"] == 42
        # ltrim mantém só os 200 últimos
        redis.ltrim.assert_called_once_with(chave_esperada, -200, -1)
        # expire renovou TTL
        redis.expire.assert_called_once_with(chave_esperada, TTL_DEFAULT)

    def test_redis_None_devolve_False(self):
        from voice_agent.tracing import gravar_trace, TraceTurno
        assert gravar_trace(None, TraceTurno(lead_id=1)) is False

    def test_lead_id_None_devolve_False(self):
        from voice_agent.tracing import gravar_trace, TraceTurno
        assert gravar_trace(MagicMock(), TraceTurno(lead_id=None)) is False

    def test_redis_falha_devolve_False(self):
        from voice_agent.tracing import gravar_trace, TraceTurno
        redis = MagicMock()
        redis.rpush.side_effect = RuntimeError("conn lost")
        assert gravar_trace(redis, TraceTurno(lead_id=1)) is False


class TestCarregarTraces:

    def test_lrange_e_parse(self):
        from voice_agent.tracing import (
            carregar_traces, TraceTurno,
        )
        # Mocka Redis devolvendo 2 traces
        t1 = TraceTurno(lead_id=1, user_text="oi", output_final="olá")
        t2 = TraceTurno(lead_id=1, user_text="agendar", output_final="claro!")
        redis = MagicMock()
        redis.lrange.return_value = [
            json.dumps(t1.to_dict()),
            json.dumps(t2.to_dict()),
        ]
        out = carregar_traces(redis, 1)
        assert len(out) == 2
        assert out[0].user_text == "oi"
        assert out[1].output_final == "claro!"

    def test_aceita_bytes_do_redis(self):
        from voice_agent.tracing import (
            carregar_traces, TraceTurno,
        )
        redis = MagicMock()
        redis.lrange.return_value = [
            json.dumps(TraceTurno(lead_id=1).to_dict()).encode("utf-8"),
        ]
        out = carregar_traces(redis, 1)
        assert len(out) == 1

    def test_entrada_invalida_ignorada(self):
        from voice_agent.tracing import (
            carregar_traces, TraceTurno,
        )
        redis = MagicMock()
        redis.lrange.return_value = [
            "{invalid json",
            json.dumps(TraceTurno(lead_id=1, user_text="ok").to_dict()),
        ]
        out = carregar_traces(redis, 1)
        # Só 1 válido
        assert len(out) == 1
        assert out[0].user_text == "ok"

    def test_redis_None_devolve_vazia(self):
        from voice_agent.tracing import carregar_traces
        assert carregar_traces(None, 1) == []

    def test_redis_erro_devolve_vazia(self):
        from voice_agent.tracing import carregar_traces
        redis = MagicMock()
        redis.lrange.side_effect = RuntimeError("down")
        assert carregar_traces(redis, 1) == []


# ----------------------------------------------------------------------
# esta_habilitado
# ----------------------------------------------------------------------

class TestHabilitado:

    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("TRACING_ENABLED", raising=False)
        from voice_agent.tracing import esta_habilitado
        assert esta_habilitado() is False

    def test_on(self, monkeypatch):
        monkeypatch.setenv("TRACING_ENABLED", "1")
        from voice_agent.tracing import esta_habilitado
        assert esta_habilitado() is True

    def test_qualquer_outro_valor_off(self, monkeypatch):
        monkeypatch.setenv("TRACING_ENABLED", "true")
        from voice_agent.tracing import esta_habilitado
        # Só "1" liga (estrito)
        assert esta_habilitado() is False
