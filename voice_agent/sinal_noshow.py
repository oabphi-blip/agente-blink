"""
Bug C-109 (11/08/2026) — NO-SHOW COUNT → sinal Pix obrigatório antes de oferecer slot.

Causa raiz: LLM recebia ctx.known (incluindo noshow_count) mas NUNCA verificava
esse campo antes de ofertar slots. Pacientes com 2+ no-shows recebiam oferta de
slot idêntica a pacientes sem histórico — sem exigência de sinal Pix.

Resultado: slots reservados por pacientes que não compareceram, bloqueando vagas
para quem realmente ia. Médica reclamava de grade vazia no dia.

Política (KB 38_politica_sinal_remarcacao_noshow.md):
  • 1 no-show: aviso amigável. Sem sanção financeira ainda.
  • 2+ no-shows: Reserva Imediata 50% OBRIGATÓRIA. Sem opção Fila de Encaixe.
  • 3+ no-shows: pagamento INTEGRAL antecipado + escalar para equipe humana.
  • 4+ no-shows: bloqueio de agendamento online (só aprovação médica direta).

Decisão arquitetural (P0):
  - Python detecta noshow_count >= 2 em ctx.known (injetado por C-109 step 15)
  - ANTES de oferecer slots, retorna mensagem de sinal obrigatório
  - Para >= 3: grava flag Redis para pipeline mover para ATENDIMENTO HUMANO
  - O bypass dispara UMA VEZ por sessão (flag Redis TTL 8h) — não repete a cada turno

Chaves Pix oficiais (allowlist):
  - Asa Norte: karladelaliberaoftalmo@gmail.com
  - Águas Claras: 52.303.729/0001-30

Toggle: SINAL_NOSHOW_ATIVADO (default ON)
Fail-open: exceção → None
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("SINAL_NOSHOW_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# Redis key para não repetir o aviso a cada turno
REDIS_KEY_SINAL_COBRADO = "blink:c109_sinal_cobrado:{lead_id}"
# Redis key para pipeline escalar (>= 3 no-shows)
REDIS_KEY_ESCALAR_NOSHOW = "blink:c109_escalar_noshow:{lead_id}"

# Chaves Pix por unidade
_PIX_POR_UNIDADE = {
    "asa norte": "karladelaliberaoftalmo@gmail.com",
    "águas claras": "52.303.729/0001-30",
    "aguas claras": "52.303.729/0001-30",
}
_PIX_FALLBACK = "karladelaliberaoftalmo@gmail.com"  # Asa Norte como default

# Valores de sinal por médico (50% do valor da consulta)
_SINAL_POR_MEDICO = {
    "karla": {
        "apv": 400,    # APV R$ 800 → 50% = R$ 400
        "default": 305.50,  # R$ 611 → 50% = R$ 305,50
    },
    "fabrício": {
        "catarata": 222.50,   # R$ 445 → 50%
        "default": 305.50,    # R$ 611 → 50%
    },
}
_SINAL_DEFAULT = 305.50


def _pix_key(ctx: dict) -> str:
    unidade = (
        (ctx.get("known") or {}).get("unidade") or ""
    ).lower().strip()
    return _PIX_POR_UNIDADE.get(unidade, _PIX_FALLBACK)


def _valor_sinal(ctx: dict) -> str:
    known = ctx.get("known") or {}
    medico = (known.get("medico") or "").lower()
    motivo = (known.get("motivo") or "").lower()

    if "karla" in medico:
        if any(k in motivo for k in ("processamento", "apv", "sdp", "postural")):
            v = _SINAL_POR_MEDICO["karla"]["apv"]
        else:
            v = _SINAL_POR_MEDICO["karla"]["default"]
    elif "fabr" in medico:
        if "catarata" in motivo:
            v = _SINAL_POR_MEDICO["fabrício"]["catarata"]
        else:
            v = _SINAL_POR_MEDICO["fabrício"]["default"]
    else:
        v = _SINAL_DEFAULT

    # Formatar: inteiro sem centavos se .0, ou com vírgula
    if v == int(v):
        return f"R$ {int(v)}"
    return f"R$ {v:.2f}".replace(".", ",")


def _nome(ctx: dict) -> str:
    nome = (ctx.get("name") or ctx.get("contact_name") or "").strip()
    if not nome or nome.lower() in ("você", "cliente", "lead"):
        return ""
    return nome.split()[0].capitalize()


def _mensagem_sinal_obrigatorio(ctx: dict) -> str:
    """Mensagem para paciente com 2 no-shows (sinal 50% obrigatório)."""
    nome = _nome(ctx)
    saud = f"{nome}, " if nome else ""
    pix = _pix_key(ctx)
    sinal = _valor_sinal(ctx)

    return (
        f"{saud}temos horários disponíveis para você! 😊\n\n"
        f"Como precaução para garantir sua vaga, precisamos de uma reserva de "
        f"50% ({sinal}) via Pix antes de confirmar o horário.\n\n"
        f"🔑 Chave Pix: `{pix}`\n\n"
        f"Assim que receber a confirmação do pagamento, já te passo o horário exato. "
        f"Tem alguma dúvida?"
    )


def _mensagem_escalar_noshow(ctx: dict) -> str:
    """Mensagem para paciente com 3+ no-shows (escalação obrigatória)."""
    nome = _nome(ctx)
    saud = f"{nome}, " if nome else ""

    return (
        f"{saud}obrigada pelo contato! 😊\n\n"
        f"Para confirmar seu agendamento, precisamos passar sua solicitação "
        f"para nossa equipe, que vai entrar em contato para alinhar os detalhes. "
        f"Pode aguardar?"
    )


def deve_exigir_sinal_noshow(
    ctx: Optional[dict],
    user_text: str = "",
    redis_client=None,
) -> Optional[str]:
    """Retorna mensagem de sinal obrigatório ou escalação, ou None se não aplicável.

    Dispara quando:
    - sinal_obrigatorio=True (noshow_count >= 2) OU
    - escalar_noshow=True (noshow_count >= 3)
    E o lead está em fluxo de agendamento (ctx.agenda não vazio).
    E o aviso ainda não foi dado nessa sessão (Redis flag).

    Fail-open: exceção → None.
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        known = ctx.get("known") or {}

        # Só atua se há sinal de que o paciente está no fluxo de agendamento:
        # - há agenda disponível no ctx, OU
        # - user_text indica confirmação/aceitação de slot
        tem_agenda = bool(ctx.get("agenda"))
        _RE_ACEITE = __import__("re").compile(
            r"\b(?:1[️⃣]|2[️⃣]|3[️⃣]|op[çc][aã]o\s*[123]|primeira|segunda|terceira"
            r"|hor[aá]rio\s*[123]|quero\s+(?:o\s+)?(?:primeiro|segundo|terceiro)"
            r"|confirmo|confirmar|esse\s+hor[aá]rio|esse\s+dia|pode\s+ser)",
            __import__("re").IGNORECASE,
        )
        user_quer_slot = bool(_RE_ACEITE.search(user_text)) if user_text else False

        if not tem_agenda and not user_quer_slot:
            return None

        lead_id = ctx.get("lead_id") or (known.get("lead_id"))

        # ── Caso 3+ no-shows: escalação para humano ──
        if known.get("escalar_noshow"):
            # Verificar se já foi escalado nesta sessão
            if redis_client and lead_id:
                flag_key = REDIS_KEY_ESCALAR_NOSHOW.format(lead_id=lead_id)
                if redis_client.get(flag_key):
                    return None  # já escalado — não repetir
                redis_client.setex(flag_key, 28800, "1")  # TTL 8h

            log.info("[C-109] noshow>=3 lead=%s → escalar para humano", lead_id)
            # Grava flag para pipeline mover para ATENDIMENTO HUMANO
            if redis_client and lead_id:
                redis_client.setex(
                    f"blink:c109_move_humano:{lead_id}", 86400, "1"
                )

            return _mensagem_escalar_noshow(ctx)

        # ── Caso 2 no-shows: sinal Pix 50% obrigatório ──
        if known.get("sinal_obrigatorio"):
            # Verificar se já cobrou sinal nesta sessão
            if redis_client and lead_id:
                flag_key = REDIS_KEY_SINAL_COBRADO.format(lead_id=lead_id)
                if redis_client.get(flag_key):
                    return None  # já cobrou — LLM trata resposta do paciente
                redis_client.setex(flag_key, 28800, "1")  # TTL 8h

            log.info("[C-109] noshow>=2 lead=%s → exigir sinal Pix", lead_id)
            return _mensagem_sinal_obrigatorio(ctx)

        return None

    except Exception as exc:
        log.warning("[C-109] deve_exigir_sinal_noshow falhou: %s", exc)
        return None  # fail-open
