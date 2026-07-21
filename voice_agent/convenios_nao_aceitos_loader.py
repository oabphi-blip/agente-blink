"""
Task #400 (20/07/2026) — Migração _CONVENIOS_NAO_ACEITOS_KB18 pra JSON externo.

Origem: Fábio 11/07 P0 arquitetural (Bug C-53):
    "continuar disfuncional porque não grava esta tabela no database, para
    não ocorrer retrocessos. Já tivemos este mesmo tipo de erro 1000 vezes."

Mesmo padrão do calendar_atendimento.json (C-53) e planos_medware.json (C-43).

Como usar (do responder.py):
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos,
        detectar_convenio_nao_aceito,
    )
    lista = convenios_nao_aceitos()            # -> frozenset[str]
    conv = detectar_convenio_nao_aceito(text)  # -> Optional[str]

Bugs que essa migração blinda:
- C-22 (Sandra 24130752) — token "gdf" isolado adicionado sem redeploy
- Qualquer convênio novo NÃO aceito = editar JSON + commit + push (60s cache)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time as _time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_JSON_PATH_ENV = "BLINK_CONVENIOS_NAO_ACEITOS_JSON"
_JSON_DEFAULT = Path(__file__).parent / "convenios_nao_aceitos.json"

# TTL curto — mudança em prod sem redeploy.
_CACHE_TTL_SEG = 60

_cache_lock = threading.Lock()
_cache: frozenset[str] = frozenset()
_cache_carregado_em: float = 0.0
_cache_versao_arquivo: str = ""


def _caminho_json() -> Path:
    env = os.environ.get(_JSON_PATH_ENV, "").strip()
    if env:
        return Path(env)
    return _JSON_DEFAULT


def _fallback_hardcoded() -> frozenset[str]:
    """Fallback se JSON quebrar/desaparecer. Cópia da lista canônica
    original em responder.py::_CONVENIOS_NAO_ACEITOS_KB18. Safety net."""
    return frozenset({
        "afeb", "afego", "amil", "assefaz", "asete", "aste",
        "bradesco", "brb",
        "cassi", "caeme", "caesan", "camed", "cnti",
        "eletronorte", "embratel",
        "fusex", "fapes",
        "geap", "golden",
        "hapvida", "hap vida", "hap-vida",
        "inas", "gdf inas", "inas gdf", "inas-gdf", "gdf saúde",
        "gdf saude", "gdf",
        "notre dame", "notredame",
        "polícia militar", "policia militar", "porto seguro",
        "quality",
        "sul américa", "sul america", "sulamérica", "sulamerica",
        "sul-américa",
        "sus", "unimed", "unafisco", "sindifisco",
    })


def _versao_arquivo(path: Path) -> str:
    """Hash barato = mtime + size. Detecta mudança sem ler o arquivo todo."""
    try:
        st = path.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return ""


def _carregar_do_json(path: Path) -> frozenset[str]:
    """Lê o JSON, extrai lista canônica de convênios. Normaliza pra lower."""
    try:
        raw = path.read_text(encoding="utf-8")
        dados = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log.warning(
            "convenios_nao_aceitos_loader: erro ao ler %s: %s. Usando fallback.",
            path, exc,
        )
        return _fallback_hardcoded()

    lista = dados.get("convenios", [])
    if not isinstance(lista, list) or not lista:
        log.warning(
            "convenios_nao_aceitos_loader: JSON %s sem chave 'convenios' ou "
            "lista vazia. Fallback.",
            path,
        )
        return _fallback_hardcoded()

    # Normaliza: strip + lowercase; remove vazios/duplicatas.
    normalizados = frozenset(
        s.strip().lower() for s in lista
        if isinstance(s, str) and s.strip()
    )
    if not normalizados:
        return _fallback_hardcoded()
    return normalizados


def convenios_nao_aceitos() -> frozenset[str]:
    """Retorna set canônico de convênios NÃO aceitos.

    Cache TTL 60s + invalida quando mtime/size do arquivo muda. Thread-safe.
    Fail-safe: qualquer exceção retorna fallback hard-coded.
    """
    global _cache, _cache_carregado_em, _cache_versao_arquivo
    path = _caminho_json()
    agora = _time.time()
    versao_atual = _versao_arquivo(path)

    with _cache_lock:
        cache_valido = (
            _cache
            and (agora - _cache_carregado_em) < _CACHE_TTL_SEG
            and versao_atual == _cache_versao_arquivo
        )
        if cache_valido:
            return _cache

        # Recarrega.
        try:
            novo = _carregar_do_json(path)
        except Exception as exc:  # noqa: BLE001
            log.critical(
                "convenios_nao_aceitos_loader: falha crítica ao carregar %s: %s. "
                "Fallback hard-coded.",
                path, exc,
            )
            novo = _fallback_hardcoded()

        _cache = novo
        _cache_carregado_em = agora
        _cache_versao_arquivo = versao_atual
        return _cache


def detectar_convenio_nao_aceito(text: str) -> Optional[str]:
    """Retorna a chave canônica curta do convênio NÃO aceito no texto,
    ou None se nenhum.

    Regra: case-insensitive substring. Itera por tamanho crescente pra
    retornar a variante MAIS CURTA que casar (ex: "inas" em vez de
    "inas gdf"). Idêntica à semântica antiga do
    _CONVENIOS_NAO_ACEITOS_KB18 — zero breaking change.
    """
    if not text:
        return None
    low = text.lower()
    for conv in sorted(convenios_nao_aceitos(), key=len):
        if conv in low:
            return conv
    return None


def invalidar_cache() -> None:
    """Força reload no próximo acesso. Útil pra testes e admin."""
    global _cache, _cache_carregado_em, _cache_versao_arquivo
    with _cache_lock:
        _cache = frozenset()
        _cache_carregado_em = 0.0
        _cache_versao_arquivo = ""
