"""Detector de leads-fantasma — Pilar #1 da fila de robustez.

Origem: Fábio 01/06/2026 — leads 24057561 e 24060221 chegaram em
0-ENTRADA / 0-A CLASSIFICAR sem mensagem real (chat 36818 estranho,
ou Meta Lead Form, ou bug de canal). Lia ficou muda. Fábio só
descobriu horas depois pelo paciente reclamando.

Solução: cron 5 min varre Kommo procurando leads "novos demais"
(criados nas últimas 30 min) em status de entrada, com idade > 3 min,
sem custom_fields preenchidos E sem nota inbound. Dispara alerta
Slack com link Kommo.

Liga via env `LEADS_FANTASMA_ENABLED=1`. Webhook Slack via
`SLACK_WEBHOOK_FANTASMA_URL` (ou usa `SLACK_WEBHOOK_URL` como
fallback).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# Status que contam como "entrada" e devem receber atenção rápida
STATUS_ENTRADA = [
    96441724,    # 0-ETAPA ENTRADA
    106919911,   # 0-a classificar
]
PIPELINE_ATENDE = 8601819

# Idade mínima pra considerar fantasma (segundos)
IDADE_MIN_SEG = 180  # 3 min
# Idade máxima — leads muito velhos não interessam (já passaram do ponto)
IDADE_MAX_SEG = 30 * 60  # 30 min

# Chave Redis dedup — evita alertar 2x o mesmo lead
REDIS_DEDUP_PREFIX = "blink:fantasma:alertado:"
DEDUP_TTL = 24 * 3600  # 24h


@dataclass
class LeadFantasma:
    lead_id: int
    nome: str = ""
    status_id: int = 0
    criado_ts: int = 0
    idade_seg: int = 0
    motivo: str = ""

    @property
    def url_kommo(self) -> str:
        return f"https://univeja.kommo.com/leads/detail/{self.lead_id}"


@dataclass
class TickResultado:
    varridos: int = 0
    fantasmas_encontrados: int = 0
    alertados: int = 0
    ja_alertados_dedup: int = 0
    erros: int = 0
    detalhes: list[dict] = field(default_factory=list)


def esta_habilitado() -> bool:
    return os.getenv("LEADS_FANTASMA_ENABLED", "0") == "1"


def _webhook_url() -> str:
    return (
        os.getenv("SLACK_WEBHOOK_FANTASMA_URL")
        or os.getenv("SLACK_WEBHOOK_URL")
        or ""
    )


def _ja_alertado(redis_client: Any, lead_id: int) -> bool:
    if not redis_client:
        return False
    try:
        return bool(redis_client.exists(f"{REDIS_DEDUP_PREFIX}{lead_id}"))
    except Exception:  # noqa: BLE001
        return False


def _marca_alertado(redis_client: Any, lead_id: int) -> None:
    if not redis_client:
        return
    try:
        redis_client.setex(
            f"{REDIS_DEDUP_PREFIX}{lead_id}", DEDUP_TTL, int(time.time()),
        )
    except Exception:  # noqa: BLE001
        pass


def _classifica_fantasma(lead_completo: dict, agora_ts: int) -> Optional[str]:
    """Decide se um lead é 'fantasma' (motivo) ou None se OK.

    Critério: idade entre IDADE_MIN e IDADE_MAX + custom_fields vazio
    + sem nota inbound do paciente nem nota outbound da Lia.
    """
    if not isinstance(lead_completo, dict):
        return None
    try:
        criado_iso = lead_completo.get("created_at") or ""
    except Exception:
        criado_iso = ""
    criado_ts = lead_completo.get("_criado_ts") or 0
    if not criado_ts and criado_iso:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(criado_iso.replace("Z", "+00:00"))
            criado_ts = int(dt.timestamp())
        except Exception:  # noqa: BLE001
            criado_ts = 0
    if not criado_ts:
        return None
    idade = agora_ts - criado_ts
    if idade < IDADE_MIN_SEG:
        return None  # cedo demais, espera próximo tick
    if idade > IDADE_MAX_SEG:
        return None  # tarde demais, não vale alertar
    # Custom_fields vazio?
    cf = lead_completo.get("custom_fields") or lead_completo.get("custom_fields_values") or []
    cf_preenchidos = 0
    for f in cf:
        vals = f.get("values") or []
        if vals and any((v.get("value") not in (None, "", 0)) for v in vals):
            cf_preenchidos += 1
    # Notas: paciente OU Lia?
    notas = lead_completo.get("notes") or []
    notas_count = len(notas)
    if cf_preenchidos == 0 and notas_count == 0:
        return f"custom_fields=0 + notas=0 (idade={idade}s)"
    if cf_preenchidos <= 1 and notas_count == 0:
        return f"custom_fields={cf_preenchidos} + notas=0 (idade={idade}s)"
    return None


def _envia_slack(webhook_url: str, payload: dict) -> bool:
    """Envia mensagem ao Slack via webhook incoming."""
    if not webhook_url:
        return False
    try:
        import httpx
        with httpx.Client(timeout=8.0) as c:
            r = c.post(webhook_url, json=payload)
        return 200 <= r.status_code < 300
    except Exception as e:  # noqa: BLE001
        log.warning("[FANTASMA] erro slack: %s", e)
        return False


def _payload_slack(lead: LeadFantasma) -> dict:
    return {
        "text": (
            f":ghost: *Lead-fantasma detectado* — `{lead.lead_id}`\n"
            f"• Status: `{lead.status_id}` "
            f"• Idade: `{lead.idade_seg}s`\n"
            f"• Motivo: {lead.motivo}\n"
            f"• URL: {lead.url_kommo}\n"
            "Provável causa: canal Kommo não plugado no webhook /kommo, "
            "ou Meta Lead Form sem mensagem real."
        ),
    }


def tick(
    kommo: Any,
    redis_client: Any,
    *,
    pipeline_id: int = PIPELINE_ATENDE,
    statuses: Optional[list[int]] = None,
    dry_run: bool = False,
) -> TickResultado:
    """Roda 1 varredura. Lista leads dos status de entrada (recentes),
    busca detalhe de cada, classifica como fantasma, dispara Slack
    (dedup 24h via Redis), devolve relatório."""
    res = TickResultado()
    if not kommo:
        return res
    sids = statuses or STATUS_ENTRADA
    try:
        leads_basicos = kommo.list_leads_by_status(
            pipeline_id=pipeline_id,
            status_ids=sids,
            limit=50,
            page=1,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[FANTASMA] erro list: %s", e)
        res.erros += 1
        return res
    agora_ts = int(time.time())
    webhook = _webhook_url()
    for ld in leads_basicos:
        res.varridos += 1
        lid = ld.get("id")
        if lid is None:
            continue
        try:
            detalhe = kommo.get_lead(lid) or {}
        except Exception:  # noqa: BLE001
            res.erros += 1
            continue
        motivo = _classifica_fantasma(detalhe, agora_ts)
        if not motivo:
            continue
        res.fantasmas_encontrados += 1
        # Dedup
        if _ja_alertado(redis_client, lid):
            res.ja_alertados_dedup += 1
            continue
        # Monta lead-fantasma + dispara
        criado_ts = 0
        criado_iso = detalhe.get("created_at") or ""
        if criado_iso:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(criado_iso.replace("Z", "+00:00"))
                criado_ts = int(dt.timestamp())
            except Exception:  # noqa: BLE001
                pass
        lf = LeadFantasma(
            lead_id=lid,
            nome=detalhe.get("name") or f"Lead #{lid}",
            status_id=detalhe.get("status_id") or 0,
            criado_ts=criado_ts,
            idade_seg=agora_ts - criado_ts if criado_ts else 0,
            motivo=motivo,
        )
        res.detalhes.append({
            "lead_id": lf.lead_id,
            "url": lf.url_kommo,
            "motivo": lf.motivo,
            "idade_seg": lf.idade_seg,
        })
        if dry_run:
            continue
        if webhook and _envia_slack(webhook, _payload_slack(lf)):
            res.alertados += 1
            _marca_alertado(redis_client, lid)
        else:
            log.warning(
                "[FANTASMA] %s detectado mas Slack não disponível "
                "(webhook=%s)",
                lid, "ok" if webhook else "vazio",
            )
    return res
