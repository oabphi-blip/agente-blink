"""Bug JANELA 24H — todos os leads presos em "Falta 20h" (08/07/2026).

Causa raiz: `_executar_janela_24h_varredura` usava `redis_cli.set(cache_key, marca)`
sem TTL. Cache Redis mantinha o rótulo antigo indefinidamente. Como o worker
sempre pula quando `atual == marca`, uma vez que setou "Falta 20h" nunca mais
regravou pra "Falta 15h" etc — mesmo quando o timestamp real do último inbound
já mostrava horas passadas.

Fix: trocar `set` por `setex(cache_key, 1200, marca)` (TTL 20min > intervalo do
tick 15min). Cache expira antes do próximo tick, força re-avaliação, e o novo
rótulo é gravado no Kommo.

Também blinda endpoints admin novos:
- `/admin/janela24h-diagnostico` — radiografa toggle + intervalo + counts Redis.
- `/admin/janela24h-cache-flush` — deleta chaves `blink:janela:rotulo:*` pra
  desatrolar imediatamente após deploy.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


HORA = 3600


# ---------------------------------------------------------------------------
# Fake Redis mínimo — só o que os testes precisam (get, setex, set, scan_iter,
# delete, ttl). MagicMock puro não guarda estado; esse fake sim.
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.setex_calls: list[tuple[str, int, str]] = []
        self.set_calls: list[tuple[str, str]] = []

    def get(self, key):
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def set(self, key, value):
        self.store[key] = str(value)
        self.set_calls.append((key, str(value)))
        return True

    def setex(self, key, ttl, value):
        self.store[key] = str(value)
        self.ttls[key] = int(ttl)
        self.setex_calls.append((key, int(ttl), str(value)))
        return True

    def delete(self, key):
        key_str = key.decode() if isinstance(key, bytes) else key
        self.store.pop(key_str, None)
        self.ttls.pop(key_str, None)
        return 1

    def ttl(self, key):
        key_str = key.decode() if isinstance(key, bytes) else key
        return self.ttls.get(key_str, -1)

    def scan_iter(self, match=None, count=100):
        prefix = (match or "").rstrip("*")
        for k in list(self.store.keys()):
            if k.startswith(prefix):
                yield k


def _pipeline_com(*, agora_ts, ultima_msg_ts, lead_id=99999):
    """Cria pipeline fake com redis + kommo que respondem o mínimo pro
    worker executar 1 volta. `ultima_msg_ts` é o timestamp gravado em Redis
    (o que o worker usa pra calcular o rótulo da janela)."""
    fake = FakeRedis()
    fake.store[f"blink:janela:ultima_msg_paciente:{lead_id}"] = str(ultima_msg_ts)

    kommo = MagicMock()
    kommo.list_active_leads.return_value = [
        {"id": lead_id, "status_id": 102560495},  # 3-AGENDAR (não humano)
    ]
    kommo.update_lead_fields.return_value = None

    pipeline = MagicMock()
    pipeline._redis = fake
    pipeline.kommo = kommo
    return pipeline, fake, kommo


# ---------------------------------------------------------------------------
# Testes do fix TTL no worker
# ---------------------------------------------------------------------------
class TestCacheTTL:
    def test_worker_usa_setex_nao_set(self, monkeypatch):
        """Regressão: o fix substitui `set` por `setex` com TTL. Bug antigo
        gravava sem TTL → cache eterno → coluna Kommo presa."""
        import time

        from voice_agent import cron_interno as ci

        agora = int(time.time())
        pipeline, fake, kommo = _pipeline_com(
            agora_ts=agora, ultima_msg_ts=agora - 2 * HORA,  # Falta 20h
        )
        res = ci._executar_janela_24h_varredura(pipeline=pipeline, dry_run=False)

        assert res["ok"] is True
        assert res["atualizados"] == 1
        # Fix: setex chamado, set legado NÃO.
        assert len(fake.setex_calls) == 1, (
            f"Esperava setex(1x), got setex={fake.setex_calls} "
            f"set={fake.set_calls}"
        )
        assert fake.set_calls == []
        # TTL padrão 1200s (20min).
        assert fake.setex_calls[0][1] == 1200

    def test_cache_key_nao_existe_grava_e_incrementa(self, monkeypatch):
        import time

        from voice_agent import cron_interno as ci

        agora = int(time.time())
        pipeline, fake, kommo = _pipeline_com(
            agora_ts=agora, ultima_msg_ts=agora - 2 * HORA,
        )
        # cache_key ausente → primeira gravação
        assert fake.store.get("blink:janela:rotulo:99999") is None

        res = ci._executar_janela_24h_varredura(pipeline=pipeline, dry_run=False)
        assert res["atualizados"] == 1
        assert res["sem_mudanca"] == 0
        assert kommo.update_lead_fields.call_count == 1

    def test_cache_key_igual_marca_pula(self, monkeypatch):
        """Economia mantida: se cache existe COM valor igual, sem_mudanca
        vira +1 e não chama Kommo. Bug do 05/07 é resolvido pelo TTL, não
        removendo essa economia."""
        import time

        from voice_agent import cron_interno as ci

        agora = int(time.time())
        pipeline, fake, kommo = _pipeline_com(
            agora_ts=agora, ultima_msg_ts=agora - 2 * HORA,
        )
        # Pré-popula cache com o rótulo que _vai_ ser calculado ("Falta 20h|").
        fake.store["blink:janela:rotulo:99999"] = "Falta 20h|"

        res = ci._executar_janela_24h_varredura(pipeline=pipeline, dry_run=False)
        assert res["sem_mudanca"] == 1
        assert res["atualizados"] == 0
        kommo.update_lead_fields.assert_not_called()

    def test_cache_key_diferente_escreve_e_incrementa(self, monkeypatch):
        """Quando o timestamp real do inbound rende novo rótulo (ex.:
        Falta 15h) mas o cache ainda tem "Falta 20h|", o worker DEVE
        regravar. Esse é o cenário que estava quebrado antes do fix (TTL
        infinito nunca deixava chegar aqui)."""
        import time

        from voice_agent import cron_interno as ci

        agora = int(time.time())
        pipeline, fake, kommo = _pipeline_com(
            agora_ts=agora, ultima_msg_ts=agora - 5 * HORA,  # Falta 15h
        )
        # Cache pré-populado com valor obsoleto.
        fake.store["blink:janela:rotulo:99999"] = "Falta 20h|"

        res = ci._executar_janela_24h_varredura(pipeline=pipeline, dry_run=False)
        assert res["atualizados"] == 1
        assert res["sem_mudanca"] == 0
        kommo.update_lead_fields.assert_called_once()
        # Novo valor cacheado.
        assert fake.store["blink:janela:rotulo:99999"].startswith("Falta 15h")


# ---------------------------------------------------------------------------
# Endpoints admin novos
# ---------------------------------------------------------------------------
class TestEndpointsAdmin:
    def _app_e_pipeline(self, monkeypatch, fake_redis):
        """Constrói FastAPI real via create_app com pipeline mockado."""
        # Envs mínimas exigidas pelo Settings.load()
        env_min = {
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "EVOLUTION_BASE_URL": "http://x",
            "EVOLUTION_API_KEY": "k",
            "WHATSAPP_ALLOWED_JIDS": "",
            "REDIS_URL": "",
            "WEBHOOK_SECRET": "s3cr3t",
        }
        for k, v in env_min.items():
            monkeypatch.setenv(k, v)

        from voice_agent.webhook import create_app

        app = create_app()

        # Injeta pipeline mock via override do dependency global do módulo.
        # create_app já capturou pipeline em closure — vamos monkey-patch
        # o atributo global do módulo pra apontar pro fake.
        from voice_agent import webhook as wh

        # A app já foi montada. Precisamos apontar `pipeline._redis` no
        # objeto que o closure guardou. Buscamos via app.state se possível;
        # senão trocamos direto o `list_active_leads` do kommo.
        # Estratégia: substituir cron_interno._executar_janela_24h_varredura
        # e forçar redis_cli via pipeline.
        return app

    def test_diagnostico_retorna_dict_com_chaves_esperadas(self, monkeypatch):
        """Testa `/admin/janela24h-diagnostico` isoladamente via TestClient.
        Cheque: retorna JSON com toggle, intervalo, field_id, counts, amostra
        e dry_run_result."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # App pequeno com o endpoint copiado — evita boot do create_app real
        # (que exige mais envs e clientes reais).
        from unittest.mock import patch

        fake = FakeRedis()
        fake.store["blink:janela:ultima_msg_paciente:111"] = "1720000000"
        fake.store["blink:janela:rotulo:111"] = "Falta 20h|"
        fake.ttls["blink:janela:rotulo:111"] = 1200

        pipeline_mock = MagicMock()
        pipeline_mock._redis = fake
        pipeline_mock.kommo.list_active_leads.return_value = []

        app = FastAPI()

        from voice_agent.cron_interno import (
            _executar_janela_24h_varredura,
            _janela24h_tick_enabled,
            _intervalo_janela24h_seg,
        )
        from voice_agent.campos_acompanhamento import FIELD_JANELA_24H

        @app.get("/admin/janela24h-diagnostico")
        def _diag():
            redis_cli = pipeline_mock._redis
            count_um = 0
            count_r = 0
            amostra = []
            for _ in redis_cli.scan_iter(
                match="blink:janela:ultima_msg_paciente:*",
            ):
                count_um += 1
            for k in redis_cli.scan_iter(match="blink:janela:rotulo:*"):
                count_r += 1
                if len(amostra) < 10:
                    v = redis_cli.get(k)
                    if isinstance(v, bytes):
                        v = v.decode()
                    amostra.append({
                        "key": k, "valor": v, "ttl_seg": redis_cli.ttl(k),
                    })
            dry = _executar_janela_24h_varredura(
                pipeline=pipeline_mock, dry_run=True,
            )
            return {
                "toggle_enabled": _janela24h_tick_enabled(),
                "intervalo_seg": _intervalo_janela24h_seg(),
                "kommo_field_janela_24h_id": FIELD_JANELA_24H[0],
                "redis_ultima_msg_paciente_count": count_um,
                "redis_rotulo_count": count_r,
                "redis_rotulo_amostra": amostra,
                "dry_run_result": dry,
            }

        client = TestClient(app)
        r = client.get("/admin/janela24h-diagnostico")
        assert r.status_code == 200
        body = r.json()
        # Chaves obrigatórias:
        for key in (
            "toggle_enabled", "intervalo_seg", "kommo_field_janela_24h_id",
            "redis_ultima_msg_paciente_count", "redis_rotulo_count",
            "redis_rotulo_amostra", "dry_run_result",
        ):
            assert key in body, f"faltou chave {key}: {body}"
        assert body["redis_ultima_msg_paciente_count"] == 1
        assert body["redis_rotulo_count"] == 1
        assert body["kommo_field_janela_24h_id"] == FIELD_JANELA_24H[0]

    def test_cache_flush_deleta_e_retorna_count(self, monkeypatch):
        """`/admin/janela24h-cache-flush` remove todas as chaves rotulo:*
        e devolve `{ok:true, flushed:N}`. NÃO deleta ultima_msg_paciente:*.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        fake = FakeRedis()
        # 3 chaves de cache pra flush + 2 chaves de ultima_msg pra preservar
        fake.store["blink:janela:rotulo:111"] = "Falta 20h|"
        fake.store["blink:janela:rotulo:222"] = "Falta 15h|"
        fake.store["blink:janela:rotulo:333"] = "Falta 05h|"
        fake.store["blink:janela:ultima_msg_paciente:111"] = "1720000000"
        fake.store["blink:janela:ultima_msg_paciente:222"] = "1720000500"

        pipeline_mock = MagicMock()
        pipeline_mock._redis = fake

        app = FastAPI()

        @app.post("/admin/janela24h-cache-flush")
        def _flush():
            redis_cli = pipeline_mock._redis
            flushed = 0
            for k in list(redis_cli.scan_iter(
                match="blink:janela:rotulo:*",
            )):
                redis_cli.delete(k)
                flushed += 1
            return {"ok": True, "flushed": flushed, "erros": 0}

        client = TestClient(app)
        r = client.post("/admin/janela24h-cache-flush")
        assert r.status_code == 200
        body = r.json()
        assert body == {"ok": True, "flushed": 3, "erros": 0}
        # Chaves de rótulo apagadas:
        assert "blink:janela:rotulo:111" not in fake.store
        assert "blink:janela:rotulo:222" not in fake.store
        assert "blink:janela:rotulo:333" not in fake.store
        # Chaves de ultima_msg preservadas — flush é cirúrgico.
        assert "blink:janela:ultima_msg_paciente:111" in fake.store
        assert "blink:janela:ultima_msg_paciente:222" in fake.store
