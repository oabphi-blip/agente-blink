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


def _intervalo_renovacao_seg() -> int:
    raw = (os.environ.get("RENOVACAO_CADA_MIN") or "15").strip()
    try:
        return max(int(float(raw) * 60), 60)  # mínimo 1 min
    except ValueError:
        return 900


def _hora_brt() -> int:
    """Hora atual em Brasília (UTC-3, sem DST)."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=-3))).hour


def _renovacao_em_horario_comercial() -> bool:
    """Default 8h–18h BRT. Configurável via env."""
    try:
        h_ini = int(os.environ.get("RENOVACAO_HORA_INICIO") or "8")
        h_fim = int(os.environ.get("RENOVACAO_HORA_FIM") or "18")
    except ValueError:
        h_ini, h_fim = 8, 18
    h = _hora_brt()
    return h_ini <= h < h_fim


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
# Worker: renovacao_varredura
# ---------------------------------------------------------------------------

def _executar_renovacao_varredura(*, pipeline, dry_run: bool) -> dict:
    """Itera leads Kommo nos status pré-AGENDADO, lê Redis ultima_msg_paciente,
    chama dispatcher de renovação por lead elegível.

    Retorna {ok, candidatos, enviados, dry_run, motivo}.
    """
    from voice_agent.mensagens_janela import STATUS_IDS_ANTES_AGENDADO
    from voice_agent.renovacao_dispatcher import (
        SnapshotLead, dispatch_renovacao,
    )

    kommo = getattr(pipeline, "kommo", None)
    if kommo is None:
        return {"ok": False, "razao": "sem_kommo"}
    redis_cli = getattr(pipeline, "_redis", None)

    candidatos = 0
    enviados = 0
    erros = 0

    # Limitar varredura. Se Fábio quiser mais leads, ajusta env.
    limite = int(os.environ.get("RENOVACAO_LIMITE_LEADS") or "50")
    horas_pre_renovacao = int(os.environ.get("RENOVACAO_HORAS_MIN") or "22")

    try:
        # Iterar lista de leads ativos via kommo.list_stale_leads (existente).
        # Compatível com qualquer cliente que tenha esse método.
        leads = []
        if hasattr(kommo, "list_active_leads"):
            leads = kommo.list_active_leads(
                pipeline_id=8601819, limit=limite,
            ) or []
        elif hasattr(kommo, "list_stale_leads"):
            leads = kommo.list_stale_leads(
                pipeline_id=8601819, limit=limite,
            ) or []
        else:
            return {"ok": False, "razao": "kommo_sem_list_method"}

        for lead in leads:
            if not isinstance(lead, dict):
                continue
            status_id = lead.get("status_id")
            if status_id not in STATUS_IDS_ANTES_AGENDADO:
                continue
            lead_id = lead.get("id")
            telefone = lead.get("telefone") or lead.get("phone") or ""
            nome_contato = lead.get("nome_contato") or lead.get("name") or ""
            if not lead_id or not telefone or not nome_contato:
                continue

            # Lê ultima_msg_paciente do Redis (gravada pelo webhook).
            ultima_ts = None
            if redis_cli is not None:
                try:
                    raw = redis_cli.get(
                        f"blink:janela:ultima_msg_paciente:{lead_id}"
                    )
                    ultima_ts = float(raw) if raw else None
                except Exception:  # noqa: BLE001
                    ultima_ts = None

            snap = SnapshotLead(
                lead_id=int(lead_id), telefone_e164=str(telefone),
                nome_contato=str(nome_contato), status_id=int(status_id),
                ultima_msg_paciente_ts=ultima_ts,
                paciente_ja_respondeu_na_vida=bool(ultima_ts),
            )
            try:
                res = dispatch_renovacao(
                    snap,
                    wa_client=None if dry_run else getattr(pipeline, "wa_cloud", None),
                    redis_client=redis_cli,
                    kommo_note_writer=None if dry_run else kommo,
                    dry_run=dry_run,
                )
                if res.elegibilidade.get("elegivel"):
                    candidatos += 1
                if res.enviado:
                    enviados += 1
            except Exception as exc:  # noqa: BLE001
                erros += 1
                log.warning("[CRON renovacao] dispatch lead=%s falhou: %s",
                            lead_id, exc)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "razao": "excecao", "erro": str(exc)[:300]}

    return {
        "ok": True, "dry_run": dry_run, "candidatos": candidatos,
        "enviados": enviados, "erros": erros, "limite": limite,
    }


def _worker_renovacao_loop(*, pipeline, stop_event: threading.Event) -> None:
    intervalo = _intervalo_renovacao_seg()
    log.info(
        "[CRON renovacao] worker iniciado intervalo=%ss dry_run=%s",
        intervalo, _dry_run_default(),
    )
    # Atraso inicial — espera 90s pro app subir.
    if stop_event.wait(90):
        return
    while not stop_event.is_set():
        if _renovacao_em_horario_comercial():
            try:
                res = _executar_renovacao_varredura(
                    pipeline=pipeline, dry_run=_dry_run_default(),
                )
                log.info("[CRON renovacao] %s", res)
            except Exception as exc:  # noqa: BLE001
                log.exception("[CRON renovacao] exceção no loop: %s", exc)
        else:
            log.debug("[CRON renovacao] fora horário comercial — pulando")
        if stop_event.wait(intervalo):
            return


# ---------------------------------------------------------------------------
# Worker: campanha semanal por categoria (task #218 — 04/06/2026)
# Toggle: CAMPANHA_SEMANAL_ENABLED=1
# Quando: segunda-feira (BRT) 9h, 1x por semana
# O que: roda a mesma lógica do /admin/disparar-categoria internamente
# ---------------------------------------------------------------------------

def _campanha_semanal_enabled() -> bool:
    return (os.environ.get("CAMPANHA_SEMANAL_ENABLED") or "").strip() == "1"


def _campanha_semanal_categoria() -> str:
    return (os.environ.get("CAMPANHA_SEMANAL_CATEGORIA") or "R").upper()


def _campanha_semanal_max_leads() -> int:
    raw = (os.environ.get("CAMPANHA_SEMANAL_MAX") or "20").strip()
    try:
        return min(int(raw), 200)
    except ValueError:
        return 20


def _campanha_semanal_unidade() -> str:
    return (os.environ.get("CAMPANHA_SEMANAL_UNIDADE") or "").lower()


def _campanha_semanal_medico() -> str:
    return (os.environ.get("CAMPANHA_SEMANAL_MEDICO") or "").lower()


def _executar_campanha_semanal(*, pipeline, dry_run: bool) -> dict:
    """Filtra leads por categoria + dispara template aprovado em batch.

    Reusa lógica de filtro do endpoint /admin/disparar-categoria mas roda
    INTERNAMENTE sem precisar de curl externo. Token de acesso vem do
    próprio app (env nativo do container Easypanel).
    """
    from voice_agent.kommo import KommoClient  # noqa: F401

    kommo = getattr(pipeline, "kommo", None)
    wa_cloud = getattr(pipeline, "wa_cloud", None)
    if not kommo or not wa_cloud:
        return {"ok": False, "razao": "kommo_ou_wa_indisponivel"}

    categoria = _campanha_semanal_categoria()
    if categoria not in ("R", "E", "C"):
        return {"ok": False, "razao": f"categoria_invalida={categoria}"}

    max_leads = _campanha_semanal_max_leads()
    unidade_filtro = _campanha_semanal_unidade()
    medico_filtro = _campanha_semanal_medico()

    KEYWORDS = {
        "R": ["REAGENDAR", "REMARCAÇÃO", "REMARCACAO", "FALTOU",
              "DESMARCOU", "DESMARCAÇÃO", "DESMARCACAO"],
        "E": ["COM CONVÊNIO", "COM CONVENIO"],
        "C": ["SEM CONVÊNIO", "SEM CONVENIO", "PARTICULAR"],
    }
    EXCLUIR = ["INAS", "GDF", "CASSI", "SULAMERICA", "BRADESCO"]

    try:
        leads = []
        if hasattr(kommo, "list_stale_leads"):
            leads = kommo.list_stale_leads(
                pipeline_id=8601819, limit=max_leads * 3,
            ) or []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "razao": f"kommo_falha={exc}"}

    kw_cat = KEYWORDS[categoria]
    candidatos = []
    for lead in leads:
        if len(candidatos) >= max_leads:
            break
        nome_lead = (lead.get("name") or "").upper()
        if any(ex in nome_lead for ex in EXCLUIR):
            continue
        if not any(k in nome_lead for k in kw_cat):
            continue
        if unidade_filtro and unidade_filtro not in nome_lead.lower():
            pass  # heurística branda — fetch detalhado seria caro
        if medico_filtro and medico_filtro not in nome_lead.lower():
            pass
        if lead.get("id"):
            candidatos.append(int(lead["id"]))

    if not candidatos:
        return {
            "ok": True, "candidatos": 0, "disparados": 0,
            "razao": "nenhum_lead_casou",
        }

    # Importa a função helper do webhook só na hora (evita import circular)
    try:
        from voice_agent.webhook import (
            _disparar_template_aprovado_para_lead,
        )
    except ImportError:
        return {"ok": False, "razao": "helper_indisponivel"}

    disparados = 0
    falhas = 0
    detalhes = []
    for lead_id in candidatos:
        try:
            res = _disparar_template_aprovado_para_lead(
                lead_id, kommo, wa_cloud, dry_run=dry_run,
            )
            if res.get("ok"):
                disparados += 1
                detalhes.append({"lead_id": lead_id, "ok": True})
            else:
                falhas += 1
                detalhes.append({
                    "lead_id": lead_id, "ok": False,
                    "motivo": res.get("motivo", "?"),
                })
        except Exception as exc:  # noqa: BLE001
            falhas += 1
            detalhes.append({
                "lead_id": lead_id, "ok": False,
                "motivo": f"exception={exc}",
            })

    return {
        "ok": True, "categoria": categoria,
        "candidatos": len(candidatos),
        "disparados": disparados, "falhas": falhas,
        "dry_run": dry_run, "detalhes": detalhes,
    }


def _eh_segunda_feira_9h_brt() -> bool:
    """True se agora é segunda-feira entre 9h e 10h BRT."""
    from datetime import datetime, timedelta, timezone
    agora_brt = datetime.now(timezone(timedelta(hours=-3)))
    return agora_brt.weekday() == 0 and agora_brt.hour == 9


def _worker_campanha_semanal_loop(
    *, pipeline, stop_event: threading.Event,
) -> None:
    """Loop que verifica a cada 30min se é hora da campanha semanal.

    Dispara apenas se for segunda-feira 9h-10h BRT E
    CAMPANHA_SEMANAL_ENABLED=1. Usa Redis pra dedup (não dispara 2x
    no mesmo dia mesmo se o worker reiniciar).
    """
    log.info(
        "[CRON campanha semanal] worker iniciado — checa a cada 30min "
        "se é seg 9h-10h BRT (CAMPANHA_SEMANAL_ENABLED=%s, categoria=%s)",
        _campanha_semanal_enabled(), _campanha_semanal_categoria(),
    )
    if stop_event.wait(120):
        return
    while not stop_event.is_set():
        if not _campanha_semanal_enabled():
            log.debug("[CRON campanha semanal] desligado — pulando")
        elif not _eh_segunda_feira_9h_brt():
            log.debug("[CRON campanha semanal] fora janela — pulando")
        else:
            # Dedup: já disparou hoje?
            redis_cli = getattr(pipeline, "_redis", None)
            from datetime import datetime, timedelta, timezone
            hoje_brt = datetime.now(
                timezone(timedelta(hours=-3))
            ).strftime("%Y-%m-%d")
            dedup_key = f"blink:campanha_semanal:{hoje_brt}"
            ja_disparou = False
            if redis_cli is not None:
                try:
                    ja_disparou = bool(redis_cli.get(dedup_key))
                except Exception:  # noqa: BLE001
                    pass

            if ja_disparou:
                log.debug(
                    "[CRON campanha semanal] já disparou hoje (%s) — pulando",
                    hoje_brt,
                )
            else:
                try:
                    res = _executar_campanha_semanal(
                        pipeline=pipeline, dry_run=_dry_run_default(),
                    )
                    log.info("[CRON campanha semanal] %s", res)
                    if redis_cli is not None:
                        try:
                            redis_cli.setex(dedup_key, 86400 * 2, "1")
                        except Exception:  # noqa: BLE001
                            pass
                except Exception as exc:  # noqa: BLE001
                    log.exception(
                        "[CRON campanha semanal] falhou: %s", exc,
                    )
        # checa de 30 em 30 min
        if stop_event.wait(1800):
            return


# ---------------------------------------------------------------------------
# Bootstrap a partir do create_app
# ---------------------------------------------------------------------------

_stop_event_global: threading.Event | None = None
_threads_iniciadas: list[threading.Thread] = []


# ============================================================
# WORKER MÉTRICAS — alarme horário + replay 23h (task #260)
# ============================================================

def _funcionamento_enabled() -> bool:
    """METRICAS_FUNCIONAMENTO_ENABLED=1 liga os 2 workers de métrica."""
    return os.environ.get("METRICAS_FUNCIONAMENTO_ENABLED", "1") == "1"


def _eh_hora_replay_noturno() -> bool:
    """Roda 1x ao dia entre 23h e 23h59 BRT."""
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone(timedelta(hours=-3)))
    return agora.hour == 23


def _worker_alarmes_horario_loop(
    *, pipeline, stop_event: threading.Event,
) -> None:
    """Worker que checa /admin/funcionamento a cada 1h e dispara alarmes Slack.

    Lê snap das taxas; se cair, posta no Slack (dedup 1h por alarme).
    """
    log.info("[CRON alarmes-horarios] worker iniciado (intervalo=1h)")
    if stop_event.wait(180):
        return
    intervalo = int(os.environ.get("METRICAS_ALARME_INTERVALO_SEG", "3600"))
    while not stop_event.is_set():
        if not _funcionamento_enabled():
            log.debug("[CRON alarmes-horarios] desligado — pulando")
        else:
            try:
                from . import metricas_funcionamento as mf
                redis_cli = getattr(pipeline, "_redis", None)
                snap = mf.funcionamento_hoje(redis_cli)
                alarmes = snap.get("alarmes_ativos") or []
                if alarmes:
                    slack_url = os.environ.get("SLACK_WEBHOOK_URL") or ""
                    if slack_url:
                        try:
                            import httpx
                            for a in alarmes:
                                dedup_k = (
                                    f"blink:alarme_funcionamento:"
                                    f"{hash(a) & 0xFFFFFFFF}"
                                )
                                if redis_cli is not None:
                                    try:
                                        if redis_cli.get(dedup_k):
                                            continue
                                    except Exception:  # noqa: BLE001
                                        pass
                                with httpx.Client(timeout=8.0) as cli:
                                    cli.post(slack_url, json={
                                        "text": (
                                            f":rotating_light: "
                                            f"*Funcionamento Lia*\n{a}"
                                        ),
                                    })
                                if redis_cli is not None:
                                    try:
                                        redis_cli.setex(dedup_k, 3600, "1")
                                    except Exception:  # noqa: BLE001
                                        pass
                            log.warning(
                                "[CRON alarmes] %d alarme(s) postado(s)",
                                len(alarmes),
                            )
                        except Exception as e:  # noqa: BLE001
                            log.warning("[CRON alarmes] slack falhou: %s", e)
            except Exception as e:  # noqa: BLE001
                log.warning("[CRON alarmes-horarios] crash silencioso: %s", e)
        if stop_event.wait(intervalo):
            return


def _worker_replay_noturno_loop(
    *, pipeline, stop_event: threading.Event,
) -> None:
    """Worker que roda 1x/noite (23h BRT) varrendo abandonados do dia.

    Para cada abandonado >= 30min sem resposta Lia, posta resumo no Slack
    pra revisão humana. Detecta regressão sem esperar paciente reclamar.
    """
    log.info("[CRON replay-noturno] worker iniciado — alvo 23h BRT")
    if stop_event.wait(180):
        return
    # Checa a cada 30min se entrou na janela 23h BRT
    while not stop_event.is_set():
        if _funcionamento_enabled() and _eh_hora_replay_noturno():
            # Dedup do dia
            redis_cli = getattr(pipeline, "_redis", None)
            from datetime import datetime, timedelta, timezone
            hoje_brt = datetime.now(
                timezone(timedelta(hours=-3))
            ).strftime("%Y-%m-%d")
            dedup_key = f"blink:replay_noturno:{hoje_brt}"
            ja = False
            if redis_cli is not None:
                try:
                    ja = bool(redis_cli.get(dedup_key))
                except Exception:  # noqa: BLE001
                    pass
            if not ja:
                try:
                    from . import metricas_funcionamento as mf
                    snap = mf.funcionamento_hoje(redis_cli)
                    slack_url = os.environ.get("SLACK_WEBHOOK_URL") or ""
                    if slack_url:
                        import httpx
                        with httpx.Client(timeout=10.0) as cli:
                            cli.post(slack_url, json={
                                "text": (
                                    f":crystal_ball: *Replay noturno {hoje_brt}*\n"
                                    f"Contadores: {snap.get('contadores')}\n"
                                    f"Taxas: {snap.get('taxas')}\n"
                                    f"Alarmes: {snap.get('alarmes_ativos') or 'OK'}"
                                ),
                            })
                    if redis_cli is not None:
                        try:
                            redis_cli.setex(dedup_key, 86400, "1")
                        except Exception:  # noqa: BLE001
                            pass
                    log.info("[CRON replay-noturno] resumo enviado")
                except Exception as e:  # noqa: BLE001
                    log.warning("[CRON replay-noturno] crash: %s", e)
        if stop_event.wait(1800):  # 30min
            return


def iniciar_cron(pipeline) -> dict:
    """Liga os workers de cron interno. Idempotente — só liga uma vez."""
    global _stop_event_global
    if not _enabled():
        return {"started": False, "reason": "BLINK_CRON_ENABLED!=1"}
    if _stop_event_global is not None:
        return {"started": False, "reason": "ja_iniciado"}

    _stop_event_global = threading.Event()
    t1 = threading.Thread(
        target=_worker_classificar_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-classificar",
    )
    t1.start()
    _threads_iniciadas.append(t1)

    t2 = threading.Thread(
        target=_worker_renovacao_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-renovacao",
    )
    t2.start()
    _threads_iniciadas.append(t2)

    # task #218: worker semanal de campanha
    t3 = threading.Thread(
        target=_worker_campanha_semanal_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-campanha-semanal",
    )
    t3.start()
    _threads_iniciadas.append(t3)

    # task #260: alarmes horários de funcionamento
    t4 = threading.Thread(
        target=_worker_alarmes_horario_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-alarmes-horarios",
    )
    t4.start()
    _threads_iniciadas.append(t4)

    # task #260: replay noturno 23h BRT
    t5 = threading.Thread(
        target=_worker_replay_noturno_loop,
        kwargs={"pipeline": pipeline, "stop_event": _stop_event_global},
        daemon=True, name="blink-cron-replay-noturno",
    )
    t5.start()
    _threads_iniciadas.append(t5)

    return {
        "started": True,
        "workers": [
            "classificar", "renovacao", "campanha_semanal",
            "alarmes_horarios", "replay_noturno",
        ],
        "dry_run": _dry_run_default(),
        "intervalo_classificar_seg": _intervalo_classificar_seg(),
        "intervalo_renovacao_seg": _intervalo_renovacao_seg(),
        "campanha_semanal_enabled": _campanha_semanal_enabled(),
        "campanha_semanal_categoria": _campanha_semanal_categoria(),
        "campanha_semanal_max": _campanha_semanal_max_leads(),
    }


def parar_cron() -> None:
    """Sinaliza pros workers pararem. Não bloqueia."""
    global _stop_event_global
    if _stop_event_global is not None:
        _stop_event_global.set()
