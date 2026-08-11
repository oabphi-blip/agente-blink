"""
Task #325 (20/07/2026) — Regra E6-B: reserva de slot por 10 min +
não repetir slot já ofertado.

CONTEXTO Fábio 14/06/2026 (lead Victor 24147566): Lia ofertou os mesmos
slots várias vezes em 24h, e sem mecanismo de "vaga vai pra fila se não
confirmar em X min". Regra desenhada mas não implementada até hoje.

Como funciona:

1. Quando Lia oferta slot X pro lead Y, chama `marcar_slot_ofertado()`.
   Grava em Redis 2 chaves:
     - `blink:slot_reservado:{cod_med}:{cod_unid}:{YYYYMMDDHHMM}` = lead_id
       com TTL 600s (10 min). Se outro lead tentar oferecer no mesmo slot
       dentro dos 10 min, `slot_reservado_por_outro()` retorna True.
     - Adiciona `{cod_med}:{cod_unid}:{YYYYMMDDHHMM}` ao SET
       `blink:slots_ofertados_lead:{lead_id}` (sem TTL — histórico
       permanente). Evita re-oferta do MESMO slot pro MESMO lead depois
       que expira.

2. `filtrar_slots_disponiveis()` recebe agenda bruta do Medware + lead_id
   e devolve só slots que NÃO estão reservados por outro E que NÃO foram
   ofertados a esse lead antes.

3. `descobrir_reservas_expiradas()` varre chaves e retorna reservas que
   expiraram nos últimos N segundos — usado pelo worker cron pra enviar
   mensagem-gatilho.

Fail-safe: se Redis está fora, todas as funções degradam gracefully —
`filtrar_slots_disponiveis()` retorna agenda inteira, `marcar_slot_ofertado()`
loga warning e segue. Prefere-se aceitar risco de re-oferta a bloquear tudo.

Toggle: env `RESERVA_SLOT_ENABLED=1` (default ON). Setar 0 desativa o
filtro (rollback emergência sem revert de código).
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

log = logging.getLogger(__name__)


# TTL da reserva "quente" (competição entre pacientes).
RESERVA_TTL_SEG = int(os.environ.get("RESERVA_SLOT_TTL_SEG", "600"))  # 10 min

# Prefixos Redis
KEY_RESERVA = "blink:slot_reservado"          # HASH-like: {chave_slot} = lead_id (TTL)
KEY_OFERTADOS_LEAD = "blink:slots_ofertados_lead"  # SET por lead (sem TTL)


def _feature_ligada() -> bool:
    """Default ON. Setar 0/false/no desativa."""
    raw = (os.environ.get("RESERVA_SLOT_ENABLED") or "1").lower()
    return raw not in ("0", "false", "no", "off", "")


def _chave_slot(cod_medico: int, cod_unidade: int, data_hora_iso: str) -> str:
    """`YYYYMMDDHHMM` — mesma granularidade Medware (minutos, não segundos)."""
    limpo = data_hora_iso.replace("-", "").replace(":", "").replace("T", "")
    return f"{int(cod_medico)}:{int(cod_unidade)}:{limpo[:12]}"


def marcar_slot_ofertado(
    redis_client,
    lead_id: int,
    cod_medico: int,
    cod_unidade: int,
    data_hora_iso: str,
    ttl_seg: Optional[int] = None,
) -> bool:
    """Registra que Lia ofertou slot X pro lead Y.

    Retorna True se registrou, False em erro (fail-safe).
    """
    if not _feature_ligada() or redis_client is None:
        return False
    try:
        slot_key = _chave_slot(cod_medico, cod_unidade, data_hora_iso)
        # 1) reserva quente (só o primeiro a ofertar ganha)
        redis_client.setex(
            f"{KEY_RESERVA}:{slot_key}",
            int(ttl_seg or RESERVA_TTL_SEG),
            str(int(lead_id)),
        )
        # 2) histórico permanente por lead
        redis_client.sadd(f"{KEY_OFERTADOS_LEAD}:{int(lead_id)}", slot_key)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("marcar_slot_ofertado erro (fail-safe): %s", exc)
        return False


def slot_reservado_por_outro(
    redis_client,
    lead_id: int,
    cod_medico: int,
    cod_unidade: int,
    data_hora_iso: str,
) -> bool:
    """True se OUTRO lead reservou esse slot nas últimas 10 min."""
    if not _feature_ligada() or redis_client is None:
        return False
    try:
        slot_key = _chave_slot(cod_medico, cod_unidade, data_hora_iso)
        holder = redis_client.get(f"{KEY_RESERVA}:{slot_key}")
        if holder is None:
            return False
        holder_str = holder.decode() if isinstance(holder, bytes) else str(holder)
        return holder_str != str(int(lead_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("slot_reservado_por_outro erro (fail-safe): %s", exc)
        return False


def slot_ja_ofertado_ao_lead(
    redis_client,
    lead_id: int,
    cod_medico: int,
    cod_unidade: int,
    data_hora_iso: str,
) -> bool:
    """True se esse slot já foi ofertado a esse lead antes (mesmo que
    reserva quente tenha expirado). Evita repetir slot X pro Victor 3x."""
    if not _feature_ligada() or redis_client is None:
        return False
    try:
        slot_key = _chave_slot(cod_medico, cod_unidade, data_hora_iso)
        return bool(
            redis_client.sismember(f"{KEY_OFERTADOS_LEAD}:{int(lead_id)}", slot_key)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("slot_ja_ofertado_ao_lead erro (fail-safe): %s", exc)
        return False


def filtrar_slots_disponiveis(
    redis_client,
    lead_id: int,
    cod_medico: int,
    cod_unidade: int,
    slots: Iterable[dict],
) -> list[dict]:
    """Filtra slots removendo:
    - Já reservados nas últimas 10 min por OUTRO lead
    - Já ofertados a esse lead antes

    Se Redis fora / feature off / lead_id inválido → retorna a lista intacta
    (fail-open).
    """
    lista = list(slots)
    if not _feature_ligada() or redis_client is None or not lead_id:
        return lista

    resultado = []
    for s in lista:
        data_iso = s.get("data_iso") or s.get("dataInicio") or ""
        hora = s.get("hora") or ""
        if not data_iso or not hora:
            resultado.append(s)  # não sei o slot, deixa passar
            continue
        dh = f"{data_iso}T{hora}:00" if "T" not in data_iso else data_iso
        try:
            if slot_ja_ofertado_ao_lead(
                redis_client, lead_id, cod_medico, cod_unidade, dh
            ):
                continue
            if slot_reservado_por_outro(
                redis_client, lead_id, cod_medico, cod_unidade, dh
            ):
                continue
        except Exception as exc:  # noqa: BLE001
            log.warning("filtrar_slots_disponiveis erro (fail-open): %s", exc)
        resultado.append(s)
    return resultado


def liberar_reserva(
    redis_client,
    cod_medico: int,
    cod_unidade: int,
    data_hora_iso: str,
) -> bool:
    """Libera reserva antes do TTL — usado quando paciente confirma
    e slot vira agendamento real (não precisa mais bloquear pra fila)."""
    if redis_client is None:
        return False
    try:
        slot_key = _chave_slot(cod_medico, cod_unidade, data_hora_iso)
        redis_client.delete(f"{KEY_RESERVA}:{slot_key}")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("liberar_reserva erro: %s", exc)
        return False


def descobrir_reservas_expiradas_por_lead(
    redis_client,
    lead_id: int,
) -> list[str]:
    """Lista slots que esse lead recebeu oferta mas cuja reserva
    quente já expirou (paciente não confirmou no prazo). Usado pelo
    worker cron pra decidir se dispara mensagem-gatilho.

    Retorna lista de chaves `{cod_med}:{cod_unid}:{YYYYMMDDHHMM}`.
    """
    if redis_client is None:
        return []
    try:
        set_key = f"{KEY_OFERTADOS_LEAD}:{int(lead_id)}"
        todos = redis_client.smembers(set_key) or set()
        expirados = []
        for slot_key_raw in todos:
            slot_key = (
                slot_key_raw.decode()
                if isinstance(slot_key_raw, bytes)
                else str(slot_key_raw)
            )
            ainda_reservado = redis_client.exists(f"{KEY_RESERVA}:{slot_key}")
            if not ainda_reservado:
                expirados.append(slot_key)
        return expirados
    except Exception as exc:  # noqa: BLE001
        log.warning("descobrir_reservas_expiradas_por_lead erro: %s", exc)
        return []
