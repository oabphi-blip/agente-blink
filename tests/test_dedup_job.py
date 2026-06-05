"""Blindagem do dedup_job (task #229)."""
import json
import time
from unittest.mock import MagicMock

import pytest

from voice_agent.dedup_job import (
    gerar_job_id, _key, _salvar_estado, get_status,
    calcular_eta, JOB_KEY_PREFIX,
)


def test_gerar_job_id_unico_e_curto():
    a = gerar_job_id()
    b = gerar_job_id()
    assert a != b
    assert len(a) == 8
    assert all(c in "0123456789abcdef" for c in a)


def test_key_prefixa_namespace_blink():
    assert _key("xyz").startswith(JOB_KEY_PREFIX)
    assert "xyz" in _key("xyz")


def test_salvar_e_recuperar_estado():
    fake_redis = MagicMock()
    storage = {}

    def fake_setex(k, ttl, v):
        storage[k] = v
        return True

    def fake_get(k):
        return storage.get(k)

    fake_redis.setex.side_effect = fake_setex
    fake_redis.get.side_effect = fake_get

    estado = {"status": "running", "total_lidos": 50}
    _salvar_estado(fake_redis, "abc", estado)
    out = get_status(fake_redis, "abc")
    assert out["status"] == "running"
    assert out["total_lidos"] == 50
    # campo atualizado_em deve ter sido injetado
    assert "atualizado_em" in out


def test_get_status_inexistente_devolve_none():
    fake_redis = MagicMock()
    fake_redis.get.return_value = None
    assert get_status(fake_redis, "nao-existe") is None


def test_get_status_redis_none_devolve_none():
    assert get_status(None, "qualquer") is None


def test_salvar_estado_redis_none_nao_levanta():
    # Não deve falhar — só ignora
    _salvar_estado(None, "x", {"a": 1})


def test_salvar_estado_funciona_com_bytes():
    """Redis às vezes devolve bytes em vez de str."""
    fake_redis = MagicMock()
    storage = {}
    fake_redis.setex.side_effect = (
        lambda k, ttl, v: storage.__setitem__(k, v.encode("utf-8"))
    )
    fake_redis.get.side_effect = lambda k: storage.get(k)
    _salvar_estado(fake_redis, "abc", {"x": 1})
    out = get_status(fake_redis, "abc")
    assert out["x"] == 1


# ---------------------------------------------------------------------------
# ETA
# ---------------------------------------------------------------------------

def test_eta_zero_pra_estado_vazio():
    assert calcular_eta({}) is None


def test_eta_zero_pra_sem_progresso():
    estado = {"iniciado_em": int(time.time()),
              "total_lidos": 0, "max_leads": 500}
    assert calcular_eta(estado) is None


def test_eta_calcula_em_caso_real():
    """Iniciou há 60s, leu 100 leads, max=500 → ETA ~240s."""
    estado = {
        "iniciado_em": int(time.time()) - 60,
        "total_lidos": 100,
        "max_leads": 500,
    }
    eta = calcular_eta(estado)
    assert eta is not None
    # ritmo = 100/60 = 1.67/s, restantes=400 → 240s
    assert 200 <= eta <= 300


def test_eta_pra_quase_concluido():
    estado = {
        "iniciado_em": int(time.time()) - 60,
        "total_lidos": 495,
        "max_leads": 500,
    }
    eta = calcular_eta(estado)
    assert eta is not None
    assert eta < 10  # poucos segundos
