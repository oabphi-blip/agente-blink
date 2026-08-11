# Plano Camada 3 — MCP local `blink-calendar-mcp`

**Objetivo:** eliminar definitivamente o Bug C-35 (Claude inventa dia da semana). Toda menção a data em qualquer texto que eu produzir (Cowork) PASSA OBRIGATORIAMENTE por uma ferramenta determinística antes de chegar ao usuário.

**Status arquitetural:**

| Camada | O que faz | Status |
|---|---|---|
| 1 — Tabela 30+ dias no CLAUDE.md | Eu leio visualmente antes de redigir | ✅ Implantado 17/06/2026 |
| 2 — `voice_agent/calendar_oracle.py` + 32 pytest | Helper canônico Python via bash | ✅ Implantado 17/06/2026 |
| **3 — MCP `blink-calendar-mcp` no Cowork** | **Toda data passa por tool obrigatória** | **Este plano** |

---

## Por que a Camada 3 é necessária

As Camadas 1 e 2 dependem de **eu lembrar** de consultar a tabela ou rodar o helper. **Disciplina ≠ garantia.** O bug C-35 já mostrou que esquecer custa 12 notas erradas. A Camada 3 torna IMPOSSÍVEL eu finalizar resposta com data inventada — porque o modelo precisa chamar a tool primeiro.

Mesma lógica do `oferecer_slot` tool calling forçado na Lia (fix #183) — mas pra mim (Claude operando Cowork), off-prod.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│ Cowork — Claude (Sonnet/Opus)                           │
│                                                          │
│ System prompt CLAUDE.md (seção 0-AAA):                   │
│   "Antes de redigir QUALQUER texto com data, chame      │
│    mcp__blink_calendar__validar_data."                   │
│                                                          │
│ ┌────────────────────────────────────────────────────┐  │
│ │ MCP local: blink-calendar-mcp (stdio)              │  │
│ │   Wrapper sobre voice_agent/calendar_oracle.py     │  │
│ │                                                     │  │
│ │ Tools expostas:                                     │  │
│ │   1. dia_da_semana(data_iso) -> "Quinta-feira"     │  │
│ │   2. unidade_karla(data_iso) -> "Águas Claras"     │  │
│ │   3. validar_oferta(data_iso, unidade) -> bool+ctx │  │
│ │   4. proximas_datas(unidade, qtde) -> [datas]      │  │
│ │   5. gerar_oferta_slots(unidade, h1, h2) -> texto  │  │
│ └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Pré-requisitos

- Python 3.10+ (já tem)
- Pip pacotes: `mcp[cli]>=1.0` (SDK oficial Anthropic Python pra MCP)
- Acesso ao folder do projeto (já tem)
- Cowork app instalado (já tem)

---

## Passo 1 — Instalar dependência MCP

Abrir Terminal e rodar:

```bash
pip3 install --upgrade "mcp[cli]" --break-system-packages
```

Validar:

```bash
python3 -c "import mcp; print('OK mcp version:', mcp.__version__)"
```

---

## Passo 2 — Criar o servidor MCP

Arquivo já gerado em `mcp_blink_calendar/server.py` (este pacote). Conteúdo:

```python
"""MCP server blink-calendar — expõe calendar_oracle.py como ferramentas."""
import sys
from datetime import date
from pathlib import Path

# Importar oracle (módulo já blindado por 32 pytest)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from voice_agent.calendar_oracle import (
    validar, dia_semana, unidade_medico_em,
    proximas_datas_validas, gerar_oferta_2_slots,
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("blink-calendar")


def _parse(data_iso: str) -> date:
    return date.fromisoformat(data_iso)


@mcp.tool()
def dia_da_semana(data_iso: str) -> str:
    """Retorna o dia da semana em pt-BR pra uma data ISO (YYYY-MM-DD).
    Exemplo: dia_da_semana('2026-06-18') -> 'Quinta-feira'"""
    return dia_semana(_parse(data_iso))


@mcp.tool()
def unidade_karla(data_iso: str) -> str:
    """Retorna onde a Dra. Karla atende numa data específica.
    Retorna 'Asa Norte', 'Águas Claras', ou 'NÃO atende (sábado/domingo)'."""
    u = unidade_medico_em(_parse(data_iso), "karla")
    return u if u else "NÃO atende (sábado/domingo)"


@mcp.tool()
def validar_oferta_slot(data_iso: str, unidade_pretendida: str,
                        medico: str = "karla") -> dict:
    """Valida se uma data + unidade são compatíveis pra ofertar slot.
    Use SEMPRE antes de escrever 'X-feira (DD/MM)' em qualquer mensagem.

    Args:
        data_iso: data no formato YYYY-MM-DD
        unidade_pretendida: 'Asa Norte' ou 'Águas Claras'
        medico: 'karla' (default) ou 'fabricio'

    Returns:
        {valido_para_oferta, dia, unidade_real, texto_pronto, motivo_invalido}
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
    """Retorna as N próximas datas em que o médico atende a unidade pedida.
    Use pra montar oferta de slots sem inventar data.

    Args:
        unidade: 'Asa Norte' ou 'Águas Claras'
        qtde: quantas datas retornar (default 4)
        medico: 'karla' (default) ou 'fabricio'
    """
    datas = proximas_datas_validas(unidade, medico, qtde=qtde)
    return [{"data_br": d.data_br, "dia": d.dia,
             "texto_pronto": d.texto_pronto} for d in datas]


@mcp.tool()
def gerar_oferta_slots(unidade: str, horario1: str = "09:30",
                       horario2: str = "14:30", medico: str = "karla") -> str:
    """Retorna texto pronto com 2 slots reais pra colar no WhatsApp.

    Args:
        unidade: 'Asa Norte' ou 'Águas Claras'
        horario1: ex '09:30'
        horario2: ex '14:30'
        medico: 'karla' (default) ou 'fabricio'

    Returns:
        Texto formatado tipo:
          "1️⃣ Sexta-feira (19/06) às 09:30
           2️⃣ Segunda-feira (22/06) às 14:30"
    """
    return gerar_oferta_2_slots(medico, unidade, [horario1, horario2])


if __name__ == "__main__":
    mcp.run()
```

---

## Passo 3 — Configurar no Cowork

O Cowork lê MCPs de um arquivo `mcp.json` ou da UI Settings → Connectors.

**Opção A — Via arquivo (recomendado):**

Editar (ou criar) o arquivo `~/Library/Application Support/Claude/mcp.json`:

```json
{
  "mcpServers": {
    "blink-calendar": {
      "command": "python3",
      "args": [
        "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp_blink_calendar/server.py"
      ],
      "env": {}
    }
  }
}
```

**Opção B — Via Cowork UI:**

1. Abrir Cowork
2. Settings → Capabilities → Add MCP Server
3. Nome: `blink-calendar`
4. Command: `python3`
5. Args: `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp_blink_calendar/server.py`
6. Salvar

---

## Passo 4 — Restart Cowork pra carregar o MCP

Cmd+Q no Cowork → reabrir.

---

## Passo 5 — Validar que carregou

No Cowork, perguntar: *"Lista as ferramentas do MCP blink-calendar."*

Eu (Claude) devo responder com as 5 tools:
- `mcp__blink_calendar__dia_da_semana`
- `mcp__blink_calendar__unidade_karla`
- `mcp__blink_calendar__validar_oferta_slot`
- `mcp__blink_calendar__proximas_datas`
- `mcp__blink_calendar__gerar_oferta_slots`

---

## Passo 6 — Smoke test funcional

No Cowork, pedir: *"Valida 18/06/2026 pra Asa Norte com Karla."*

Eu devo chamar `mcp__blink_calendar__validar_oferta_slot` e responder:

```
"18/06/2026 é quinta-feira. Karla atende Águas Claras nesse dia, NÃO Asa Norte. 
Oferta INVÁLIDA."
```

Pedir também: *"Gera oferta de 2 slots Karla Asa Norte 09:30 e 14:30 começando hoje."*

Eu devo retornar:

```
"1️⃣ Sexta-feira (19/06) às 09:30
2️⃣ Segunda-feira (22/06) às 14:30"
```

---

## Passo 7 — Atualizar CLAUDE.md com regra de uso forçado

Adicionar na seção 0-AAA (já existente) o bloco:

```markdown
**REGRA INVIOLÁVEL — uso obrigatório do MCP:**

Antes de redigir QUALQUER texto (nota Kommo, WhatsApp, e-mail, planilha) que 
mencione data no formato "DD/MM" OU dia-da-semana ("quinta", "sexta", etc), 
chamar OBRIGATORIAMENTE uma das tools `mcp__blink_calendar__*`:

- Pra validar 1 slot específico: `mcp__blink_calendar__validar_oferta_slot`
- Pra montar oferta de 2 slots: `mcp__blink_calendar__gerar_oferta_slots`
- Pra listar próximas N datas: `mcp__blink_calendar__proximas_datas`

NUNCA digitar dia-da-semana baseado em intuição. SEMPRE delegar pro MCP.

Se o MCP não estiver carregado (ex: sandbox sem acesso), DEGRADAR pra 
Camada 2 (bash `python3 voice_agent/calendar_oracle.py`). NUNCA seguir sem 
nenhuma das 2 camadas — preferir não responder.
```

---

## Passo 8 — Rollback de emergência

Se o MCP der problema (ex: travar Cowork):

1. Editar `~/Library/Application Support/Claude/mcp.json`
2. Remover entrada `"blink-calendar"`
3. Restart Cowork
4. Continuar usando Camadas 1 + 2 (tabela CLAUDE.md + bash)

---

## Passo 9 — Atualização automática da tabela do CLAUDE.md

Conforme dias passam, a tabela de 30 dias precisa rolar. Criar scheduled task semanal:

**Arquivo:** `ATUALIZAR_TABELA_CALENDARIO.command`

```bash
#!/bin/bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
python3 voice_agent/calendar_oracle.py tabela-120 | head -50 > /tmp/tabela_calendario.md
# Substituir bloco no CLAUDE.md (regex sed)
# (script de update detalhado a fazer)
```

OU mais simples: via `mcp__scheduled-tasks__create_scheduled_task` (no Cowork), criar tarefa "Toda segunda 6h, regenerar tabela calendário no CLAUDE.md".

---

## Validação final — Critérios de aceitação

A Camada 3 está **funcionando** se:

- [ ] `pip3 install "mcp[cli]"` rodou sem erro
- [ ] `python3 mcp_blink_calendar/server.py` inicia sem traceback
- [ ] Cowork lista as 5 tools `mcp__blink_calendar__*`
- [ ] Pedido "valida 18/06 Asa Norte" retorna INVÁLIDO com motivo correto
- [ ] Pedido "gera oferta 2 slots Asa Norte" retorna texto com datas calculadas
- [ ] Em outra sessão Cowork (próxima vez que eu abrir), CLAUDE.md me lembra de chamar a tool ANTES de digitar data
- [ ] 32/32 testes `tests/test_calendar_oracle.py` continuam verde

---

## Custo / Benefício

| Item | Custo |
|---|---|
| Setup inicial (1ª vez) | 10 min (pip install + criar arquivo mcp.json + restart) |
| Manutenção contínua | Zero — `calendar_oracle.py` já é blindado por pytest |
| Overhead por tool call | <50ms (stdio local Python) |

| Benefício | Impacto |
|---|---|
| Bug C-35 zerado em qualquer texto meu | 100% — impossível inventar data |
| Notas Kommo erradas | Zero (vs 12 nesta sessão) |
| Confiança Fábio | Volta — proteção mecânica em vez de "Claude promete não errar" |

---

## Diferença vs camadas anteriores

| Camada | Garantia | Falha em |
|---|---|---|
| 1 — tabela CLAUDE.md | Eu LEMBRAR de olhar | Esquecimento humano (LLM) |
| 2 — bash helper | Eu LEMBRAR de rodar | Esquecimento humano (LLM) |
| **3 — MCP forçado** | **Tool calling estruturado** | **Apenas se Cowork não carregar o MCP** |

A Camada 3 é cinto + suspensório. As 3 camadas juntas = redundância dura.

---

## Próxima evolução possível (não pra agora)

**Camada 4 — Filtro pós-geração no Cowork CLAUDE side.** Antes do meu texto ir pro Fábio, regex extrai `(dia-da-semana DD/MM)` e revalida via MCP. Se inconsistente, eu refaço automaticamente. Implementação requer hook no Cowork interno — não está exposto hoje. Aguardar Anthropic expor "pre-response validators".

---

**Pra executar:** rodar o script `INSTALAR_MCP_CALENDARIO.command` (duplo clique no Finder).
