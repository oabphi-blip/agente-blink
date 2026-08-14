"""
voice_agent/fora_escopo.py — Bug C-146 (14/08/2026)

REGRA FÁBIO (14/08/2026):
  "somente responder, se tiver o código determinístico do Python.
   Se não tiver, transfere para atendimento humano, muda a etapa pro
   atendimento humano, e o campo ativado IA, desativa IA, para que o
   atendimento humano especializado conduza a resposta e não inventar."

CASO REAL (lead 24328426 Alice Tavares):
  Paciente pagou sinal Pix. Depois conseguiu vaga pelo convênio. Perguntou:
  "gostaria de saber se o valor enviado poderia ser reembolsado, pois
  consegui uma vaga no meu convênio."
  Lia inventou: "a consulta com a Doutora Karla cobre a avaliação" — ERRADO.
  Causa raiz: C-129 tem r"reembolso\\b" (só o substantivo) mas não captura
  "reembolsado" (particípio verbal). A mensagem escapou para o LLM → LLM
  inventou resposta sobre cobertura, completamente fora do escopo da pergunta.

DOIS TIERS DE DETECÇÃO:

  Tier 1 — FINANCEIRO UNIVERSAL (sempre escalar):
    Qualquer menção a reembolso/estorno/devolução de valor já pago.
    Não requer contexto específico — política financeira é SEMPRE humano.
    Cobre formas verbais (reembolsado, reembolsar) que C-129 não cobria.

  Tier 2 — ESCOPO FECHADO (ja_agendado=True + pergunta não whitelistada):
    Paciente já agendado fazendo pergunta que não é:
      - Confirmar/cancelar consulta
      - Pedir endereço / horário
      - Pedir atendente (C-84 já cobre)
    Qualquer outra pergunta administrativa → escalar.
    Gate: só ativa quando lead já está agendado (evita falso positivo em triagem).

Toggle: FORA_ESCOPO_C146_ATIVADO (default ON). Fail-open em tudo.
Redis flag: blink:c146_fora_escopo:{lead_id} TTL 86400s (24h).
Rollback: FORA_ESCOPO_C146_ATIVADO=0 em Easypanel → Implantar.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)


# ─── Toggle ────────────────────────────────────────────────────────────────────

def _ativado() -> bool:
    return (os.environ.get("FORA_ESCOPO_C146_ATIVADO") or "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


# ─── Tier 1: Financeiro universal ─────────────────────────────────────────────
# Reembolso, estorno, devolução de valor — SEMPRE escalar.
# C-129 cobria apenas reembolso\b (substantivo). Este padrão cobre todas as
# formas verbais (reembolsado, reembolsar, estornar, devolver).

_RE_FINANCEIRO_C146 = re.compile(
    r"(?:"
    # Reembolso — TODAS as formas (substantivo + infinitivo + particípio)
    # Cobre: reembolso, reembolsos, reembolsar, reembolsado, reembolsada,
    #        reembolsados, reembolsadas — Bug C-146: C-129 só tinha "reembolso\b"
    r"reembolso[sr]?\b|"
    r"reembolsa(?:r|do[sa]?|da[s]?)?\b|"
    r"pedir\s+reembolso|"
    r"solicitar\s+reembolso|"
    r"quero\s+(?:o\s+)?reembolso|"
    r"tenho\s+direito\s+(?:ao\s+)?reembolso|"
    # Estorno — todas as formas
    r"\bestorno[sr]?\b|"
    r"\bestornar\b|"
    r"\bestornado[sa]?\b|"
    r"fazer\s+(?:o\s+)?estorno|"
    r"solicitar\s+(?:o\s+)?estorno|"
    # Devolução de valor / dinheiro
    r"devolu[cç][aã]o\b|"
    r"devolver\s+(?:o\s+)?valor|"
    r"devolver\s+(?:o\s+)?dinheiro|"
    r"devolvido[sa]?\b|"
    r"dinheiro\s+de\s+volta|"
    r"valor\s+de\s+volta|"
    r"receber\s+de\s+volta|"
    r"me\s+devolver|"
    # Padrões compostos — pagamento + mudança de contexto
    r"valor\s+enviado.{0,60}(?:receber|voltar|devolver)|"
    r"(?:paguei|j[aá]\s+paguei|tinha\s+pago).{0,60}(?:devolver|estorno|reembolso)|"
    # Caso Alice exato (lead 24328426): "consegui uma vaga no meu convênio"
    # Implica: paciente que pagou, agora tem plano, quer dinheiro de volta.
    r"consegui\s+(?:uma?\s+)?vaga\s+(?:(?:no|pelo|com)\s+)?(?:meu\s+|seu\s+|o\s+)?conv[eê]nio|"
    # Orientação de estorno (artigo 15 KB)
    r"orientac[aã]o\s+de\s+estorno"
    r")",
    re.IGNORECASE | re.DOTALL,
)


# ─── Tier 2: Escopo fechado pós-agendamento ───────────────────────────────────
# Quando lead já está agendado (ja_agendado=True), qualquer pergunta que
# não seja sobre confirmação/endereço/data deve ser escalada.
# Gate: ativa SOMENTE quando ja_agendado=True (evita falso positivo em triagem).

# Perguntas whitelistadas para leads agendados — Python tem resposta para essas
_RE_WHITELIST_POS_AGENDA = re.compile(
    r"(?:"
    r"(?:qual|onde)\s+(?:fica|é)\s+(?:a\s+)?(?:clínica|clinica|endere[cç]o|rua)|"
    r"endere[cç]o\b|"
    r"como\s+(?:chegar|ir)|"
    r"(?:qual|que)\s+(?:dia|hora|horário|horario)\s+(?:da|é|é\s+a|)\s*(?:minha\s+)?consulta|"
    r"minha\s+consulta|"
    r"confirmar\s+(?:a\s+)?consulta|"
    r"(?:cancelar|desmarcar|remarcar|remarcação)\b|"  # C-117 cuida
    r"quero\s+(?:cancelar|desmarcar|remarcar)|"
    r"(?:n[aã]o\s+(?:vou\s+)?(?:poder|consigo)\s+(?:ir|comparecer))|"
    r"vou\s+(?:atrasar|me\s+atrasar)|"
    r"(?:lembro|esqueci)\s+(?:o\s+)?hor[aá]rio|"
    r"quero\s+(?:marcar|agendar)\s+(?:nova|outra|pr[oó]xima)|"   # novo agendamento OK
    r"nova\s+consulta"
    r")",
    re.IGNORECASE,
)

# Marcadores de pergunta genuína (filtra mensagens de confirmação simples)
_RE_PERGUNTA_C146 = re.compile(
    r"\?|gostaria\s+de\s+saber|queria\s+saber|pode\s+me\s+(?:dizer|informar|ajudar)|"
    r"como\s+(?:faço|funciona)|tem\s+como|[eé]\s+possível|preciso\s+(?:de|saber)",
    re.IGNORECASE,
)


# ─── Mensagem canônica ─────────────────────────────────────────────────────────

def _montar_handoff_c146(nome: str | None) -> str:
    saud = f"{nome}, " if nome else ""
    return (
        f"{saud}vou conectar você agora com nossa equipe — "
        "eles conseguem te ajudar com isso direto. "
        "Em instantes alguém da Blink responde! 🤝"
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _gravar_flag_c146(ctx: dict | None, redis_client=None) -> None:
    """Grava flag Redis para pipeline mover lead pra ATENDIMENTO HUMANO."""
    try:
        if not redis_client or not ctx:
            return
        lead_id = (
            (ctx.get("known") or {}).get("lead_id")
            or ctx.get("lead_id")
            or (ctx.get("lead") or {}).get("id")
        )
        if lead_id:
            redis_client.setex(f"blink:c146_fora_escopo:{lead_id}", 86400, "1")
            log.info("[C-146] flag gravado lead=%s TTL=24h", lead_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("[C-146] gravar_flag_c146 falhou: %s", exc)


# ─── Função principal ──────────────────────────────────────────────────────────

def deve_escalar_fora_escopo_c146(
    ctx: Optional[dict],
    user_text: str,
    redis_client=None,
) -> Optional[str]:
    """Detecta perguntas fora do escopo Python e retorna mensagem de escalada.

    Tier 1 (universal): reembolso/estorno/devolução de valor — SEMPRE escalar.
    Tier 2 (pós-agenda): lead já agendado + pergunta não whitelistada → escalar.

    Retorna None para fail-open (LLM continua). Toggle: FORA_ESCOPO_C146_ATIVADO=0.
    """
    if not _ativado():
        return None
    if not user_text or not user_text.strip():
        return None

    try:
        known = ((ctx or {}).get("known") or {}) if ctx else {}
        nome = (
            (known.get("nome_contato") or known.get("nome") or "").split()[0]
            if (known.get("nome_contato") or known.get("nome") or "").strip()
            else None
        )
        lead_id = (
            known.get("lead_id") or (ctx or {}).get("lead_id")
            or ((ctx or {}).get("lead") or {}).get("id")
        )

        # ── Tier 1: Financeiro universal ──────────────────────────────────────
        if _RE_FINANCEIRO_C146.search(user_text):
            log.warning(
                "[C-146] Tier 1 FINANCEIRO — reembolso/estorno detectado. "
                "lead=%s msg=%r",
                lead_id,
                user_text[:120],
            )
            _gravar_flag_c146(ctx, redis_client)
            return _montar_handoff_c146(nome)

        # ── Tier 2: Escopo fechado pós-agendamento ────────────────────────────
        # Só ativa quando lead já está agendado E a pergunta não tem resposta
        # Python whitelistada (evita falso positivo em leads de triagem).
        # Mínimo 4 palavras: exclui saudações curtas ("Tudo bem?", "Oi", "Ok")
        if known.get("ja_agendado"):
            # Pergunta sem resposta Python + não whitelistada
            if (
                len(user_text.split()) >= 4  # Anti-falso-positivo: saudações curtas
                and _RE_PERGUNTA_C146.search(user_text)
                and not _RE_WHITELIST_POS_AGENDA.search(user_text)
            ):
                log.warning(
                    "[C-146] Tier 2 PÓS-AGENDA — pergunta sem handler Python. "
                    "lead=%s ja_agendado=True msg=%r",
                    lead_id,
                    user_text[:120],
                )
                _gravar_flag_c146(ctx, redis_client)
                return _montar_handoff_c146(nome)

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-146] deve_escalar_fora_escopo_c146 falhou (fail-open): %s", exc)

    return None
