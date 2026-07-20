"""Dedup outbound anti-loop (Bug C-62 / 20-07-2026).

Origem: Fábio 20/07 — lead 24325532. Lia mandou 'Anotado. Qual dia da
semana e turno funcionam melhor pra vocês?' **7 vezes** em 5 minutos
(21:16-21:21). Paciente disse 'meu deus' e desistiu.

Solução:
    1. Hash SHA256 do outbound (primeiros 300 chars normalizados)
    2. Registro em Redis com TTL 180s (3min)
    3. Se mesmo hash detectado 3× em janela → LOOP DETECTADO
    4. Loop detectado → substitui resposta pela nota humana canônica +
       flag Redis pra pipeline mover lead pra 1-ATENDIMENTO HUMANO

Design defensivo:
    - Fail-open: sem Redis / erro → retorna 'OK enviar' (não bloqueia fluxo)
    - Normalização hash: lower + strip + colapsa espaços (ignora emojis/case)
    - Contador reseta em Redis a cada janela de 300s
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any, Optional

log = logging.getLogger(__name__)

TTL_JANELA_SEG = 180                # 3min — quanto tempo o hash "conta"
LIMITE_LOOP = 3                     # 3 vezes = loop
CHAVE_PREFIXO = "blink:c62_dedup:"  # chave Redis
CHAVE_LOOP_FLAG = "blink:c62_loop_detectado:"  # flag Redis pra pipeline


def _ativado() -> bool:
    return (os.getenv("DEDUP_OUTBOUND_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off",
    )


# ═══════════════════════════════════════════════════════════════════════
# HASH normalizado
# ═══════════════════════════════════════════════════════════════════════

_RE_ESPACOS = re.compile(r"\s+")


def _normalizar_texto(texto: str) -> str:
    """Normaliza pra hash consistente: lower + strip + espaços únicos."""
    if not texto:
        return ""
    t = texto.strip().lower()
    t = _RE_ESPACOS.sub(" ", t)
    # Primeiros 300 chars evita hash de textos idênticos com sufixo diferente
    return t[:300]


def _calcular_hash(texto: str) -> str:
    normalizado = _normalizar_texto(texto)
    if not normalizado:
        return ""
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════
# CHECAGEM PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════

def verificar_e_registrar(
    lead_id: int | str,
    texto: str,
    redis_client: Optional[Any] = None,
) -> dict:
    """Verifica se outbound é duplicata + registra.

    Returns:
        {
            'permitir_envio': bool,       # False = está em loop, bloqueia
            'eh_duplicata': bool,         # True se já foi vista antes
            'loop_detectado': bool,       # True se ≥ LIMITE_LOOP repetições
            'contador': int,              # quantas vezes viu essa mensagem
            'hash': str,                  # hash calculado
            'razao': str,                 # 'ok' | 'duplicata' | 'loop'
        }
    """
    resultado = {
        "permitir_envio": True,
        "eh_duplicata": False,
        "loop_detectado": False,
        "contador": 0,
        "hash": "",
        "razao": "ok",
    }

    if not _ativado():
        return resultado

    if not texto or not texto.strip() or lead_id is None:
        return resultado

    hash_msg = _calcular_hash(texto)
    resultado["hash"] = hash_msg

    if not hash_msg:
        return resultado

    if redis_client is None:
        # Fail-open: sem Redis, permite envio
        return resultado

    try:
        chave = f"{CHAVE_PREFIXO}{lead_id}:{hash_msg}"

        # INCR + set TTL na primeira vez
        contador = int(redis_client.incr(chave) or 1)
        if contador == 1:
            redis_client.expire(chave, TTL_JANELA_SEG)

        resultado["contador"] = contador
        resultado["eh_duplicata"] = contador >= 2

        if contador >= LIMITE_LOOP:
            resultado["loop_detectado"] = True
            resultado["permitir_envio"] = False
            resultado["razao"] = "loop"
            # Grava flag pro pipeline detectar e desativar IA
            try:
                redis_client.setex(
                    f"{CHAVE_LOOP_FLAG}{lead_id}",
                    3600,  # 1h
                    hash_msg,
                )
            except Exception:  # noqa: BLE001
                pass
            log.error(
                "[C-62 DEDUP] LOOP detectado lead=%s hash=%s contador=%d",
                lead_id, hash_msg, contador,
            )
        elif contador >= 2:
            resultado["razao"] = "duplicata"
            log.warning(
                "[C-62 DEDUP] DUPLICATA lead=%s hash=%s contador=%d",
                lead_id, hash_msg, contador,
            )

    except Exception as e:  # noqa: BLE001
        log.warning("[C-62 DEDUP] Falha Redis: %s — fail-open", e)
        # Fail-open

    return resultado


# ═══════════════════════════════════════════════════════════════════════
# RESPOSTA CANÔNICA quando loop é detectado
# ═══════════════════════════════════════════════════════════════════════

def resposta_canonica_loop(nome_paciente: Optional[str] = None) -> str:
    """Substituto pro texto que estava em loop."""
    saudacao = f"{nome_paciente.split()[0]}, " if nome_paciente else ""
    return (
        f"{saudacao}peço desculpas — nosso sistema estava com uma repetição. "
        "Já passei seu atendimento pra nossa equipe. Em instantes uma pessoa "
        "da Blink responde por aqui. 🤝"
    )


def lead_esta_em_loop(
    lead_id: int | str,
    redis_client: Optional[Any] = None,
) -> bool:
    """Query rápida pro pipeline decidir se move lead pra 1-ATENDIMENTO HUMANO."""
    if redis_client is None or not _ativado():
        return False
    try:
        v = redis_client.get(f"{CHAVE_LOOP_FLAG}{lead_id}")
        return bool(v)
    except Exception:  # noqa: BLE001
        return False


def limpar_flag_loop(
    lead_id: int | str,
    redis_client: Optional[Any] = None,
) -> None:
    """Chamado depois de mover lead pra humano — evita retrigger."""
    if redis_client is None:
        return
    try:
        redis_client.delete(f"{CHAVE_LOOP_FLAG}{lead_id}")
    except Exception:  # noqa: BLE001
        pass
