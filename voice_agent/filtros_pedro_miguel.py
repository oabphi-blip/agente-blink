"""Filtros pós-geração pros 2 bugs recorrentes do lead Pedro Miguel 24102510.

Origem: Fábio 04/06/2026 — 2 bugs detectados em conversa real:

**Bug #226 — Cronologia errada:**
  Pedro pediu "dia 29 segunda". Lia ofereceu D+30 (30/06) e D+02/07
  ignorando quinta 11/06 (D+7) que tinha 7 vacâncias na agenda.
  Regra: sempre ofertar SLOT MAIS PRÓXIMO cronologicamente que case
  com preferência, mesmo que não seja o "dia 29" exato.

**Bug #224 — Ignorou pergunta conceitual:**
  Pedro perguntou "o que é convênio?". Lia respondeu "qual é o nome
  do seu convênio?" — ignorou a dúvida.
  Regra: paciente pergunta "o que é X" / "como funciona X" /
  "não entendi" → EXPLICAR primeiro, depois retomar coleta.

Ambos os filtros são sempre-on (não dependem de FILTROS_LEGACY).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional


# Fuso Brasília
_TZ_BR = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Bug #226 — Cronologia: detecta oferta de data DISTANTE quando há mais próxima
# ---------------------------------------------------------------------------

# Captura "30/06", "02/07", "30/06/2026" etc.
_RE_DATA_OFERECIDA = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?!\d)",
)

# Captura "1️⃣" / "2️⃣" / "1." pra detectar oferta de slot
_RE_FORMATO_OFERTA = re.compile(
    r"(?:1⃣|2⃣|1º|2º|1\.|2\.|primeira|segunda)",
    re.IGNORECASE,
)


def _parse_data(dia: int, mes: int, ano: int | None = None) -> datetime | None:
    """Constrói datetime BRT a partir de (dia, mês, ano opcional).

    Se ano omitido, infere: usa ano corrente; se mês já passou no ano
    corrente, usa próximo ano.
    """
    hoje = datetime.now(_TZ_BR)
    try:
        if ano:
            if ano < 100:
                ano += 2000
        else:
            ano = hoje.year
            # se data já passou neste ano, considera próximo
            try:
                cand = datetime(ano, mes, dia, tzinfo=_TZ_BR)
                if cand < hoje - timedelta(days=7):
                    ano += 1
            except ValueError:
                return None
        return datetime(ano, mes, dia, tzinfo=_TZ_BR)
    except (ValueError, TypeError):
        return None


def extrair_datas_oferecidas(text: str) -> list[datetime]:
    """Devolve lista de datas (datetime BRT) detectadas no texto."""
    if not text:
        return []
    out: list[datetime] = []
    for m in _RE_DATA_OFERECIDA.finditer(text):
        d, mes, ano = m.group(1), m.group(2), m.group(3)
        try:
            dt = _parse_data(int(d), int(mes), int(ano) if ano else None)
        except (ValueError, TypeError):
            continue
        if dt:
            out.append(dt)
    return out


def menor_data_na_agenda(agenda: list) -> datetime | None:
    """Olha ctx.agenda (lista de slots Medware) e devolve a data mais
    próxima disponível, em formato datetime BRT.

    Slots têm campos tipo `dia_iso`, `data`, `data_iso`, ou um string
    ISO formato `YYYY-MM-DD HH:MM:SS`. Tolerante a múltiplos formatos.
    """
    if not agenda:
        return None
    datas: list[datetime] = []
    for slot in agenda:
        if not isinstance(slot, dict):
            continue
        # Tenta várias chaves
        for chave in ("dia_iso", "data_iso", "data", "dia"):
            v = slot.get(chave)
            if not v:
                continue
            try:
                if isinstance(v, str):
                    # Aceita "2026-06-11" ou "2026-06-11 14:30:00"
                    dt = datetime.fromisoformat(v[:10])
                    dt = dt.replace(tzinfo=_TZ_BR)
                    datas.append(dt)
                    break
                elif isinstance(v, (int, float)):
                    dt = datetime.fromtimestamp(int(v), tz=_TZ_BR)
                    datas.append(dt)
                    break
            except (ValueError, TypeError):
                continue
    if not datas:
        return None
    return min(datas)


def _viola_data_distante(
    text: str, ctx: Optional[dict] = None,
    limite_dias_aceitavel: int = 10,
) -> bool:
    """True se Lia ofereceu data MUITO MAIS DISTANTE que slot disponível.

    Regra: se a data mais próxima da agenda real está dentro de
    `limite_dias_aceitavel` dias E Lia ofereceu data que está
    `>= limite_dias_aceitavel + 7` dias DEPOIS da agenda mais próxima
    → bug cronológico, substitui.

    Origem: lead 24102510 Pedro Miguel. Quinta 11/06 (7 slots livres
    Karla Asa Norte tarde) ignorada — ofereceu D+30 (30/06).
    """
    if not text or not ctx:
        return False
    agenda = ctx.get("agenda") or []
    if not agenda:
        return False
    mais_proxima = menor_data_na_agenda(agenda)
    if not mais_proxima:
        return False
    hoje = datetime.now(_TZ_BR)
    dias_ate_mais_proxima = (mais_proxima - hoje).days
    if dias_ate_mais_proxima > limite_dias_aceitavel:
        # Nem a agenda tem slot próximo — não pode reclamar do Lia.
        return False
    # Olha o que Lia ofereceu
    datas_ofertadas = extrair_datas_oferecidas(text)
    if not datas_ofertadas:
        return False
    # Pega a MENOR data oferecida
    menor_ofertada = min(datas_ofertadas)
    # Diff: quão mais distante a oferta está do slot real mais próximo?
    diff_dias = (menor_ofertada - mais_proxima).days
    return diff_dias >= limite_dias_aceitavel


def _gerar_oferta_mais_proxima(ctx: Optional[dict]) -> str:
    """Fallback educado oferecendo a data mais próxima da agenda real."""
    if not ctx:
        return (
            "Deixa eu reconsultar a agenda real aqui — volto em 1 minutinho "
            "com os horários mais próximos."
        )
    agenda = ctx.get("agenda") or []
    if not agenda:
        return (
            "Deixa eu reconsultar a agenda aqui — volto em 1 minuto com "
            "os horários mais próximos disponíveis."
        )
    mais_proxima = menor_data_na_agenda(agenda)
    if not mais_proxima:
        return (
            "Deixa eu reconsultar a agenda aqui — volto em 1 minuto com "
            "os horários mais próximos disponíveis."
        )
    # Texto humanizado
    dia_str = mais_proxima.strftime("%d/%m")
    return (
        f"Achei aqui — tenho horários disponíveis a partir de **{dia_str}**. "
        "Vou te passar 2 opções concretas, me confirma qual fica melhor?"
    )


# ---------------------------------------------------------------------------
# Bug #224 — Pergunta conceitual ignorada
# ---------------------------------------------------------------------------

# Detecta na MENSAGEM DO PACIENTE padrão de pergunta conceitual
_RE_PERGUNTA_CONCEITUAL = re.compile(
    r"(?ix)\b(?:"
    r"o\s+que\s+(?:é|eh|sao|seriam?)\s+\w+"
    r"|como\s+funciona"
    r"|n[aã]o\s+(?:entendi|sei\s+(?:o\s+que|como))"
    r"|me\s+explica"
    r"|n[aã]o\s+entendo"
    r"|isso\s+(?:significa|quer\s+dizer)"
    r"|qual\s+(?:a\s+)?diferen[cç]a"
    r")\b",
)

# Mapa de conceitos → explicação curta
_EXPLICACOES_CONCEITOS = {
    "convenio": (
        "Convênio é o plano de saúde — tipo Saúde Caixa, Cassi, TRF, "
        "Sul América, etc. Se você tem um plano, costuma cobrir a "
        "consulta. Se não tem, é particular (paga direto à clínica). "
    ),
    "convênio": None,  # alias
    "sinal": (
        "Sinal é um valor pago antecipado pra reservar a vaga — metade "
        "do valor da consulta. Ele evita que outra pessoa pegue o seu "
        "horário e, se você comparecer, é deduzido do valor total. "
    ),
    "pix": (
        "Pix é a forma de pagamento — transferência instantânea pelo "
        "banco. Te passo a chave depois de confirmar o slot. "
    ),
    "particular": (
        "Particular significa pagar direto à clínica, sem usar plano de "
        "saúde. Os valores estão na tabela. "
    ),
    "rotina": (
        "Rotina é a consulta de check-up — pra ver se está tudo OK, sem "
        "queixa específica. "
    ),
}


def detectar_pergunta_conceitual(text_paciente: str) -> str | None:
    """Recebe a última mensagem do paciente. Se contém padrão de pergunta
    conceitual, devolve o CONCEITO perguntado (palavra-chave) ou None.
    """
    if not text_paciente:
        return None
    if not _RE_PERGUNTA_CONCEITUAL.search(text_paciente):
        return None
    txt = text_paciente.lower()
    for conceito in _EXPLICACOES_CONCEITOS:
        if conceito in txt and _EXPLICACOES_CONCEITOS[conceito]:
            return conceito
    return None


def _viola_ignorar_pergunta_conceitual(
    text_lia: str, ctx: Optional[dict] = None,
) -> tuple[bool, str | None]:
    """True + conceito se paciente perguntou "o que é X" e Lia ignorou.

    Lia "ignorou" = na resposta dela NÃO há trecho que explique o conceito
    (heurística: palavra do conceito NÃO aparece OU resposta é < 30 chars
    e contém só pergunta).
    """
    if not text_lia or not ctx:
        return False, None
    ultima_msg = ctx.get("user_text") or ctx.get("ultima_msg_paciente") or ""
    conceito = detectar_pergunta_conceitual(ultima_msg)
    if not conceito:
        return False, None
    explicacao = _EXPLICACOES_CONCEITOS.get(conceito) or ""
    if not explicacao:
        return False, None
    # Resposta tem alguma palavra-chave da explicação?
    palavras_chave = [
        p.lower().strip(".,;:!?")
        for p in explicacao.split()
        if len(p) >= 5
    ][:3]
    if not palavras_chave:
        return True, conceito
    texto_norm = text_lia.lower()
    explicou = any(pc in texto_norm for pc in palavras_chave)
    return (not explicou), conceito


def _gerar_explicacao_e_retoma(
    conceito: str, ctx: Optional[dict] = None,
) -> str:
    """Devolve resposta que EXPLICA o conceito + faz pergunta de retomada."""
    explicacao = _EXPLICACOES_CONCEITOS.get(conceito) or ""
    if not explicacao:
        return (
            "Boa pergunta! Vou te explicar rapidinho e seguimos. "
            "Me diz: você tem algum plano de saúde, ou prefere particular?"
        )
    return (
        f"{explicacao}\n\n"
        "E aí, você tem ou prefere particular?"
    )
