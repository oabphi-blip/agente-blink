"""Testes do SLO board (voice_agent/slo.py + endpoints /admin/slo).

8 cenários:
1. hallucination_rate calculado corretamente
2. latency p99 calculado corretamente
3. tool_call_success_rate calculado corretamente
4. error_budget classifica warning/burnt
5. janelas 24h e 7d retornam chaves diferentes
6. Redis vazio → defaults None (sem mentir)
7. endpoint HTML retorna 200 com secret + corpo contém "SLO"
8. endpoint .json sem secret retorna 401 + com secret tem keys esperadas
"""
from __future__ import annotations

import json
import os
import time
from typing import Iterable
from unittest.mock import MagicMock

import pytest


# Garante secret estável pros testes ANTES de qualquer import do app
os.environ.setdefault("WEBHOOK_SECRET", "test-secret-slo")


# -----------------------------------------------------------------------
# Fake Redis — implementa só o que slo.py usa (scan_iter, lrange, get)
# -----------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.strings: dict[str, str] = {}

    def scan_iter(self, match: str = "*") -> Iterable[str]:
        import fnmatch
        keys = set(self.lists.keys()) | set(self.strings.keys())
        return [k for k in keys if fnmatch.fnmatch(k, match)]

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        lst = self.lists.get(key, [])
        # Redis semantics: -1 = último
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    def get(self, key: str):
        return self.strings.get(key)

    # Helpers de teste
    def add_trace(self, lead_id: int, trace: dict):
        key = f"blink:trace:{lead_id}"
        self.lists.setdefault(key, []).append(json.dumps(trace))

    def add_wamid(self, wamid: str, status: str):
        self.strings[f"blink:wamid:status:{wamid}"] = status

    def add_health(self, yyyymmdd: str, ok: int, fail: int):
        self.strings[f"blink:func:health:{yyyymmdd}:ok"] = str(ok)
        self.strings[f"blink:func:health:{yyyymmdd}:fail"] = str(fail)


def _ts_recent(minutes_ago: float = 1.0) -> int:
    return int(time.time() - minutes_ago * 60)


def _ts_old(days_ago: float = 30.0) -> int:
    return int(time.time() - days_ago * 86400)


# -----------------------------------------------------------------------
# 1. Hallucination rate
# -----------------------------------------------------------------------

def test_1_hallucination_rate():
    from voice_agent.slo import calcular_slos_24h
    r = FakeRedis()
    # 10 turnos recentes: 2 com filtro, 8 limpos
    for i in range(2):
        r.add_trace(100 + i, {
            "ts_epoch": _ts_recent(),
            "filtros_disparados": ["_viola_oferta_apos_agendado"],
            "elapsed_ms": 500,
            "tools_chamadas": [],
        })
    for i in range(8):
        r.add_trace(200 + i, {
            "ts_epoch": _ts_recent(),
            "filtros_disparados": [],
            "elapsed_ms": 400,
            "tools_chamadas": [],
        })
    s = calcular_slos_24h(r, kommo_client=None)
    assert s["conversations_total"] == 10
    assert s["turnos_com_filtro"] == 2
    assert s["hallucination_rate"] == 20.0  # 2/10 = 20%


# -----------------------------------------------------------------------
# 2. Latency p99
# -----------------------------------------------------------------------

def test_2_latency_p99():
    from voice_agent.slo import calcular_slos_24h
    r = FakeRedis()
    # 100 valores: 1..100 → p99 deve ser 99 ou 100 (perto do máximo).
    # Garante que p99 não é só "média" — pega o tail real.
    for i, lat in enumerate(range(1, 101)):
        r.add_trace(i, {
            "ts_epoch": _ts_recent(),
            "filtros_disparados": [],
            "elapsed_ms": lat,
            "tools_chamadas": [],
        })
    s = calcular_slos_24h(r, kommo_client=None)
    # nearest-rank NIST: ceil(0.99 * 100) - 1 = 98 → arr[98] = 99
    assert s["response_latency_p99"] in (99, 100)
    # E p99 deve ser drasticamente maior que a mediana (50)
    assert s["response_latency_p99"] > 50


# -----------------------------------------------------------------------
# 3. Tool call success rate
# -----------------------------------------------------------------------

def test_3_tool_call_success_rate():
    from voice_agent.slo import calcular_slos_24h
    r = FakeRedis()
    # 4 chamadas: 3 ok, 1 fail
    r.add_trace(1, {
        "ts_epoch": _ts_recent(),
        "filtros_disparados": [],
        "elapsed_ms": 100,
        "tools_chamadas": [
            {"name": "oferecer_slot", "ok": True},
            {"name": "gravar_agendamento_medware", "ok": True},
        ],
    })
    r.add_trace(2, {
        "ts_epoch": _ts_recent(),
        "filtros_disparados": [],
        "elapsed_ms": 200,
        "tools_chamadas": [
            {"name": "oferecer_slot", "ok": True},
            {"name": "gravar_agendamento_medware", "ok": False},
        ],
    })
    s = calcular_slos_24h(r, kommo_client=None)
    assert s["tool_total"] == 4
    assert s["tool_ok"] == 3
    assert s["tool_call_success_rate"] == 75.0


# -----------------------------------------------------------------------
# 4. Error budget classifica warning / burnt
# -----------------------------------------------------------------------

def test_4_error_budget_warning_burnt():
    from voice_agent.slo import error_budget_status, SLO_HALLUCINATION_PCT_MAX

    # Saudável: hallucination 0.5% (< 1% alvo)
    healthy = error_budget_status(slos={
        "hallucination_rate": 0.5,
        "agent_uptime_pct": 99.9,
        "response_latency_p99": 1000,
        "message_delivery_rate": 99.0,
        "tool_call_success_rate": 99.0,
    })
    assert healthy["status"] == "healthy"
    assert healthy["dimensoes"]["hallucination"] == "healthy"

    # Warning: hallucination 1.5% (entre 1% e 2%)
    warning = error_budget_status(slos={
        "hallucination_rate": 1.5,
        "agent_uptime_pct": 99.5,
        "response_latency_p99": 1000,
        "message_delivery_rate": 99.0,
        "tool_call_success_rate": 99.0,
    })
    assert warning["dimensoes"]["hallucination"] == "warning"
    assert warning["status"] in ("warning", "burnt")

    # Burnt: hallucination 10% (>> 2x alvo)
    burnt = error_budget_status(slos={
        "hallucination_rate": 10.0,
        "agent_uptime_pct": 99.9,
        "response_latency_p99": 1000,
        "message_delivery_rate": 99.0,
        "tool_call_success_rate": 99.0,
    })
    assert burnt["dimensoes"]["hallucination"] == "burnt"
    assert burnt["status"] == "burnt"
    assert burnt["burn_rate"] >= 1.0
    # minutos_ate_burn deve ser finito e razoável
    assert burnt["minutos_ate_burn"] is not None
    assert burnt["minutos_ate_burn"] >= 0


# -----------------------------------------------------------------------
# 5. Janelas 24h e 7d retornam labels diferentes
# -----------------------------------------------------------------------

def test_5_janela_24h_vs_7d():
    from voice_agent.slo import (
        calcular_slos_24h, calcular_slos_7d,
        JANELA_24H_SEG, JANELA_7D_SEG,
    )
    r = FakeRedis()
    # 1 turno recente (entra em 24h E em 7d)
    r.add_trace(1, {
        "ts_epoch": _ts_recent(),
        "filtros_disparados": [],
        "elapsed_ms": 100,
        "tools_chamadas": [],
    })
    # 1 turno de 3 dias atrás (só entra em 7d)
    r.add_trace(2, {
        "ts_epoch": int(time.time() - 3 * 86400),
        "filtros_disparados": ["_viola_x"],
        "elapsed_ms": 200,
        "tools_chamadas": [],
    })
    s24 = calcular_slos_24h(r, None)
    s7 = calcular_slos_7d(r, None)
    assert s24["janela_label"] == "24h"
    assert s7["janela_label"] == "7d"
    assert s24["janela_seg"] == JANELA_24H_SEG
    assert s7["janela_seg"] == JANELA_7D_SEG
    # 24h: 1 turno. 7d: 2 turnos.
    assert s24["conversations_total"] == 1
    assert s7["conversations_total"] == 2
    # conversations_total_24h só populado em janela 24h
    assert s24["conversations_total_24h"] == 1
    assert s7["conversations_total_24h"] is None


# -----------------------------------------------------------------------
# 6. Redis vazio → defaults None
# -----------------------------------------------------------------------

def test_6_redis_vazio_retorna_none():
    from voice_agent.slo import calcular_slos_24h, error_budget_status
    r = FakeRedis()
    s = calcular_slos_24h(r, kommo_client=None)
    assert s["conversations_total"] == 0
    assert s["hallucination_rate"] is None
    assert s["response_latency_p99"] is None
    assert s["tool_call_success_rate"] is None
    assert s["message_delivery_rate"] is None
    assert s["agent_uptime_pct"] is None
    assert s["escalations_to_human"] is None  # kommo None → None

    eb = error_budget_status(slos=s)
    # Sem dados, status deve ser "no_data" ou "healthy" (não burnt)
    assert eb["status"] in ("no_data", "healthy", "warning")
    assert eb["dimensoes"]["hallucination"] == "no_data"


# -----------------------------------------------------------------------
# 7+8. Endpoints HTML + JSON
# -----------------------------------------------------------------------

@pytest.fixture
def client():
    """FastAPI TestClient com app real, pipeline mockado e secret estável."""
    # Garante envs mínimas pra Settings.load não explodir
    os.environ.setdefault("WEBHOOK_SECRET", "test-secret-slo")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
    os.environ.setdefault("EVOLUTION_BASE_URL", "http://localhost")
    os.environ.setdefault("EVOLUTION_API_KEY", "fake")
    os.environ.setdefault("EVOLUTION_INSTANCE", "test")
    os.environ.setdefault("EVOLUTION_DEFAULT_INSTANCE", "test")

    from fastapi.testclient import TestClient
    from voice_agent.webhook import create_app

    app = create_app()
    return TestClient(app)


def test_7_endpoint_html_com_secret_retorna_200_com_SLO(client):
    resp = client.get(
        "/admin/slo",
        params={"secret": os.environ["WEBHOOK_SECRET"]},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "SLO" in body
    # Algumas verificações de conteúdo do dashboard
    assert "Hallucination" in body or "hallucination" in body.lower()
    assert "<html" in body.lower() or "<!doctype" in body.lower()


def test_8_endpoint_json_401_sem_secret_e_keys_com_secret(client):
    # Sem secret → 401
    resp = client.get("/admin/slo.json")
    assert resp.status_code == 401

    # Com secret → 200 + keys esperadas
    resp_ok = client.get(
        "/admin/slo.json",
        params={"secret": os.environ["WEBHOOK_SECRET"]},
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert "slos_24h" in data
    assert "slos_7d" in data
    assert "error_budget" in data
    assert "status" in data["error_budget"]
    assert "burn_rate" in data["error_budget"]
    assert "dimensoes" in data["error_budget"]
