"""Pytest da Parte 2 de observabilidade Meta → Kommo (task #379).

Cobre:
  1. gravar_template_disparado chama update_lead_fields com 5 campos.
  2. Categoria auto-calculada quando None.
  3. Categoria explícita vence auto-cálculo.
  4. wamid→lead grava em Redis (mock).
  5. webhook status `delivered` atualiza STATUS via lookup Redis.
  6. sincronizar() retorna dict completo (mock httpx Meta + Kommo).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fakes leves — sem mexer em rede de verdade.
# ---------------------------------------------------------------------------

class FakeKommoClient:
    """Mock leve do KommoClient — captura chamadas pra update_lead_fields."""

    def __init__(self, fields_mapping: dict | None = None):
        self.update_calls: list[tuple[int, dict]] = []
        self.list_custom_fields_calls: list[str] = []
        # Por padrão, lista os 5 campos exigidos pelo módulo.
        self._fields = fields_mapping or {
            "ULTIMO TEMPLATE META": 9001,
            "TEMPLATES JÁ RECEBIDOS": 9002,
            "CATEGORIA TEMPLATE": 9003,
            "DATA ÚLTIMO DISPARO META": 9004,
            "STATUS ÚLTIMO DISPARO": 9005,
        }
        self.update_return = True

    def update_lead_fields(self, lead_id: int, fields: dict) -> bool:
        self.update_calls.append((lead_id, dict(fields)))
        return self.update_return

    def list_custom_fields(self, entity: str = "leads") -> list[dict]:
        self.list_custom_fields_calls.append(entity)
        return [
            {"id": fid, "name": name, "type": "select"}
            for name, fid in self._fields.items()
        ]


class FakeRedis:
    """Mock simples — apenas dict in-memory com setex e get."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value):
        self.store[key] = str(value)
        self.ttls[key] = int(ttl)

    def set(self, key: str, value, ex: int | None = None):
        self.store[key] = str(value)
        if ex is not None:
            self.ttls[key] = int(ex)

    def get(self, key: str):
        return self.store.get(key)


@pytest.fixture(autouse=True)
def _limpar_cache_field_ids():
    """Garante que cache de field_ids não vaza entre testes."""
    from voice_agent.templates_observabilidade import resetar_cache_field_ids
    resetar_cache_field_ids()
    yield
    resetar_cache_field_ids()


# ---------------------------------------------------------------------------
# Teste 1 — gravar_template_disparado chama update_lead_fields com 5 campos.
# ---------------------------------------------------------------------------

class TestGravarTemplateDisparado:

    def test_chama_update_lead_fields_com_5_chaves(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado, CAMPO_TO_KOMMO_KEY,
        )
        kc = FakeKommoClient()
        rc = FakeRedis()
        res = gravar_template_disparado(
            kommo_client=kc,
            lead_id=12345,
            template_name="captar_novo_paciente",
            wamid="wamid.ABC",
            redis_client=rc,
            timestamp=1750000000,
        )

        assert res["ok"] is True
        assert res["erro"] is None
        assert len(res["fields_atualizados"]) == 5

        assert len(kc.update_calls) == 1
        lead_id, payload = kc.update_calls[0]
        assert lead_id == 12345

        # Todas as 5 chaves canônicas presentes:
        for chave in CAMPO_TO_KOMMO_KEY.values():
            assert chave in payload, (
                f"chave {chave!r} ausente no payload {payload!r}"
            )

        # ULTIMO TEMPLATE META = template_name
        assert payload[CAMPO_TO_KOMMO_KEY["ULTIMO TEMPLATE META"]] == (
            "captar_novo_paciente"
        )
        # STATUS ÚLTIMO DISPARO = "sent"
        assert payload[CAMPO_TO_KOMMO_KEY["STATUS ÚLTIMO DISPARO"]] == "sent"
        # DATA = timestamp passado
        assert payload[CAMPO_TO_KOMMO_KEY["DATA ÚLTIMO DISPARO META"]] == (
            1750000000
        )

    def test_template_name_vazio_falha_sem_chamar_kommo(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado,
        )
        kc = FakeKommoClient()
        res = gravar_template_disparado(
            kommo_client=kc, lead_id=1, template_name="",
        )
        assert res["ok"] is False
        assert res["erro"] == "template_name_vazio"
        assert kc.update_calls == []

    def test_kommo_client_none_falha_silencioso(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado,
        )
        res = gravar_template_disparado(
            kommo_client=None, lead_id=1, template_name="x",
        )
        assert res["ok"] is False
        assert res["erro"] == "kommo_client_invalido"


# ---------------------------------------------------------------------------
# Teste 2 — Categoria auto-calculada quando None.
# ---------------------------------------------------------------------------

class TestCategoriaAutoCalculada:

    def test_reativar_prefix_vira_reativacao(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado, CAMPO_TO_KOMMO_KEY,
        )
        kc = FakeKommoClient()
        res = gravar_template_disparado(
            kommo_client=kc, lead_id=99,
            template_name="reativar_lista_fria_v3",
            categoria=None,
        )
        assert res["ok"] is True
        _, payload = kc.update_calls[0]
        cat = payload[CAMPO_TO_KOMMO_KEY["CATEGORIA TEMPLATE"]]
        assert cat == "Reativação"

    def test_captar_prefix_vira_captacao(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado, CAMPO_TO_KOMMO_KEY,
        )
        kc = FakeKommoClient()
        gravar_template_disparado(
            kommo_client=kc, lead_id=100,
            template_name="captar_novo_lead",
            categoria=None,
        )
        _, payload = kc.update_calls[0]
        assert payload[CAMPO_TO_KOMMO_KEY["CATEGORIA TEMPLATE"]] == "Captação"


# ---------------------------------------------------------------------------
# Teste 3 — Categoria explícita vence auto-cálculo.
# ---------------------------------------------------------------------------

class TestCategoriaExplicita:

    def test_categoria_explicita_vence(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado, CAMPO_TO_KOMMO_KEY,
        )
        kc = FakeKommoClient()
        # Template name diz "reativar_*" mas passo "Operacional" explícito.
        gravar_template_disparado(
            kommo_client=kc, lead_id=101,
            template_name="reativar_lista_fria_v3",
            categoria="Operacional",
        )
        _, payload = kc.update_calls[0]
        assert payload[CAMPO_TO_KOMMO_KEY["CATEGORIA TEMPLATE"]] == (
            "Operacional"
        )


# ---------------------------------------------------------------------------
# Teste 4 — wamid→lead grava em Redis.
# ---------------------------------------------------------------------------

class TestWamidLeadRedis:

    def test_grava_wamid_lead_em_redis_com_ttl(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado, WAMID_LEAD_KEY_FMT,
            WAMID_LEAD_TTL_SEG,
        )
        kc = FakeKommoClient()
        rc = FakeRedis()
        res = gravar_template_disparado(
            kommo_client=kc, lead_id=55555,
            template_name="captar_qq", wamid="wamid.XYZ", redis_client=rc,
        )
        assert res["ok"] is True
        assert res["wamid_gravado_redis"] is True
        chave = WAMID_LEAD_KEY_FMT.format(wamid="wamid.XYZ")
        assert rc.store.get(chave) == "55555"
        assert rc.ttls.get(chave) == WAMID_LEAD_TTL_SEG

    def test_sem_redis_nao_grava_mas_nao_falha(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado,
        )
        kc = FakeKommoClient()
        res = gravar_template_disparado(
            kommo_client=kc, lead_id=1, template_name="x",
            wamid="wamid.ABC", redis_client=None,
        )
        assert res["ok"] is True
        assert res["wamid_gravado_redis"] is False

    def test_sem_wamid_nao_grava_em_redis(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado,
        )
        kc = FakeKommoClient()
        rc = FakeRedis()
        res = gravar_template_disparado(
            kommo_client=kc, lead_id=1, template_name="x",
            wamid=None, redis_client=rc,
        )
        assert res["ok"] is True
        assert res["wamid_gravado_redis"] is False
        assert rc.store == {}


# ---------------------------------------------------------------------------
# Teste 5 — webhook status `delivered` atualiza STATUS pro lead via Redis.
# ---------------------------------------------------------------------------

class TestStatusCallback:

    def test_delivered_atualiza_status_no_lead_certo(self):
        from voice_agent.templates_observabilidade import (
            gravar_template_disparado,
            lookup_lead_por_wamid,
            atualizar_status_ultimo_disparo,
            CAMPO_TO_KOMMO_KEY,
        )
        kc = FakeKommoClient()
        rc = FakeRedis()

        # 1. Disparo grava wamid→lead.
        gravar_template_disparado(
            kommo_client=kc, lead_id=7777,
            template_name="captar_qq", wamid="wamid.DEF", redis_client=rc,
        )
        kc.update_calls.clear()  # zera pra observar só a 2ª chamada.

        # 2. Webhook simula callback delivered.
        lead_id = lookup_lead_por_wamid(rc, "wamid.DEF")
        assert lead_id == 7777
        res = atualizar_status_ultimo_disparo(kc, lead_id, "delivered")
        assert res["ok"] is True

        # Só STATUS ÚLTIMO DISPARO deve ter sido enviado.
        assert len(kc.update_calls) == 1
        lid, payload = kc.update_calls[0]
        assert lid == 7777
        assert payload == {
            CAMPO_TO_KOMMO_KEY["STATUS ÚLTIMO DISPARO"]: "delivered",
        }

    def test_lookup_wamid_inexistente_retorna_none(self):
        from voice_agent.templates_observabilidade import lookup_lead_por_wamid
        rc = FakeRedis()
        assert lookup_lead_por_wamid(rc, "wamid.naoexiste") is None

    def test_parse_status_callbacks_extrai_delivered(self):
        # Sanidade do parser de payload Meta.
        from voice_agent.whatsapp_cloud import parse_status_callbacks
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.DEF",
                            "status": "delivered",
                            "recipient_id": "5561988888888",
                            "timestamp": "1750000000",
                        }],
                    },
                }],
            }],
        }
        out = parse_status_callbacks(payload)
        assert len(out) == 1
        assert out[0]["wamid"] == "wamid.DEF"
        assert out[0]["status"] == "delivered"


# ---------------------------------------------------------------------------
# Teste 6 — sincronizar() retorna dict com chaves esperadas.
# ---------------------------------------------------------------------------

class TestSincronizar:

    def test_sem_token_kommo_retorna_erro(self, monkeypatch):
        monkeypatch.setenv("KOMMO_TOKEN", "")
        # Reimporta pra módulo capturar env vazia.
        import importlib
        import voice_agent.scripts.sync_meta_to_kommo as mod
        importlib.reload(mod)
        res = mod.sincronizar()
        assert res["ok"] is False
        assert res["erro"] == "KOMMO_TOKEN nao setado"
        assert res["total_aprovados"] == 0

    def test_dict_completo_quando_sucesso(self, monkeypatch):
        # Mocka as 2 funções de rede pra não bater fora.
        import voice_agent.scripts.sync_meta_to_kommo as mod

        # Garante envs presentes pra passar do guarda inicial.
        monkeypatch.setenv("KOMMO_TOKEN", "fake_kommo_token")
        monkeypatch.setenv("WHATSAPP_CLOUD_TOKEN", "fake_meta_token")
        # As envs viram CONSTANTES do módulo, então re-import via reload.
        import importlib
        importlib.reload(mod)

        templates_fake = [
            {"name": "captar_x", "category": "MARKETING",
             "language": "pt_BR", "blink_categoria": "Captação"},
            {"name": "reativar_y", "category": "MARKETING",
             "language": "pt_BR", "blink_categoria": "Reativação"},
        ]

        upsert_calls = []

        def fake_listar_templates_meta():
            return list(templates_fake)

        def fake_encontrar_field_ids():
            return {
                "ULTIMO TEMPLATE META": 9001,
                "TEMPLATES JÁ RECEBIDOS": 9002,
            }

        def fake_upsert_enums(field_id, templates):
            upsert_calls.append((field_id, len(templates)))
            return {
                "status": 200,
                "adicionados": [t["name"] for t in templates],
                "obsoletos": [],
                "total_kommo_apos": len(templates),
            }

        with patch.object(mod, "listar_templates_meta",
                          fake_listar_templates_meta), \
             patch.object(mod, "encontrar_field_ids",
                          fake_encontrar_field_ids), \
             patch.object(mod, "upsert_enums", fake_upsert_enums):
            res = mod.sincronizar()

        assert res["ok"] is True
        assert res["erro"] is None
        assert res["total_aprovados"] == 2
        # union de adicionados (set ordenado)
        assert set(res["adicionados"]) == {"captar_x", "reativar_y"}
        assert res["obsoletos"] == []
        # relatorio cobre os 2 campos
        assert "ULTIMO TEMPLATE META" in res["relatorio"]
        assert "TEMPLATES JÁ RECEBIDOS" in res["relatorio"]
        # 1 upsert por campo
        assert len(upsert_calls) == 2

    def test_sem_campos_kommo_retorna_erro_estruturado(self, monkeypatch):
        import voice_agent.scripts.sync_meta_to_kommo as mod
        monkeypatch.setenv("KOMMO_TOKEN", "x")
        monkeypatch.setenv("WHATSAPP_CLOUD_TOKEN", "y")
        import importlib
        importlib.reload(mod)

        with patch.object(mod, "listar_templates_meta",
                          lambda: [{"name": "captar_z",
                                    "blink_categoria": "Captação"}]), \
             patch.object(mod, "encontrar_field_ids", lambda: {}):
            res = mod.sincronizar()
        assert res["ok"] is False
        assert res["erro"].startswith("campos_kommo_faltando")
        assert res["total_aprovados"] == 1
