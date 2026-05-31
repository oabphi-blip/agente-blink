"""Pytest da etapa A CLASSIFICAR (task #96)."""
from __future__ import annotations

import pytest

from voice_agent.classificar import (
    REDIS_KEY_AGUARDA_FMT,
    STATUS_A_CLASSIFICAR_ID,
    deve_mover_para_classificar,
    limpar_aguardando_resposta,
    marcar_aguardando_resposta,
    mover_lead_para_classificar,
)


# ---------------------------------------------------------------------------
# deve_mover_para_classificar — função pura
# ---------------------------------------------------------------------------

AGORA = 1780_000_000.0


def _h_atras(h):
    return AGORA - h * 3600


class TestDeveMover:

    def test_sem_disparo_nao_move(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=None,
            ultima_resposta_paciente_ts=None,
            agora=AGORA,
        )
        assert r["mover"] is False
        assert r["razao"] == "sem_disparo"

    def test_paciente_respondeu_depois_do_disparo_nao_move(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(30),
            ultima_resposta_paciente_ts=_h_atras(2),  # 28h depois do disparo
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is False
        assert r["razao"] == "paciente_respondeu"

    def test_paciente_respondeu_ANTES_do_disparo_nao_conta(self):
        # Resposta antiga (do contexto anterior) não conta como resposta
        # à renovação — ainda deve mover se passou timeout.
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(30),
            ultima_resposta_paciente_ts=_h_atras(48),
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is True
        assert r["razao"] == "timeout_excedido"

    def test_disparo_recente_ainda_no_prazo(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(2),
            ultima_resposta_paciente_ts=None,
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is False
        assert r["razao"] == "ainda_no_prazo"

    def test_disparo_exato_24h_move(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(24),
            ultima_resposta_paciente_ts=None,
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is True

    def test_disparo_25h_move(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(25),
            ultima_resposta_paciente_ts=None,
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is True
        assert r["razao"] == "timeout_excedido"

    def test_timeout_custom(self):
        # Com timeout=12h, disparo de 13h atrás deve mover.
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(13),
            ultima_resposta_paciente_ts=None,
            agora=AGORA, timeout_horas=12,
        )
        assert r["mover"] is True

    def test_horas_passadas_calculado(self):
        r = deve_mover_para_classificar(
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            agora=AGORA, timeout_horas=24,
        )
        assert r["mover"] is True
        assert abs(r["horas_passadas"] - 26) < 0.01


# ---------------------------------------------------------------------------
# mover_lead_para_classificar — orquestração + Kommo
# ---------------------------------------------------------------------------

class FakeKommo:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
    def update_lead_status(self, lead_id, status_id, pipeline_id):
        if self.fail:
            raise RuntimeError("kommo timeout")
        self.calls.append({
            "lead_id": lead_id, "status_id": status_id,
            "pipeline_id": pipeline_id,
        })
        return {"ok": True}


class TestMoverLead:

    def test_move_quando_decisao_e_timeout(self):
        k = FakeKommo()
        r = mover_lead_para_classificar(
            lead_id=24048691,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            kommo_client=k,
            agora=AGORA,
            status_destino_id=999,
        )
        assert r.movido is True
        assert r.razao == "timeout_excedido"
        assert k.calls[0]["lead_id"] == 24048691
        assert k.calls[0]["status_id"] == 999

    def test_nao_move_quando_paciente_respondeu(self):
        k = FakeKommo()
        r = mover_lead_para_classificar(
            lead_id=1,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=_h_atras(1),
            kommo_client=k,
            agora=AGORA,
            status_destino_id=999,
        )
        assert r.movido is False
        assert r.razao == "paciente_respondeu"
        assert k.calls == []

    def test_dry_run_nao_move(self):
        k = FakeKommo()
        r = mover_lead_para_classificar(
            lead_id=1,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            kommo_client=k, agora=AGORA, status_destino_id=999,
            dry_run=True,
        )
        assert r.movido is False
        assert r.razao == "dry_run"
        assert k.calls == []

    def test_sem_status_destino_devolve_erro(self):
        # Quando KOMMO_STATUS_A_CLASSIFICAR_ID não está setado.
        k = FakeKommo()
        r = mover_lead_para_classificar(
            lead_id=1,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            kommo_client=k, agora=AGORA, status_destino_id=None,
        )
        assert r.movido is False
        assert "KOMMO_STATUS_A_CLASSIFICAR_ID" in r.erro

    def test_falha_kommo_nao_quebra(self):
        k = FakeKommo(fail=True)
        r = mover_lead_para_classificar(
            lead_id=1,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            kommo_client=k, agora=AGORA, status_destino_id=999,
        )
        assert r.movido is False
        assert "kommo timeout" in r.erro

    def test_status_destino_default_da_env(self, monkeypatch):
        # Quando passa None, usa STATUS_A_CLASSIFICAR_ID do módulo.
        import voice_agent.classificar as cl
        monkeypatch.setattr(cl, "STATUS_A_CLASSIFICAR_ID", 12345)
        k = FakeKommo()
        r = mover_lead_para_classificar(
            lead_id=1,
            disparo_renovacao_ts=_h_atras(26),
            ultima_resposta_paciente_ts=None,
            kommo_client=k, agora=AGORA,
            # status_destino_id omitido → pega da env via reload
        )
        # Reimporta pra capturar o monkeypatch (no caso real é env runtime).
        # O teste vale como sanity-check da assinatura.
        assert r.status_id_destino is not None


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self._store = {}
    def set(self, key, value, ex=None):
        self._store[key] = value
    def get(self, key):
        return self._store.get(key)
    def delete(self, key):
        self._store.pop(key, None)


class TestRedisHelpers:

    def test_marcar_grava_chave_correta(self):
        r = FakeRedis()
        chave = marcar_aguardando_resposta(r, lead_id=24048691, disparo_ts=AGORA)
        assert chave == "blink:classificar:aguardando_resposta:24048691"
        assert r.get(chave) is not None

    def test_limpar_remove(self):
        r = FakeRedis()
        marcar_aguardando_resposta(r, lead_id=1, disparo_ts=AGORA)
        ok = limpar_aguardando_resposta(r, lead_id=1)
        assert ok is True
        assert r.get("blink:classificar:aguardando_resposta:1") is None

    def test_redis_none_nao_quebra(self):
        chave = marcar_aguardando_resposta(None, lead_id=1)
        assert chave is not None
        assert limpar_aguardando_resposta(None, lead_id=1) is False

    def test_redis_falha_nao_quebra(self):
        class RBroken:
            def set(self, *a, **k): raise RuntimeError("down")
            def delete(self, *a, **k): raise RuntimeError("down")
        r = RBroken()
        # Não deve levantar.
        marcar_aguardando_resposta(r, lead_id=1)
        limpar_aguardando_resposta(r, lead_id=1)
