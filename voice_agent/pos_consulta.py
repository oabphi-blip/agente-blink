"""Bug C-129 (12/08/2026) — Bypass pós-consulta: escalar para atendimento humano.

Qualquer mensagem de paciente em contexto pós-consulta deve ser escalada para
atendente humana — Lia não tem como resolver recibos, resultados, laudos ou
questões administrativas geradas após a consulta.

Caso real: lead 14230149 Luciana — paciente perguntou "recibo de pagamento" e Lia
respondeu com tabela de preços + "Gostaria de agendar?" (non-sequitur total).

Camadas de detecção:
  A) Pedido de documento/administrativo → escalar sempre, independente de ctx
  B) ctx.known["a_fazer_pos_consulta"] = True + msg não é novo agendamento → escalar

Toggle: POS_CONSULTA_ATIVADO (default ON). Fail-open: exceção → None.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ─── Toggle ────────────────────────────────────────────────────────────────────

def _ativado() -> bool:
    return (os.environ.get("POS_CONSULTA_ATIVADO") or "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


# ─── Camada A: Pedidos de documento / administrativo ──────────────────────────
# Dispara independente de ctx — paciente pedindo qualquer documento pós-consulta
# deve ir ao humano (Lia não tem acesso a recibos, laudos, etc.).

_RE_PEDIDO_DOCUMENTO_C129 = re.compile(
    r"(?:"
    # Recibo / nota fiscal / comprovante financeiro
    r"recibo\b|"
    r"nota\s+fiscal|"
    r"comprovante\s+de\s+pagamento|"
    r"comprovante\s+da\s+consulta|"
    r"solicitar\s+recibo|"
    r"preciso\s+do\s+recibo|"
    # Reembolso
    r"reembolso\b|"
    r"pedir\s+reembolso|"
    r"solicitar\s+reembolso|"
    # Declaração / atestado
    r"declara[cç][aã]o\s+de\s+comparecimento|"
    r"declara[cç][aã]o\s+m[eé]dica|"
    r"atestado\s+m[eé]dico|"
    r"\batestado\b|"
    # Laudo / resultado
    r"laudo\s+m[eé]dico|"
    r"\blaudo\b|"
    r"resultado\s+do\s+exame|"
    r"resultado\s+da\s+consulta|"
    r"resultado\s+dos\s+exames|"
    # Receita
    r"receita\s+m[eé]dica|"
    # Histórico / prontuário
    r"hist[oó]rico\s+m[eé]dico|"
    r"prontu[aá]rio|"
    # Link de pagamento / financeiro
    r"link\s+de\s+pagamento|"
    r"cobran[cç]a\b|"
    # Segunda via
    r"segunda\s+via|"
    r"enviar\s+recibo|"
    r"mandar\s+recibo"
    r")",
    re.IGNORECASE,
)

# ─── Camada B: Intent de novo agendamento (EXCLUIR da escalada C-129) ─────────
# Se a_fazer_pos_consulta=True mas o paciente claramente quer agendar nova consulta
# → não escalar para humano, deixar o fluxo normal de agendamento.

_RE_INTENT_NOVO_AGENDAMENTO_C129 = re.compile(
    r"(?:"
    r"quero\s+(?:marcar|agendar)|"
    r"marcar\s+(?:uma\s+)?(?:consulta|retorno)|"
    r"agendar\s+(?:uma\s+)?(?:consulta|retorno|nova)|"
    r"nova\s+consulta|"
    r"pr[oó]xima\s+consulta|"
    r"proxima\s+consulta|"
    r"retorno\s+(?:com\s+a?\s*dra?\.?|pra|para)|"
    r"quando\s+(?:devo|posso)\s+voltar|"
    r"volta[rr]?"
    r")",
    re.IGNORECASE,
)

# ─── Mensagem canônica de escalada ────────────────────────────────────────────

_MSG_ESCALAR_C129 = (
    "Entendido! Para te ajudar com isso, vou chamar nossa equipe — "
    "eles conseguem resolver essa questão direto com você. "
    "Em instantes alguém da Blink responde! 🤝"
)


# ─── Função principal ─────────────────────────────────────────────────────────

def deve_escalar_pos_consulta(
    ctx: Optional[dict],
    user_text: str,
    redis_client=None,
) -> Optional[str]:
    """Detecta mensagens pós-consulta e retorna mensagem de escalada para humano.

    Camada A: pedido de documento/administrativo → escalar sempre.
    Camada B: ctx.known.a_fazer_pos_consulta=True + não é intent de agendamento → escalar.

    Retorna None para fail-open (LLM continua normalmente).
    Toggle: POS_CONSULTA_ATIVADO=0 desliga.
    """
    if not _ativado():
        return None
    if not user_text or not user_text.strip():
        return None

    try:
        known = (ctx or {}).get("known") or {}

        # Camada A: pedido de documento/administrativo — sempre escalar
        if _RE_PEDIDO_DOCUMENTO_C129.search(user_text):
            log.info(
                "[C-129] Camada A: pedido de documento detectado — escalando humano. "
                "lead=%s msg=%r",
                known.get("lead_id") or (ctx or {}).get("lead_id"),
                user_text[:80],
            )
            _gravar_flag_c129(ctx, redis_client)
            return _MSG_ESCALAR_C129

        # Camada B: a_fazer_pos_consulta=True + msg não é novo agendamento
        if known.get("a_fazer_pos_consulta"):
            if _RE_INTENT_NOVO_AGENDAMENTO_C129.search(user_text):
                log.debug(
                    "[C-129] Camada B: a_fazer_pos_consulta=True MAS "
                    "intent de novo agendamento — não escalar."
                )
                return None  # deixar fluxo de agendamento seguir normalmente

            log.info(
                "[C-129] Camada B: a_fazer_pos_consulta=True + msg geral — "
                "escalando humano. lead=%s msg=%r",
                known.get("lead_id") or (ctx or {}).get("lead_id"),
                user_text[:80],
            )
            _gravar_flag_c129(ctx, redis_client)
            return _MSG_ESCALAR_C129

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-129] bypass falhou (fail-open): %s", exc)

    return None


def _gravar_flag_c129(ctx: Optional[dict], redis_client=None) -> None:
    """Grava flag Redis para pipeline mover lead → 1-ATENDIMENTO HUMANO."""
    if redis_client is None:
        try:
            from voice_agent.redis_client import get_redis
            redis_client = get_redis()
        except Exception:  # noqa: BLE001
            return

    if redis_client is None:
        return

    lead_id = (
        ((ctx or {}).get("known") or {}).get("lead_id")
        or (ctx or {}).get("lead_id")
    )
    if not lead_id:
        return

    try:
        redis_client.setex(f"blink:c129_pos_consulta:{lead_id}", 86400, "1")
        log.debug("[C-129] flag Redis gravado lead=%s", lead_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("[C-129] gravar flag Redis falhou: %s", exc)
