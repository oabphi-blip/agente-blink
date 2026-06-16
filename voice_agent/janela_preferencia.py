"""Parser da preferência textual do paciente → janela de datas (request Medware).

Origem: Bug C-30 (Fábio 16/06/2026, lead Sofia 24158652). A paciente pediu
"entre 7 e 15 de julho", mas o pipeline SEMPRE consultava o Medware na janela
fixa amanhã→+90 dias e deixava o cruzamento da preferência por conta do LLM.
Resultado: o request nunca era específico, o log não dizia o que foi pedido, e
a Lia travava entre a "JANELA DE 5 DIAS ÚTEIS" do prompt e a agenda real de 90d.

Este módulo transforma o campo Kommo DIA/TURNO/PERÍODO (1259960 → known["dia_turno"])
numa janela concreta (data_inicio, data_fim) para virar um request ESPECÍFICO ao
Medware. Se não conseguir parsear com confiança, devolve None — o chamador cai no
default seguro de 90 dias (nunca regride).

Regras de design:
- Determinístico, sem dependência externa.
- Conservador: só devolve janela quando há confiança; caso contrário None.
- Inferência de ano: se o mês/dia resolvido já passou, assume o próximo ano.
- Clamp: data_inicio nunca antes de amanhã (não se agenda hoje/passado).
- Cap de segurança: janela máxima de 120 dias.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

# Janela máxima que aceitamos derivar da preferência (segurança).
_MAX_JANELA_DIAS = 120

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm(texto: str) -> str:
    """Minúsculo, sem acento, parentéticos removidos, espaços normalizados."""
    t = _strip_accents(texto or "").lower()
    t = re.sub(r"\([^)]*\)", " ", t)        # remove "(aguardando disponibilidade)"
    t = t.replace("º", " ").replace("°", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _resolver_ano(mes: int, dia: int, hoje: date) -> int:
    """Ano para (mes, dia): se a data já passou neste ano, usa o próximo."""
    try:
        candidato = date(hoje.year, mes, dia)
    except ValueError:
        return hoje.year
    return hoje.year if candidato >= hoje else hoje.year + 1


def _clamp(di: date, df: date, hoje: date) -> Optional[tuple[date, date]]:
    """Garante di <= df, di >= amanhã e janela <= _MAX_JANELA_DIAS."""
    if df < di:
        di, df = df, di
    amanha = hoje + timedelta(days=1)
    if df < amanha:
        return None                      # janela inteira no passado
    if di < amanha:
        di = amanha
    if (df - di).days > _MAX_JANELA_DIAS:
        df = di + timedelta(days=_MAX_JANELA_DIAS)
    return (di, df)


def parse_janela_preferencia(
    texto: str, hoje: Optional[date] = None
) -> Optional[tuple[date, date]]:
    """Converte a preferência textual numa janela (data_inicio, data_fim).

    Devolve None quando não há confiança suficiente — o chamador então usa
    o default de 90 dias. Nunca levanta exceção.
    """
    if hoje is None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    t = _norm(texto)
    if not t:
        return None
    meses_alt = "|".join(_MESES.keys())

    try:
        # 1) "entre 7 e 15 de julho" | "de 7 a 15 de julho" | "7 a 15 de julho"
        m = re.search(
            rf"(?:entre|de)?\s*(\d{{1,2}})\s*(?:e|a|ate|-|/)\s*(\d{{1,2}})\s*"
            rf"(?:de\s+)?({meses_alt})",
            t,
        )
        if m:
            d1, d2, mes_nome = int(m.group(1)), int(m.group(2)), m.group(3)
            mes = _MESES[mes_nome]
            ano = _resolver_ano(mes, min(d1, d2), hoje)
            try:
                di, df = date(ano, mes, min(d1, d2)), date(ano, mes, max(d1, d2))
                return _clamp(di, df, hoje)
            except ValueError:
                pass

        # 2) "entre 07/07 e 15/07" | "de 07/07 a 15/07" | "07/07 a 15/07"
        m = re.search(
            r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*(?:e|a|ate|-)\s*"
            r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?",
            t,
        )
        if m:
            d1, mo1 = int(m.group(1)), int(m.group(2))
            d2, mo2 = int(m.group(4)), int(m.group(5))
            a1 = _ano_de(m.group(3), mo1, d1, hoje)
            a2 = _ano_de(m.group(6), mo2, d2, hoje)
            try:
                return _clamp(date(a1, mo1, d1), date(a2, mo2, d2), hoje)
            except ValueError:
                pass

        # 3) "semana de 29/06" → 7 dias a partir da data
        m = re.search(r"semana\s+(?:de|do dia)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
        if m:
            d1, mo1 = int(m.group(1)), int(m.group(2))
            a1 = _ano_de(m.group(3), mo1, d1, hoje)
            try:
                di = date(a1, mo1, d1)
                return _clamp(di, di + timedelta(days=6), hoje)
            except ValueError:
                pass

        # 4) "semana de 7 de julho"
        m = re.search(rf"semana\s+(?:de|do dia)\s+(\d{{1,2}})\s+de\s+({meses_alt})", t)
        if m:
            d1, mes = int(m.group(1)), _MESES[m.group(2)]
            a1 = _resolver_ano(mes, d1, hoje)
            try:
                di = date(a1, mes, d1)
                return _clamp(di, di + timedelta(days=6), hoje)
            except ValueError:
                pass

        # 5) data única "dia 10/07" | "10/07/2026" | "10/07"
        m = re.search(r"(?:dia\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
        if m:
            d1, mo1 = int(m.group(1)), int(m.group(2))
            a1 = _ano_de(m.group(3), mo1, d1, hoje)
            try:
                d = date(a1, mo1, d1)
                return _clamp(d, d, hoje)
            except ValueError:
                pass

        # 6) data única por extenso "10 de julho" | "dia 10 de julho"
        m = re.search(rf"(?:dia\s+)?(\d{{1,2}})\s+de\s+({meses_alt})", t)
        if m:
            d1, mes = int(m.group(1)), _MESES[m.group(2)]
            a1 = _resolver_ano(mes, d1, hoje)
            try:
                d = date(a1, mes, d1)
                return _clamp(d, d, hoje)
            except ValueError:
                pass

        # 7) mês inteiro por extenso "em julho" | "no mes de julho"
        m = re.search(rf"\b(?:em|no mes de|mes de)\s+({meses_alt})\b", t)
        if m:
            mes = _MESES[m.group(1)]
            ano = _resolver_ano(mes, 1, hoje)
            try:
                di = date(ano, mes, 1)
                # último dia do mês
                if mes == 12:
                    df = date(ano, 12, 31)
                else:
                    df = date(ano, mes + 1, 1) - timedelta(days=1)
                return _clamp(di, df, hoje)
            except ValueError:
                pass

        # 8) expressões relativas
        if "proxima semana" in t or "semana que vem" in t:
            # próxima segunda a domingo
            dias_ate_seg = (7 - hoje.weekday()) % 7 or 7
            seg = hoje + timedelta(days=dias_ate_seg)
            return _clamp(seg, seg + timedelta(days=6), hoje)
        if "essa semana" in t or "esta semana" in t:
            dom = hoje + timedelta(days=(6 - hoje.weekday()))
            return _clamp(hoje + timedelta(days=1), dom, hoje)
        if "proximo mes" in t or "mes que vem" in t:
            mes = 1 if hoje.month == 12 else hoje.month + 1
            ano = hoje.year + 1 if hoje.month == 12 else hoje.year
            di = date(ano, mes, 1)
            df = (date(ano, 12, 31) if mes == 12
                  else date(ano, mes + 1, 1) - timedelta(days=1))
            return _clamp(di, df, hoje)
    except Exception:  # noqa: BLE001 — parser nunca derruba o pipeline
        return None

    return None


def _ano_de(grupo_ano: Optional[str], mes: int, dia: int, hoje: date) -> int:
    """Resolve o ano de uma data DD/MM[/AAAA]: usa o explícito, senão infere."""
    if grupo_ano:
        a = int(grupo_ano)
        return a + 2000 if a < 100 else a
    return _resolver_ano(mes, dia, hoje)
