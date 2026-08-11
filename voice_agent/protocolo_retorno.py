"""
Bug C-112 (11/08/2026) — Protocolo retorno pediátrico: bloquear oferta prematura.

Causa raiz: batch de campanhas (e Lia em conversa) ofertava agendamento sem verificar
se a Dra. Karla já havia definido uma janela de retorno. Resultado: atropelar protocolo
médico (Dra. Karla define retorno em consulta, Lia agenda antes da janela).

Caso real: lead 21545155 Maria Alice Alvarenga Peixoto (12a, oftalmopediatria).
Campo `1.MÊS PRÓX CONSULTA = "Maio 2027"`. Batch agendou mesmo assim.

Decisão arquitetural (P0):
  - Python verifica ANTES de ofertar: 1.MÊS PRÓX CONSULTA preenchido → bloqueio
  - Python verifica 1.DIA CONSULTA < janela mínima → bloqueio
  - Janela mínima por faixa etária: 0-2a = 6 meses; 3-12a = 12 meses; 13+ = 12 meses
  - Quando dentro da janela: mensagem educativa ("Dra. Karla programou seu retorno para X")
  - Fail-open: qualquer exceção → None (pipeline continua; LLM decide)

Toggle: PROTOCOLO_RETORNO_ATIVADO (default ON)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("PROTOCOLO_RETORNO_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# Janela mínima de retorno em dias por faixa etária
_JANELA_BEBE_DIAS = 180       # 0-2 anos: 6 meses
_JANELA_CRIANCA_DIAS = 365    # 3-12 anos: 12 meses
_JANELA_ADULTO_DIAS = 365     # 13+ anos: 12 meses

# Regex pra detectar mês/ano no campo 1.MÊS PRÓX CONSULTA
# Formatos aceitos: "Maio 2027", "05/2027", "2027-05", "maio/2027"
_RE_MES_ANO = re.compile(
    r"""
    (?:
        # "Maio 2027" ou "Maio/2027" ou "Maio de 2027"
        (?P<nome_mes>jan(?:eiro)?|fev(?:ereiro)?|mar(?:ço)?|abr(?:il)?|mai(?:o)?|
                     jun(?:ho)?|jul(?:ho)?|ago(?:sto)?|set(?:embro)?|out(?:ubro)?|
                     nov(?:embro)?|dez(?:embro)?)
        [\s/\-de]*
        (?P<ano1>\d{4})
    |
        # "05/2027" ou "05-2027"
        (?P<mes_num>\d{1,2})[/\-](?P<ano2>\d{4})
    |
        # "2027-05"
        (?P<ano3>\d{4})[/\-](?P<mes_num2>\d{1,2})
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def _parse_mes_ano(texto: str) -> Optional[date]:
    """Tenta extrair data (1° dia do mês) a partir de string de mês/ano."""
    if not texto:
        return None
    m = _RE_MES_ANO.search(texto.strip())
    if not m:
        return None
    try:
        if m.group("nome_mes"):
            mes_str = m.group("nome_mes").lower()[:3]
            mes = _MESES_PT.get(mes_str)
            ano = int(m.group("ano1"))
        elif m.group("mes_num"):
            mes = int(m.group("mes_num"))
            ano = int(m.group("ano2"))
        elif m.group("ano3"):
            ano = int(m.group("ano3"))
            mes = int(m.group("mes_num2"))
        else:
            return None
        if not (1 <= mes <= 12) or not (2020 <= ano <= 2035):
            return None
        return date(ano, mes, 1)
    except (ValueError, TypeError):
        return None


def _parse_data_iso(texto: str) -> Optional[date]:
    """Tenta parsear data ISO (YYYY-MM-DD) ou DD/MM/YYYY."""
    if not texto:
        return None
    # ISO
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _janela_minima_dias(idade_anos: Optional[int]) -> int:
    """Retorna janela mínima de retorno em dias por faixa etária."""
    if idade_anos is None:
        return _JANELA_ADULTO_DIAS
    if idade_anos <= 2:
        return _JANELA_BEBE_DIAS
    if idade_anos <= 12:
        return _JANELA_CRIANCA_DIAS
    return _JANELA_ADULTO_DIAS


def _formatar_mes_ano(d: date) -> str:
    """Formata date como 'Mês/AAAA' em português."""
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return f"{meses[d.month - 1]}/{d.year}"


def _formatar_data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def deve_bloquear_oferta_retorno(ctx: Optional[dict]) -> Optional[str]:
    """Verifica protocolo de retorno e retorna mensagem de bloqueio se aplicável.

    Lógica:
    1. `1.MÊS PRÓX CONSULTA` preenchido e ainda no futuro → bloqueia com data programada
    2. `1.DIA CONSULTA` < janela mínima atrás → bloqueia (muito cedo para retorno)
    3. Caso contrário → None (oferta pode prosseguir)

    Fail-open: qualquer exceção → None.
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        known = ctx.get("known") or {}
        hoje = date.today()

        # ── 1. 1.MÊS PRÓX CONSULTA preenchido → verificar se ainda está no futuro ──
        prox_mes_raw = (
            known.get("prox_consulta_mes")
            or known.get("mes_prox_consulta")
            or ctx.get("prox_consulta_mes")
            or _extrair_campo_kommo(ctx, "1.MÊS PRÓX CONSULTA", "prox_consulta_mes", "mes_prox_consulta")
        )
        if prox_mes_raw:
            prox_data = _parse_mes_ano(str(prox_mes_raw))
            if prox_data and prox_data > hoje:
                mes_fmt = _formatar_mes_ano(prox_data)
                nome = known.get("nome_paciente") or known.get("nome") or ""
                nome_parte = f" {nome.split()[0]}" if nome else ""
                return (
                    f"A Dra. Karla Delalíbera já programou o próximo retorno"
                    f"{nome_parte} para {mes_fmt}. 😊\n\n"
                    "Quando chegar a época, é só me chamar aqui e eu agendo direto! "
                    "Quer fazer algo mais por enquanto?"
                )

        # ── 2. 1.DIA CONSULTA < janela mínima atrás → muito cedo para retorno ──
        dia_consulta_raw = (
            known.get("dia_consulta")
            or known.get("data_consulta")
            or _extrair_campo_kommo(ctx, "1.DIA CONSULTA", "dia_consulta", "data_consulta")
        )
        if dia_consulta_raw:
            data_ultima = _parse_data_iso(str(dia_consulta_raw))
            if data_ultima and data_ultima < hoje:
                # Calcular idade do paciente para saber janela
                idade_anos: Optional[int] = known.get("idade_anos")
                if idade_anos is None:
                    data_nasc_raw = known.get("data_nasc") or known.get("data_nascimento")
                    if data_nasc_raw:
                        data_nasc = _parse_data_iso(str(data_nasc_raw))
                        if data_nasc:
                            idade_anos = (hoje - data_nasc).days // 365

                janela_dias = _janela_minima_dias(idade_anos)
                prox_retorno_esperado = data_ultima + timedelta(days=janela_dias)

                if prox_retorno_esperado > hoje:
                    # Consulta foi recente — dentro da janela mínima
                    data_fmt = _formatar_data_br(data_ultima)
                    prox_fmt = _formatar_data_br(prox_retorno_esperado)
                    nome = known.get("nome_paciente") or known.get("nome") or ""
                    nome_parte = f" {nome.split()[0]}" if nome else ""
                    faixa = "bebê" if (idade_anos is not None and idade_anos <= 2) else "paciente"
                    return (
                        f"A última consulta{nome_parte} foi em {data_fmt}. 😊\n\n"
                        f"O protocolo da Dra. Karla Delalíbera para {faixa} indica "
                        f"retorno a partir de {prox_fmt}. "
                        "Quando chegar a data, é só me chamar aqui para agendar!"
                    )

        return None

    except Exception as exc:
        log.warning("[C-112] deve_bloquear_oferta_retorno falhou (fail-open): %s", exc)
        return None


def _extrair_campo_kommo(ctx: dict, *nomes: str) -> Optional[str]:
    """Busca valor de campos Kommo em ctx por nome (case-insensitive).

    Percorre ctx.get("custom_fields_values") ou ctx.get("campos_kommo") buscando
    qualquer dos nomes fornecidos. Retorna o primeiro valor encontrado.
    """
    try:
        campos = ctx.get("custom_fields_values") or ctx.get("campos_kommo") or []
        for cf in campos:
            fn = (cf.get("field_name") or "").strip()
            for nome in nomes:
                if fn.lower() == nome.lower():
                    vals = cf.get("values") or []
                    if vals:
                        return str(vals[0].get("value") or "").strip() or None
    except Exception:
        pass
    return None


def enriquecer_ctx_protocolo_retorno(ctx: dict) -> None:
    """Step C-112 do enriquecimento_ctx: extrai campos de retorno do Kommo para known.

    Injeta em known:
      - prox_consulta_mes: valor de 1.MÊS PRÓX CONSULTA
      - dia_consulta: valor de 1.DIA CONSULTA
    Não sobrescreve se já preenchido.
    Fail-open.
    """
    try:
        known = ctx.get("known") or {}

        if not known.get("prox_consulta_mes"):
            val = _extrair_campo_kommo(ctx, "1.MÊS PRÓX CONSULTA", "prox_consulta_mes")
            if val:
                known["prox_consulta_mes"] = val

        if not known.get("dia_consulta"):
            val = _extrair_campo_kommo(ctx, "1.DIA CONSULTA", "dia_consulta")
            if val:
                known["dia_consulta"] = val

    except Exception as exc:
        log.warning("[C-112] enriquecer_ctx_protocolo_retorno falhou: %s", exc)
