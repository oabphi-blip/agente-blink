"""
supabase_memory.py — Memória persistente via Supabase (C-150)

Substitui/complementa Zep com banco real. Cada turno grava em conversations.
Antes do LLM, lemos as últimas 20 msgs do telefone para contexto.

Fail-open: se Supabase indisponível, pipeline continua normalmente.
Toggle: SUPABASE_MEMORY_ENABLED (default 1 quando SUPABASE_URL configurado)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy-init do client Supabase. Retorna None se não configurado."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")  # service_role key
    enabled = os.getenv("SUPABASE_MEMORY_ENABLED", "1" if url else "0")

    if enabled in ("0", "false", "no", "off") or not url or not key:
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        log.info("[SUPABASE] client inicializado — %s", url[:40])
    except Exception as e:
        log.warning("[SUPABASE] falha ao inicializar client: %s", e)
        _client = None

    return _client


def gravar_mensagem(
    phone: str,
    role: str,
    content: str,
    lead_id: Optional[int] = None,
    channel: str = "wa_cloud",
    metadata: Optional[dict] = None,
) -> bool:
    """
    Grava 1 mensagem no histórico.
    role: 'patient' | 'lia' | 'human'
    Retorna True se gravou, False se falhou (fail-open).
    """
    if not content or not content.strip():
        return False

    client = _get_client()
    if client is None:
        return False

    try:
        row = {
            "phone": phone,
            "role": role,
            "content": content[:4000],
            "channel": channel,
            "metadata": metadata or {},
        }
        if lead_id:
            row["lead_id"] = lead_id

        client.table("conversations").insert(row).execute()
        return True
    except Exception as e:
        log.warning("[SUPABASE] gravar_mensagem falhou: %s", e)
        return False


def ler_historico(phone: str, limit: int = 20) -> list[dict]:
    """
    Retorna últimas `limit` mensagens do telefone, ordenadas crescente (mais antiga primeiro).
    Cada item: {"role": str, "content": str, "ts": str}
    Retorna [] em caso de falha.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        resp = (
            client.table("conversations")
            .select("role, content, ts")
            .eq("phone", phone)
            .order("ts", desc=True)
            .limit(limit)
            .execute()
        )
        msgs = list(reversed(resp.data or []))
        return msgs
    except Exception as e:
        log.warning("[SUPABASE] ler_historico falhou: %s", e)
        return []


def montar_bloco_historico_supabase(phone: str, limit: int = 20) -> str:
    """
    Monta bloco de texto para injeção no system prompt.
    Formato: [PACIENTE HH:MM DD/MM] texto / [LIA HH:MM DD/MM] texto
    Retorna "" se vazio ou falha.
    """
    msgs = ler_historico(phone, limit=limit)
    if not msgs:
        return ""

    linhas = []
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        ts_str = m.get("ts", "")

        if role == "patient":
            label = "PACIENTE"
        elif role == "lia":
            label = "LIA"
        elif role == "human":
            label = "HUMANO"
        else:
            label = role.upper()

        hora = ""
        if ts_str:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                hora = dt.strftime("%H:%M %d/%m")
            except Exception:
                hora = ts_str[:16]

        linhas.append(f"[{label} {hora}] {content[:300]}")

    return "\n".join(linhas)


def esta_ativo() -> bool:
    """Retorna True se o módulo está configurado e operacional."""
    return _get_client() is not None
