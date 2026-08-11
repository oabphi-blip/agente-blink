"""Prompt versioning — registra cada versão do _MASTER_INSTRUCTION.md no Redis.

Permite auditoria de drift: quando uma versão entrou em prod, qual hash,
quando foi substituída. NÃO armazena texto completo (custa Redis); usa
snippet 200 chars + length + hash SHA256[:16] como digital fingerprint.

Endpoints:
  /admin/prompt-versions  → histórico (LRANGE blink:prompt_versions_history)
  /admin/prompt-diff?a=X&b=Y → diff_versoes()

Bootstrap: `auto_registrar_no_startup()` é chamado no
@app.on_event("startup") do webhook.py. Idempotente — só grava se a
versão+hash atual ainda não está no Redis.

Convenção: o marcador `<!-- VERSAO_PROMPT: xxx -->` vive no header do
voice_agent/knowledge_base/_MASTER_INSTRUCTION.md (linha 1).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# Regex permissivo — aceita ou não espaços ao redor.
_VERSAO_REGEX = re.compile(
    r"<!--\s*VERSAO_PROMPT\s*:\s*([A-Za-z0-9._\-]+)\s*-->",
    re.IGNORECASE,
)

_REDIS_KEY_PREFIX = "blink:prompt_version:"
_REDIS_HISTORY_KEY = "blink:prompt_versions_history"
_HISTORY_CAP = 50


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------

def extrair_versao_prompt(texto: str) -> Optional[str]:
    """Lê o marcador `<!-- VERSAO_PROMPT: xxx -->` do header.

    Retorna a versão (slug string) ou None se ausente / texto vazio.
    """
    if not texto:
        return None
    m = _VERSAO_REGEX.search(texto)
    if not m:
        return None
    return m.group(1).strip()


def hash_prompt(texto: str) -> str:
    """SHA256 truncado em 16 chars hex — digital fingerprint do prompt."""
    if texto is None:
        texto = ""
    data = texto.encode("utf-8", errors="ignore")
    return hashlib.sha256(data).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Persistência Redis
# ---------------------------------------------------------------------------

def registrar_versao(
    redis_client,
    versao: str,
    hash_atual: str,
    texto: str,
) -> bool:
    """Grava versão no Redis. Idempotente.

    Estrutura:
      HSET blink:prompt_version:{versao} ts <epoch> hash <hex16>
                                         snippet_first_200 <str>
                                         length_chars <int>
      LPUSH blink:prompt_versions_history {versao}
      LTRIM blink:prompt_versions_history 0 49

    Retorna True se gravou, False se já existia OU sem redis OU erro.
    """
    if not redis_client or not versao:
        return False
    key = f"{_REDIS_KEY_PREFIX}{versao}"
    try:
        # Idempotente: só grava se hash mudou OU se key não existe
        try:
            existing = redis_client.hgetall(key)
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            # decode tolerante (fakeredis às vezes retorna bytes)
            ex_hash = (existing.get(b"hash") if isinstance(existing, dict) and b"hash" in existing
                       else existing.get("hash") if isinstance(existing, dict) else None)
            if isinstance(ex_hash, bytes):
                ex_hash = ex_hash.decode("utf-8", errors="ignore")
            if ex_hash == hash_atual:
                return False  # já está gravado com mesmo hash
        snippet = (texto or "")[:200]
        payload = {
            "ts": str(int(time.time())),
            "hash": hash_atual,
            "snippet_first_200": snippet,
            "length_chars": str(len(texto or "")),
        }
        try:
            redis_client.hset(key, mapping=payload)
        except TypeError:
            # API antiga: hmset
            redis_client.hmset(key, payload)
        try:
            redis_client.lpush(_REDIS_HISTORY_KEY, versao)
            redis_client.ltrim(_REDIS_HISTORY_KEY, 0, _HISTORY_CAP - 1)
        except Exception:  # noqa: BLE001
            log.exception("[PROMPT-VERSION] LPUSH/LTRIM falhou")
        log.info("[PROMPT-VERSION] gravada versao=%s hash=%s", versao, hash_atual)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[PROMPT-VERSION] falha gravando versao=%s: %s", versao, e)
        return False


def _hgetall_decoded(redis_client, key: str) -> dict:
    try:
        raw = redis_client.hgetall(key) or {}
    except Exception:  # noqa: BLE001
        return {}
    out: dict = {}
    for k, v in raw.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8", errors="ignore")
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        out[k] = v
    return out


def listar_versoes(redis_client) -> list[dict]:
    """Retorna histórico: lista de dicts (mais recente primeiro).

    Cada dict = {versao, ts, hash, snippet_first_200, length_chars}.
    """
    if not redis_client:
        return []
    try:
        versoes_raw = redis_client.lrange(_REDIS_HISTORY_KEY, 0, -1) or []
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for v in versoes_raw:
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        versao = str(v)
        info = _hgetall_decoded(redis_client, f"{_REDIS_KEY_PREFIX}{versao}")
        info["versao"] = versao
        # Converte ts e length_chars pra int quando possível
        for k in ("ts", "length_chars"):
            if k in info:
                try:
                    info[k] = int(info[k])
                except (ValueError, TypeError):
                    pass
        out.append(info)
    return out


def diff_versoes(
    redis_client,
    versao_a: str,
    versao_b: str,
) -> dict:
    """Compara 2 versões via metadados (não armazena texto completo)."""
    info_a = _hgetall_decoded(redis_client, f"{_REDIS_KEY_PREFIX}{versao_a}") if redis_client else {}
    info_b = _hgetall_decoded(redis_client, f"{_REDIS_KEY_PREFIX}{versao_b}") if redis_client else {}
    def _as_int(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return None
    ts_a = _as_int(info_a.get("ts"))
    ts_b = _as_int(info_b.get("ts"))
    len_a = _as_int(info_a.get("length_chars")) or 0
    len_b = _as_int(info_b.get("length_chars")) or 0
    return {
        "versao_a": versao_a,
        "versao_b": versao_b,
        "ts_a": ts_a,
        "ts_b": ts_b,
        "hash_a": info_a.get("hash"),
        "hash_b": info_b.get("hash"),
        "mesmo_hash": (
            bool(info_a.get("hash"))
            and info_a.get("hash") == info_b.get("hash")
        ),
        "mudou_length": len_b - len_a,
        "snippet_a": info_a.get("snippet_first_200"),
        "snippet_b": info_b.get("snippet_first_200"),
    }


# ---------------------------------------------------------------------------
# Bootstrap startup
# ---------------------------------------------------------------------------

def _localizar_master_instruction() -> Optional[Path]:
    """Busca _MASTER_INSTRUCTION.md de forma robusta (importa do path do módulo).

    Esse módulo vive em voice_agent/prompt_versioning.py → sobe 1 nível e
    desce em knowledge_base/.
    """
    try:
        here = Path(__file__).resolve().parent
        candidato = here / "knowledge_base" / "_MASTER_INSTRUCTION.md"
        if candidato.exists():
            return candidato
    except Exception:  # noqa: BLE001
        pass
    # Fallback: cwd
    cwd_path = Path("voice_agent/knowledge_base/_MASTER_INSTRUCTION.md")
    if cwd_path.exists():
        return cwd_path
    return None


def auto_registrar_no_startup(redis_client=None) -> dict:
    """Lê _MASTER_INSTRUCTION.md, extrai versão, grava no Redis.

    Pode ser chamado sem `redis_client` — nesse caso retorna info sem gravar.
    Nunca levanta exceção pra cima (no startup, falha silenciosa é ok).
    """
    resultado = {
        "versao": None,
        "hash": None,
        "length_chars": 0,
        "gravou": False,
        "arquivo_lido": None,
        "erro": None,
    }
    try:
        path = _localizar_master_instruction()
        if not path:
            resultado["erro"] = "master_instruction_nao_encontrado"
            return resultado
        try:
            texto = path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            resultado["erro"] = f"read_failed:{e}"
            return resultado
        resultado["arquivo_lido"] = str(path)
        resultado["length_chars"] = len(texto)
        versao = extrair_versao_prompt(texto)
        resultado["versao"] = versao
        h = hash_prompt(texto)
        resultado["hash"] = h
        if versao and redis_client is not None:
            resultado["gravou"] = registrar_versao(redis_client, versao, h, texto)
        return resultado
    except Exception as e:  # noqa: BLE001
        log.exception("[PROMPT-VERSION] auto_registrar_no_startup falhou")
        resultado["erro"] = str(e)[:200]
        return resultado
