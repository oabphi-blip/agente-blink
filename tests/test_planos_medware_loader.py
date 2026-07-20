"""
Task #400/405 (15/07/2026) — Migração PLANO_CODES pra JSON externo.

Blindagem:
1. JSON externo carrega e resolve aliases corretamente.
2. Editar JSON reflete em <TTL (via env override + forcar_recarregar_cache).
3. JSON quebrado / arquivo inexistente → fallback hard-coded ainda resolve.
4. Match parcial ("uso o plano da polícia federal") funciona.
5. Bug C-43 (Afego) resolvido no JSON.
6. Integração com medware.resolver_plano (fluxo real).

Estratégia de teste:
- Cada teste tem `setup` que zera o cache via env override + forcar_recarregar_cache.
- Uso tmp_path pra criar JSONs de teste sem tocar no arquivo real.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from voice_agent import planos_medware_loader as loader


@pytest.fixture(autouse=True)
def _reset_env_e_cache(monkeypatch):
    """Zera cache e env antes de cada teste. Evita vazamento de estado."""
    monkeypatch.delenv(loader._JSON_PATH_ENV, raising=False)
    loader._cache.clear()
    loader._cache_carregado_em = 0.0
    loader._cache_versao_arquivo = ""
    yield
    loader._cache.clear()
    loader._cache_carregado_em = 0.0
    loader._cache_versao_arquivo = ""


def _escrever_json_temp(tmp_path: Path, dados: dict) -> Path:
    p = tmp_path / "planos_test.json"
    p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return p


# ---------- 1. JSON externo default carrega ----------

def test_json_default_existe_e_carrega():
    """voice_agent/planos_medware.json existe e tem >20 aliases."""
    total = loader.forcar_recarregar_cache()
    assert total >= 20, f"esperava >=20 aliases no JSON default, achou {total}"


def test_json_default_resolve_saude_caixa():
    assert loader.resolver_plano_codigo("Saúde Caixa") == 29
    assert loader.resolver_plano_codigo("saude caixa") == 29
    assert loader.resolver_plano_codigo("caixa") == 29


def test_json_default_resolve_bacen():
    assert loader.resolver_plano_codigo("Bacen") == 9
    assert loader.resolver_plano_codigo("banco central") == 9


def test_json_default_resolve_particular():
    assert loader.resolver_plano_codigo("Particular") == 1
    assert loader.resolver_plano_codigo("Sem convênio") == 1
    assert loader.resolver_plano_codigo("N/A") == 1


# ---------- 2. Bug C-43 — Afego ----------

def test_bug_c43_afego_1f_resolve():
    """Kommo grafa 'Afego' com 1 F — precisa mapear pro codPlano 7."""
    assert loader.resolver_plano_codigo("Afego") == 7
    assert loader.resolver_plano_codigo("afego") == 7


def test_bug_c43_affego_2f_tambem_resolve():
    """Medware grafa 'AFFEGO' com 2 F — mesmo codPlano."""
    assert loader.resolver_plano_codigo("Affego") == 7


def test_bug_c43_variantes_regionais():
    assert loader.resolver_plano_codigo("Afego BH") == 7
    assert loader.resolver_plano_codigo("Afego Brasília") == 7 or loader.resolver_plano_codigo("Afego Brasilia") == 7


# ---------- 3. Vazio / desconhecido ----------

def test_vazio_retorna_zero():
    assert loader.resolver_plano_codigo("") == 0
    assert loader.resolver_plano_codigo(None) == 0
    assert loader.resolver_plano_codigo("   ") == 0


def test_convenio_desconhecido_retorna_zero():
    """Convênio realmente inexistente → 0 (Lia escala humano)."""
    assert loader.resolver_plano_codigo("Plano Inexistente XPTO 2099") == 0


# ---------- 4. Match parcial ----------

def test_match_parcial_frase_paciente():
    """Paciente escreve frase, alias fica no meio."""
    assert loader.resolver_plano_codigo("uso o plano da polícia federal") == 26
    assert loader.resolver_plano_codigo("plano da caixa") == 29


# ---------- 5. Edição JSON reflete via env override ----------

def test_edicao_json_reflete_apos_recarga(tmp_path, monkeypatch):
    """Simula: edita JSON → força recarga → alias novo aparece."""
    # JSON inicial com 1 bloco
    json_v1 = {
        "_versao": "v1",
        "particular": {
            "codPlano": 1,
            "aliases": ["particular", "sem convenio"],
        },
    }
    json_path = _escrever_json_temp(tmp_path, json_v1)
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(json_path))
    loader.forcar_recarregar_cache()

    assert loader.resolver_plano_codigo("particular") == 1
    # convênio novo AINDA não existe
    assert loader.resolver_plano_codigo("teste_novo") == 0

    # Simula edição: adiciona bloco novo
    json_v2 = dict(json_v1)
    json_v2["_versao"] = "v2"
    json_v2["teste_bloco"] = {
        "codPlano": 999,
        "aliases": ["teste_novo", "teste_alias_2"],
    }
    _escrever_json_temp(tmp_path, json_v2)
    # Sobrescreve arquivo (o path é o mesmo do write anterior)
    json_path.write_text(json.dumps(json_v2, ensure_ascii=False), encoding="utf-8")

    loader.forcar_recarregar_cache()
    assert loader.resolver_plano_codigo("teste_novo") == 999
    assert loader.resolver_plano_codigo("teste_alias_2") == 999


# ---------- 6. Fallback quando JSON quebra ----------

def test_fallback_quando_json_nao_existe(tmp_path, monkeypatch):
    """Aponta pra path que não existe → fallback hard-coded."""
    fake_path = tmp_path / "nao_existe.json"
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(fake_path))
    loader.forcar_recarregar_cache()

    # Fallback pega do PLANO_CODES hard-coded (medware.py)
    assert loader.resolver_plano_codigo("Bacen") == 9
    assert loader.resolver_plano_codigo("Saúde Caixa") == 29


def test_fallback_quando_json_quebrado(tmp_path, monkeypatch):
    """JSON com sintaxe inválida → fallback hard-coded."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ isto não é JSON válido }}}", encoding="utf-8")
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(bad))
    loader.forcar_recarregar_cache()

    # Ainda resolve via fallback
    assert loader.resolver_plano_codigo("Bacen") == 9


def test_fallback_quando_json_vazio(tmp_path, monkeypatch):
    """JSON válido mas sem aliases (só metadados) → fallback."""
    vazio = {"_versao": "empty"}
    p = _escrever_json_temp(tmp_path, vazio)
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(p))
    loader.forcar_recarregar_cache()

    assert loader.resolver_plano_codigo("Bacen") == 9


# ---------- 7. Bloco malformado no JSON ----------

def test_bloco_sem_codPlano_e_ignorado(tmp_path, monkeypatch):
    dados = {
        "_versao": "malformed",
        "ok": {"codPlano": 5, "aliases": ["alias_ok"]},
        "quebrado": {"aliases": ["alias_ignorado"]},  # sem codPlano
        "quebrado2": {"codPlano": "não_é_int", "aliases": ["alias_ignorado2"]},
    }
    p = _escrever_json_temp(tmp_path, dados)
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(p))
    loader.forcar_recarregar_cache()

    assert loader.resolver_plano_codigo("alias_ok") == 5
    assert loader.resolver_plano_codigo("alias_ignorado") == 0
    assert loader.resolver_plano_codigo("alias_ignorado2") == 0


# ---------- 8. Integração com medware.resolver_plano ----------

def test_integracao_medware_resolver_plano_usa_json():
    """medware.resolver_plano deve usar JSON externo primeiro."""
    from voice_agent.medware import resolver_plano
    # Convênios que estão no JSON default
    assert resolver_plano("Bacen") == 9
    assert resolver_plano("Saúde Caixa") == 29
    assert resolver_plano("Afego") == 7


def test_integracao_medware_fallback_funciona(tmp_path, monkeypatch):
    """Se JSON some, medware.resolver_plano ainda funciona via PLANO_CODES."""
    from voice_agent.medware import resolver_plano
    fake = tmp_path / "nao_existe.json"
    monkeypatch.setenv(loader._JSON_PATH_ENV, str(fake))
    loader.forcar_recarregar_cache()

    assert resolver_plano("Bacen") == 9


# ---------- 9. Estatísticas / observabilidade ----------

def test_estatisticas_retorna_dict_com_qtd():
    loader.forcar_recarregar_cache()
    stats = loader.estatisticas()
    assert "qtd_aliases" in stats
    assert stats["qtd_aliases"] > 0
    assert "json_path" in stats


def test_snapshot_cache_retorna_copia():
    loader.forcar_recarregar_cache()
    snap = loader.snapshot_cache()
    assert isinstance(snap, dict)
    assert "bacen" in snap


# ---------- 10. Consistência JSON ↔ hard-coded ----------

def test_json_e_hardcoded_concordam_em_bacen():
    """Se algum dia forem diferentes, alguém ficou pra trás. Aqui atende só
    validar que bacen bate em ambos (chave altamente estável)."""
    from voice_agent.medware import PLANO_CODES
    loader.forcar_recarregar_cache()
    assert loader.resolver_plano_codigo("bacen") == PLANO_CODES.get("bacen")


def test_json_cobre_convenios_criticos_kommo():
    """Convênios de maior volume no Kommo devem estar todos no JSON."""
    loader.forcar_recarregar_cache()
    criticos = [
        ("Saúde Caixa", 29),
        ("Bacen", 9),
        ("PF Saúde", 26),
        ("STJ", 3),
        ("Afego", 7),
        ("Particular", 1),
    ]
    for nome, cod_esperado in criticos:
        cod = loader.resolver_plano_codigo(nome)
        assert cod == cod_esperado, f"{nome} esperava {cod_esperado}, achou {cod}"
