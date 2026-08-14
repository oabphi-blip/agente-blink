"""Bug C-70 — MODO ESTRITO DETERMINÍSTICO (Fábio 14/08/2026).

Regra INVIOLÁVEL:
    Se NENHUM bypass determinístico retornou resposta canônica → SILENCIA
    a Lia + move lead pra 1-ATENDIMENTO HUMANO. Zero LLM improvisado.

Origem: Fábio 14/08/2026 P0 — "Definir a partir de agora que o agente não deve
enviar nenhuma resposta se nao for deterministica. Se não tiver resposta
transfere para o atendimento humano mas nao inventa. [...] Não é permitido
ficar brincando e inventando com os pacientes."

Ativação:
    Env MODO_ESTRITO_DETERMINISTICO=1 (default OFF pra rollout gradual).
    Quando ligado, LLM nunca é chamado — se bypass não respondeu, humano assume.

Como plugar:
    1. Em pipeline.py, após TODOS os bypasses determinísticos rodarem:
       from voice_agent.modo_estrito import deve_bloquear_llm_e_escalar
       flag_estrito = deve_bloquear_llm_e_escalar(bypass_result, ctx, redis_client)
       if flag_estrito:
           # Suprime resposta LLM. Marca flag pra pipeline mover lead.
           return silencio_estrito()

    2. Após pipeline processar, se flag_estrito ativa:
       - Move lead pra status_id 106563343 (1-ATENDIMENTO HUMANO)
       - Desativa IA (ATIVADO IA = Desativado)
       - Grava nota Kommo "🚨 C-70 MODO ESTRITO: sem resposta determinística,
         escalando pra humano"
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional


log = logging.getLogger(__name__)


def modo_estrito_ativo() -> bool:
    """Toggle env — default OFF pra rollout gradual.

    Pra ligar em prod: setar MODO_ESTRITO_DETERMINISTICO=1 no Easypanel.
    """
    return (os.environ.get("MODO_ESTRITO_DETERMINISTICO") or "0").lower() in (
        "1", "true", "yes", "on"
    )


def deve_bloquear_llm_e_escalar(
    bypass_result: Optional[str],
    ctx: Any,
    redis_client: Any = None,
) -> bool:
    """Retorna True quando devemos:
        (1) NÃO chamar o LLM
        (2) Escalar lead pra 1-ATENDIMENTO HUMANO

    Condições:
        - Modo estrito está LIGADO (env MODO_ESTRITO_DETERMINISTICO=1)
        - Nenhum bypass determinístico retornou resposta (bypass_result é None
          ou string vazia)

    Fail-open: se modo estrito está OFF → sempre retorna False (deixa LLM
    responder normalmente). Se ctx é None → False (não bloqueia).
    """
    if not modo_estrito_ativo():
        return False

    if bypass_result is not None and str(bypass_result).strip():
        return False  # bypass respondeu — LLM não é necessário

    # Modo estrito + nenhum bypass respondeu → escala
    lead_id = _extrair_lead_id(ctx)
    log.warning(
        "[MODO-ESTRITO] Sem resposta determinística lead=%s → escalando humano",
        lead_id,
    )

    # Grava flag Redis pra pipeline mover lead
    if redis_client and lead_id:
        try:
            key = f"blink:c70_modo_estrito_escalar:{lead_id}"
            redis_client.setex(key, 24 * 3600, "1")  # TTL 24h
        except Exception as exc:
            log.warning("[MODO-ESTRITO] Falhou setex Redis lead=%s: %s", lead_id, exc)

    return True


def _extrair_lead_id(ctx: Any) -> Optional[str]:
    """Extrai lead_id do ctx de forma tolerante."""
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return str(ctx.get("lead_id") or "") or None
    return str(getattr(ctx, "lead_id", "") or "") or None


def silencio_estrito() -> dict:
    """Payload de resposta quando modo estrito silencia a Lia.

    Retorna dict com answer="" e flag pra pipeline detectar e mover lead.
    """
    return {
        "answer": "",
        "modo_estrito_escalado": True,
        "motivo": "sem_resposta_deterministica",
    }


# ═════════════════════════════════════════════════════════════════════════
# Nota Kommo padrão pra registrar handoff
# ═════════════════════════════════════════════════════════════════════════

def montar_nota_handoff(user_text: str) -> str:
    """Nota Kommo canônica registrando escalação C-70."""
    ut = (user_text or "").strip()[:200]
    return (
        "🚨 [C-70 MODO ESTRITO]\n"
        "Sem resposta determinística para a mensagem do paciente.\n"
        f"Mensagem: {ut}\n"
        "\n"
        "Ação: lead movido para 1-ATENDIMENTO HUMANO, IA desativada.\n"
        "Motivo arquitetural: proibido responder sem regra canônica "
        "(Fábio 14/08/2026 P0)."
    )
