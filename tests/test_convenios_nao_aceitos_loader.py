"""Task #400 (20/07/2026) — Loader JSON convênios NÃO aceitos.

Blinda:
- Ler lista canônica do JSON
- Fallback hard-coded se JSON quebrar
- Cache TTL 60s (invalida quando mtime muda)
- Semântica idêntica ao _CONVENIOS_NAO_ACEITOS_KB18 antigo
- Bug C-22 (GDF) continua sendo detectado
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


ENV_KEY = "BLINK_CONVENIOS_NAO_ACEITOS_JSON"


@pytest.fixture(autouse=True)
def _reset_cache_e_env(monkeypatch):
    """Cache do loader é module-level; reseta antes/depois de cada teste."""
    from voice_agent import convenios_nao_aceitos_loader as mod
    mod.invalidar_cache()
    yield
    mod.invalidar_cache()


def test_carrega_do_json_default():
    """Sem override de env → lê convenios_nao_aceitos.json ao lado do módulo."""
    from voice_agent.convenios_nao_aceitos_loader import convenios_nao_aceitos
    convs = convenios_nao_aceitos()
    assert isinstance(convs, frozenset)
    assert len(convs) > 30
    # Sanity: nomes canônicos presentes
    for essencial in ("inas", "gdf", "amil", "bradesco", "sulamerica", "unimed"):
        assert essencial in convs, f"{essencial} sumiu do JSON canônico"


def test_bug_c22_gdf_isolado_ainda_pega(monkeypatch):
    """Bug Sandra 24130752 (10/06): 'gdf' sozinho tem que ser detectado."""
    from voice_agent.convenios_nao_aceitos_loader import detectar_convenio_nao_aceito
    assert detectar_convenio_nao_aceito("Meu convênio é GDF") == "gdf"
    assert detectar_convenio_nao_aceito("gdf saúde") == "gdf"


def test_detecta_variantes_case_insensitive():
    from voice_agent.convenios_nao_aceitos_loader import detectar_convenio_nao_aceito
    assert detectar_convenio_nao_aceito("meu plano é AMIL") == "amil"
    assert detectar_convenio_nao_aceito("Sul América S.A.") == "sul américa"
    assert detectar_convenio_nao_aceito("Hapvida cobre?") == "hapvida"


def test_retorna_none_quando_convenio_ok():
    from voice_agent.convenios_nao_aceitos_loader import detectar_convenio_nao_aceito
    assert detectar_convenio_nao_aceito("meu plano é Bacen") is None
    assert detectar_convenio_nao_aceito("saúde caixa") is None
    assert detectar_convenio_nao_aceito("") is None


def test_json_customizado_via_env(monkeypatch, tmp_path):
    """Env override deixa carregar JSON alternativo (útil pra teste ou hotfix)."""
    fake = tmp_path / "custom.json"
    fake.write_text(json.dumps({"convenios": ["xyz_convenio_teste", "amil"]}))
    monkeypatch.setenv(ENV_KEY, str(fake))
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos, invalidar_cache,
    )
    invalidar_cache()
    convs = convenios_nao_aceitos()
    assert "xyz_convenio_teste" in convs
    assert "amil" in convs
    # NÃO tem os outros do canônico
    assert "bradesco" not in convs


def test_fallback_se_json_desaparece(monkeypatch, tmp_path):
    """Aponta pra path inexistente → cai no fallback hard-coded."""
    monkeypatch.setenv(ENV_KEY, str(tmp_path / "nao_existe.json"))
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos, invalidar_cache,
    )
    invalidar_cache()
    convs = convenios_nao_aceitos()
    # Fallback tem os mesmos convênios canônicos
    assert "inas" in convs
    assert "gdf" in convs
    assert "bradesco" in convs


def test_fallback_se_json_corrompido(monkeypatch, tmp_path):
    """JSON inválido → fallback silencioso, não quebra Lia."""
    fake = tmp_path / "corrupto.json"
    fake.write_text("{ isso nao é json valido }")
    monkeypatch.setenv(ENV_KEY, str(fake))
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos, invalidar_cache,
    )
    invalidar_cache()
    convs = convenios_nao_aceitos()
    assert len(convs) > 30  # fallback restaurado


def test_cache_invalida_quando_arquivo_muda(monkeypatch, tmp_path):
    """Editar o JSON e o loader reflete na próxima chamada (mtime detecta)."""
    fake = tmp_path / "mut.json"
    fake.write_text(json.dumps({"convenios": ["conv_1"]}))
    monkeypatch.setenv(ENV_KEY, str(fake))
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos, invalidar_cache,
    )
    invalidar_cache()
    assert convenios_nao_aceitos() == frozenset({"conv_1"})
    # Muda arquivo (força mtime diferente)
    import time as _t
    _t.sleep(0.01)
    fake.write_text(json.dumps({"convenios": ["conv_2", "outro"]}))
    # Loader deve pegar mudança na próxima chamada (não usa cache velho)
    novo = convenios_nao_aceitos()
    assert "conv_2" in novo
    assert "conv_1" not in novo


def test_responder_ainda_usa_lista_via_loader():
    """Regressão: responder.py::_CONVENIOS_NAO_ACEITOS_KB18 continua populado."""
    from voice_agent.responder import _CONVENIOS_NAO_ACEITOS_KB18
    assert isinstance(_CONVENIOS_NAO_ACEITOS_KB18, frozenset)
    assert len(_CONVENIOS_NAO_ACEITOS_KB18) > 30
    assert "inas" in _CONVENIOS_NAO_ACEITOS_KB18
    assert "gdf" in _CONVENIOS_NAO_ACEITOS_KB18


def test_normalizacao_lower_e_strip():
    """Loader normaliza: strip whitespace, lowercase, remove vazios/dup."""
    from voice_agent.convenios_nao_aceitos_loader import (
        _carregar_do_json, invalidar_cache,
    )
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(json.dumps({
            "convenios": ["  AMIL  ", "amil", "", "SUL América", "  "],
        }))
        path = Path(f.name)
    try:
        convs = _carregar_do_json(path)
        assert "amil" in convs  # normalizado
        assert "sul américa" in convs
        assert "" not in convs  # vazio removido
        # Sem duplicatas (AMIL e amil viram 1)
        assert list(convs).count("amil") <= 1
    finally:
        path.unlink()
