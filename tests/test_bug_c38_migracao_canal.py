"""Bug C-38 — leads em canais Kommo não vinculados ficam fantasma.

Wire de `voice_agent/migracao_canal.py::talvez_disparar_migracao_canal` no
handler /kommo. Este pytest exercita a lógica pura (sem FastAPI, sem rede
real), mockando Kommo/Meta/Redis.

Cenários cobertos:

1. Lead vazio em 0-ETAPA ENTRADA → dispara migração + nota + desativa IA.
2. Mesmo lead 2x em 24h → 2ª ignorada por dedup Redis.
3. Lead com nota já existente (canal reconhecido) → NÃO dispara.
4. Lead não em 96441724 (etapa diferente) → NÃO dispara.
5. Toggle LIA_MIGRACAO_CANAL_ENABLED=0 → NÃO dispara.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from voice_agent.migracao_canal import (
    STATUS_ID_ETAPA_ENTRADA,
    lead_candidato_migracao_canal_novo,
    talvez_disparar_migracao_canal,
)


# ---------------------------------------------------------------- fakes

class FakeRedis:
    """In-memory stand-in for Redis (exists + setex)."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.calls_setex: list[tuple] = []

    def exists(self, key):
        return 1 if key in self.store else 0

    def setex(self, key, ttl, value):
        self.store[key] = str(value)
        self.calls_setex.append((key, int(ttl), value))
        return True


def _make_kommo_mock(
    *,
    status_id: int,
    custom_fields_values=None,
    notes=None,
    telefone: str | None = "5561999990000",
):
    """Kommo mock que satisfaz a superfície usada pelo orquestrador."""
    kc = MagicMock()
    kc.get_lead.return_value = {
        "id": 999,
        "status_id": status_id,
        "custom_fields_values": custom_fields_values,
    }
    kc.get_lead_notes.return_value = notes or []
    kc.get_lead_main_phone.return_value = telefone
    kc.add_note.return_value = True
    kc.update_lead_fields.return_value = True
    return kc


def _make_wa_mock(wamid: str = "wamid.TEST_FAKE_123"):
    wa = MagicMock()
    wa.send_text.return_value = {
        "messaging_product": "whatsapp",
        "messages": [{"id": wamid}],
    }
    return wa


@pytest.fixture(autouse=True)
def _limpa_toggle(monkeypatch):
    """Cada teste começa com toggle no default (ON via _or '1')."""
    monkeypatch.delenv("LIA_MIGRACAO_CANAL_ENABLED", raising=False)
    yield


# ---------------------------------------------------------------- helper puro

class TestHeuristicaC38:
    def test_padrao_exato_e_candidato(self):
        assert lead_candidato_migracao_canal_novo(
            status_id=STATUS_ID_ETAPA_ENTRADA,
            custom_fields=[],
            notes_count=0,
        ) is True

    def test_cf_preenchido_nao_candidato(self):
        assert lead_candidato_migracao_canal_novo(
            status_id=STATUS_ID_ETAPA_ENTRADA,
            custom_fields=[{"field_id": 1245125, "values": [{"value": "Asa Norte"}]}],
            notes_count=0,
        ) is False

    def test_com_notas_nao_candidato(self):
        assert lead_candidato_migracao_canal_novo(
            status_id=STATUS_ID_ETAPA_ENTRADA,
            custom_fields=[],
            notes_count=1,
        ) is False

    def test_status_diferente_nao_candidato(self):
        assert lead_candidato_migracao_canal_novo(
            status_id=101508307,  # 2.LEADS FRIO
            custom_fields=[],
            notes_count=0,
        ) is False


# --------------------------------------------------- 5 cenários pedidos

def test_cenario1_lead_vazio_0_entrada_dispara_migracao():
    """Lead vazio em 0-ENTRADA + zero notas → dispara + nota + desativa IA."""
    redis = FakeRedis()
    kommo = _make_kommo_mock(status_id=STATUS_ID_ETAPA_ENTRADA)
    wa = _make_wa_mock(wamid="wamid.LEAD_VAZIO_1")

    res = talvez_disparar_migracao_canal(
        lead_id="12345",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )

    assert res["acao"] == "disparado", res
    assert res["wamid"] == "wamid.LEAD_VAZIO_1"
    assert res["telefone"] == "5561999990000"

    # Meta send_text foi chamado com texto de migração
    wa.send_text.assert_called_once()
    to_arg, texto_arg = wa.send_text.call_args.args
    assert to_arg == "5561999990000"
    assert "(61) 8133-1005" in texto_arg
    assert "wa.me/556181331005" in texto_arg

    # Nota gravada mencionando Bug C-38 + wamid
    kommo.add_note.assert_called_once()
    nota_lead_id, nota_texto = kommo.add_note.call_args.args
    assert nota_lead_id == 12345
    assert "C-38" in nota_texto
    assert "wamid.LEAD_VAZIO_1" in nota_texto

    # IA desativada pra não fazer loop
    kommo.update_lead_fields.assert_called_once_with(
        12345, {"ativado_ia": "Desativado"},
    )

    # Dedup gravado no Redis
    assert redis.calls_setex, "esperado setex de dedup"
    key, ttl, _val = redis.calls_setex[0]
    assert key == "blink:migracao_canal:12345"
    assert ttl == 7 * 24 * 60 * 60


def test_cenario2_mesmo_lead_duas_vezes_dedup_pula_segunda():
    """Dedup Redis 7d: 2ª chamada retorna dedup sem tocar Meta/Kommo."""
    redis = FakeRedis()
    kommo = _make_kommo_mock(status_id=STATUS_ID_ETAPA_ENTRADA)
    wa = _make_wa_mock()

    r1 = talvez_disparar_migracao_canal(
        lead_id="55555",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )
    assert r1["acao"] == "disparado"

    # Segunda chamada — mesmo lead. Sem batimento em Meta.
    wa.send_text.reset_mock()
    kommo.add_note.reset_mock()
    kommo.update_lead_fields.reset_mock()

    r2 = talvez_disparar_migracao_canal(
        lead_id="55555",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )
    assert r2["acao"] == "dedup"
    assert r2["motivo"] == "ja_disparou_7d"
    wa.send_text.assert_not_called()
    kommo.add_note.assert_not_called()
    kommo.update_lead_fields.assert_not_called()


def test_cenario3_lead_com_nota_existente_nao_dispara():
    """Lead já tem nota humana (canal reconhecido) → não é fantasma."""
    redis = FakeRedis()
    kommo = _make_kommo_mock(
        status_id=STATUS_ID_ETAPA_ENTRADA,
        notes=[{"id": 111, "text": "Já falamos com esse paciente ontem"}],
    )
    wa = _make_wa_mock()

    res = talvez_disparar_migracao_canal(
        lead_id="77777",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )

    assert res["acao"] == "pulado"
    assert "nao_candidato" in res["motivo"]
    wa.send_text.assert_not_called()
    kommo.add_note.assert_not_called()


def test_cenario4_lead_fora_etapa_entrada_nao_dispara():
    """Lead em 2.LEADS FRIO ou 3-AGENDAR → não é candidato ao C-38."""
    redis = FakeRedis()
    kommo = _make_kommo_mock(
        status_id=101508307,  # 2.LEADS FRIO
    )
    wa = _make_wa_mock()

    res = talvez_disparar_migracao_canal(
        lead_id="88888",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )

    assert res["acao"] == "pulado"
    assert "nao_candidato" in res["motivo"]
    assert "status_id=101508307" in res["motivo"]
    wa.send_text.assert_not_called()


def test_cenario5_toggle_desligado_nao_dispara(monkeypatch):
    """LIA_MIGRACAO_CANAL_ENABLED=0 → orquestrador retorna sem tocar nada."""
    monkeypatch.setenv("LIA_MIGRACAO_CANAL_ENABLED", "0")

    redis = FakeRedis()
    kommo = _make_kommo_mock(status_id=STATUS_ID_ETAPA_ENTRADA)
    wa = _make_wa_mock()

    res = talvez_disparar_migracao_canal(
        lead_id="99999",
        kommo_client=kommo,
        wa_client=wa,
        redis_client=redis,
    )

    assert res["acao"] == "pulado"
    assert res["motivo"] == "toggle_desligado"
    # Nem mesmo get_lead deve ser chamado — short-circuit imediato
    kommo.get_lead.assert_not_called()
    wa.send_text.assert_not_called()
