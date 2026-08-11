"""Loop principal do Lia Engineer Autônomo.

Roda a cada 5 minutos via cron Easypanel (ou local). Etapas:

    1. fetch_recent_kommo_notes(últimas 30min, autor=Lia)
    2. detect_bugs_em_lead(notas) → List[BugReport]
    3. dedup_via_redis (bugs já processados na última hora)
    4. pra cada bug:
        a. propor_fix(bug) → FixProposal
        b. if confianca >= 70 and risco != high:
              apply_fix(proposta) → resultado
              if smoke_test_passou: notify_slack("✅ fix aplicado")
              else:                rollback() + notify("❌ revertido")
           else:
              notify_slack("⚠️ bug detectado, requer humano: " + detalhes)
    5. atualizar contadores no /status endpoint

Limites de segurança:
    - MAX_FIXES_POR_DIA = 3 (configurável via env)
    - COOLDOWN entre fixes = 30min
    - SE 3 rollbacks consecutivos → PAUSA total + alerta urgente

Cosmoética: sempre transparente sobre o que fez, nunca esconde falha.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .detect_bugs import BugReport, detectar_bugs_em_lead
from .propose_fix import FixProposal, confianca_suficiente, propor_fix


log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────
# Configuração
# ────────────────────────────────────────────────────────────────────────

MAX_FIXES_POR_DIA = int(os.getenv("LIA_ENGINEER_MAX_FIXES_DIA", "3"))
COOLDOWN_ENTRE_FIXES_SEG = int(os.getenv("LIA_ENGINEER_COOLDOWN_SEG", "1800"))
LIMIAR_CONFIANCA = int(os.getenv("LIA_ENGINEER_LIMIAR_CONFIANCA", "70"))
MAX_ROLLBACKS_CONSECUTIVOS = 3
KOMMO_LOOKBACK_MINUTOS = int(os.getenv("LIA_ENGINEER_LOOKBACK_MIN", "30"))


# ────────────────────────────────────────────────────────────────────────
# Estado persistente (Redis em prod, dict em teste)
# ────────────────────────────────────────────────────────────────────────

@dataclass
class EngineerState:
    """Estado do agente. Persistido em Redis em produção."""

    ultimo_tick: Optional[datetime] = None
    bugs_detectados_24h: int = 0
    fixes_aplicados_24h: int = 0
    fixes_escalados_24h: int = 0
    rollbacks_24h: int = 0
    rollbacks_consecutivos: int = 0
    pausado: bool = False
    motivo_pausa: str = ""
    bugs_processados_chaves: set = field(default_factory=set)
    """Chaves dedup (BugReport.chave_dedup) já processadas. Persiste 24h."""


# ────────────────────────────────────────────────────────────────────────
# Ações
# ────────────────────────────────────────────────────────────────────────

def fetch_recent_kommo_notes(
    kommo_client,
    lookback_minutos: int = KOMMO_LOOKBACK_MINUTOS,
) -> List[dict]:
    """Busca notas Kommo dos últimos N minutos onde autor=Lia (user 0).

    Retorna lista de dicts com {lead_id, nota_texto, timestamp, contexto_lead}.
    Implementação real depende do kommo_client. Aqui assume método:
        kommo_client.list_recent_notes(since=datetime, author_user_id=0)
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutos)
    return kommo_client.list_recent_notes(since=since, author_user_id=0)


def processar_bug(
    bug: BugReport,
    state: EngineerState,
    arquivo_codigo_path,
    apply_fix_fn,
    smoke_test_fn,
    notify_fn,
    rollback_fn,
    anthropic_client=None,
) -> str:
    """Processa 1 bug. Retorna status.

    Status possíveis:
        - "fix_aplicado" : push + deploy OK + smoke OK
        - "rollback"     : push aplicado mas smoke falhou, revertido
        - "escalado"     : confiança baixa, humano notificado
        - "skipped_cap"  : já bateu MAX_FIXES_POR_DIA
        - "skipped_pausa": state.pausado=True
        - "duplicado"    : chave_dedup já estava em bugs_processados_chaves
    """
    if state.pausado:
        return "skipped_pausa"

    if bug.chave_dedup() in state.bugs_processados_chaves:
        return "duplicado"

    if state.fixes_aplicados_24h >= MAX_FIXES_POR_DIA:
        notify_fn(
            f"⚠️ MAX_FIXES_POR_DIA atingido ({MAX_FIXES_POR_DIA}). "
            f"Bug {bug.padrao_id} no lead {bug.lead_id} fica pra próximo dia "
            f"ou requer revisão humana se P0."
        )
        state.bugs_processados_chaves.add(bug.chave_dedup())
        return "skipped_cap"

    proposta = propor_fix(bug, arquivo_codigo_path, anthropic_client=anthropic_client)
    if proposta is None:
        notify_fn(
            f"⚠️ Bug detectado em lead {bug.lead_id} ({bug.padrao_id}) — "
            f"Opus não conseguiu propor fix. Escalando."
        )
        state.fixes_escalados_24h += 1
        state.bugs_processados_chaves.add(bug.chave_dedup())
        return "escalado"

    if not confianca_suficiente(proposta, LIMIAR_CONFIANCA):
        notify_fn(
            f"⚠️ Bug detectado em lead {bug.lead_id} ({bug.padrao_id}). "
            f"Opus propôs fix com confiança {proposta.confianca}/100 (limiar "
            f"{LIMIAR_CONFIANCA}). Risco: {proposta.risco}. "
            f"Escalando pra revisão humana.\nCommit proposto: "
            f"{proposta.commit_message}"
        )
        state.fixes_escalados_24h += 1
        state.bugs_processados_chaves.add(bug.chave_dedup())
        return "escalado"

    # Aplicar fix
    aplicacao = apply_fix_fn(proposta)
    if not aplicacao.get("push_ok"):
        notify_fn(
            f"❌ Tentei aplicar fix pro bug {bug.padrao_id} lead {bug.lead_id} "
            f"mas push falhou: {aplicacao.get('erro', 'desconhecido')}"
        )
        state.bugs_processados_chaves.add(bug.chave_dedup())
        return "escalado"

    # Aguardar deploy + smoke
    time.sleep(int(os.getenv("LIA_ENGINEER_DEPLOY_AGUARDA_SEG", "180")))
    smoke = smoke_test_fn()
    if smoke.get("passou"):
        notify_fn(
            f"✅ Fix aplicado e validado!\n"
            f"Bug: {bug.padrao_id} (lead {bug.lead_id})\n"
            f"Commit: {proposta.commit_message}\n"
            f"Smoke: {smoke.get('cenarios_ok', 0)}/{smoke.get('cenarios_total', 0)}"
        )
        state.fixes_aplicados_24h += 1
        state.rollbacks_consecutivos = 0
        state.bugs_processados_chaves.add(bug.chave_dedup())
        return "fix_aplicado"

    # Smoke falhou → rollback
    rollback_fn(aplicacao.get("commit_sha"))
    state.rollbacks_24h += 1
    state.rollbacks_consecutivos += 1
    notify_fn(
        f"❌ Fix aplicado pro bug {bug.padrao_id} (lead {bug.lead_id}) "
        f"falhou smoke test. Revertido.\n"
        f"Smoke: {smoke.get('cenarios_ok', 0)}/{smoke.get('cenarios_total', 0)}\n"
        f"Causa provável: {smoke.get('falha_motivo', 'desconhecida')}"
    )
    if state.rollbacks_consecutivos >= MAX_ROLLBACKS_CONSECUTIVOS:
        state.pausado = True
        state.motivo_pausa = f"{MAX_ROLLBACKS_CONSECUTIVOS} rollbacks consecutivos"
        notify_fn(
            f"🚨 LIA ENGINEER PAUSADO — {MAX_ROLLBACKS_CONSECUTIVOS} rollbacks "
            f"consecutivos. Requer intervenção humana pra investigar e "
            f"reativar via /admin/engineer/resume."
        )
    state.bugs_processados_chaves.add(bug.chave_dedup())
    return "rollback"


def engineer_tick(
    kommo_client,
    state: EngineerState,
    arquivo_codigo_path,
    apply_fix_fn,
    smoke_test_fn,
    notify_fn,
    rollback_fn,
    anthropic_client=None,
) -> dict:
    """1 iteração completa do loop. Chamada pelo cron.

    Returns dict com resumo do tick pra observabilidade.
    """
    state.ultimo_tick = datetime.now(timezone.utc)

    if state.pausado:
        return {"pausado": True, "motivo": state.motivo_pausa}

    notas = fetch_recent_kommo_notes(kommo_client)
    todos_bugs: List[BugReport] = []
    # Agrupar notas por lead pra detectar sliding window corretamente
    por_lead: dict = {}
    for n in notas:
        por_lead.setdefault(n["lead_id"], []).append(n)
    for lead_id, lead_notas in por_lead.items():
        bugs = detectar_bugs_em_lead(lead_notas, lead_id)
        todos_bugs.extend(bugs)

    state.bugs_detectados_24h += len(todos_bugs)

    resultados = {"fix_aplicado": 0, "rollback": 0, "escalado": 0,
                  "skipped_cap": 0, "skipped_pausa": 0, "duplicado": 0}

    # Ordenar por severidade (P0 primeiro)
    ordem_sev = {"P0": 0, "P1": 1, "P2": 2}
    todos_bugs.sort(key=lambda b: ordem_sev.get(b.severidade, 9))

    for bug in todos_bugs:
        if state.pausado:
            break
        status = processar_bug(
            bug, state, arquivo_codigo_path,
            apply_fix_fn, smoke_test_fn, notify_fn, rollback_fn,
            anthropic_client=anthropic_client,
        )
        resultados[status] = resultados.get(status, 0) + 1

        # Cooldown entre fixes
        if status == "fix_aplicado":
            time.sleep(COOLDOWN_ENTRE_FIXES_SEG)

    return {
        "tick_em": state.ultimo_tick.isoformat(),
        "bugs_detectados": len(todos_bugs),
        "resultados": resultados,
        "state_snapshot": {
            "fixes_aplicados_24h": state.fixes_aplicados_24h,
            "rollbacks_24h": state.rollbacks_24h,
            "pausado": state.pausado,
        },
    }
