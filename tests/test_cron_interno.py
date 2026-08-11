"""Pytest do cron interno (task #105)."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from voice_agent.cron_interno import (
    _dry_run_default,
    _enabled,
    _executar_classificar,
    _intervalo_classificar_seg,
    iniciar_cron,
    parar_cron,
)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("BLINK_CRON_ENABLED", raising=False)
    monkeypatch.delenv("BLINK_CRON_DRY_RUN", raising=False)
    monkeypatch.delenv("CLASSIFICAR_CADA_HORAS", raising=False)
    monkeypatch.delenv("CLASSIFICAR_TIMEOUT_HORAS", raising=False)
    yield monkeypatch


class TestFlags:

    def test_desligado_por_default(self, env):
        assert _enabled() is False

    def test_ligado_com_env_1(self, env):
        env.setenv("BLINK_CRON_ENABLED", "1")
        assert _enabled() is True

    def test_dry_run_default_on(self, env):
        assert _dry_run_default() is True

    def test_dry_run_off_com_env_false(self, env):
        env.setenv("BLINK_CRON_DRY_RUN", "false")
        assert _dry_run_default() is False

    def test_intervalo_default_3600s(self, env):
        assert _intervalo_classificar_seg() == 3600

    def test_intervalo_custom_meia_hora(self, env):
        env.setenv("CLASSIFICAR_CADA_HORAS", "0.5")
        assert _intervalo_classificar_seg() == 1800

    def test_intervalo_minimo_60s(self, env):
        env.setenv("CLASSIFICAR_CADA_HORAS", "0.001")
        assert _intervalo_classificar_seg() == 60

    def test_intervalo_invalido_cai_no_default(self, env):
        env.setenv("CLASSIFICAR_CADA_HORAS", "abc")
        assert _intervalo_classificar_seg() == 3600


class FakeRedis:
    def __init__(self, keys=None):
        self._store = {}
        for k, v in (keys or {}).items():
            self._store[k] = v

    def scan(self, cursor=0, match=None, count=200):
        return (0, list(self._store.keys()))

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ex=None):
        self._store[key] = value


class FakeKommo:
    def __init__(self):
        self.calls = []

    def update_lead_status(self, lead_id, status_id, pipeline_id):
        self.calls.append((lead_id, status_id, pipeline_id))


class FakePipeline:
    def __init__(self, redis_client, kommo_client=None):
        self._redis = redis_client
        self.kommo = kommo_client


class TestExecutarClassificar:
    """Caminho idêntico ao endpoint, mas em loop interno."""

    def test_sem_redis_devolve_erro(self, env):
        pipeline = FakePipeline(redis_client=None)
        env.setenv("KOMMO_STATUS_A_CLASSIFICAR_ID", "999")
        res = _executar_classificar(pipeline=pipeline, dry_run=True)
        assert res["ok"] is False
        assert res["razao"] == "sem_redis"

    def test_dry_run_nao_move_mas_conta_candidatos(self, env):
        import time as _t
        env.setenv("KOMMO_STATUS_A_CLASSIFICAR_ID", "999")
        env.setenv("CLASSIFICAR_TIMEOUT_HORAS", "24")
        agora = _t.time()
        # Lead com disparo 30h atrás (excede 24h)
        r = FakeRedis({
            "blink:classificar:aguardando_resposta:42": str(int(agora - 30 * 3600)),
        })
        kommo = FakeKommo()
        pipeline = FakePipeline(redis_client=r, kommo_client=kommo)
        res = _executar_classificar(pipeline=pipeline, dry_run=True)
        assert res["ok"] is True
        assert res["dry_run"] is True
        assert res["candidatos"] == 1
        assert res["movidos"] == 0  # dry_run não move
        assert kommo.calls == []

    def test_modo_real_move_no_kommo(self, env):
        import time as _t
        env.setenv("KOMMO_STATUS_A_CLASSIFICAR_ID", "999")
        env.setenv("CLASSIFICAR_TIMEOUT_HORAS", "24")
        agora = _t.time()
        r = FakeRedis({
            "blink:classificar:aguardando_resposta:42": str(int(agora - 30 * 3600)),
        })
        kommo = FakeKommo()
        pipeline = FakePipeline(redis_client=r, kommo_client=kommo)
        res = _executar_classificar(pipeline=pipeline, dry_run=False)
        assert res["movidos"] == 1
        assert kommo.calls == [(42, 999, 8601819)]

    def test_disparo_recente_nao_move(self, env):
        import time as _t
        env.setenv("KOMMO_STATUS_A_CLASSIFICAR_ID", "999")
        env.setenv("CLASSIFICAR_TIMEOUT_HORAS", "24")
        agora = _t.time()
        r = FakeRedis({
            "blink:classificar:aguardando_resposta:99": str(int(agora - 2 * 3600)),
        })
        kommo = FakeKommo()
        pipeline = FakePipeline(redis_client=r, kommo_client=kommo)
        res = _executar_classificar(pipeline=pipeline, dry_run=False)
        assert res["candidatos"] == 0
        assert res["movidos"] == 0
        assert kommo.calls == []


class TestBootstrap:

    def test_nao_inicia_se_desligado(self, env):
        # default: BLINK_CRON_ENABLED não setado
        res = iniciar_cron(pipeline=FakePipeline(FakeRedis()))
        assert res["started"] is False
        assert "BLINK_CRON_ENABLED" in res["reason"]
        parar_cron()

    def test_inicia_quando_ligado(self, env):
        env.setenv("BLINK_CRON_ENABLED", "1")
        # Reseta estado global (módulo)
        import voice_agent.cron_interno as ci
        ci._stop_event_global = None
        ci._threads_iniciadas = []

        res = iniciar_cron(pipeline=FakePipeline(FakeRedis()))
        assert res["started"] is True
        assert "classificar" in res["workers"]
        parar_cron()

    def test_idempotente(self, env):
        env.setenv("BLINK_CRON_ENABLED", "1")
        import voice_agent.cron_interno as ci
        ci._stop_event_global = None
        ci._threads_iniciadas = []
        iniciar_cron(pipeline=FakePipeline(FakeRedis()))
        # Segunda chamada
        res2 = iniciar_cron(pipeline=FakePipeline(FakeRedis()))
        assert res2["started"] is False
        assert res2["reason"] == "ja_iniciado"
        parar_cron()


# ---------------------------------------------------------------------------
# Worker renovacao
# ---------------------------------------------------------------------------

class TestHorarioComercial:
    """Worker renovacao só roda dentro do horário comercial."""

    def test_horario_comercial_8_18(self, env):
        from voice_agent.cron_interno import _renovacao_em_horario_comercial
        # Por padrão 8-18 BRT. Função depende do tempo real → smoke test.
        r = _renovacao_em_horario_comercial()
        assert isinstance(r, bool)

    def test_intervalo_renovacao_default_15_min(self, env):
        from voice_agent.cron_interno import _intervalo_renovacao_seg
        assert _intervalo_renovacao_seg() == 900


class FakeKommoComLeads:
    def __init__(self, leads):
        self._leads = leads
        self.add_note_calls = []

    def list_active_leads(self, pipeline_id, limit):
        return self._leads

    def add_note(self, lead_id, text):
        self.add_note_calls.append((lead_id, text))


class FakeRedisInbound:
    """Redis com chave ultima_msg_paciente preenchida pra alguns leads."""
    def __init__(self, snapshots):
        # snapshots = {lead_id: epoch_ts}
        self._store = {}
        for lid, ts in snapshots.items():
            self._store[f"blink:janela:ultima_msg_paciente:{lid}"] = str(int(ts))

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ex=None):
        self._store[key] = value

    def delete(self, key):
        self._store.pop(key, None)


class TestExecutarRenovacaoVarredura:

    def test_sem_kommo_devolve_erro(self, env):
        from voice_agent.cron_interno import _executar_renovacao_varredura
        pipeline = FakePipeline(redis_client=FakeRedis(), kommo_client=None)
        res = _executar_renovacao_varredura(pipeline=pipeline, dry_run=True)
        assert res["ok"] is False
        assert res["razao"] == "sem_kommo"

    def test_lead_em_status_pos_agendado_e_ignorado(self, env):
        from voice_agent.cron_interno import _executar_renovacao_varredura
        kommo = FakeKommoComLeads([
            {"id": 1, "status_id": 101507507, "telefone": "5561999999999",
             "nome_contato": "Ana"},  # AGENDADO — pula
        ])
        pipeline = FakePipeline(redis_client=FakeRedis(), kommo_client=kommo)
        res = _executar_renovacao_varredura(pipeline=pipeline, dry_run=True)
        assert res["ok"] is True
        assert res["candidatos"] == 0
        assert res["enviados"] == 0

    def test_lead_em_pre_agendado_e_com_resposta_recente_e_processado(self, env):
        import time as _t
        from voice_agent.cron_interno import _executar_renovacao_varredura
        agora = _t.time()
        kommo = FakeKommoComLeads([
            {"id": 42, "status_id": 102560495,
             "telefone": "5561999990000", "nome_contato": "Marcela"},
        ])
        redis_cli = FakeRedisInbound({42: agora - 23 * 3600})  # 23h atrás
        pipeline = FakePipeline(redis_client=redis_cli, kommo_client=kommo)
        res = _executar_renovacao_varredura(pipeline=pipeline, dry_run=True)
        assert res["ok"] is True
        assert res["candidatos"] >= 1


class TestIniciarCronComRenovacao:

    def test_inicia_2_workers(self, env):
        env.setenv("BLINK_CRON_ENABLED", "1")
        import voice_agent.cron_interno as ci
        ci._stop_event_global = None
        ci._threads_iniciadas = []
        res = iniciar_cron(pipeline=FakePipeline(FakeRedis()))
        assert res["started"] is True
        assert "classificar" in res["workers"]
        assert "renovacao" in res["workers"]
        parar_cron()
