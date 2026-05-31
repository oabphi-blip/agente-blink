"""Cron interno do voice_agent — roda background dentro do FastAPI.

Substitui necessidade de N8N ou scheduled task externa. Hook no startup
do app (em webhook.py:create_app). Loops em threads daemon:

  1. classificar_tick — a cada CLASSIFICAR_CADA_HORAS (default 1h)
     varre Redis blink:classificar:aguardando_resposta:* e move quem
     passou timeout pra etapa "0-a classificar".

  2. renovacao_varredura — TODO próxima sessão. Vai iterar leads Kommo
     em STATUS_IDS_ANTES_AGENDADO + ja_respondeu, e disparar dispatcher.

Envs:
  BLINK_CRON_ENABLED=1     → liga (default OFF)
  BLINK_CRON_DRY_RUN=true  → não move/dispara, só loga (default ON)
  CLASSIFICAR_CADA_HORAS=1 → frequência do classificar (default 1h)
  CLASSIFICAR_TIMEOUT_HORAS=24 → tempo após disparo pra mover (default 24h)

Pra desligar: setar BLINK_CRON_ENABLED=0 e redeploy.
"""
from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger(__name__)


def _enabled() -> bool:
    return (os.environ.get("BLINK_CRON_ENABLED") or "").strip() == "1"


def _dry_run_default() -> bool:
    raw = (os.environ.get("BLINK_CRON_DRY_RUN") or "true").lower()
    return raw in ("1", "true", "yes", "on")


def _intervalo_classificar_seg() -> int:
    raw = (os.environ.get("CLASSIFICAR_CADA_HORAS") or "1").strip()
    try:
        return max(int(float(raw) * 3600), 60)  # mínimo 1 min
    except ValueError:
        return 3600


# ---------------------------------------------------------------------------
# Worker: classificar_tick
# ---------------------------------------------------------------------------

def _executar_classificar(*, pipeline, dry_run: bool) -> dict:
    """Lógica idêntica ao endpoint /admin/classificar-tick (varredura completa).

    Devolve resumo {ok, total_candidatos, movidos, dry_run}.
    """
    from voice_agent.classificar import (
        REDIS_KEY_AGUARDA_FMT,
        get_status_a_classificar_id,
        get_timeout_classificar_horas,
        mover_lead_para_classificar,
    )

    destino = get_status_a_classificar_id()
    if destino is None:
        return {"ok": False, "razao": "sem_status_destino"}

    redis_cli = getattr(pipeline, "_redis", None)
    kommo_cli = getattr(pipeline, "kommo", None)
    if redis_cli is None:
        return {"ok": False, "razao": "sem_redis"}

    agora = time.time()
    timeout_h = get_timeout_classificar_horas()
    movidos = 0
    candidatos = 0

    try:
        cursor = 0
        pattern = "blink:classificar:aguardando_resposta:*"
        while True:
            cursor, batch = redis_cli.scan(
                cursor=cursor, match=pattern, count=200,
            )
            for k in batch:
                key_str = k.decode() if isinstance(k, bytes) else k
                try:
                    lead_id = int(key_str.rsplit(":", 1)[1])
                except (IndexError, ValueError):
                    continue
                try:
                    raw = redis_cli.get(key_str)
                    disparo_ts = float(raw) if raw else None
                except Exception:  # noqa: BLE001
                    disparo_ts = None
                r = mover_lead_para_classificar(
                    lead_id=lead_id,
                    disparo_renovacao_ts=disparo_ts,
                    ultima_resposta_paciente_ts=None,
                    kommo_client=None if dry_run else kommo_cli,
                    agora=agora, dry_run=dry_run,
                    timeout_horas=timeout_h,
                    status_destino_id=destino,  # passa explícito (lê env atual)
                )
                # Candidato = passou do timeout. `razao` pode virar "dry_run"
                # depois da decisão original, então usamos horas_passadas.
                if r.horas_passadas is not None and r.horas_passadas >= timeout_h:
                    candidatos += 1
                    if r.movido:
                        movidos += 1
            if cursor == 0:
                break
    except Exception as exc:  # noqa: BLE001
        log.warning("[CRON classificar] varredura falhou: %s", exc)
        return {
            "ok": False, "razao": "excecao_varredura",
            "candidatos": candidatos, "movidos": movidos,
        }

    return {
        "ok": True, "dry_run": dry_run,
        "candidatos": candidatos, "movidos": movidos,
        "timeout_horas": timeout_h, "status_destino": destino,
    }


def _worker_classificar_loop(*, pipeline, stop_event: threading.Event) -> None:
    intervalo = _intervalo_classificar_seg()
    log.info(
        "[CRON classificar] worker iniciado intervalo=%ss dry_run=%s",
        intervalo, _dry_run_default(),
    )
    # Atraso inicial — espera 60s pro app subir 100%.
    if stop_event.wait(60):
        return
    while not stop_event.is_set():
        try:
            res = _executar_classificar(
                pipeline=pipeline, dry_run=_dry_run_default(),
            )
            log.info("[CRON classificar] %s", res)
        except Exception as exc:  # noqa: BLE001
            log.exception("[CRON classificar] exceção no loop: %s", exc)
        if stop_event.wait(intervalo):
            return


# ---------------------------------------------------------------------------
# Bootstrap a partir do create_app
# ---------------------------------------------------------------------------

_stop_event_global: threading.Event | None = None
_threads_iniciadas: list[threading.Thread] = []


def iniciar_cron(pipeline) -> dict:
    """Liga os workers de cron interno. Idempotente — só liga uma vez."""
    global _stop_event_global
    if not _enabled():
        return {"started": False, "reason": "BLINK_CRON_ENABLED!=1"}
    if _stop_event_global is not None:
        return {"started": False, "reason": "ja_iniciado"}

    _stop_event_global = threading.Event()
    t = threading.Thread(
        target=_worker_classificar_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-classificar",
    )
    t.start()
    _threads_iniciadas.append(t)
    return {
        "started": True,
        "workers": ["classificar"],
        "dry_run": _dry_run_default(),
        "intervalo_seg": _intervalo_classificar_seg(),
    }


def parar_cron() -> None:
    """Sinaliza pros workers pararem. Não bloqueia."""
    global _stop_event_global
    if _stop_event_global is not None:
        _stop_event_global.set()
