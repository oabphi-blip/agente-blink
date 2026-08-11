"""
Bug C-108 (11/08/2026) — Desistência explícita do paciente.

Quando o paciente diz "desisti", "não quero mais", "vou em outro lugar",
o LLM tentava salvar a conversa — perguntando turno, oferecendo desconto,
pedindo mais informações. Resultado: paciente ignorado em sua decisão,
Lia em loop.

Caso real que motivou: Juliana lead 24413852 disse "Desisto." + "Falar
com atendente" — Lia continuou perguntando turno. C-84b capturou o
segundo sinal (atendente) mas o primeiro (desistência) passou batido.

Decisão arquitetural (P0):
  - Desistência explícita = fim da conversa pelo paciente
  - Python detecta, agradece, sugere retorno futuro, e para
  - Lead movido para 2.LEADS FRIO (não Closed-lost) — paciente pode
    mudar de ideia; mas IA para imediatamente
  - Flag Redis com TTL 24h para pipeline agir

NUNCA:
  - Insistir ("tenho uma oferta especial...")
  - Perguntar "tem certeza?" — invade a decisão do paciente
  - Ignorar e continuar o fluxo normal

Toggle: DESISTENCIA_ATIVADO (default ON)
Fail-open: exceção → None
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("DESISTENCIA_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# ─────────────────────────────────────────────────────────────────────────────
# Redis key
# ─────────────────────────────────────────────────────────────────────────────

REDIS_KEY_DESISTENCIA = "blink:c108_desistencia:{lead_id}"

# ─────────────────────────────────────────────────────────────────────────────
# Padrões de desistência inequívoca
# ─────────────────────────────────────────────────────────────────────────────

_RE_DESISTENCIA = re.compile(
    r"\b(?:"
    # Desistência direta
    r"desist[oi](?:\s+mesmo)?"
    r"|n[aã]o\s+quero\s+mais"
    r"|n[aã]o\s+tenho\s+mais\s+interesse"
    r"|n[aã]o\s+preciso\s+mais"
    r"|pode\s+(?:cancelar|esquecer|desconsiderar)\s+tudo"
    r"|cancela\s+tudo"
    r"|deixa\s+pra\s+l[aá]"
    r"|n[aã]o\s+vou\s+mais\s+(?:marcar|agendar|ir)"
    # Ir em outro lugar
    r"|vou\s+(?:em|em\s+outr[ao]|pra\s+outr[ao]|buscar\s+outr[ao]|tentar\s+outr[ao])\s+(?:lugar|local|cl[ií]nica|m[eé]dic[oa]|hospital)"
    r"|encontrei\s+(?:outro|outra)\s+(?:cl[ií]nica|m[eé]dic[oa]|lugar|local)"
    r"|j[aá]\s+(?:marquei|agendei|resolvi)\s+(?:em|com|outro|outra)"
    r"|pref[ei]r[io]\s+outr[ao]\s+(?:lugar|local|m[eé]dic[oa]|cl[ií]nica)"
    # Encerramento explícito
    r"|(?:pode\s+)?encerr[ae](?:r)?\s+(?:o\s+atendimento|a\s+conversa|aqui)"
    r"|n[aã]o\s+tenho\s+interesse"
    r"|obrigad[ao],?\s+(?:mas\s+)?n[aã]o"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# Frases que parecem desistência mas não são
_RE_NAO_DESISTENCIA = re.compile(
    r"\b(?:"
    r"n[aã]o\s+quero\s+(?:esse|este|aquele)\s+hor[aá]rio"  # recusando slot específico
    r"|n[aã]o\s+quero\s+mais\s+(?:esse|este|aquele)\s+(?:hor[aá]rio|slot)"  # recusando slot
    r"|n[aã]o\s+quero\s+(?:mais\s+)?(?:de\s+)?(?:manh[aã]|tarde|s[aá]bado)"  # preferência
    r"|n[aã]o\s+preciso\s+mais\s+(?:de\s+)?(?:esses\s+)?hor[aá]rios"  # recusando slots
    r"|vou\s+tentar\s+(?:outro\s+)?hor[aá]rio"  # querendo outro slot
    r")",
    re.IGNORECASE,
)


def detectar_desistencia(user_text: str) -> bool:
    """Retorna True se o texto indica desistência explícita da consulta."""
    if not user_text:
        return False
    if _RE_NAO_DESISTENCIA.search(user_text):
        return False
    return bool(_RE_DESISTENCIA.search(user_text))


# ─────────────────────────────────────────────────────────────────────────────
# Resposta canônica
# ─────────────────────────────────────────────────────────────────────────────

def _resposta_desistencia(nome: str) -> str:
    saudacao = f"{nome}, " if nome else ""
    return (
        f"{saudacao}tudo bem — entendemos completamente. 😊\n\n"
        "Sempre que precisar de cuidados com a visão, estaremos aqui. "
        "Pode entrar em contato quando quiser. Cuide-se bem!"
    )


def _extrair_nome(ctx: Optional[dict]) -> str:
    if not ctx:
        return ""
    nome = (ctx.get("name") or ctx.get("contact_name") or "").strip()
    if not nome or nome.lower() in ("você", "cliente", "lead"):
        return ""
    return nome.split()[0].capitalize()


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────

def deve_responder_desistencia(
    ctx: Optional[dict],
    user_text: str = "",
    redis_client=None,
) -> Optional[str]:
    """Retorna resposta de encerramento, ou None se não aplicável.

    Efeito colateral: se redis_client fornecido, grava flag para pipeline
    mover lead para 2.LEADS FRIO e desativar IA.

    Fail-open: exceção → None.
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        # Verifica flag do enriquecimento OU detecta no user_text
        known = ctx.get("known") or {}
        tem_flag = known.get("desistencia_explicita", False)
        tem_regex = detectar_desistencia(user_text)

        if not tem_flag and not tem_regex:
            return None

        # Grava flag Redis para pipeline agir
        if redis_client is not None:
            lead_id = ctx.get("lead_id") or (known.get("lead_id"))
            if lead_id:
                try:
                    key = REDIS_KEY_DESISTENCIA.format(lead_id=lead_id)
                    redis_client.setex(key, 86400, "1")  # TTL 24h
                    log.info(
                        "[C-108] desistencia detectada lead=%s — flag Redis gravado",
                        lead_id,
                    )
                except Exception as _e_redis:
                    log.warning("[C-108] setex Redis falhou: %s", _e_redis)

        nome = _extrair_nome(ctx)
        return _resposta_desistencia(nome)

    except Exception as exc:
        log.warning("[C-108] deve_responder_desistencia falhou: %s", exc)
        return None  # fail-open
