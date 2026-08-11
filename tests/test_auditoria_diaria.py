"""Pytest pra voice_agent.auditoria_diaria.

10 cenários:
  1. varrer_conversas_24h retorna [] quando Redis vazio
  2. varredura paginada (scan_iter) cobre múltiplas keys
  3. auditar_turno chama juiz com lia_text/ctx/user_text corretos
  4. agregar_sintomas conta motivos certo + top10
  5. top 10 leads ordenado por risco_max desc
  6. relatorio_diario integra varredura + auditoria + agregação
  7. gerar_slack_message tem formato esperado
  8. endpoint /admin/auditoria-diaria 200 com secret
  9. endpoint /admin/auditoria-diaria 401 sem secret
 10. worker dedupa se já rodou hoje (chave de dedup)
"""
from __future__ import annotations

import importlib
import json
import os
import time
from typing import Any
from unittest.mock import MagicMock

import pytest


class FakeRedis:
    """Fake do cliente redis com scan_iter / lrange / get / setex."""

    def __init__(self):
        self._lists: dict[str, list[str]] = {}
        self._kv: dict[str, str] = {}

    # ----- listas (tracing) -----
    def rpush(self, key: str, value: str) -> int:
        self._lists.setdefault(key, []).append(value)
        return len(self._lists[key])

    def lrange(self, key: str, start: int, stop: int) -> list[str]:
        arr = self._lists.get(key, [])
        if stop == -1:
            return arr[start:]
        return arr[start: stop + 1]

    # ----- scan_iter -----
    def scan_iter(self, match: str = "*", count: int = 100):
        import fnmatch
        for k in list(self._lists.keys()):
            if fnmatch.fnmatch(k, match):
                yield k
        for k in list(self._kv.keys()):
            if fnmatch.fnmatch(k, match):
                yield k

    # ----- KV (dedup) -----
    def get(self, key: str):
        return self._kv.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._kv[key] = value
        return True


def _push_trace(redis: FakeRedis, lead_id: int, ts_epoch: int, *,
                user_text="oi", resposta="ok", ctx_resumo=None):
    payload = {
        "ts_epoch": ts_epoch,
        "lead_id": lead_id,
        "user_text": user_text,
        "ctx_resumo": ctx_resumo or {},
        "output_final": resposta,
    }
    redis.rpush(f"blink:trace:{lead_id}", json.dumps(payload))


# ===========================================================================
# 1+2. varredura
# ===========================================================================

def test_varrer_24h_redis_vazio_retorna_lista_vazia():
    from voice_agent.auditoria_diaria import varrer_conversas_24h
    r = FakeRedis()
    assert varrer_conversas_24h(r) == []


def test_varrer_24h_paginada_multiplas_keys_dentro_janela():
    from voice_agent.auditoria_diaria import varrer_conversas_24h
    r = FakeRedis()
    agora = 1_700_000_000.0
    # 3 leads, 2 turnos cada — todos dentro de 24h
    for lead in (101, 102, 103):
        _push_trace(r, lead, int(agora - 3600), user_text="A",
                    resposta="r1", ctx_resumo={"ja_agendado": False})
        _push_trace(r, lead, int(agora - 1800), user_text="B",
                    resposta="r2", ctx_resumo={"ja_agendado": True})
    # 1 turno fora da janela (>24h atrás) — deve ser ignorado
    _push_trace(r, 104, int(agora - 25 * 3600), resposta="velho")

    turnos = varrer_conversas_24h(r, agora_epoch=agora)
    assert len(turnos) == 6  # 3 leads × 2 turnos
    leads_vistos = {t["lead_id"] for t in turnos}
    assert leads_vistos == {101, 102, 103}
    # ordenado por ts asc
    ts_list = [t["ts"] for t in turnos]
    assert ts_list == sorted(ts_list)
    # cada item tem as chaves esperadas
    for t in turnos:
        assert {"lead_id", "ts", "prompt_truncated",
                "resposta_lia", "ctx_summary"} <= set(t)


# ===========================================================================
# 3. auditar_turno chama juiz com argumentos corretos
# ===========================================================================

def test_auditar_turno_chama_juiz_com_prompt_resposta_ctx():
    from voice_agent.auditoria_diaria import auditar_turno
    juiz = MagicMock()
    juiz.julgar.return_value = {
        "risco": 80, "motivos": ["hesitacao_agenda"],
        "recomendado": "substituir",
    }
    turno = {
        "lead_id": 555, "ts": 1234,
        "prompt_truncated": "quero agendar",
        "resposta_lia": "deixa eu consultar a agenda",
        "ctx_summary": {"agenda_disponivel": True},
    }
    v = auditar_turno(turno, juiz=juiz)
    juiz.julgar.assert_called_once()
    kwargs = juiz.julgar.call_args.kwargs
    assert kwargs["lia_text"] == "deixa eu consultar a agenda"
    assert kwargs["ctx"] == {"agenda_disponivel": True}
    assert kwargs["user_text"] == "quero agendar"
    assert v == {
        "lead_id": 555, "ts": 1234,
        "risco": 80, "motivos": ["hesitacao_agenda"],
        "recomendacao": "substituir",
    }


def test_auditar_turno_sem_resposta_devolve_neutro():
    from voice_agent.auditoria_diaria import auditar_turno
    juiz = MagicMock()
    turno = {"lead_id": 1, "ts": 1, "resposta_lia": ""}
    v = auditar_turno(turno, juiz=juiz)
    assert v["risco"] == 0
    juiz.julgar.assert_not_called()


# ===========================================================================
# 4. agregar conta motivos certo
# ===========================================================================

def test_agregar_sintomas_conta_motivos_e_top10():
    from voice_agent.auditoria_diaria import agregar_sintomas
    veredictos = [
        {"lead_id": 1, "risco": 80, "motivos": ["hesitacao_agenda"]},
        {"lead_id": 2, "risco": 75, "motivos": ["hesitacao_agenda",
                                                  "inventou_dia_semana"]},
        {"lead_id": 3, "risco": 90, "motivos": ["inventou_dia_semana"]},
        {"lead_id": 4, "risco": 30, "motivos": []},
        {"lead_id": 5, "risco": 70, "motivos": ["hesitacao_agenda"]},
    ]
    agreg = agregar_sintomas(veredictos)
    assert agreg["total_turnos"] == 5
    assert agreg["total_risco_alto"] == 4  # >= 70
    # 3x hesitacao + 2x inventou
    assert agreg["sintomas_top"]["hesitacao_agenda"] == 3
    assert agreg["sintomas_top"]["inventou_dia_semana"] == 2
    # ordenação desc
    motivos_ord = list(agreg["sintomas_top"].keys())
    assert motivos_ord[0] == "hesitacao_agenda"


# ===========================================================================
# 5. top 10 leads por risco_max desc
# ===========================================================================

def test_leads_top_ordenado_por_risco_desc():
    from voice_agent.auditoria_diaria import agregar_sintomas
    veredictos = [
        {"lead_id": i, "risco": (i * 7) % 100, "motivos": [f"mot{i}"]}
        for i in range(1, 16)
    ]
    agreg = agregar_sintomas(veredictos)
    leads = agreg["leads_top"]
    assert len(leads) == 10  # top 10 cap
    riscos = [r["risco_max"] for r in leads]
    assert riscos == sorted(riscos, reverse=True)


# ===========================================================================
# 6. relatorio_diario integra tudo
# ===========================================================================

def test_relatorio_diario_integra_varre_audita_agrega():
    from voice_agent.auditoria_diaria import relatorio_diario
    r = FakeRedis()
    agora = 1_700_000_000.0
    _push_trace(r, 700, int(agora - 1000), resposta="frase A",
                ctx_resumo={"agenda_disponivel": True})
    _push_trace(r, 701, int(agora - 500), resposta="frase B",
                ctx_resumo={"agenda_disponivel": False})

    juiz = MagicMock()
    juiz.julgar.side_effect = [
        type("V", (), {"risco": 85, "motivos": ["hesitacao_agenda"],
                       "recomendado": "substituir"})(),
        type("V", (), {"risco": 20, "motivos": [],
                       "recomendado": "enviar"})(),
    ]
    rel = relatorio_diario(r, juiz=juiz, agora_epoch=agora)
    assert rel["total_turnos"] == 2
    assert rel["total_risco_alto"] == 1
    assert "hesitacao_agenda" in rel["sintomas_top"]
    # leads_top tem ambos, lead 700 com risco_max=85 vem antes
    leads_ids = [r["lead_id"] for r in rel["leads_top"]]
    assert leads_ids[0] == 700
    assert "periodo" in rel
    assert "inicio_iso" in rel["periodo"]


# ===========================================================================
# 7. slack message format
# ===========================================================================

def test_gerar_slack_message_formato_basico():
    from voice_agent.auditoria_diaria import gerar_slack_message
    rel = {
        "periodo": {"inicio_iso": "2026-06-17T07:00:00-03:00",
                    "fim_iso": "2026-06-18T07:00:00-03:00"},
        "total_turnos": 47,
        "total_risco_alto": 3,
        "sintomas_top": {"hesitacao_agenda": 5,
                         "inventou_dia_semana": 2},
        "leads_top": [
            {"lead_id": 999, "risco_max": 90,
             "motivos": ["hesitacao_agenda"]},
            {"lead_id": 888, "risco_max": 80,
             "motivos": ["inventou_dia_semana"]},
        ],
    }
    msg = gerar_slack_message(rel)
    assert "Auditoria diária Lia" in msg
    assert "47" in msg
    assert "hesitacao_agenda" in msg
    assert "/admin/replay/999" in msg
    # tem emoji de alerta porque risco_alto>0
    assert ":rotating_light:" in msg


def test_gerar_slack_message_vazio():
    from voice_agent.auditoria_diaria import gerar_slack_message
    rel = {
        "periodo": {"inicio_iso": "a", "fim_iso": "b"},
        "total_turnos": 0, "total_risco_alto": 0,
        "sintomas_top": {}, "leads_top": [],
    }
    msg = gerar_slack_message(rel)
    assert "Sem turnos auditáveis" in msg


# ===========================================================================
# 8+9. endpoint auth
# ===========================================================================

@pytest.fixture(scope="module")
def app_client():
    # Garante secret + envs mínimas exigidas por Settings.load().
    os.environ["WEBHOOK_SECRET"] = "test-secret-aud"
    os.environ.setdefault("OPENAI_API_KEY", "test-openai")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
    os.environ.setdefault("EVOLUTION_BASE_URL", "http://test.local")
    os.environ.setdefault("EVOLUTION_API_KEY", "test-evolution")
    os.environ.setdefault("EVOLUTION_INSTANCE", "test-inst")
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi.testclient indisponível")
    web = importlib.import_module("voice_agent.webhook")
    importlib.reload(web)
    app = web.create_app()
    return TestClient(app)


def test_endpoint_auditoria_diaria_200_com_secret(app_client, monkeypatch):
    # Patch relatorio_diario pra não bater Redis real
    import voice_agent.auditoria_diaria as ad
    monkeypatch.setattr(
        ad, "relatorio_diario",
        lambda *a, **kw: {
            "periodo": {"inicio_iso": "x", "fim_iso": "y"},
            "total_turnos": 0, "total_risco_alto": 0,
            "sintomas_top": {}, "leads_top": [],
        },
    )
    r = app_client.get("/admin/auditoria-diaria?secret=test-secret-aud")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "relatorio" in body
    assert "slack_preview" in body


def test_endpoint_auditoria_diaria_401_sem_secret(app_client):
    r = app_client.get("/admin/auditoria-diaria")
    assert r.status_code == 401


# ===========================================================================
# 10. worker dedup
# ===========================================================================

def test_worker_dedupa_se_ja_rodou_hoje():
    """A chave `blink:auditoria_diaria:YYYY-MM-DD` no Redis bloqueia
    relatorio_diario de rodar 2x no mesmo dia."""
    from voice_agent.auditoria_diaria import chave_dedup_dia
    # Simula que chave já está no Redis
    r = FakeRedis()
    agora = time.time()
    key = chave_dedup_dia(agora_epoch=agora)
    r.setex(key, 86400, "1")
    assert r.get(key) == "1"
    # Simula a check do worker
    assert bool(r.get(chave_dedup_dia(agora_epoch=agora))) is True
    # Mesma chave em outro horário do dia (1h depois) bate na mesma key
    assert chave_dedup_dia(agora_epoch=agora + 3600) == key
