"""blink-state — Sprint 3.

Servidor MCP que encapsula estado da conversa em Redis. Implementa
nativamente:
- Dedup por (phone, hash da msg) com TTL 5min (Bug C-11)
- Lock por conversation_key (Fix #183)
- Reserva temporária de slot 10min (Regra E6-B)
- Contagem de turnos do dia (3-turnos máx 0710)

Princípios do livro aplicados:
- 1.1.1: estado isolado em servidor próprio.
- 1.2.2: tools com efeito colateral em chaves Redis.
- 4.5: servidor é o guardião (TTL forçado, validação tipo).
- 6.1: logs stderr.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from typing import Optional

import redis
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-state - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-state")


# ─── Configuração ───────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEDUP_TTL_SECONDS = int(os.getenv("BLINK_DEDUP_TTL_SECONDS", "300"))
LOCK_TTL_SECONDS = int(os.getenv("BLINK_LOCK_TTL_SECONDS", "30"))
RESERVA_SLOT_TTL_SECONDS = int(os.getenv("BLINK_RESERVA_SLOT_TTL_SECONDS", "600"))

# Cliente Redis. Em teste, é substituído por fakeredis via monkeypatch.
_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _set_redis(client: redis.Redis) -> None:
    """Para uso em testes."""
    global _redis_client
    _redis_client = client


mcp = FastMCP("blink-state")


# ─── DEDUP DE MENSAGEM ──────────────────────────────────────────────

@mcp.tool()
def dedup_check(phone: str, texto: str) -> bool:
    """Verifica e marca dedup de mensagem inbound do paciente.

    Retorna True se a mensagem é nova (deve ser processada). Retorna False
    se foi vista nos últimos 5 minutos (deve ser ignorada).

    Implementa a defesa contra rajadas de webhook (Bug C-11) e pipeline
    duplicado (Fix #183).

    Args:
        phone: Telefone E.164 do paciente. Ex: "5561981331005".
        texto: Texto literal da mensagem.

    Returns:
        True se é mensagem nova, False se é duplicata.
    """
    h = hashlib.sha256(f"{phone}|{texto}".encode()).hexdigest()[:16]
    key = f"blink:dedup:{phone}:{h}"
    r = _get_redis()
    # SETNX com TTL — operação atômica
    foi_nova = r.set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
    log.info("dedup_check phone=%s h=%s nova=%s", phone, h, bool(foi_nova))
    return bool(foi_nova)


# ─── LOCK POR CONVERSA ──────────────────────────────────────────────

@mcp.tool()
def acquire_conversation_lock(phone: str) -> bool:
    """Adquire lock para evitar processamento concorrente da mesma conversa.

    Use ANTES de chamar o pipeline da Lia. Se já existe lock, espera ou
    retorna False. Resolve o problema do Fix #183 (mensagens em rajada
    sendo processadas em paralelo causando estado inconsistente).

    Args:
        phone: Telefone E.164.

    Returns:
        True se conseguiu o lock. False se outro processo já está rodando.
    """
    key = f"blink:lock:conv:{phone}"
    r = _get_redis()
    pego = r.set(key, str(int(time.time())), nx=True, ex=LOCK_TTL_SECONDS)
    log.info("acquire_lock phone=%s pego=%s", phone, bool(pego))
    return bool(pego)


@mcp.tool()
def release_conversation_lock(phone: str) -> None:
    """Libera o lock da conversa. Chame ao terminar o processamento."""
    key = f"blink:lock:conv:{phone}"
    _get_redis().delete(key)
    log.info("release_lock phone=%s", phone)


# ─── RESERVA TEMPORÁRIA DE SLOT ─────────────────────────────────────

class ReservaSlotInput(BaseModel):
    phone: str = Field(..., min_length=10)
    cod_agenda: int = Field(..., ge=1)
    cod_medico: int = Field(..., ge=1)
    cod_unidade: int = Field(..., ge=1)
    data_iso: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    hora: str = Field(..., pattern=r"^\d{2}:\d{2}$")


@mcp.tool()
def reservar_slot_temporariamente(
    phone: str,
    cod_agenda: int,
    cod_medico: int,
    cod_unidade: int,
    data_iso: str,
    hora: str,
) -> dict:
    """Reserva slot Medware por 10 minutos para um paciente.

    Implementa a regra E6-B (Bug Victor 24147566). Quando a Lia oferta um
    slot ao paciente, o slot fica reservado por 10 min — ninguém mais pode
    receber a mesma oferta. Após 10 min sem confirmação, libera.

    Args:
        phone, cod_agenda, cod_medico, cod_unidade, data_iso, hora.

    Returns:
        Dict com {ok, reservado_ate_epoch, ja_reservado_por_outro}.
    """
    inp = ReservaSlotInput(
        phone=phone, cod_agenda=cod_agenda, cod_medico=cod_medico,
        cod_unidade=cod_unidade, data_iso=data_iso, hora=hora,
    )
    slot_key = (
        f"blink:reserva_slot:{inp.cod_agenda}:{inp.cod_medico}:"
        f"{inp.cod_unidade}:{inp.data_iso}:{inp.hora}"
    )
    r = _get_redis()
    ja_existe = r.get(slot_key)

    if ja_existe and ja_existe != inp.phone:
        log.warning(
            "Slot já reservado por outro phone=%s tentou phone=%s",
            ja_existe, inp.phone,
        )
        return {
            "ok": False,
            "ja_reservado_por_outro": True,
            "phone_dono": ja_existe,
        }

    expira_em = int(time.time()) + RESERVA_SLOT_TTL_SECONDS
    r.set(slot_key, inp.phone, ex=RESERVA_SLOT_TTL_SECONDS)
    log.info("reserva ok phone=%s slot=%s expira=%d", inp.phone, slot_key, expira_em)
    return {
        "ok": True,
        "reservado_ate_epoch": expira_em,
        "ja_reservado_por_outro": False,
    }


@mcp.tool()
def liberar_reserva_slot(
    cod_agenda: int, cod_medico: int, cod_unidade: int,
    data_iso: str, hora: str,
) -> None:
    """Libera reserva de slot (chamar após confirmação ou cancelamento)."""
    slot_key = (
        f"blink:reserva_slot:{cod_agenda}:{cod_medico}:"
        f"{cod_unidade}:{data_iso}:{hora}"
    )
    _get_redis().delete(slot_key)


# ─── CONTAGEM DE TURNOS DO DIA ──────────────────────────────────────

@mcp.tool()
def incrementar_turno_dia(phone: str) -> int:
    """Incrementa contador de turnos do paciente neste dia.

    Usado pelo agente 0710 para limitar a 3 turnos/dia (regra anti-spam).
    TTL automático de 24h.

    Returns:
        Novo valor do contador.
    """
    from datetime import date
    hoje = date.today().isoformat()
    key = f"blink:turnos_dia:{phone}:{hoje}"
    r = _get_redis()
    novo = r.incr(key)
    if novo == 1:
        r.expire(key, 86400)  # 24h TTL na primeira inserção
    return int(novo)


@mcp.tool()
def consultar_turno_dia(phone: str) -> int:
    """Consulta quantos turnos o paciente já teve hoje."""
    from datetime import date
    hoje = date.today().isoformat()
    key = f"blink:turnos_dia:{phone}:{hoje}"
    val = _get_redis().get(key)
    return int(val) if val else 0


# ─── CTX KNOWN (estado da conversa) ─────────────────────────────────

@mcp.tool()
def salvar_ctx_known(phone: str, ctx: dict, ttl_horas: int = 48) -> None:
    """Salva ctx.known da conversa em Redis com TTL configurável.

    ctx.known é o estado consolidado da Lia: nome paciente, médico,
    unidade, convênio, preferência de horário, especialidade. Persistido
    para sobreviver entre turnos.

    Args:
        phone: Telefone E.164.
        ctx: Dict com os campos consolidados.
        ttl_horas: Tempo de vida em horas. Default 48h.
    """
    key = f"blink:ctx_known:{phone}"
    _get_redis().set(key, json.dumps(ctx), ex=ttl_horas * 3600)


@mcp.tool()
def carregar_ctx_known(phone: str) -> Optional[dict]:
    """Carrega ctx.known persistido. Retorna None se não existe."""
    key = f"blink:ctx_known:{phone}"
    val = _get_redis().get(key)
    return json.loads(val) if val else None


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("state://conversa/{phone}/ctx")
def resource_ctx(phone: str) -> str:
    """Leitura do ctx.known atual de uma conversa."""
    ctx = carregar_ctx_known(phone)
    if ctx is None:
        return f"Nenhum ctx persistido para phone={phone}"
    return json.dumps(ctx, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    log.info("Iniciando blink-state MCP server. REDIS_URL=%s", REDIS_URL)
    mcp.run()
