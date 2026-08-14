"""Bug C-72 — Nunca inventar horário (Fábio 14/08/2026).

Regra INVIOLÁVEL:
    TODO horário HH:MM que a Lia mencionar em uma oferta DEVE existir em
    ctx.agenda (fonte Medware). Se não existir → substitui a mensagem +
    escala pra humano.

Origem: Fábio 14/08 P0 — lead 20325187 Lucas Machado Casotti (Asa Norte,
Pro ser STJ, bebê 0-2). Lia ofertou "Segunda 17/08 10:00 + Quarta 19/08
14:00" — dias da semana batem (C-31 protegeu) mas horários foram
inventados sem consultar Medware.

Como funciona:
    1. Extrai todos os HH:MM da resposta da Lia (regex).
    2. Compara cada um contra ctx.agenda (slots reais Medware).
    3. Se algum horário mencionado NÃO existe em nenhum slot Medware:
       → substitui a mensagem inteira por texto neutro
       → grava flag Redis blink:c72_horario_inventado:{lead_id} TTL 24h
       → pipeline hook move lead pra 1-ATENDIMENTO HUMANO

Fail-open:
    - Se toggle desligado → retorna texto original.
    - Se resposta não tem HH:MM → retorna texto original.
    - Se ctx.agenda está VAZIO → BLOQUEIA (não pode ter HH:MM sem Medware).
    - Exceções → retorna texto original + log warning.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional


log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Extrator de horários mencionados no texto
# ═════════════════════════════════════════════════════════════════════════

# Casa HH:MM (24h) — 00:00 até 23:59. Aceita "às 10:00" ou "10h" ou "10h30".
_RE_HORARIO_HHMM = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
    re.IGNORECASE,
)

# "10h", "10h30", "10 h 30" — formato Brasil sem dois pontos
_RE_HORARIO_HBRA = re.compile(
    r"\b([01]?\d|2[0-3])\s*h\s*([0-5]\d)?\b",
    re.IGNORECASE,
)


def extrair_horarios(text: str) -> set[str]:
    """Retorna set de horários no formato canônico HH:MM encontrados no texto.

    Exemplo:
        "1️⃣ 17/08 às 10:00\n2️⃣ 19/08 às 14h30"
        → {"10:00", "14:30"}
    """
    if not text:
        return set()

    horarios: set[str] = set()

    for m in _RE_HORARIO_HHMM.finditer(text):
        h, mn = m.group(1), m.group(2)
        horarios.add(f"{int(h):02d}:{mn}")

    for m in _RE_HORARIO_HBRA.finditer(text):
        h = m.group(1)
        mn = m.group(2) or "00"
        # Evita duplo-matching: "10:00" tbm casa "10" no _RE_HORARIO_HBRA se
        # não tomar cuidado. Só adiciona se não tem ":" próximo.
        span = m.span()
        contexto = text[max(0, span[0] - 2):span[1] + 2]
        if ":" in contexto:
            continue
        horarios.add(f"{int(h):02d}:{mn}")

    return horarios


# ═════════════════════════════════════════════════════════════════════════
# Extrator de horários válidos do Medware (ctx.agenda)
# ═════════════════════════════════════════════════════════════════════════

def horarios_medware_ctx(ctx: Any) -> set[str]:
    """Retorna set de horários HH:MM presentes em ctx.agenda (fonte Medware).

    ctx.agenda é lista de dicts com key "hora" (ex: "10:00") OU pode vir
    como string "17/08/2026 10:00" — tenta extrair HH:MM.

    Retorna set vazio quando agenda vazia ou não disponível.
    """
    if ctx is None:
        return set()

    agenda = None
    if isinstance(ctx, dict):
        agenda = ctx.get("agenda")
    else:
        agenda = getattr(ctx, "agenda", None)

    if not agenda:
        return set()

    horarios: set[str] = set()
    for slot in agenda:
        if isinstance(slot, dict):
            # Formato: {"data": "17/08/2026", "hora": "10:00"}
            hora = slot.get("hora") or slot.get("hour") or slot.get("time")
            if hora:
                m = _RE_HORARIO_HHMM.search(str(hora))
                if m:
                    horarios.add(f"{int(m.group(1)):02d}:{m.group(2)}")
        elif isinstance(slot, str):
            # Formato flat: "17/08/2026 10:00"
            m = _RE_HORARIO_HHMM.search(slot)
            if m:
                horarios.add(f"{int(m.group(1)):02d}:{m.group(2)}")

    return horarios


# ═════════════════════════════════════════════════════════════════════════
# Detector de OFERTA (só valida texto que oferta slot)
# ═════════════════════════════════════════════════════════════════════════

_RE_TEXTO_PARECE_OFERTA = re.compile(
    r"1️⃣|2️⃣|3️⃣|"
    r"tenho\s+.{0,30}(?:hor[áa]rios?|slots?)|"
    r"posso\s+oferecer|"
    r"algum\s+desses|"
    r"qual\s+fica\s+melhor|"
    r"(?:segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado)"
    r"(?:-feira)?\s*\(?\d{1,2}[/.-]\d{1,2}",
    re.IGNORECASE,
)


def _texto_e_oferta(text: str) -> bool:
    """Retorna True se o texto claramente oferta um slot (não é confirmação
    ou referência a agendamento passado).
    """
    if not text:
        return False
    return bool(_RE_TEXTO_PARECE_OFERTA.search(text))


# ═════════════════════════════════════════════════════════════════════════
# Filtro principal
# ═════════════════════════════════════════════════════════════════════════

def _ativado() -> bool:
    """Toggle env — default ON."""
    return (os.environ.get("NUNCA_INVENTAR_HORARIO_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off", ""
    )


_FALLBACK_HORARIO_INVENTADO = (
    "Deixa eu reconferir os horários exatos com a agenda e volto em instantes. "
    "Vou passar para a equipe validar."
)


def validar_horarios_contra_medware(
    text: str,
    ctx: Any,
    redis_client: Any = None,
) -> tuple[str, bool]:
    """Retorna (texto_final, foi_bloqueado).

    Se algum HH:MM no `text` NÃO existe em ctx.agenda → substitui `text`
    inteiro por fallback neutro + grava flag Redis pra escalar humano.

    Retorna sempre uma tupla (str, bool):
        - texto_final: texto ORIGINAL se OK, ou fallback se bloqueou
        - foi_bloqueado: True se substituiu, False se passou
    """
    if not _ativado() or not text:
        return text, False

    # Só valida quando é OFERTA (texto com padrão 1️⃣/2️⃣, "tenho horários",
    # "posso oferecer", "segunda 17/08"). Confirmação ou pergunta livre passa.
    if not _texto_e_oferta(text):
        return text, False

    horarios_texto = extrair_horarios(text)
    if not horarios_texto:
        return text, False

    horarios_medware = horarios_medware_ctx(ctx)

    # Regra: TODOS os horários mencionados devem estar em Medware
    inventados = horarios_texto - horarios_medware
    if not inventados:
        return text, False  # todos batem — OK

    # BLOQUEIO — Lia inventou pelo menos 1 horário
    lead_id = _extrair_lead_id(ctx)
    log.error(
        "[C-72] HORÁRIO INVENTADO lead=%s texto_hh=%s medware_hh=%s inventados=%s "
        "texto_original=%r",
        lead_id,
        sorted(horarios_texto),
        sorted(horarios_medware),
        sorted(inventados),
        text[:200],
    )

    # Grava flag Redis pra pipeline mover lead
    if redis_client and lead_id:
        try:
            key = f"blink:c72_horario_inventado:{lead_id}"
            redis_client.setex(key, 24 * 3600, "1")
        except Exception as exc:
            log.warning("[C-72] falhou setex Redis lead=%s: %s", lead_id, exc)

    return _FALLBACK_HORARIO_INVENTADO, True


def _extrair_lead_id(ctx: Any) -> Optional[str]:
    """Extrai lead_id do ctx tolerante."""
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return str(ctx.get("lead_id") or "") or None
    return str(getattr(ctx, "lead_id", "") or "") or None


# ═════════════════════════════════════════════════════════════════════════
# Nota Kommo canônica pro handoff C-72
# ═════════════════════════════════════════════════════════════════════════

def montar_nota_handoff_c72(
    text_original: str,
    horarios_inventados: set[str],
    horarios_medware: set[str],
) -> str:
    """Nota Kommo registrando handoff por horário inventado."""
    return (
        "🚨 [C-72 HORÁRIO INVENTADO]\n"
        "A Lia mencionou horário(s) que NÃO existem na agenda Medware.\n"
        "\n"
        f"Horários mencionados (inventados): {sorted(horarios_inventados)}\n"
        f"Horários REAIS no Medware: {sorted(horarios_medware) or '(agenda vazia)'}\n"
        "\n"
        f"Texto original suprimido:\n{text_original[:300]}\n"
        "\n"
        "Ação: mensagem substituída + lead movido pra 1-ATENDIMENTO HUMANO.\n"
        "Motivo: proibido ofertar horário sem confirmação Medware "
        "(Fábio 14/08/2026 P0)."
    )
