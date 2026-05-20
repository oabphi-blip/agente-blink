"""Armazenamento persistente de conversas e dedup de mensagens.

PROBLEMA QUE RESOLVE: o histórico das conversas vivia em RAM. Todo
redeploy/restart do container apagava TUDO — o agente perdia o contexto
no meio do atendimento e disparava o menu de boas-vindas como se fosse
uma conversa nova ("pulo de cena"). Mensagens duplicadas idem (o set de
dedup também era volátil).

SOLUÇÃO: persistir em Redis (já existe no stack). Se REDIS_URL não estiver
configurado, cai num fallback em memória — o agente continua funcionando,
só sem sobreviver a restart.

Chaves Redis:
  blink:conv:<key>   → JSON list de {role, content}  (EXPIRE = ttl)
  blink:seen:<msgid> → "1"                            (EXPIRE = 5 min)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Optional

log = logging.getLogger(__name__)

try:
    import redis as _redis  # type: ignore
except ImportError:  # pragma: no cover
    _redis = None


class ConversationStore:
    """Histórico de conversa + dedup de mensagens, com persistência opcional.

    Usa Redis se `redis_url` for fornecido e a lib estiver disponível.
    Caso contrário, fallback em memória (não sobrevive a restart).
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_turns: int = 12,
        ttl_seconds: int = 60 * 60 * 6,  # 6h
        dedup_ttl_seconds: int = 300,    # 5 min
    ):
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.dedup_ttl_seconds = dedup_ttl_seconds

        self._redis = None
        if redis_url and _redis is not None:
            try:
                client = _redis.from_url(
                    redis_url, decode_responses=True,
                    socket_connect_timeout=5, socket_timeout=5,
                )
                client.ping()
                self._redis = client
                log.info("ConversationStore: Redis conectado (persistente)")
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "ConversationStore: Redis indisponível (%s) — usando memória", e
                )
        elif redis_url and _redis is None:
            log.warning("ConversationStore: lib 'redis' ausente — usando memória")

        # Fallback em memória
        self._mem: dict[str, Deque[dict]] = defaultdict(deque)
        self._mem_last_seen: dict[str, float] = {}
        self._mem_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------- histórico

    def get(self, key: str) -> list[dict]:
        """Retorna o histórico da conversa (lista de {role, content})."""
        if self._redis is not None:
            try:
                raw = self._redis.get(f"blink:conv:{key}")
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        return data
                return []
            except Exception as e:  # noqa: BLE001
                log.warning("ConversationStore.get Redis falhou: %s", e)
        # memória
        with self._lock:
            self._gc_mem()
            return list(self._mem.get(key, []))

    def append(self, key: str, role: str, content: str) -> None:
        """Adiciona um turno ao histórico e renova o TTL."""
        if self._redis is not None:
            try:
                rkey = f"blink:conv:{key}"
                history = self.get(key)
                history.append({"role": role, "content": content})
                # janela deslizante
                limit = self.max_turns * 2
                if len(history) > limit:
                    history = history[-limit:]
                self._redis.set(
                    rkey, json.dumps(history, ensure_ascii=False),
                    ex=self.ttl_seconds,
                )
                return
            except Exception as e:  # noqa: BLE001
                log.warning("ConversationStore.append Redis falhou: %s", e)
        # memória
        with self._lock:
            dq = self._mem.setdefault(key, deque())
            dq.append({"role": role, "content": content})
            while len(dq) > self.max_turns * 2:
                dq.popleft()
            self._mem_last_seen[key] = time.time()

    def reset(self, key: str) -> None:
        """Limpa o histórico de uma conversa."""
        if self._redis is not None:
            try:
                self._redis.delete(f"blink:conv:{key}")
                return
            except Exception as e:  # noqa: BLE001
                log.warning("ConversationStore.reset Redis falhou: %s", e)
        with self._lock:
            self._mem.pop(key, None)
            self._mem_last_seen.pop(key, None)

    # ---------------------------------------------------- dedup

    def mark_seen(self, msg_id: str) -> bool:
        """Marca uma mensagem como processada.

        Retorna True se é a PRIMEIRA vez que se vê esse msg_id (deve processar).
        Retorna False se já foi vista antes (é duplicata — ignorar).
        """
        if not msg_id:
            return True
        if self._redis is not None:
            try:
                # SET NX EX — só seta se não existir; retorna True se setou
                ok = self._redis.set(
                    f"blink:seen:{msg_id}", "1",
                    nx=True, ex=self.dedup_ttl_seconds,
                )
                return bool(ok)
            except Exception as e:  # noqa: BLE001
                log.warning("ConversationStore.mark_seen Redis falhou: %s", e)
        # memória
        with self._lock:
            now = time.time()
            # limpa expirados
            cutoff = now - self.dedup_ttl_seconds
            for k in [k for k, t in self._mem_seen.items() if t < cutoff]:
                self._mem_seen.pop(k, None)
            if msg_id in self._mem_seen:
                return False
            self._mem_seen[msg_id] = now
            return True

    # ---------------------------------------------------- interno

    def _gc_mem(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for k in [k for k, t in self._mem_last_seen.items() if t < cutoff]:
            self._mem.pop(k, None)
            self._mem_last_seen.pop(k, None)
