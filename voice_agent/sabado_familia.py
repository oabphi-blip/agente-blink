"""Bug C-70 — Sábado Família determinístico (Fábio 14/08/2026).

Regra canônica INVIOLÁVEL:
    - Águas Claras: ÚLTIMO sábado do mês corrente
    - Asa Norte:    PENÚLTIMO sábado do mês corrente

Origem: Fábio 14/08/2026 P0 — "criar norma deterministica python que agenda no
sabado do mes corrente em Aguas Claras. E penultimo sabado do mes corrente na
Asa Norte. Obrigatoria converter esta resposta canonica deterministica."

Motivação: Lia estava inventando sábados (15/08, 22/08, 27/08, etc) sem regra
oficial. Paciente Karina Lícia 23469368 recebeu 6+ mensagens diferentes com
sábados inventados. Corrigido criando fonte de verdade Python.

Uso:
    from voice_agent.sabado_familia import sabado_familia_do_mes, deve_ofertar_sabado

    # Retorna date object do sábado família de agosto/2026 em Águas Claras
    d = sabado_familia_do_mes(2026, 8, unidade="Águas Claras")
    # -> date(2026, 8, 29)

    # Retorna date object do sábado família em Asa Norte
    d = sabado_familia_do_mes(2026, 8, unidade="Asa Norte")
    # -> date(2026, 8, 22)

    # Bypass: paciente perguntou "sábado" — devolve resposta canônica
    resp = deve_ofertar_sabado(ctx, user_text)
"""
from __future__ import annotations

import calendar
import os
import re
from datetime import date, datetime
from typing import Any, Optional


# ═════════════════════════════════════════════════════════════════════════
# Núcleo determinístico (sem dependência externa)
# ═════════════════════════════════════════════════════════════════════════

def _sabados_do_mes(ano: int, mes: int) -> list[date]:
    """Retorna lista ordenada de datas dos sábados do mês (weekday=5)."""
    n_dias = calendar.monthrange(ano, mes)[1]
    return [
        date(ano, mes, dia)
        for dia in range(1, n_dias + 1)
        if date(ano, mes, dia).weekday() == 5  # 5 = sábado
    ]


def sabado_familia_do_mes(
    ano: int, mes: int, unidade: str
) -> Optional[date]:
    """Retorna a data canônica do sábado família de {unidade} no mês {ano}/{mes}.

    Regra:
        - Águas Claras → último sábado
        - Asa Norte    → penúltimo sábado

    Retorna None se unidade desconhecida OU se penúltimo sábado não existe
    (mês com apenas 1 sábado — teoricamente impossível pois todo mês tem 4+).
    """
    unidade_n = (unidade or "").strip().lower()
    sabados = _sabados_do_mes(ano, mes)

    if not sabados:
        return None

    if "águas claras" in unidade_n or "aguas claras" in unidade_n:
        return sabados[-1]  # último sábado

    if "asa norte" in unidade_n:
        if len(sabados) < 2:
            return None
        return sabados[-2]  # penúltimo sábado

    return None


def proximo_sabado_familia(
    hoje: date, unidade: str
) -> Optional[date]:
    """Retorna o próximo sábado família válido (>= hoje).

    Se o sábado família do mês corrente já passou, avança pra o mês seguinte.
    Nunca retorna data no passado.
    """
    d_mes = sabado_familia_do_mes(hoje.year, hoje.month, unidade)
    if d_mes is not None and d_mes >= hoje:
        return d_mes

    # Sábado do mês corrente já passou — vai pro mês seguinte
    ano_prox = hoje.year + (1 if hoje.month == 12 else 0)
    mes_prox = 1 if hoje.month == 12 else hoje.month + 1
    return sabado_familia_do_mes(ano_prox, mes_prox, unidade)


# ═════════════════════════════════════════════════════════════════════════
# Formatação de data PT-BR
# ═════════════════════════════════════════════════════════════════════════

_MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def formatar_sabado_pt(d: date) -> str:
    """Formata data como 'sábado (DD/MM)'."""
    return f"sábado ({d.strftime('%d/%m')})"


# ═════════════════════════════════════════════════════════════════════════
# Bypass conversacional
# ═════════════════════════════════════════════════════════════════════════

_RE_PACIENTE_QUER_SABADO = re.compile(
    r"\b(?:s[áa]bad[oa]s?|sabado)\b",
    re.IGNORECASE,
)

_RE_NEGACAO = re.compile(
    r"\b(?:n[ãa]o\s+quero|n[ãa]o\s+posso|n[ãa]o\s+d[áa]|n[ãa]o\s+consigo)"
    r"\s+(?:no\s+)?s[áa]bad",
    re.IGNORECASE,
)


def _ativado() -> bool:
    """Toggle env — default ON."""
    return (os.environ.get("SABADO_FAMILIA_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off", ""
    )


def _extrair_unidade(ctx: Any) -> Optional[str]:
    """Extrai unidade do ctx.known de forma tolerante."""
    if ctx is None:
        return None
    known = getattr(ctx, "known", None) or {}
    if isinstance(ctx, dict):
        known = ctx.get("known") or ctx
    u = known.get("unidade") or known.get("UNIDADE") or ""
    return u.strip() if u else None


def _extrair_nome(ctx: Any) -> str:
    """Extrai nome do contato (primeiro nome) do ctx.known."""
    if ctx is None:
        return ""
    known = getattr(ctx, "known", None) or {}
    if isinstance(ctx, dict):
        known = ctx.get("known") or ctx
    nome = (
        known.get("nome_contato")
        or known.get("nome_paciente")
        or known.get("nome")
        or ""
    )
    return (nome.split()[0] if nome else "").strip()


def deve_ofertar_sabado(
    ctx: Any,
    user_text: str,
    hoje: Optional[date] = None,
) -> Optional[str]:
    """Bypass: se paciente pediu sábado E temos unidade, retorna resposta canônica.

    Retorna None (fail-open) quando:
        - Toggle desligado
        - Paciente NÃO mencionou sábado
        - Ctx sem unidade → não podemos calcular sábado família
        - Paciente NEGOU sábado ("não quero sábado")

    Retorna string com oferta canônica quando temos condições pra responder.
    """
    if not _ativado():
        return None

    if not user_text or not _RE_PACIENTE_QUER_SABADO.search(user_text):
        return None

    if _RE_NEGACAO.search(user_text):
        return None

    unidade = _extrair_unidade(ctx)
    if not unidade:
        return None

    if hoje is None:
        hoje = date.today()

    d = proximo_sabado_familia(hoje, unidade)
    if d is None:
        return None

    nome = _extrair_nome(ctx)
    saud = f"{nome}, " if nome else ""

    # Resposta canônica — sem inventar horário, sem mais alternativas
    unidade_display = (
        "Águas Claras"
        if "águas" in unidade.lower() or "aguas" in unidade.lower()
        else "Asa Norte"
    )
    data_pt = formatar_sabado_pt(d)

    return (
        f"{saud}o sábado família em {unidade_display} deste mês é "
        f"{data_pt}.\n\n"
        f"Vou verificar os horários exatos disponíveis nessa data e "
        f"te retorno em instantes."
    )


# ═════════════════════════════════════════════════════════════════════════
# Uso CLI (debug rápido)
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        hoje = date.today()
        print(f"Hoje: {hoje} ({hoje.strftime('%A')})")
        print()
        for uni in ("Águas Claras", "Asa Norte"):
            d = proximo_sabado_familia(hoje, uni)
            if d:
                print(f"  {uni}: {formatar_sabado_pt(d)}  ({d.strftime('%A')})")
        sys.exit(0)

    # sabado_familia.py 2026 8 "Águas Claras"
    ano, mes, unidade = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    d = sabado_familia_do_mes(ano, mes, unidade)
    if d:
        print(f"{unidade} {_MESES_PT[mes]}/{ano}: {formatar_sabado_pt(d)}")
    else:
        print(f"ERRO: unidade desconhecida ou sem sábado família")
