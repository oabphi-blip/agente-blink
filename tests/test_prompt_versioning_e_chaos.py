"""Testes Prompt Versioning + Chaos — sprint SRE 18/06.

10 cenários (5 prompt versioning + 5 chaos).

Padrão: usa FakeRedis MagicMock-like — implementa só hset/hgetall/hmset/
lpush/lrange/ltrim/setex/exists/delete que os módulos chamam.

Os testes NÃO precisam de redis real, anthropic key, kommo, medware.
"""
from __future__ import annotations

import fnmatch
import os
import time
from typing import Iterable

import pytest


os.environ.setdefault("WEBHOOK_SECRET", "test-secret-pv-chaos")


# ---------------------------------------------------------------------------
# FakeRedis enxuto pros 2 módulos novos
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.strings: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    # ---------- hash ops ----------
    def hset(self, key: str, mapping: dict | None = None, **kwargs) -> int:
        if mapping is None:
            mapping = kwargs
        d = self.hashes.setdefault(key, {})
        for k, v in mapping.items():
            d[str(k)] = str(v)
        return len(mapping)

    def hmset(self, key: str, mapping: dict) -> bool:
        self.hset(key, mapping=mapping)
        return True

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    # ---------- list ops ----------
    def lpush(self, key: str, *values) -> int:
        lst = self.lists.setdefault(key, [])
        for v in values:
            lst.insert(0, str(v))
        return len(lst)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        lst = self.lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    def ltrim(self, key: str, start: int, end: int) -> bool:
        lst = self.lists.get(key, [])
        if end == -1:
            self.lists[key] = lst[start:]
        else:
            self.lists[key] = lst[start:end + 1]
        return True

    # ---------- string / chaos ops ----------
    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.strings[key] = str(value)
        self.ttl[key] = int(ttl)
        return True

    def exists(self, key: str) -> int:
        return 1 if key in self.strings else 0

    def delete(self, key: str) -> int:
        if key in self.strings:
            del self.strings[key]
            return 1
        return 0

    def get(self, key: str):
        return self.strings.get(key)

    def scan_iter(self, match: str = "*") -> Iterable[str]:
        keys = set(self.strings.keys()) | set(self.hashes.keys()) | set(self.lists.keys())
        return [k for k in keys if fnmatch.fnmatch(k, match)]


# ===========================================================================
# 1. extrair_versao_prompt — acha marcador / retorna None sem marcador
# ===========================================================================

def test_1_extrair_versao_acha_e_retorna_none():
    from voice_agent.prompt_versioning import extrair_versao_prompt

    txt_com = "<!-- VERSAO_PROMPT: 2026-06-18-c37-proibido-comunicacao-interna -->\nResto do prompt..."
    assert extrair_versao_prompt(txt_com) == "2026-06-18-c37-proibido-comunicacao-interna"

    # Variação com espaços e case
    txt_var = "<!--  versao_prompt :  v1.2.3-alpha  -->"
    assert extrair_versao_prompt(txt_var) == "v1.2.3-alpha"

    # Sem marcador
    assert extrair_versao_prompt("Texto qualquer sem marcador") is None
    assert extrair_versao_prompt("") is None
    assert extrair_versao_prompt(None) is None  # tolerante


# ===========================================================================
# 2. hash_prompt determinístico
# ===========================================================================

def test_2_hash_prompt_deterministico():
    from voice_agent.prompt_versioning import hash_prompt

    a = "instrução de teste"
    h1 = hash_prompt(a)
    h2 = hash_prompt(a)
    assert h1 == h2
    assert len(h1) == 16
    # Texto diferente → hash diferente
    assert hash_prompt(a) != hash_prompt(a + " mudou")
    # Vazio não quebra
    assert isinstance(hash_prompt(""), str)
    assert isinstance(hash_prompt(None), str)  # type: ignore[arg-type]


# ===========================================================================
# 3. registrar_versao grava + idempotente
# ===========================================================================

def test_3_registrar_versao_grava_e_idempotente():
    from voice_agent.prompt_versioning import registrar_versao

    r = FakeRedis()
    versao = "2026-06-18-teste"
    texto = "x" * 500
    h = "abcd1234abcd1234"

    # 1ª vez grava
    assert registrar_versao(r, versao, h, texto) is True
    key = f"blink:prompt_version:{versao}"
    assert r.hashes[key]["hash"] == h
    assert r.hashes[key]["length_chars"] == "500"
    assert len(r.hashes[key]["snippet_first_200"]) == 200
    assert "blink:prompt_versions_history" in r.lists

    # 2ª vez NÃO regrava (mesmo hash)
    assert registrar_versao(r, versao, h, texto) is False

    # Hash diferente → grava de novo
    assert registrar_versao(r, versao, "ffffffffffffffff", texto + "y") is True


# ===========================================================================
# 4. listar_versoes — ordem decrescente (mais recente primeiro)
# ===========================================================================

def test_4_listar_versoes_decrescente():
    from voice_agent.prompt_versioning import registrar_versao, listar_versoes

    r = FakeRedis()
    registrar_versao(r, "v1", "h1" * 8, "primeiro")
    registrar_versao(r, "v2", "h2" * 8, "segundo")
    registrar_versao(r, "v3", "h3" * 8, "terceiro")

    historico = listar_versoes(r)
    nomes = [h["versao"] for h in historico]
    assert nomes == ["v3", "v2", "v1"]  # LPUSH = mais recente primeiro
    # Cada item tem metadados
    assert historico[0]["hash"] == "h3" * 8
    assert isinstance(historico[0]["length_chars"], int)


# ===========================================================================
# 5. diff_versoes — detecta mesmo_hash
# ===========================================================================

def test_5_diff_versoes_mesmo_hash():
    from voice_agent.prompt_versioning import registrar_versao, diff_versoes

    r = FakeRedis()
    h = "iguaisss12345678"
    registrar_versao(r, "vA", h, "texto A")
    # forçar timestamp diferente
    time.sleep(0.01)
    registrar_versao(r, "vB", h, "texto A extra")

    diff = diff_versoes(r, "vA", "vB")
    assert diff["mesmo_hash"] is True
    assert diff["versao_a"] == "vA"
    assert diff["versao_b"] == "vB"
    assert diff["mudou_length"] == (len("texto A extra") - len("texto A"))

    # Hash diferente
    registrar_versao(r, "vC", "outroooo12345678", "texto C")
    diff2 = diff_versoes(r, "vA", "vC")
    assert diff2["mesmo_hash"] is False


# ===========================================================================
# 6. auto_registrar_no_startup lê arquivo real
# ===========================================================================

def test_6_auto_registrar_arquivo_real():
    from voice_agent.prompt_versioning import auto_registrar_no_startup

    r = FakeRedis()
    res = auto_registrar_no_startup(redis_client=r)
    # Espera que tenha lido o arquivo do KB
    assert res["arquivo_lido"] is not None
    assert "_MASTER_INSTRUCTION.md" in res["arquivo_lido"]
    assert res["length_chars"] > 100  # arquivo real é grande
    # Versão é o slug do header (sabemos do CLAUDE.md)
    assert res["versao"] is not None
    assert res["hash"] is not None
    # Gravou no fake redis
    assert res["gravou"] is True
    assert "blink:prompt_versions_history" in r.lists


# ===========================================================================
# 7. injetar_falha grava com TTL
# ===========================================================================

def test_7_injetar_falha_grava_com_ttl():
    from voice_agent import chaos

    r = FakeRedis()
    assert chaos.injetar_falha(r, "medware", ttl_seg=120) is True
    key = "blink:chaos:medware:down"
    assert key in r.strings
    assert r.ttl[key] == 120

    # Serviço inválido → False
    assert chaos.injetar_falha(r, "fake_service") is False

    # Sem redis → False
    assert chaos.injetar_falha(None, "medware") is False


# ===========================================================================
# 8. esta_em_chaos True/False
# ===========================================================================

def test_8_esta_em_chaos():
    from voice_agent import chaos

    r = FakeRedis()
    assert chaos.esta_em_chaos(r, "medware") is False
    chaos.injetar_falha(r, "medware", ttl_seg=60)
    assert chaos.esta_em_chaos(r, "medware") is True
    assert chaos.esta_em_chaos(r, "kommo") is False
    # Sem redis → False
    assert chaos.esta_em_chaos(None, "medware") is False


# ===========================================================================
# 9. parar_chaos deleta
# ===========================================================================

def test_9_parar_chaos_deleta():
    from voice_agent import chaos

    r = FakeRedis()
    chaos.injetar_falha(r, "medware", ttl_seg=60)
    chaos.injetar_falha(r, "kommo", ttl_seg=60)
    chaos.injetar_falha(r, "anthropic", ttl_seg=60)

    # Para 1 só
    assert chaos.parar_chaos(r, "medware") == 1
    assert chaos.esta_em_chaos(r, "medware") is False
    assert chaos.esta_em_chaos(r, "kommo") is True

    # Para TODOS
    removidas = chaos.parar_chaos(r)
    assert removidas >= 2  # kommo + anthropic
    assert chaos.esta_em_chaos(r, "kommo") is False
    assert chaos.esta_em_chaos(r, "anthropic") is False


# ===========================================================================
# 10. executar_chaos_suite retorna dict por servico
# ===========================================================================

def test_10_executar_chaos_suite_dict_por_servico():
    from voice_agent import chaos

    r = FakeRedis()
    rel = chaos.executar_chaos_suite(r, ttl_por_servico=10)
    # 4 servicos
    assert set(rel.keys()) >= {"medware", "kommo", "anthropic", "redis_slow"}
    for s, info in rel.items():
        assert "falhou_ok" in info
        assert "escalou" in info
        assert "latencia_ms" in info
        # Sem agent_callable, valida que o gate Redis estava ativo durante a injeção
        assert info["falhou_ok"] is True

    # Após suite, tudo deve estar parado
    status = chaos.status_chaos(r)
    assert all(v is False for v in status.values())
