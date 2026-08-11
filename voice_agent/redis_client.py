"""Stub/wrapper Redis client para o voice_agent.

Em produção, lê REDIS_URL da env e retorna cliente real.
Em testes sem Redis, retorna None (todas as chamadas falham gracefully).
"""
import os
import logging

log = logging.getLogger(__name__)

_client = None
_initialized = False


def get_redis():
    """Retorna cliente Redis ou None se não disponível."""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_TLS_URL")
    if not redis_url:
        return None
    try:
        import redis as _redis  # type: ignore
        _client = _redis.from_url(redis_url, decode_responses=True)
        _client.ping()
    except Exception as e:  # noqa: BLE001
        log.warning("[REDIS] conexão falhou — sem cache: %s", e)
        _client = None
    return _client
