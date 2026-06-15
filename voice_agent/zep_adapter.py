# voice_agent/zep_adapter.py
"""Adapter Zep Cloud — memória de longo prazo para a Lia.

Integra com o ConversationStore/Redis existente:
- recuperar_contexto(): chamada ANTES de montar messages[]
- gravar_turno(): chamada APÓS resposta gerada

Falha silenciosa em todos os casos — nunca quebra reply().
Ativa com ZEP_API_KEY no ambiente; inerte se chave ausente.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_ZEP_API_KEY = os.environ.get("ZEP_API_KEY", "")


def _get_client():
      """Retorna cliente Zep ou None se chave ausente."""
      if not _ZEP_API_KEY:
                return None
            try:
                      from zep_cloud.client import Zep  # SDK sincrono
        return Zep(api_key=_ZEP_API_KEY)
except Exception as exc:
        log.warning("[ZEP] Falha ao criar cliente: %s", exc)
        return None


_client = _get_client()


def recuperar_contexto(session_id: str) -> list[dict]:
      """Busca memoria do paciente no Zep e retorna no formato messages Anthropic.

          Chamada ANTES de montar o bloco variavel do system prompt.
              Retorna [] se sessao nova, Zep down ou chave ausente.
                  """
    if not _client or not session_id:
              return []
          try:
                    memory = _client.memory.get(session_id)
                    msgs = []
                    for m in (memory.messages or []):
                                  role = "user" if (m.role_type or "").lower() == "user" else "assistant"
                                  content = (m.content or "").strip()
                                  if content:
                                                    msgs.append({"role": role, "content": content})
                                            log.info("[ZEP] recuperou %d msgs da sessao %s", len(msgs), session_id)
                              return msgs
except Exception as exc:
        log.warning("[ZEP] recuperar_contexto falhou (%s) — seguindo sem memoria", exc)
        return []


def gravar_turno(session_id: str, user_msg: str, assistant_msg: str) -> None:
      """Grava par user/assistant no Zep apos a resposta ser gerada.

          Chamada APOS _scrub_prohibited() e persistencia no ConversationStore.
              Falha silenciosa — nao levanta excecao para fora.
                  """
    if not _client or not session_id:
              return
    try:
              from zep_cloud.types import Message
        _client.memory.add(
                      session_id,
                      messages=[
                                        Message(role_type="user", content=user_msg),
                                        Message(role_type="assistant", content=assistant_msg),
                      ],
        )
        log.info("[ZEP] turno gravado na sessao %s", session_id)
except Exception as exc:
        log.warning("[ZEP] gravar_turno falhou (%s) — historico so no Redis", exc)
