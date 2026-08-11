"""Pytest do task #260 — métricas live de funcionamento.

Cobre:
1. Módulo metricas_funcionamento puro (incrementar, get_contador, taxas)
2. Plug pontos em pipeline.py, tools_lia.py
3. Endpoint /admin/funcionamento (smoke string + sintaxe)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ============================================================
# MÓDULO PURO — métricas_funcionamento
# ============================================================

class TestModuloMetricas:
    def test_incrementar_sem_redis_nao_quebra(self):
        from voice_agent import metricas_funcionamento as mf
        # Sem redis (None) — best-effort, retorna sem erro
        mf.incrementar(None, "tool:oferecer_slot:ok")

    def test_incrementar_chama_incrby_e_expire(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()
        mf.incrementar(redis_mock, "tool:oferecer_slot:ok")
        redis_mock.incrby.assert_called_once()
        redis_mock.expire.assert_called_once()
        # Chave inclui o evento e a data
        chamada_incrby = redis_mock.incrby.call_args
        chave = chamada_incrby[0][0]
        assert "blink:metric:tool:oferecer_slot:ok:" in chave

    def test_get_contador_zero_quando_vazio(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        assert mf.get_contador(redis_mock, "tool:oferecer_slot:ok") == 0

    def test_get_contador_le_int(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()
        redis_mock.get.return_value = b"42"
        assert mf.get_contador(redis_mock, "x") == 42

    def test_funcionamento_hoje_retorna_estrutura_completa(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()
        # Cenário: 100 entradas em AGENDA, 90 ofertas OK (90%)
        # 20 gravações OK, 2 fail (90.9%)

        def fake_get(key):
            counts = {
                "blink:metric:fsm:AGENDA:enter": b"100",
                "blink:metric:tool:oferecer_slot:ok": b"90",
                "blink:metric:tool:gravar_agendamento_medware:ok": b"20",
                "blink:metric:tool:gravar_agendamento_medware:fail": b"2",
            }
            for prefix, v in counts.items():
                if key.startswith(prefix):
                    return v
            return None

        redis_mock.get.side_effect = fake_get
        snap = mf.funcionamento_hoje(redis_mock)
        assert "dia" in snap
        assert snap["taxas"]["agenda_para_oferecer_slot_pct"] == 90.0
        assert snap["taxas"]["gravacao_sucesso_pct"] == 90.9
        # 90% >= 80% (OK) MAS 90.9% < 95% (alarme gravação)
        assert any("Gravação" in a for a in snap["alarmes_ativos"])

    def test_funcionamento_hoje_sem_dados_sem_alarme(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        snap = mf.funcionamento_hoje(redis_mock)
        # Sem amostras → taxas None → sem alarmes (não dispara por divisão por zero)
        assert snap["taxas"]["agenda_para_oferecer_slot_pct"] is None
        assert snap["alarmes_ativos"] == []

    def test_funcionamento_hoje_taxa_baixa_dispara_alarme(self):
        from voice_agent import metricas_funcionamento as mf
        redis_mock = MagicMock()

        def fake_get(key):
            if "fsm:AGENDA:enter" in key:
                return b"100"
            if "tool:oferecer_slot:ok" in key:
                return b"50"  # 50% — alarme!
            return None

        redis_mock.get.side_effect = fake_get
        snap = mf.funcionamento_hoje(redis_mock)
        assert snap["taxas"]["agenda_para_oferecer_slot_pct"] == 50.0
        assert any("AGENDA" in a for a in snap["alarmes_ativos"])

    def test_redis_none_retorna_erro_estruturado(self):
        from voice_agent import metricas_funcionamento as mf
        snap = mf.funcionamento_hoje(None)
        assert "erro" in snap


# ============================================================
# PLUG POINTS — pipeline.py, tools_lia.py
# ============================================================

class TestPlugPoints:
    def test_pipeline_pluga_metric_fsm_enter(self):
        path = ROOT / "voice_agent" / "pipeline.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "metricas_funcionamento" in conteudo
        assert "fsm:" in conteudo and ":enter" in conteudo

    def test_tools_lia_pluga_metric_oferecer_slot(self):
        path = ROOT / "voice_agent" / "tools_lia.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "tool:oferecer_slot:ok" in conteudo

    def test_tools_lia_pluga_metric_gravacao_ok_e_fail(self):
        path = ROOT / "voice_agent" / "tools_lia.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "tool:gravar_agendamento_medware:ok" in conteudo
        assert "tool:gravar_agendamento_medware:fail" in conteudo


# ============================================================
# ENDPOINT — /admin/funcionamento
# ============================================================

class TestEndpoint:
    def test_endpoint_string_existe(self):
        path = ROOT / "voice_agent" / "webhook.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "/admin/funcionamento" in conteudo
        assert "admin_funcionamento" in conteudo
        assert "/admin/funcionamento/checar-alarmes" in conteudo

    def test_endpoint_dedup_alarme_1h(self):
        path = ROOT / "voice_agent" / "webhook.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "blink:alarme_funcionamento:" in conteudo
        # TTL 3600s = 1h
        assert "3600" in conteudo

    def test_webhook_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "webhook.py"
        py_compile.compile(str(path), doraise=True)

    def test_pipeline_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "pipeline.py"
        py_compile.compile(str(path), doraise=True)

    def test_tools_lia_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "tools_lia.py"
        py_compile.compile(str(path), doraise=True)

    def test_metricas_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "metricas_funcionamento.py"
        py_compile.compile(str(path), doraise=True)


# ============================================================
# WORKERS — alarmes horários + replay noturno
# ============================================================

class TestWorkers:
    def test_cron_interno_pluga_workers_novos(self):
        path = ROOT / "voice_agent" / "cron_interno.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "_worker_alarmes_horario_loop" in conteudo
        assert "_worker_replay_noturno_loop" in conteudo
        assert "blink-cron-alarmes-horarios" in conteudo
        assert "blink-cron-replay-noturno" in conteudo
        # Toggle env
        assert "METRICAS_FUNCIONAMENTO_ENABLED" in conteudo
        # 23h BRT pra replay
        assert ".hour == 23" in conteudo

    def test_cron_interno_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "cron_interno.py"
        py_compile.compile(str(path), doraise=True)

    def test_alarme_horario_dedup_1h(self):
        path = ROOT / "voice_agent" / "cron_interno.py"
        conteudo = path.read_text(encoding="utf-8")
        # Dedup chave + TTL 3600s
        assert "blink:alarme_funcionamento:" in conteudo
        assert "3600" in conteudo

    def test_replay_noturno_dedup_24h(self):
        path = ROOT / "voice_agent" / "cron_interno.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "blink:replay_noturno:" in conteudo
        # TTL 86400s = 24h
        assert "86400" in conteudo
