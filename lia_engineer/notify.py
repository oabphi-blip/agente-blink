"""Notificações Slack do Lia Engineer.

Todo evento crítico (fix aplicado, rollback, escalado, pausado) gera
mensagem no Slack #lia-engineer. Webhook configurado via env.

Cosmoética: sempre transparente — incluir contexto, motivo, próxima ação.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests


SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_LIA_ENGINEER_URL", "")
log = logging.getLogger(__name__)


def notify_slack(mensagem: str, severidade: str = "info") -> bool:
    """Envia mensagem pro Slack #lia-engineer.

    Args:
        mensagem: texto Markdown-friendly
        severidade: "info" | "warning" | "error" | "critical"

    Returns:
        True se enviou OK, False se webhook não configurado ou falhou.
    """
    if not SLACK_WEBHOOK:
        log.warning("[notify] SLACK_WEBHOOK_LIA_ENGINEER_URL não configurado. Msg: %s", mensagem[:200])
        return False

    emojis = {
        "info": ":robot_face:",
        "warning": ":warning:",
        "error": ":x:",
        "critical": ":rotating_light:",
    }
    emoji = emojis.get(severidade, ":robot_face:")
    payload = {
        "text": f"{emoji} *Lia Engineer*\n{mensagem}",
        "username": "Lia Engineer",
    }
    try:
        r = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        log.exception("[notify] falha ao enviar Slack: %s", e)
        return False


def notify_fix_aplicado(bug_id: str, lead_id: int, commit_sha: str, smoke_ok: int, smoke_total: int):
    """Caminho feliz: fix aplicado, deploy OK, smoke OK."""
    return notify_slack(
        f"✅ *Fix aplicado e validado em produção*\n"
        f"• Bug: `{bug_id}` (lead {lead_id})\n"
        f"• Commit: `{commit_sha[:10]}`\n"
        f"• Smoke: {smoke_ok}/{smoke_total} cenários OK\n"
        f"• Rollback se necessário: `git revert {commit_sha[:10]}`",
        severidade="info",
    )


def notify_rollback(bug_id: str, lead_id: int, commit_sha: str, motivo: str):
    """Smoke falhou após deploy → reverti."""
    return notify_slack(
        f"❌ *Fix revertido — falhou smoke test em produção*\n"
        f"• Bug: `{bug_id}` (lead {lead_id})\n"
        f"• Commit revertido: `{commit_sha[:10]}`\n"
        f"• Motivo: {motivo}\n"
        f"• Bug original NÃO foi resolvido. Requer revisão humana.",
        severidade="error",
    )


def notify_escalado(bug_id: str, lead_id: int, motivo: str, branch: Optional[str] = None):
    """Confiança baixa, alto risco, ou Opus não conseguiu — escala humano."""
    detalhes = f"• Branch proposto: `{branch}`\n" if branch else ""
    return notify_slack(
        f"⚠️ *Bug detectado em produção — requer humano*\n"
        f"• Bug: `{bug_id}` (lead {lead_id})\n"
        f"• Motivo escalado: {motivo}\n"
        f"{detalhes}"
        f"• Próxima ação: humano abre o branch e revisa, OU ignora se falso positivo.",
        severidade="warning",
    )


def notify_pausado(motivo: str):
    """Engineer pausou autonomamente (ex: 3 rollbacks consecutivos)."""
    return notify_slack(
        f"🚨 *LIA ENGINEER PAUSOU AUTOMATICAMENTE*\n"
        f"• Motivo: {motivo}\n"
        f"• Ações automáticas suspensas até intervenção humana.\n"
        f"• Pra reativar: `curl -X POST $PROD/admin/engineer/resume?secret=$WS`",
        severidade="critical",
    )
