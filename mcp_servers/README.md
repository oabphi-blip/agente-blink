# Blink MCP Servers — Reestruturação da Lia conforme livro "Dominando MCP"

Implementação dos 6 servidores MCP + 1 Host orquestrador propostos em `PLANO_REESTRUTURACAO_MCP_BLINK.md`.

## Estrutura

```
mcp_servers/
├── README.md                       (este arquivo)
├── pyproject.toml                  (deps + scripts)
├── blink_calendar/                 (Sprint 1 — calendário Karla por dia da semana)
│   ├── server.py
│   ├── models.py
│   └── test_server.py
├── blink_knowledge/                (Sprint 2 — KB clínico como recursos URI)
│   ├── server.py
│   └── test_server.py
├── blink_state/                    (Sprint 3 — estado da conversa em Redis)
│   ├── server.py
│   └── test_server.py
├── blink_medware/                  (Sprint 4 — ERP clínico com tuning C-38b)
│   ├── server.py
│   └── test_server.py
├── blink_kommo/                    (Sprint 5 — CRM com fix Bug C-12)
│   ├── server.py
│   └── test_server.py
├── blink_whatsapp/                 (Sprint 6 — dispatch 8133 + redirect 0710)
│   ├── server.py
│   └── test_server.py
└── blink_host/                     (Host orquestrador — substitui FastAPI)
    ├── orchestrator.py
    ├── config.json
    └── test_orchestrator.py
```

## Princípios aplicados (livro)

1. **Servidor como driver de hardware** (livro 1.1.1): cada servidor encapsula UMA fonte de dados, processo isolado.
2. **Recursos vs Ferramentas** (livro 1.2): Resources para leitura passiva, Tools para ações com efeito colateral.
3. **Stdio transport** (livro 1.3.1): comunicação local, máxima segurança.
4. **Validação Pydantic** (livro 6.5): elimina alucinação de argumento da LLM.
5. **stderr para logs, nunca print** (livro 6.1): protocolo JSON-RPC fica limpo.
6. **Type hints + docstrings ricos** (livro 3.7): LLM lê interface, não código.
7. **Servidor como guardião** (livro 4.5): cada servidor valida ANTES de executar.

## Quick start

```bash
cd mcp_servers
uv sync
uv run pytest                          # roda todos os pytest
uv run python -m blink_calendar.server  # roda servidor calendário standalone
```

## Conectar ao Claude Desktop

Editar `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blink-calendar": {
      "command": "uv",
      "args": ["run", "python", "-m", "blink_calendar.server"],
      "cwd": "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp_servers"
    },
    "blink-knowledge": {
      "command": "uv",
      "args": ["run", "python", "-m", "blink_knowledge.server"],
      "cwd": "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp_servers"
    },
    "blink-medware": {
      "command": "uv",
      "args": ["run", "python", "-m", "blink_medware.server"],
      "cwd": "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp_servers",
      "env": {
        "MEDWARE_USER": "...",
        "MEDWARE_SENHA": "..."
      }
    }
  }
}
```

Após editar, reiniciar Claude Desktop. Stephany/Ariany podem usar os mesmos servidores em suas máquinas.

## Debugging

Cada servidor pode ser inspecionado isoladamente via MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run python -m blink_calendar.server
```

Abre interface web onde dá pra chamar tools, ler resources, ver logs.

## Estado da implementação

- ✅ Sprint 1 — blink_calendar (Bug C-35 eliminado)
- ✅ Sprint 2 — blink_knowledge (38 artigos KB como recursos URI)
- ✅ Sprint 3 — blink_state (Redis com dedup + lock + reserva 10 min)
- ✅ Sprint 4 — blink_medware (tuning C-38b + janela cirúrgica E6-C nativos)
- ✅ Sprint 5 — blink_kommo (fix Bug C-12 via GET pós-PATCH)
- ✅ Sprint 6 — blink_whatsapp (8133 + redirect 0710 unificados)
- ✅ Host orquestrador (loop agêntico do livro 7.2)
