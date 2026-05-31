"""Etapa "A CLASSIFICAR" — fila operacional pra atendente humano (task #96).

Princípio (Fábio, 31/05/2026):
  Quando o motor de renovação 24h dispara (template ou free-form) e o
  paciente NÃO RESPONDE dentro de N horas, o lead é movido para a etapa
  "A CLASSIFICAR" do pipeline ATENDE. Atendente humano vê a fila e qualifica
  ou descarta — em vez do lead ficar invisível na timeline.

Fluxo:
  1. Dispatcher dispara → grava `blink:janela:ultima_renovacao:<lead>`
     no Redis (já feito) E `blink:classificar:aguardando_resposta:<lead>`
     com TTL TIMEOUT_HORAS+1 e value = epoch do disparo.
  2. Inbound do paciente (webhook /whatsapp ou /kommo) → DELETE da chave
     `blink:classificar:aguardando_resposta:<lead>` (paciente respondeu —
     não precisa classificar).
  3. Cron interno chama /admin/classificar-tick a cada hora. Varre todas
     as chaves `blink:classificar:aguardando_resposta:*` cujo valor (epoch
     do disparo) é mais velho que TIMEOUT_HORAS → move pra A CLASSIFICAR.

Setup operacional (one-time, NO KOMMO via interface web):
  Configurações → Funis → ATENDE → "+ Adicionar etapa"
    Nome: "0.1-A CLASSIFICAR"
    Cor: laranja (#ffce5a) — destaca pra atendente
    Posição: logo após "0-ETAPA ENTRADA"
  Copiar o status_id e setar no Easypanel:
    KOMMO_STATUS_A_CLASSIFICAR_ID=<id_novo>
  Sem isso a feature fica em dry-run automático.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Configuração via env — defaults seguros (feature OFF até Fábio configurar).
STATUS_A_CLASSIFICAR_ID = int(
    os.environ.get("KOMMO_STATUS_A_CLASSIFICAR_ID", "0")
) or None
PIPELINE_ATENDE_ID = int(os.environ.get("KOMMO_PIPELINE_ATENDE_ID", "8601819"))

# Quantas horas após o disparo da renovação, sem resposta → move.
TIMEOUT_CLASSIFICAR_HORAS = int(
    os.environ.get("CLASSIFICAR_TIMEOUT_HORAS", "24")
)

# Padrões de chave Redis.
REDIS_KEY_AGUARDA_FMT = "blink:classificar:aguardando_resposta:{lead_id}"
REDIS_TTL_SEG_PADRAO = (TIMEOUT_CLASSIFICAR_HORAS + 1) * 3600


# ---------------------------------------------------------------------------
# Função pura — testável sem Redis/Kommo
# ---------------------------------------------------------------------------

def deve_mover_para_classificar(
    *,
    disparo_renovacao_ts: float | int | None,
    ultima_resposta_paciente_ts: float | int | None,
    agora: float | int | None = None,
    timeout_horas: int = TIMEOUT_CLASSIFICAR_HORAS,
) -> dict:
    """Decide se o lead já passou do timeout sem responder.

    Regras:
      - Sem disparo registrado → não move (`razao=sem_disparo`).
      - Paciente respondeu DEPOIS do disparo → não move (`razao=paciente_respondeu`).
      - Disparo < timeout_horas → ainda dentro do prazo (`razao=ainda_no_prazo`).
      - Senão → mover.
    """
    if not disparo_renovacao_ts:
        return {"mover": False, "razao": "sem_disparo", "horas_passadas": None}

    agora_ts = agora if agora is not None else time.time()
    delta_h = (agora_ts - float(disparo_renovacao_ts)) / 3600

    if ultima_resposta_paciente_ts is not None:
        if float(ultima_resposta_paciente_ts) > float(disparo_renovacao_ts):
            return {
                "mover": False,
                "razao": "paciente_respondeu",
                "horas_passadas": delta_h,
            }

    if delta_h < timeout_horas:
        return {
            "mover": False,
            "razao": "ainda_no_prazo",
            "horas_passadas": delta_h,
        }

    return {"mover": True, "razao": "timeout_excedido", "horas_passadas": delta_h}


# ---------------------------------------------------------------------------
# Executor — chama Kommo
# ---------------------------------------------------------------------------

@dataclass
class ResultadoClassificar:
    lead_id: int
    movido: bool
    razao: str | None
    horas_passadas: float | None
    erro: str | None = None
    dry_run: bool = False
    status_id_destino: int | None = None


def mover_lead_para_classificar(
    *,
    lead_id: int,
    disparo_renovacao_ts: float | int | None,
    ultima_resposta_paciente_ts: float | int | None,
    kommo_client=None,                # com método update_lead_status(lead_id, status_id, pipeline_id)
    agora: float | int | None = None,
    dry_run: bool = False,
    status_destino_id: int | None = None,
    pipeline_id: int = PIPELINE_ATENDE_ID,
    timeout_horas: int = TIMEOUT_CLASSIFICAR_HORAS,
) -> ResultadoClassificar:
    """Aplica a regra e (se aplicável) muda o status_id no Kommo.

    Nunca levanta — erros vão em `.erro`.
    """
    destino = status_destino_id or STATUS_A_CLASSIFICAR_ID

    decisao = deve_mover_para_classificar(
        disparo_renovacao_ts=disparo_renovacao_ts,
        ultima_resposta_paciente_ts=ultima_resposta_paciente_ts,
        agora=agora,
        timeout_horas=timeout_horas,
    )

    res = ResultadoClassificar(
        lead_id=lead_id,
        movido=False,
        razao=decisao["razao"],
        horas_passadas=decisao["horas_passadas"],
        dry_run=dry_run,
        status_id_destino=destino,
    )

    if not decisao["mover"]:
        return res

    if destino is None:
        res.erro = "KOMMO_STATUS_A_CLASSIFICAR_ID não configurado"
        return res

    if dry_run or kommo_client is None:
        res.razao = "dry_run" if dry_run else "kommo_ausente"
        return res

    try:
        kommo_client.update_lead_status(lead_id, destino, pipeline_id)
        res.movido = True
        return res
    except Exception as exc:  # noqa: BLE001
        res.erro = str(exc)[:300]
        return res


# ---------------------------------------------------------------------------
# Marca / desmarca no Redis (helpers chamados pelo dispatcher + webhook)
# ---------------------------------------------------------------------------

def marcar_aguardando_resposta(
    redis_client, lead_id: int, disparo_ts: float | int | None = None,
    ttl_seg: int = REDIS_TTL_SEG_PADRAO,
) -> str | None:
    chave = REDIS_KEY_AGUARDA_FMT.format(lead_id=lead_id)
    if redis_client is None:
        return chave
    try:
        redis_client.set(chave, int(disparo_ts or time.time()), ex=ttl_seg)
        return chave
    except Exception as exc:  # noqa: BLE001
        log.warning("[CLASSIFICAR] Falha Redis SET: %s", exc)
        return chave


def limpar_aguardando_resposta(redis_client, lead_id: int) -> bool:
    """Chamado quando paciente responde — limpa marcação."""
    chave = REDIS_KEY_AGUARDA_FMT.format(lead_id=lead_id)
    if redis_client is None:
        return False
    try:
        redis_client.delete(chave)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("[CLASSIFICAR] Falha Redis DELETE: %s", exc)
        return False
