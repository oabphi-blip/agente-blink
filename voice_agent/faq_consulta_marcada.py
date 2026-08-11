"""
Bug C-115 (11/08/2026) — FAQ "quando é minha consulta?"
========================================================
Paciente pergunta sobre data/horário da consulta marcada.
Python responde diretamente com dados do Kommo (ctx.known.dia_consulta_iso)
sem chamar Medware ou LLM.

Regra: se ctx.known tem dia_consulta_iso → formata e responde.
       Se não tem → retorna None → LLM continua normalmente (fail-open).

Casos cobertos:
  - "quando é minha consulta?"
  - "que dia é minha consulta?"
  - "qual o horário da consulta?"
  - "confirmar minha consulta"
  - "minha consulta é quando?"
  - "que horas tenho consulta?"

Consulta no passado (>= 24h atrás) → resposta diferente informando que foi realizada.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Toggle (default ON)
# ─────────────────────────────────────────────────────────────────────────────
import os as _os
_ATIVADO = _os.environ.get("FAQ_CONSULTA_MARCADA_ATIVADO", "1").strip().lower() not in (
    "0", "false", "no", "off", ""
)

# ─────────────────────────────────────────────────────────────────────────────
# Fuso horário BRT (UTC-3) — sem dependência de pytz
# ─────────────────────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo as _ZoneInfo  # Python 3.9+
    _TZ_BR = _ZoneInfo("America/Sao_Paulo")
except ImportError:
    from datetime import timezone, timedelta
    _TZ_BR = timezone(timedelta(hours=-3))  # type: ignore[assignment]

# ─────────────────────────────────────────────────────────────────────────────
# Padrões de detecção PT-BR
# ─────────────────────────────────────────────────────────────────────────────
_RE_CONSULTA_QUANDO = re.compile(
    r"""
    # Pergunta direta: quando / que dia / que horas / qual o horário
    quando\s+(?:é|fica|ser[aá]|est[aá])\s+(?:a\s+)?(?:minha\s+)?consulta
    |
    que\s+dia\s+(?:é|est[aá])\s+(?:a\s+)?(?:minha\s+)?consulta
    |
    qual\s+(?:o\s+)?(?:dia|hor[aá]rio|hora)\s+d[ao]\s+(?:minha\s+)?consulta
    |
    (?:minha\s+)?consulta\s+(?:é|fica|est[aá])\s+(?:quando|que\s+dia|para?\s+quando)
    |
    # "quando tenho consulta", "que horas tenho consulta"
    quando\s+(?:tenho|tem)\s+(?:a\s+)?(?:minha\s+)?consulta
    |
    que\s+horas\s+(?:é|tenho|tem)\s+(?:a\s+)?(?:minha\s+)?consulta
    |
    # "confirmar minha consulta" / "confirmar horário"
    confirmar?\s+(?:minha\s+)?(?:consulta|hor[aá]rio|agendamento)
    |
    # "lembrar da consulta" / "lembrete da consulta"
    (?:lembr(?:ar|ete)?)\s+(?:da\s+)?(?:minha\s+)?consulta
    |
    # "data da minha consulta" / "horário do meu agendamento"
    (?:data|hor[aá]rio|dia|hora)\s+d[ao]\s+(?:minha\s+)?(?:consulta|agendamento)
    |
    # "qual minha consulta" / "quando minha consulta"
    quando\s+(?:é\s+)?minha\s+(?:consulta|visita|atendimento)
    |
    qual\s+(?:é\s+)?(?:a\s+)?minha\s+(?:consulta|data|hora|hor[aá]rio)
    |
    # "já tenho consulta marcada?" / "minha consulta está marcada?"
    (?:j[aá]\s+)?(?:tenho|tem)\s+(?:consulta|agendamento)\s+marcad[ao]
    |
    # "minha consulta marcada" / "consulta agendada"
    (?:minha\s+)?(?:consulta|agendamento)\s+(?:marcad[ao]|agendad[ao])
    |
    # standalone simples
    \bqu(?:and|e)\s+(?:é|est|ten|tem)[oóae]?\b.*consulta
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento dia da semana PT-BR
# ─────────────────────────────────────────────────────────────────────────────
_DIAS_SEMANA = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def _formatar_dia_semana(dt: datetime) -> str:
    """Retorna nome do dia da semana em PT-BR."""
    return _DIAS_SEMANA[dt.weekday()]


def _formatar_data_hora(iso_str: str) -> tuple[str, str, bool]:
    """
    Parseia ISO string BRT e retorna (data_fmt, hora_fmt, is_passado).
    data_fmt: "Quinta-feira (14/08)"
    hora_fmt: "09:30"
    is_passado: True se consulta >= 24h atrás
    """
    dt = datetime.fromisoformat(iso_str)
    # Garantir BRT se sem timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ_BR)

    dia_semana = _formatar_dia_semana(dt)
    data_fmt = f"{dia_semana} ({dt.day:02d}/{dt.month:02d})"
    hora_fmt = f"{dt.hour:02d}:{dt.minute:02d}"

    # Consulta passada = mais de 24h atrás
    agora = datetime.now(tz=_TZ_BR)
    is_passado = (agora - dt).total_seconds() > 86400

    return data_fmt, hora_fmt, is_passado


def _extrair_medico(ctx: dict) -> str:
    """Extrai nome curto do médico do ctx.known."""
    known = ctx.get("known") or {}
    medico = known.get("medico") or ""
    if not medico:
        return "Dra. Karla Delalíbera"  # default clínico
    m = medico.lower()
    if "fabr" in m:
        return "Dr. Fabrício Freitas"
    if "katia" in m or "kátia" in m:
        return "Dra. Kátia Delalíbera"
    # Default para Karla ou qualquer outro
    return "Dra. Karla Delalíbera"


def _extrair_unidade(ctx: dict) -> str:
    """Extrai unidade do ctx.known."""
    known = ctx.get("known") or {}
    unidade = known.get("unidade") or ""
    if not unidade:
        return ""
    u = unidade.lower()
    if "norte" in u or "asa" in u:
        return "Asa Norte"
    if "claras" in u or "águas" in u or "aguas" in u:
        return "Águas Claras"
    return unidade.title()


def _montar_resposta_futura(data_fmt: str, hora_fmt: str, medico: str, unidade: str) -> str:
    """Monta mensagem de consulta futura."""
    partes = [
        f"📅 Sua consulta está marcada para **{data_fmt}** às **{hora_fmt}**",
        f"com {medico}",
    ]
    if unidade:
        partes.append(f"na unidade **{unidade}**.")
    else:
        partes.append(".")

    mensagem = " ".join(partes)

    # Adicionar lembrete gentil sobre confirmação D-1
    mensagem += (
        "\n\nQualquer dúvida é só chamar aqui. Até lá! 😊"
    )
    return mensagem


def _montar_resposta_passada(data_fmt: str, hora_fmt: str, medico: str) -> str:
    """Monta mensagem de consulta já realizada."""
    return (
        f"📋 Sua última consulta registrada foi em {data_fmt} às {hora_fmt} "
        f"com {medico}.\n\n"
        "Quer agendar uma nova consulta? É só me dizer! 😊"
    )


def deve_responder_faq_consulta_marcada(
    ctx: Optional[dict],
    user_text: str,
) -> Optional[str]:
    """
    Retorna resposta formatada se paciente perguntar sobre consulta marcada
    E ctx.known.dia_consulta_iso estiver preenchido.

    Retorna None (fail-open) em qualquer outro caso.

    Toggle: FAQ_CONSULTA_MARCADA_ATIVADO=0 desliga.
    """
    if not _ATIVADO:
        return None

    try:
        if not user_text or not isinstance(user_text, str):
            return None

        # Detecta padrão de pergunta
        if not _RE_CONSULTA_QUANDO.search(user_text):
            return None

        if not ctx or not isinstance(ctx, dict):
            return None

        known = ctx.get("known") or {}
        iso_str = known.get("dia_consulta_iso")
        if not iso_str:
            # Sem data registrada no Kommo → LLM trata
            return None

        data_fmt, hora_fmt, is_passado = _formatar_data_hora(iso_str)
        medico = _extrair_medico(ctx)
        unidade = _extrair_unidade(ctx)

        if is_passado:
            return _montar_resposta_passada(data_fmt, hora_fmt, medico)
        else:
            return _montar_resposta_futura(data_fmt, hora_fmt, medico, unidade)

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-115] faq_consulta_marcada falhou (fail-open): %s", exc)
        return None
