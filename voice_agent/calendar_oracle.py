"""calendar_oracle.py — Helper canônico de datas pra Blink Oftalmologia.

Objetivo: eliminar o bug C-35 (Claude e Lia inventam dia da semana).
Fonte única de verdade pra qualquer pergunta tipo "18/06 é qual dia?" ou
"a Dra. Karla atende quinta em qual unidade?".

USO (Claude no Cowork ANTES de redigir nota/mensagem com data):
    python3 voice_agent/calendar_oracle.py validar 2026-06-18 karla
    -> {"dia": "Quinta-feira", "unidade_atende": "Águas Claras",
        "valido_para_oferta": true, "texto_pronto": "Quinta-feira (18/06) — Águas Claras"}

    python3 voice_agent/calendar_oracle.py proximas-datas karla asa_norte 4
    -> Lista as 4 próximas datas que Karla atende Asa Norte.

    python3 voice_agent/calendar_oracle.py gerar-oferta karla asa_norte 09:30 14:30
    -> Mensagem pronta com 2 slots reais pra colar no WhatsApp.

REGRA P0 (Claude operando Cowork): NUNCA escrever "X-feira (DD/MM)" em qualquer
texto sem rodar `validar` antes. Bug C-35 (17/06/2026) custou 12 notas erradas.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional


def _normalizar(s: str) -> str:
    """Lowercase + strip acentos pra comparação robusta."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()

# ---------------- Constantes Blink ----------------
DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
           "Sexta-feira", "Sábado", "Domingo"]

# Karla Delalíbera — atendimento por dia da semana
# seg=0, ter=1, qua=2, qui=3, sex=4, sab=5, dom=6
KARLA_AGENDA = {
    0: "Asa Norte",      # segunda
    2: "Asa Norte",      # quarta
    4: "Asa Norte",      # sexta
    1: "Águas Claras",   # terça
    3: "Águas Claras",   # quinta
    5: None,             # sábado (só encaixe especial, verificar com médica)
    6: None,             # domingo (não atende)
}

# Fabrício Freitas — terça e quinta (Águas Claras default; Asa Norte sob demanda)
FABRICIO_AGENDA = {
    1: "Águas Claras",
    3: "Águas Claras",
}

MEDICOS = {
    "karla": ("Dra. Karla Delalíbera", KARLA_AGENDA),
    "fabricio": ("Dr. Fabrício Freitas", FABRICIO_AGENDA),
}


# ---------------- Modelo de retorno ----------------
@dataclass
class DataInfo:
    data_iso: str
    data_br: str            # "18/06/2026"
    dia: str                # "Quinta-feira"
    dia_idx: int            # 0..6
    unidade_atende: Optional[str]
    valido_para_oferta: bool
    texto_pronto: str       # "Quinta-feira (18/06) — Águas Claras"
    motivo_invalido: Optional[str] = None


# ---------------- API canônica ----------------
def dia_semana(d: date) -> str:
    """Retorna 'Quinta-feira' pra date(2026,6,18)."""
    return DIAS_PT[d.weekday()]


def unidade_medico_em(d: date, medico: str = "karla") -> Optional[str]:
    """Retorna 'Águas Claras' se Karla atende lá em 18/06/2026."""
    medico = medico.lower().strip()
    if medico not in MEDICOS:
        raise ValueError(f"Médico desconhecido: {medico}. Use: {list(MEDICOS.keys())}")
    _, agenda = MEDICOS[medico]
    return agenda.get(d.weekday())


def validar(d: date, medico: str = "karla",
            unidade_pretendida: Optional[str] = None) -> DataInfo:
    """Valida que uma data é válida pra oferta de slot.

    Args:
        d: data a validar.
        medico: 'karla' ou 'fabricio'.
        unidade_pretendida: se eu QUERO ofertar em 'Asa Norte', valido que ela
            casa com o dia da semana. Se None, só retorna a unidade real.

    Returns:
        DataInfo com tudo necessário pra eu redigir o texto certo.
    """
    dia_str = dia_semana(d)
    dia_idx = d.weekday()
    unidade_real = unidade_medico_em(d, medico)
    data_br = d.strftime("%d/%m/%Y")
    medico_nome, _ = MEDICOS[medico.lower()]

    if unidade_real is None:
        return DataInfo(
            data_iso=d.isoformat(), data_br=data_br, dia=dia_str, dia_idx=dia_idx,
            unidade_atende=None, valido_para_oferta=False,
            texto_pronto=f"{dia_str} ({data_br}) — {medico_nome} NÃO atende",
            motivo_invalido=f"{dia_str} {medico_nome} não tem expediente rotineiro",
        )

    if unidade_pretendida and _normalizar(unidade_pretendida) not in _normalizar(unidade_real):
        return DataInfo(
            data_iso=d.isoformat(), data_br=data_br, dia=dia_str, dia_idx=dia_idx,
            unidade_atende=unidade_real, valido_para_oferta=False,
            texto_pronto=f"{dia_str} ({data_br}) — {medico_nome} atende {unidade_real}, NÃO {unidade_pretendida}",
            motivo_invalido=f"Em {dia_str}, {medico_nome} atende {unidade_real} (você pediu {unidade_pretendida})",
        )

    return DataInfo(
        data_iso=d.isoformat(), data_br=data_br, dia=dia_str, dia_idx=dia_idx,
        unidade_atende=unidade_real, valido_para_oferta=True,
        texto_pronto=f"{dia_str} ({data_br}) — {medico_nome} {unidade_real}",
        motivo_invalido=None,
    )


def proximas_datas_validas(unidade: str, medico: str = "karla",
                           qtde: int = 4, a_partir_de: Optional[date] = None) -> list[DataInfo]:
    """Lista as próximas N datas em que o médico atende a unidade pedida.

    Útil pra eu nunca chutar 'sexta 20/06' (sábado) ou 'quarta 24/06 Águas Claras' (Asa Norte).
    """
    if a_partir_de is None:
        a_partir_de = date.today()
    saidas: list[DataInfo] = []
    d = a_partir_de
    iteracoes = 0
    while len(saidas) < qtde and iteracoes < 60:
        info = validar(d, medico, unidade)
        if info.valido_para_oferta:
            saidas.append(info)
        d = d + timedelta(days=1)
        iteracoes += 1
    return saidas


def gerar_oferta_2_slots(medico: str, unidade: str,
                         horarios_preferidos: list[str],
                         a_partir_de: Optional[date] = None) -> str:
    """Gera texto pronto com 2 slots reais pra colar no WhatsApp.

    Args:
        medico: 'karla'.
        unidade: 'asa norte' ou 'aguas claras'.
        horarios_preferidos: ['09:30', '14:30'] — vai aplicar ao 1º e 2º slot.

    Returns:
        Texto pronto. Ex.:
        "1️⃣ Sexta-feira (19/06) às 09:30
         2️⃣ Segunda-feira (22/06) às 14:30"
    """
    if len(horarios_preferidos) < 2:
        horarios_preferidos = (horarios_preferidos + ["09:30", "14:30"])[:2]
    datas = proximas_datas_validas(unidade, medico, qtde=2, a_partir_de=a_partir_de)
    if len(datas) < 2:
        return f"⚠️ Não há 2 datas disponíveis em {unidade} nos próximos 60 dias."
    return (
        f"1️⃣ {datas[0].dia} ({datas[0].data_br[:5]}) às {horarios_preferidos[0]}\n"
        f"2️⃣ {datas[1].dia} ({datas[1].data_br[:5]}) às {horarios_preferidos[1]}"
    )


def tabela_120_dias(a_partir_de: Optional[date] = None) -> str:
    """Tabela markdown com 120 dias × (Karla unidade, Fabrício unidade).

    Útil pra injetar no CLAUDE.md no topo. Claude lê visualmente e nunca chuta.
    """
    if a_partir_de is None:
        a_partir_de = date.today()
    linhas = ["| Data | Dia | Karla | Fabrício |", "|---|---|---|---|"]
    for i in range(120):
        d = a_partir_de + timedelta(days=i)
        k = unidade_medico_em(d, "karla") or "—"
        f = unidade_medico_em(d, "fabricio") or "—"
        dia = dia_semana(d)
        linhas.append(f"| {d.strftime('%d/%m/%Y')} | {dia} | {k} | {f} |")
    return "\n".join(linhas)


# ---------------- CLI ----------------
def _parse_data(s: str) -> date:
    """Aceita 'YYYY-MM-DD', 'DD/MM/YYYY', 'DD/MM' (assume ano atual)."""
    s = s.strip()
    if "-" in s:
        return date.fromisoformat(s)
    if "/" in s:
        partes = s.split("/")
        if len(partes) == 2:
            partes.append(str(date.today().year))
        d, m, y = partes
        return date(int(y), int(m), int(d))
    raise ValueError(f"Data inválida: {s}")


def _cli():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "validar":
        d = _parse_data(sys.argv[2])
        medico = sys.argv[3] if len(sys.argv) > 3 else "karla"
        unidade = sys.argv[4] if len(sys.argv) > 4 else None
        info = validar(d, medico, unidade)
        print(json.dumps(asdict(info), ensure_ascii=False, indent=2))

    elif cmd == "proximas-datas":
        medico = sys.argv[2]
        unidade = sys.argv[3].replace("_", " ")
        qtde = int(sys.argv[4]) if len(sys.argv) > 4 else 4
        datas = proximas_datas_validas(unidade, medico, qtde=qtde)
        for info in datas:
            print(info.texto_pronto)

    elif cmd == "gerar-oferta":
        medico = sys.argv[2]
        unidade = sys.argv[3].replace("_", " ")
        h1 = sys.argv[4] if len(sys.argv) > 4 else "09:30"
        h2 = sys.argv[5] if len(sys.argv) > 5 else "14:30"
        print(gerar_oferta_2_slots(medico, unidade, [h1, h2]))

    elif cmd == "tabela-120":
        print(tabela_120_dias())

    elif cmd == "tabela-30":
        print(tabela_120_dias(a_partir_de=date.today())[:1900])  # truncado

    else:
        print(f"Comando desconhecido: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
