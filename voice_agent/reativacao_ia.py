"""Reativação automática de IA em leads em etapas ativas (06/06/2026, task #264).

Problema: webhook por mudança de etapa (#233) só dispara quando lead MUDA
de etapa. Leads que ficam parados em uma etapa ativa com IA = Desativado
ficam invisíveis pra Lia indefinidamente.

Solução: função pura que varre TODOS os leads em etapas ativas e reativa
em batch. Chamada por:
- Endpoint `/admin/reativar-ia-batch` (manual)
- Cron interno 6h (automático, novo nesta task)
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Etapas ativas — leads aqui DEVEM ter IA Ativada
STATUS_ATIVOS_IA = (
    96441724,    # 0-ETAPA ENTRADA
    106919911,   # 0-a classificar
    101508307,   # 2.LEADS FRIO
    102560495,   # 3-AGENDAR
    106184631,   # 4.REAGENDAR
    101507507,   # 5-AGENDADO
    101109455,   # 6-CONFIRMAR
    106653499,   # 7.CONFIRMADO
    106184983,   # 7.1-NO-SHOW
)


def reativar_ia_em_etapas_ativas(
    kommo_client,
    *,
    max_leads: int = 500,
    status_ids: tuple = STATUS_ATIVOS_IA,
    dry_run: bool = False,
) -> dict:
    """Varre leads em etapas ativas com ATIVADO IA = Desativado e reativa.

    Retorna:
        {
          ok: bool,
          total_lidos: int,
          encontrados_desativados: int,
          reativados: int,
          falhas: int,
          dry_run: bool,
          status_ids_varridos: list,
          amostra: [ {id, nome, status_id} ]  # primeiros 30
        }
    """
    if kommo_client is None:
        return {"ok": False, "error": "kommo_client_indisponivel"}

    total_lidos = 0
    desativados = 0
    reativados = 0
    falhas = 0
    amostra: list[dict] = []
    LIMITE = 250

    for sid in status_ids:
        if total_lidos >= max_leads:
            break
        page = 1
        while total_lidos < max_leads:
            try:
                leads = kommo_client.list_leads_by_status(
                    pipeline_id=8601819, status_ids=[sid],
                    limit=LIMITE, page=page,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[reativar-ia] list_leads_by_status falhou %s: %s", sid, e)
                break
            if not leads:
                break
            for ld in leads:
                if total_lidos >= max_leads:
                    break
                total_lidos += 1
                lid = ld.get("id")
                if not lid:
                    continue
                # Lê estado atual de ATIVADO IA
                try:
                    ctx = kommo_client.get_caller_context_by_lead(lid)
                    estado = str(
                        (ctx.get("known") or {}).get("ativado_ia") or ""
                    ).upper()
                except Exception:  # noqa: BLE001
                    continue
                if estado != "DESATIVADO":
                    continue
                desativados += 1
                if len(amostra) < 30:
                    amostra.append({
                        "id": lid, "nome": ld.get("name"),
                        "status_id": sid,
                    })
                if not dry_run:
                    try:
                        if kommo_client.update_lead_fields(
                            lid, {"ativado_ia": "Ativado"},
                        ):
                            reativados += 1
                            log.info(
                                "[reativar-ia] Lead %s (%s) reativado",
                                lid, ld.get("name", ""),
                            )
                        else:
                            falhas += 1
                    except Exception as e:  # noqa: BLE001
                        log.warning(
                            "[reativar-ia] update %s falhou: %s", lid, e,
                        )
                        falhas += 1
            if len(leads) < LIMITE:
                break
            page += 1

    return {
        "ok": True,
        "total_lidos": total_lidos,
        "encontrados_desativados": desativados,
        "reativados": reativados,
        "falhas": falhas,
        "dry_run": dry_run,
        "status_ids_varridos": list(status_ids),
        "amostra": amostra,
    }
