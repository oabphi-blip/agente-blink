"""blink-calendar — Servidor MCP que elimina o Bug C-35.

Encapsula `voice_agent/calendar_oracle.py` em interface MCP padronizada.
Qualquer cliente MCP (Claude Desktop, Cursor, Zed, Host orquestrador) pode
chamar este servidor para validar datas, listar próximas disponibilidades
e gerar oferta canônica pronta para WhatsApp.

Princípios do livro aplicados:
- 1.1.1: servidor como driver — UMA fonte de conhecimento (calendário).
- 1.2.1: Recursos para leitura passiva (medicos://lista, agenda://karla).
- 1.2.2: Ferramentas para ações (validar, listar, gerar).
- 3.7: docstrings ricos = LLM entende.
- 6.1: logs para stderr, NUNCA print.
- 6.5: Pydantic estrito = sem alucinação de argumento.

USO STANDALONE:
    uv run python -m blink_calendar.server

USO COM INSPECTOR:
    npx @modelcontextprotocol/inspector uv run python -m blink_calendar.server

USO COM CLAUDE DESKTOP:
    Ver mcp_servers/README.md
"""
from __future__ import annotations

import logging
import sys
import unicodedata
from datetime import date, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP

from blink_calendar.models import (
    DataInfoOutput,
    GerarOfertaInput,
    OfertaProntaOutput,
    ProximasDatasInput,
    ValidarDataInput,
)

# Livro 6.1: logs SEMPRE para stderr, NUNCA print.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-calendar - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-calendar")


# ─── Constantes Blink (fonte única de verdade) ──────────────────────
DIAS_PT = [
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
]

KARLA_AGENDA: dict[int, Optional[str]] = {
    0: "Asa Norte",      # segunda
    1: "Águas Claras",   # terça
    2: "Asa Norte",      # quarta
    3: "Águas Claras",   # quinta
    4: "Asa Norte",      # sexta
    5: None,             # sábado — só encaixe especial
    6: None,             # domingo — não atende
}

FABRICIO_AGENDA: dict[int, Optional[str]] = {
    1: "Águas Claras",   # terça
    3: "Águas Claras",   # quinta
}

MEDICOS: dict[str, tuple[str, dict[int, Optional[str]]]] = {
    "karla": ("Dra. Karla Delalíbera", KARLA_AGENDA),
    "fabricio": ("Dr. Fabrício Freitas", FABRICIO_AGENDA),
}


def _normalizar(s: str) -> str:
    """lowercase + strip acentos para comparação robusta de unidades."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


# ─── Instância do servidor MCP ──────────────────────────────────────
mcp = FastMCP("blink-calendar")


# ─── TOOLS ──────────────────────────────────────────────────────────

@mcp.tool()
def validar_data_unidade(
    data: str,
    medico: str = "karla",
    unidade_pretendida: Optional[str] = None,
) -> dict:
    """Valida data + médico + unidade ANTES de ofertar slot ao paciente.

    Use esta ferramenta SEMPRE que precisar mencionar uma data
    específica em mensagem ao paciente ou nota Kommo. Ela protege
    contra o Bug C-35 (Claude inventou dia da semana em 12 notas).

    Args:
        data: Data no formato ISO YYYY-MM-DD. Ex: "2026-06-29".
        medico: "karla" ou "fabricio" (case-insensitive). Default karla.
        unidade_pretendida: "Asa Norte" ou "Águas Claras". Se passar,
            valida que o médico atende essa unidade nesse dia. Se None,
            apenas verifica se o dia tem atendimento.

    Returns:
        Dict com:
            - data_iso, data_br, dia (Quinta-feira etc.)
            - unidade_atende: unidade real do médico naquele dia (ou None)
            - valido_para_oferta: True/False
            - texto_pronto: pronto para colar em nota/WhatsApp
            - motivo_invalido: explicação se inválido

    Exemplo:
        validar_data_unidade("2026-06-18", "karla", "Asa Norte")
        -> {"dia": "Quinta-feira", "unidade_atende": "Águas Claras",
            "valido_para_oferta": False,
            "motivo_invalido": "Karla atende Águas Claras nessa quinta, não Asa Norte"}
    """
    # Validação Pydantic explícita (livro 6.5)
    inp = ValidarDataInput(data=data, medico=medico, unidade_pretendida=unidade_pretendida)
    log.info("validar_data_unidade input=%s", inp.model_dump())

    d = inp.data
    if inp.medico not in MEDICOS:
        raise ValueError(
            f"Médico desconhecido: {inp.medico}. Use 'karla' ou 'fabricio'."
        )

    nome_completo, agenda = MEDICOS[inp.medico]
    dia_idx = d.weekday()
    dia_nome = DIAS_PT[dia_idx]
    unidade_real = agenda.get(dia_idx)

    valido = True
    motivo = None

    if unidade_real is None:
        valido = False
        motivo = (
            f"{nome_completo} NÃO atende em {dia_nome.lower()}s. "
            f"Dias de atendimento: {sorted(k for k, v in agenda.items() if v)}"
        )
    elif inp.unidade_pretendida is not None:
        if _normalizar(inp.unidade_pretendida) != _normalizar(unidade_real):
            valido = False
            motivo = (
                f"{nome_completo} atende {unidade_real} nessa {dia_nome.lower()}, "
                f"NÃO {inp.unidade_pretendida}."
            )

    texto_pronto = (
        f"{dia_nome} ({d.strftime('%d/%m')}) — {unidade_real}"
        if unidade_real else
        f"{dia_nome} ({d.strftime('%d/%m')}) — {nome_completo} NÃO ATENDE"
    )

    out = DataInfoOutput(
        data_iso=d.isoformat(),
        data_br=d.strftime("%d/%m/%Y"),
        dia=dia_nome,
        dia_idx=dia_idx,
        unidade_atende=unidade_real,
        valido_para_oferta=valido,
        texto_pronto=texto_pronto,
        motivo_invalido=motivo,
    )
    return out.model_dump()


@mcp.tool()
def proximas_datas_disponiveis(
    medico: str = "karla",
    unidade: str = "Asa Norte",
    n: int = 4,
    a_partir_de: Optional[str] = None,
) -> list[dict]:
    """Lista próximas N datas em que o médico atende a unidade indicada.

    Use para mostrar à equipe humana quais são as próximas oportunidades
    de slot, sem precisar consultar o Medware. Útil para campanhas e
    para confirmação rápida de "qual a próxima quarta da Karla na Asa Norte?".

    Args:
        medico: "karla" ou "fabricio". Default karla.
        unidade: "Asa Norte" ou "Águas Claras".
        n: Quantas datas retornar. Min 1, max 20. Default 4.
        a_partir_de: Data inicial ISO YYYY-MM-DD. Default hoje.

    Returns:
        Lista de dicts {data_iso, data_br, dia, unidade}. Ordenada
        cronologicamente.

    Exemplo:
        proximas_datas_disponiveis("karla", "Asa Norte", 3)
        -> [
            {"data_iso": "2026-06-22", "data_br": "22/06/2026",
             "dia": "Segunda-feira", "unidade": "Asa Norte"},
            ...
        ]
    """
    inp = ProximasDatasInput(medico=medico, unidade=unidade, n=n)
    log.info("proximas_datas_disponiveis input=%s a_partir_de=%s", inp.model_dump(), a_partir_de)

    if inp.medico not in MEDICOS:
        raise ValueError(f"Médico desconhecido: {inp.medico}")
    _, agenda = MEDICOS[inp.medico]

    start = date.fromisoformat(a_partir_de) if a_partir_de else date.today()
    alvo_normalizado = _normalizar(inp.unidade)

    resultado = []
    cursor = start
    # Buscar até 90 dias à frente; safety guard contra loop infinito
    for _ in range(90):
        unidade_real = agenda.get(cursor.weekday())
        if unidade_real and _normalizar(unidade_real) == alvo_normalizado:
            resultado.append({
                "data_iso": cursor.isoformat(),
                "data_br": cursor.strftime("%d/%m/%Y"),
                "dia": DIAS_PT[cursor.weekday()],
                "unidade": unidade_real,
            })
            if len(resultado) >= inp.n:
                break
        cursor += timedelta(days=1)

    return resultado


@mcp.tool()
def gerar_oferta_pronta(
    medico: str = "karla",
    unidade: str = "Asa Norte",
    hora1: str = "09:30",
    hora2: str = "14:30",
    nome_paciente: Optional[str] = None,
) -> dict:
    """Gera mensagem canônica 1️⃣/2️⃣ pronta para colar no WhatsApp.

    Pega as 2 próximas datas em que o médico atende a unidade, combina
    com as horas informadas, e retorna mensagem formatada. Garante
    coerência data × dia × unidade (Bug C-35 impossível).

    Args:
        medico: "karla" ou "fabricio". Default karla.
        unidade: "Asa Norte" ou "Águas Claras".
        hora1: Hora do primeiro slot. Formato HH:MM. Ex: "09:30".
        hora2: Hora do segundo slot. Formato HH:MM. Ex: "14:30".
        nome_paciente: Primeiro nome para personalizar saudação. Opcional.

    Returns:
        Dict com mensagem (texto pronto), datas e dias usados.

    Exemplo:
        gerar_oferta_pronta("karla", "Asa Norte", "09:00", "14:30", "Maria")
        -> {"mensagem": "Maria, tenho estes horários com a Dra. Karla...
                         1️⃣ Segunda-feira (22/06) às 09:00
                         2️⃣ Quarta-feira (24/06) às 14:30
                         Qual prefere?", ...}
    """
    inp = GerarOfertaInput(
        medico=medico, unidade=unidade,
        hora1=hora1, hora2=hora2, nome_paciente=nome_paciente,
    )
    log.info("gerar_oferta_pronta input=%s", inp.model_dump())

    proximas = proximas_datas_disponiveis(
        medico=inp.medico, unidade=inp.unidade, n=2,
    )
    if len(proximas) < 2:
        raise ValueError(
            f"Não foi possível encontrar 2 datas disponíveis para "
            f"{inp.medico} em {inp.unidade}. Verifique a agenda."
        )

    d1, d2 = proximas[0], proximas[1]
    nome_med, _ = MEDICOS[inp.medico]

    saudacao = (
        f"{inp.nome_paciente}! "
        if inp.nome_paciente else
        ""
    )

    mensagem = (
        f"{saudacao}Tenho estes horários com a {nome_med} na {inp.unidade}:\n\n"
        f"1️⃣ {d1['dia']} ({d1['data_br'][:5]}) às {inp.hora1}\n"
        f"2️⃣ {d2['dia']} ({d2['data_br'][:5]}) às {inp.hora2}\n\n"
        f"Qual prefere?"
    )

    out = OfertaProntaOutput(
        mensagem=mensagem,
        data1_iso=d1["data_iso"],
        data2_iso=d2["data_iso"],
        data1_br=d1["data_br"],
        data2_br=d2["data_br"],
        dia1=d1["dia"],
        dia2=d2["dia"],
    )
    return out.model_dump()


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("calendar://medicos")
def listar_medicos() -> str:
    """Lista completa dos médicos da Blink com agenda semanal.

    Recurso passivo: a LLM consulta para descobrir quem atende, quando
    e onde, sem precisar perguntar para o usuário.
    """
    linhas = ["MÉDICOS BLINK — AGENDA SEMANAL\n"]
    for chave, (nome, agenda) in MEDICOS.items():
        linhas.append(f"\n[{chave}] {nome}")
        for idx in range(7):
            unid = agenda.get(idx)
            dia = DIAS_PT[idx]
            if unid:
                linhas.append(f"  - {dia}: {unid}")
            else:
                linhas.append(f"  - {dia}: NÃO ATENDE")
    return "\n".join(linhas)


@mcp.resource("calendar://medicos/karla/agenda")
def agenda_karla() -> str:
    """Agenda semanal específica da Dra. Karla Delalíbera."""
    linhas = ["AGENDA DRA. KARLA DELALÍBERA — POR DIA DA SEMANA\n"]
    for idx, unid in sorted(KARLA_AGENDA.items()):
        dia = DIAS_PT[idx]
        linhas.append(f"{dia}: {unid or 'NÃO ATENDE'}")
    return "\n".join(linhas)


@mcp.resource("calendar://medicos/fabricio/agenda")
def agenda_fabricio() -> str:
    """Agenda semanal específica do Dr. Fabrício Freitas."""
    linhas = ["AGENDA DR. FABRÍCIO FREITAS — POR DIA DA SEMANA\n"]
    for idx in range(7):
        unid = FABRICIO_AGENDA.get(idx)
        dia = DIAS_PT[idx]
        linhas.append(f"{dia}: {unid or 'NÃO ATENDE'}")
    return "\n".join(linhas)


# ─── PROMPTS ────────────────────────────────────────────────────────

@mcp.prompt()
def revisar_oferta_antes_enviar(
    data_iso: str,
    medico: str = "karla",
    unidade: str = "Asa Norte",
) -> str:
    """Prompt para revisar oferta de slot antes de enviar ao paciente.

    Use este prompt no Claude Desktop quando estiver redigindo nota
    Kommo ou mensagem ao paciente que mencione data específica.
    """
    return (
        f"Você é o revisor sênior do agente Lia. Antes de eu enviar uma "
        f"oferta com a data {data_iso} para {medico} na unidade {unidade}, "
        f"chame a tool 'validar_data_unidade' e confirme que está coerente. "
        f"Se NÃO estiver, sugira 2 alternativas usando a tool "
        f"'proximas_datas_disponiveis'. Bug C-35 não pode acontecer."
    )


# ─── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Iniciando blink-calendar MCP server (stdio)")
    mcp.run()
