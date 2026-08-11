"""
Task #400/405 (15/07/2026) — Migração PLANO_CODES pra JSON externo.

Contexto Fábio (11/07 P0 arquitetural, Bug C-53):
    "continuar disfuncional porque não grava esta tabela no database, para
    não ocorrer retrocessos. Já tivemos este mesmo tipo de erro 1000 vezes."

Padrão arquitetural (mesmo do C-53 calendar_atendimento.json):
    - JSON externo em voice_agent/planos_medware.json
    - Cache TTL 60s (mudança em prod sem redeploy — só editar o JSON)
    - Fallback pra tabela hard-coded (safety net se JSON quebrar/desaparecer)

Bugs conhecidos que essa migração blinda:
    - C-43 (Mariana Lopes 22617170, 12/07/2026): convênio "Afego" (1F Kommo)
      não estava em PLANO_CODES. Medware grafa "AFFEGO" (2F). Aliases novos
      = editar JSON, sem redeploy.
    - Qualquer convênio novo Kommo pode ser adicionado editando JSON.
    - Alias novo pra convênio existente (variante de digitação do paciente)
      = editar aliases, sem redeploy.

Como usar (do medware.py):
    from voice_agent.planos_medware_loader import resolver_plano_codigo
    cod = resolver_plano_codigo("Afego")  # -> 7
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

# Caminho canônico do JSON. Env pode sobrescrever pra testes.
_JSON_PATH_ENV = "BLINK_PLANOS_MEDWARE_JSON"
_JSON_DEFAULT = Path(__file__).parent / "planos_medware.json"

# TTL do cache — 60s dá janela pra edição em prod sem parar tudo pra
# esperar redeploy. Se editar e quiser efeito imediato, restart do container.
_CACHE_TTL_SEG = 60

_cache_lock = threading.Lock()
_cache: dict[str, int] = {}
_cache_carregado_em: float = 0.0
_cache_versao_arquivo: str = ""


def _caminho_json() -> Path:
    """Retorna path do JSON — env override tem prioridade."""
    env = os.environ.get(_JSON_PATH_ENV, "").strip()
    if env:
        return Path(env)
    return _JSON_DEFAULT


def _carregar_fallback_hardcoded() -> dict[str, int]:
    """Import lazy do PLANO_CODES hard-coded (safety net)."""
    try:
        from voice_agent.medware import PLANO_CODES  # noqa: WPS433
        return dict(PLANO_CODES)
    except Exception as exc:  # noqa: BLE001
        log.critical(
            "planos_medware_loader: fallback hard-coded FALHOU tb: %s. "
            "Retornando dict vazio — TODOS os agendamentos vão pra humano!",
            exc,
        )
        return {}


def _achatar_json_em_aliases(dados: dict) -> dict[str, int]:
    """Converte estrutura JSON (com blocos) em dict {alias -> codPlano}.

    Estrutura esperada:
        {
          "chave_bloco": {
            "codPlano": 7,
            "aliases": ["afego", "affego", ...]
          },
          ...
        }
    Chaves que começam com "_" (metadados) são ignoradas.
    """
    plano_codes: dict[str, int] = {}
    for chave_bloco, bloco in dados.items():
        if chave_bloco.startswith("_"):
            continue
        if not isinstance(bloco, dict):
            continue
        cod = bloco.get("codPlano")
        aliases = bloco.get("aliases") or []
        if not isinstance(cod, int) or cod < 1:
            log.warning(
                "planos_medware.json: bloco %r com codPlano inválido: %r — pulando",
                chave_bloco, cod,
            )
            continue
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            key = alias.strip().lower()
            if not key:
                continue
            if key in plano_codes and plano_codes[key] != cod:
                log.warning(
                    "planos_medware.json: alias %r conflita — bloco %r define %d "
                    "mas alias já mapeava pra %d. Mantendo primeiro.",
                    key, chave_bloco, cod, plano_codes[key],
                )
                continue
            plano_codes[key] = cod
    return plano_codes


def _recarregar_cache_se_necessario() -> None:
    """Recarrega JSON se TTL expirou OU nunca foi carregado.

    Se arquivo não existe / JSON quebrado / dict vazio → fallback hard-coded.
    Sempre popula cache pra não bloquear resolver_plano_codigo.
    """
    global _cache, _cache_carregado_em, _cache_versao_arquivo

    with _cache_lock:
        agora = _time.time()
        # Cache válido?
        if _cache and (agora - _cache_carregado_em) < _CACHE_TTL_SEG:
            return

        path = _caminho_json()
        try:
            texto = path.read_text(encoding="utf-8")
            dados = json.loads(texto)
            plano_codes = _achatar_json_em_aliases(dados)
            versao = dados.get("_versao", "sem-versao")
            if not plano_codes:
                raise ValueError("JSON válido mas 0 aliases resolvidos")
            _cache = plano_codes
            _cache_carregado_em = agora
            if versao != _cache_versao_arquivo:
                log.info(
                    "planos_medware_loader: JSON carregado — %d aliases, versão %s",
                    len(_cache), versao,
                )
                _cache_versao_arquivo = versao
        except FileNotFoundError:
            log.critical(
                "planos_medware.json NÃO EXISTE em %s — usando fallback hard-coded",
                path,
            )
            _cache = _carregar_fallback_hardcoded()
            _cache_carregado_em = agora
        except json.JSONDecodeError as exc:
            log.critical(
                "planos_medware.json QUEBRADO (JSON inválido) em %s: %s — "
                "usando fallback hard-coded",
                path, exc,
            )
            _cache = _carregar_fallback_hardcoded()
            _cache_carregado_em = agora
        except Exception as exc:  # noqa: BLE001
            log.critical(
                "planos_medware_loader falha inesperada: %s — fallback hard-coded",
                exc,
            )
            _cache = _carregar_fallback_hardcoded()
            _cache_carregado_em = agora


def resolver_plano_codigo(convenio: Optional[str]) -> int:
    """Nome do convênio (livre) → codPlano Medware. 0 = desconhecido (humano).

    Regras:
    - Vazio → 0 (não presumir particular; deixa medware.py::resolver_plano
      decidir o comportamento particular).
    - Match exato (lower/strip) primeiro.
    - Match parcial (alias contido no texto, ≥4 chars) — pra frases tipo
      "uso o plano da polícia federal".
    - 0 = não mapeado → medware.py vai escalar humano.
    """
    if not convenio or not str(convenio).strip():
        return 0

    _recarregar_cache_se_necessario()
    chave = str(convenio).strip().lower()

    # Match exato
    if chave in _cache:
        return _cache[chave]

    # Match parcial (alias contido no texto do paciente)
    for alias, cod in _cache.items():
        if len(alias) >= 4 and alias in chave:
            return cod

    return 0


def forcar_recarregar_cache() -> int:
    """Força recarregamento imediato do JSON (pra testes / admin endpoint).
    Retorna qtd de aliases carregados."""
    global _cache, _cache_carregado_em
    with _cache_lock:
        _cache = {}
        _cache_carregado_em = 0.0
    _recarregar_cache_se_necessario()
    return len(_cache)


def snapshot_cache() -> dict:
    """Devolve cópia do cache pra debug/auditoria."""
    _recarregar_cache_se_necessario()
    with _cache_lock:
        return dict(_cache)


def estatisticas() -> dict:
    """Estado do loader (útil pra healthz)."""
    with _cache_lock:
        return {
            "qtd_aliases": len(_cache),
            "carregado_em": _cache_carregado_em,
            "idade_seg": _time.time() - _cache_carregado_em if _cache_carregado_em else None,
            "versao_arquivo": _cache_versao_arquivo,
            "cache_ttl_seg": _CACHE_TTL_SEG,
            "json_path": str(_caminho_json()),
        }
