"""MCP server blink-calendar — expõe calendar_oracle.py como ferramentas.

Bug C-35 (17/06/2026): Claude (LLM) inventa dia da semana sem rodar
date.weekday(). Este servidor força tool calling pra TODA menção a data.

Arquitetura: 3 camadas anti-bug C-35
  1. Tabela 30+ dias no CLAUDE.md (eu leio visualmente)
  2. voice_agent/calendar_oracle.py + 32 pytest (helper via bash)
  3. ESTE MCP — tool calling forçado no Cowork

Tools expostas:
  - dia_da_semana(data_iso)
  - unidade_karla(data_iso)
  - validar_oferta_slot(data_iso, unidade_pretendida, medico)
  - proximas_datas(unidade, qtde, medico)
  - gerar_oferta_slots(unidade, horario1, horario2, medico)

Uso (Cowork):
  ~/Library/Application Support/Claude/mcp.json:
    {"mcpServers": {"blink-calendar": {
      "command": "python3",
      "args": ["<caminho>/mcp_blink_calendar/server.py"]
    }}}
"""
import sys
from datetime import date
from pathlib import Path

# Importar o oracle (blindado por 32 pytest)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from voice_agent.calendar_oracle import (
        validar,
        dia_semana,
        unidade_medico_em,
        proximas_datas_validas,
        gerar_oferta_2_slots,
    )
except ImportError as e:
    print(f"ERRO: não consegui importar voice_agent.calendar_oracle: {e}",
          file=sys.stderr)
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("ERRO: pacote 'mcp' não instalado. Rode:", file=sys.stderr)
    print("  pip3 install --upgrade 'mcp[cli]' --break-system-packages",
          file=sys.stderr)
    sys.exit(1)


mcp = FastMCP("blink-calendar")


def _parse(data_iso: str) -> date:
    """Aceita 'YYYY-MM-DD' (formato ISO 8601)."""
    return date.fromisoformat(data_iso.strip())


@mcp.tool()
def dia_da_semana(data_iso: str) -> str:
    """Retorna o dia da semana em pt-BR pra uma data ISO YYYY-MM-DD.

    Exemplos:
        dia_da_semana('2026-06-18') -> 'Quinta-feira'
        dia_da_semana('2026-06-20') -> 'Sábado'

    Args:
        data_iso: Data no formato YYYY-MM-DD (ex: '2026-06-18').

    Returns:
        Nome do dia da semana em português brasileiro.
    """
    return dia_semana(_parse(data_iso))


@mcp.tool()
def unidade_karla(data_iso: str) -> str:
    """Retorna onde a Dra. Karla Delalíbera atende numa data específica.

    Regra: seg/qua/sex Asa Norte · ter/qui Águas Claras · sáb/dom não atende.

    Args:
        data_iso: Data no formato YYYY-MM-DD (ex: '2026-06-18').

    Returns:
        'Asa Norte', 'Águas Claras' ou 'NÃO atende (sábado/domingo)'.
    """
    u = unidade_medico_em(_parse(data_iso), "karla")
    return u if u else "NÃO atende (sábado/domingo)"


@mcp.tool()
def validar_oferta_slot(data_iso: str, unidade_pretendida: str,
                        medico: str = "karla") -> dict:
    """Valida se uma data + unidade são compatíveis pra ofertar slot.

    Use SEMPRE antes de escrever "X-feira (DD/MM)" em qualquer mensagem
    (nota Kommo, WhatsApp, e-mail). É a barreira anti-bug C-35.

    Args:
        data_iso: Data no formato YYYY-MM-DD (ex: '2026-06-18').
        unidade_pretendida: 'Asa Norte' ou 'Águas Claras'.
        medico: 'karla' (default) ou 'fabricio'.

    Returns:
        Dict com:
          - data_br: '18/06/2026'
          - dia: 'Quinta-feira'
          - unidade_atende: 'Águas Claras' (real, não a pretendida)
          - valido_para_oferta: bool
          - texto_pronto: string formatada
          - motivo_invalido: explica por que falhou (se aplicável)
    """
    info = validar(_parse(data_iso), medico, unidade_pretendida)
    return {
        "data_br": info.data_br,
        "dia": info.dia,
        "unidade_atende": info.unidade_atende,
        "valido_para_oferta": info.valido_para_oferta,
        "texto_pronto": info.texto_pronto,
        "motivo_invalido": info.motivo_invalido,
    }


@mcp.tool()
def proximas_datas(unidade: str, qtde: int = 4,
                   medico: str = "karla") -> list[dict]:
    """Lista as próximas N datas em que o médico atende a unidade pedida.

    Use pra montar oferta de slots sem inventar data.

    Args:
        unidade: 'Asa Norte' ou 'Águas Claras'.
        qtde: Quantas datas retornar (default 4).
        medico: 'karla' (default) ou 'fabricio'.

    Returns:
        Lista de dicts com data_br, dia e texto_pronto.
    """
    datas = proximas_datas_validas(unidade, medico, qtde=qtde)
    return [
        {
            "data_br": d.data_br,
            "dia": d.dia,
            "texto_pronto": d.texto_pronto,
        }
        for d in datas
    ]


@mcp.tool()
def gerar_oferta_slots(unidade: str, horario1: str = "09:30",
                       horario2: str = "14:30",
                       medico: str = "karla") -> str:
    """Retorna texto pronto com 2 slots reais pra colar no WhatsApp.

    Exemplo de saída:
        1️⃣ Sexta-feira (19/06) às 09:30
        2️⃣ Segunda-feira (22/06) às 14:30

    Args:
        unidade: 'Asa Norte' ou 'Águas Claras'.
        horario1: Ex '09:30'.
        horario2: Ex '14:30'.
        medico: 'karla' (default) ou 'fabricio'.

    Returns:
        Texto multi-linha pronto pra colar no WhatsApp/Kommo.
    """
    return gerar_oferta_2_slots(medico, unidade, [horario1, horario2])


if __name__ == "__main__":
    mcp.run()
