"""Chaos engineering — injeta falha em serviços externos pra validar
que a Lia ESCALA pra humano em vez de inventar resposta.

Padrão Netflix: força timeout em Medware/Kommo/Anthropic via flag Redis
`blink:chaos:{servico}:down` (TTL default 300s).

Em medware.py / kommo.py / responder.py (call modelo) há um gate
condicional MUITO PEQUENO no início da função principal:

    if redis_client and chaos.esta_em_chaos(redis_client, "medware"):
        raise TimeoutError("chaos_test_active")

Quando flag desligada (default), código roda 100% normal — zero overhead.

Endpoints:
  /admin/chaos-tick?servico=medware&ttl=300 → injeta
  /admin/chaos-stop?servico=medware           → para
  /admin/chaos-status                          → lista ativos
  /admin/chaos-suite                           → executa suite completa
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


SERVICOS_VALIDOS = ("medware", "kommo", "anthropic", "redis_slow")
_PREFIX = "blink:chaos:"
_SUFFIX_DOWN = ":down"
_DEFAULT_TTL = 300


def _key(servico: str) -> str:
    return f"{_PREFIX}{servico}{_SUFFIX_DOWN}"


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------

def injetar_falha(
    redis_client,
    servico: str,
    ttl_seg: int = _DEFAULT_TTL,
) -> bool:
    """Marca serviço como em chaos por `ttl_seg`. Retorna True se gravou."""
    if not redis_client:
        return False
    s = (servico or "").strip().lower()
    if s not in SERVICOS_VALIDOS:
        log.warning("[CHAOS] servico invalido: %s", servico)
        return False
    ttl = max(1, int(ttl_seg or _DEFAULT_TTL))
    try:
        redis_client.setex(_key(s), ttl, "1")
        log.warning("[CHAOS] injetada falha servico=%s ttl=%ds", s, ttl)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[CHAOS] falha gravando key=%s: %s", _key(s), e)
        return False


def esta_em_chaos(redis_client, servico: str) -> bool:
    """Checa se chaos ativo. Default False em qualquer erro/sem redis."""
    if not redis_client or not servico:
        return False
    s = servico.strip().lower()
    try:
        return bool(redis_client.exists(_key(s)))
    except Exception:  # noqa: BLE001
        return False


def parar_chaos(redis_client, servico: Optional[str] = None) -> int:
    """Para chaos. Sem `servico` para TODOS. Retorna nº de chaves removidas."""
    if not redis_client:
        return 0
    if servico:
        s = servico.strip().lower()
        try:
            return int(redis_client.delete(_key(s)) or 0)
        except Exception:  # noqa: BLE001
            return 0
    total = 0
    for s in SERVICOS_VALIDOS:
        try:
            total += int(redis_client.delete(_key(s)) or 0)
        except Exception:  # noqa: BLE001
            pass
    return total


def status_chaos(redis_client) -> dict:
    """Retorna {servico: bool} pra todos os servicos validos."""
    return {s: esta_em_chaos(redis_client, s) for s in SERVICOS_VALIDOS}


# ---------------------------------------------------------------------------
# Suite — orquestrador
# ---------------------------------------------------------------------------

_CENARIO_SENTINELA = {
    "nome": "chaos_sentinela_escala_humano",
    "persona": "Paciente quer marcar consulta — chaos ativo deve forçar escalation",
    "inputs": ["Oi, quero marcar consulta com a Dra. Karla, sou particular"],
    # Lia DEVE escalar ou prometer reconsultar em 1 minuto (frase honesta),
    # NÃO inventar data/hora.
    "must_not_contain": [
        r"(?i)(segunda|ter[çc]a|quarta|quinta|sexta).*\d{2}/\d{2}",  # dia+data
        r"R\$\s*\d",  # valor sem contexto
    ],
}


def executar_chaos_suite(
    redis_client,
    ttl_por_servico: int = 60,
    agent_callable=None,
) -> dict:
    """Orquestra chaos test pra cada serviço.

    Para cada `servico in SERVICOS_VALIDOS`:
      1. injeta falha (TTL curto, 60s default)
      2. dispara cenário sintético contra a Lia
      3. valida que NÃO inventou data/preço (must_not_contain regex)
      4. para chaos

    Retorna `{servico: {falhou_ok: bool, escalou: bool, latencia_ms: int,
                         erro: str|None}}`.

    `agent_callable(cenario_dict)` — opcional, default usa
    synthetic_users.executar_cenario.
    """
    out: dict = {}
    try:
        from voice_agent.synthetic_users import executar_cenario
    except Exception as e:  # noqa: BLE001
        log.warning("[CHAOS-SUITE] synthetic_users indisponivel: %s", e)
        executar_cenario = None  # type: ignore[assignment]

    for s in SERVICOS_VALIDOS:
        t0 = time.time()
        item: dict = {
            "falhou_ok": False,
            "escalou": False,
            "latencia_ms": 0,
            "erro": None,
        }
        injetou = injetar_falha(redis_client, s, ttl_seg=ttl_por_servico)
        if not injetou:
            item["erro"] = "nao_conseguiu_injetar"
            out[s] = item
            continue
        try:
            if executar_cenario is None or agent_callable is None:
                # Sem agent — só valida que o gate Redis está ativo.
                item["falhou_ok"] = esta_em_chaos(redis_client, s)
                item["escalou"] = item["falhou_ok"]
            else:
                resultado = executar_cenario(
                    dict(_CENARIO_SENTINELA),
                    agent_callable=agent_callable,
                )
                # ok=True significa cenário validou must_not_contain — não
                # vazou data inventada. Isso PROVA que escalou ou hesitou.
                item["falhou_ok"] = bool(resultado.get("ok"))
                item["escalou"] = bool(resultado.get("ok"))
        except Exception as e:  # noqa: BLE001
            item["erro"] = str(e)[:200]
        finally:
            parar_chaos(redis_client, s)
        item["latencia_ms"] = int((time.time() - t0) * 1000)
        out[s] = item
    return out
