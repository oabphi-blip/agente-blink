"""Gerenciador de job assíncrono pra dedup de leads.

Origem: Fábio 05/06/2026 — pediu barra de progresso live + breakdown
por etapa + ETA, podendo fazer outras coisas em paralelo.

Como funciona:
1. POST /admin/dedup-async-start dispara `iniciar_job()` numa thread
2. Thread grava estado em Redis (`blink:dedup_job:{job_id}`) a cada N leads
3. GET /admin/dedup-async-status?job_id=X lê Redis e devolve JSON
4. Artifact HTML faz polling a cada 3s e renderiza a UI

Estado em Redis (TTL 2h):
  {
    "job_id": "abc123",
    "status": "running" | "done" | "error",
    "iniciado_em": ts,
    "atualizado_em": ts,
    "concluido_em": ts | null,
    "fase": "lendo_etapa" | "agrupando" | "aplicando" | "concluido",
    "etapa_atual": int | null,
    "etapa_nome": str | null,
    "params": {dry_run, max_leads, status_ids, status_destino},
    "total_lidos": int, "max_leads": int,
    "com_telefone": int, "sem_telefone": int,
    "grupos_duplicados": int, "total_duplicados": int,
    "movidos": int, "falhas": int,
    "por_etapa": {...},
    "amostra_grupos": [...],  # só ao concluir
    "erro": str | null
  }
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Optional

log = logging.getLogger(__name__)

JOB_KEY_PREFIX = "blink:dedup_job"
JOB_TTL_SEG = 2 * 60 * 60  # 2 horas


def gerar_job_id() -> str:
    """8 chars hex — suficiente pra evitar colisão em sessão."""
    return uuid.uuid4().hex[:8]


def _key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}:{job_id}"


def _salvar_estado(redis_cli, job_id: str, estado: dict) -> None:
    """Grava estado JSON em Redis com TTL."""
    if redis_cli is None:
        return
    estado["atualizado_em"] = int(time.time())
    try:
        redis_cli.setex(_key(job_id), JOB_TTL_SEG, json.dumps(estado))
    except Exception as exc:  # noqa: BLE001
        log.warning("[DEDUP-JOB] salvar_estado %s: %s", job_id, exc)


def get_status(redis_cli, job_id: str) -> Optional[dict]:
    """Lê estado atual do job. None se não existe."""
    if redis_cli is None:
        return None
    try:
        raw = redis_cli.get(_key(job_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("[DEDUP-JOB] get_status %s: %s", job_id, exc)
        return None


def iniciar_job(
    redis_cli,
    kommo_client,
    *,
    pipeline_id: int = 8601819,
    status_ids: Optional[list[int]] = None,
    status_destino: int = 143,
    max_leads: int = 500,
    dry_run: bool = True,
) -> str:
    """Inicia job em background. Devolve job_id pra polling."""
    from voice_agent.deduplicar_leads import (
        deduplicar_batch, STATUS_IDS_DEDUP_SEGUROS,
    )

    job_id = gerar_job_id()
    sids = status_ids or list(STATUS_IDS_DEDUP_SEGUROS)
    estado_inicial = {
        "job_id": job_id,
        "status": "running",
        "iniciado_em": int(time.time()),
        "concluido_em": None,
        "fase": "iniciando",
        "etapa_atual": None,
        "etapa_nome": None,
        "params": {
            "pipeline_id": pipeline_id,
            "status_ids": sids,
            "status_destino": status_destino,
            "max_leads": max_leads,
            "dry_run": dry_run,
        },
        "total_lidos": 0,
        "max_leads": max_leads,
        "com_telefone": 0,
        "sem_telefone": 0,
        "grupos_duplicados": 0,
        "total_duplicados": 0,
        "movidos": 0,
        "falhas": 0,
        "por_etapa": {},
        "amostra_grupos": [],
        "erro": None,
    }
    _salvar_estado(redis_cli, job_id, estado_inicial)

    def _progress(stats: dict) -> None:
        estado_atual = get_status(redis_cli, job_id) or estado_inicial
        estado_atual.update({
            "fase": stats.get("fase", estado_atual.get("fase")),
            "total_lidos": stats.get(
                "total_lidos", estado_atual.get("total_lidos")
            ),
            "com_telefone": stats.get(
                "com_telefone", estado_atual.get("com_telefone")
            ),
            "sem_telefone": stats.get(
                "sem_telefone", estado_atual.get("sem_telefone")
            ),
            "grupos_duplicados": stats.get(
                "grupos_duplicados", estado_atual.get("grupos_duplicados")
            ),
            "total_duplicados": stats.get(
                "total_duplicados", estado_atual.get("total_duplicados")
            ),
            "movidos": stats.get("movidos", estado_atual.get("movidos")),
            "falhas": stats.get("falhas", estado_atual.get("falhas")),
        })
        if "etapa_atual" in stats:
            estado_atual["etapa_atual"] = stats["etapa_atual"]
            estado_atual["etapa_nome"] = stats.get("etapa_nome")
        if "resultado" in stats:
            r = stats["resultado"]
            estado_atual["por_etapa"] = r.get("por_etapa", {})
            estado_atual["amostra_grupos"] = r.get("amostra_grupos", [])
        _salvar_estado(redis_cli, job_id, estado_atual)

    def _worker():
        try:
            resultado = deduplicar_batch(
                kommo_client,
                pipeline_id=pipeline_id,
                status_ids=sids,
                status_destino_duplicado=status_destino,
                max_leads=max_leads,
                dry_run=dry_run,
                progress_callback=_progress,
            )
            final = get_status(redis_cli, job_id) or estado_inicial
            final.update({
                "status": "done",
                "fase": "concluido",
                "concluido_em": int(time.time()),
                "total_lidos": resultado.get("total_lidos", 0),
                "com_telefone": resultado.get("com_telefone", 0),
                "sem_telefone": resultado.get("sem_telefone", 0),
                "grupos_duplicados": resultado.get("grupos_duplicados", 0),
                "total_duplicados": resultado.get("total_duplicados", 0),
                "movidos": resultado.get("movidos", 0),
                "falhas": resultado.get("falhas", 0),
                "por_etapa": resultado.get("por_etapa", {}),
                "amostra_grupos": resultado.get("amostra_grupos", []),
                "etapas_varridas": resultado.get("etapas_varridas", []),
            })
            _salvar_estado(redis_cli, job_id, final)
            log.info(
                "[DEDUP-JOB] %s done — %d duplicados em %d grupos · movidos=%d",
                job_id, resultado.get("total_duplicados", 0),
                resultado.get("grupos_duplicados", 0),
                resultado.get("movidos", 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("[DEDUP-JOB] %s erro: %s", job_id, exc)
            erro_state = get_status(redis_cli, job_id) or estado_inicial
            erro_state.update({
                "status": "error",
                "fase": "erro",
                "concluido_em": int(time.time()),
                "erro": str(exc)[:500],
            })
            _salvar_estado(redis_cli, job_id, erro_state)

    t = threading.Thread(target=_worker, daemon=True, name=f"dedup-{job_id}")
    t.start()
    return job_id


def calcular_eta(estado: dict) -> Optional[int]:
    """Estima segundos restantes baseado em ritmo atual.

    Heurística: tempo_decorrido / total_lidos × max_leads_restantes.
    Devolve None se não dá pra estimar.
    """
    iniciado = estado.get("iniciado_em")
    total_lidos = estado.get("total_lidos", 0)
    max_leads = estado.get("max_leads", 0)
    if not iniciado or total_lidos <= 0 or max_leads <= 0:
        return None
    decorrido = max(1, int(time.time()) - int(iniciado))
    ritmo = total_lidos / decorrido  # leads/s
    if ritmo <= 0:
        return None
    restantes = max(0, max_leads - total_lidos)
    return int(restantes / ritmo)
