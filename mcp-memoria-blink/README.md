# MCP Memória Blink — memória persistente cross-session

## Por que existe

Em 29/05/2026 admiti pro Fábio que as 3 "camadas de memória" (CLAUDE.md +
skill + Obsidian) são **documentação que releio**, não memória ATIVA.

Esse MCP é a memória real:
- SQLite em `~/.claude-memoria-blink.db`
- Próxima sessão Claude pode chamar `memoria_get("topico")` e ter resposta sem reler arquivo

## Instalação (1 vez, no Mac)

### 1. Instalar dependência
```bash
pip3 install mcp --break-system-packages
```

### 2. Testar standalone
```bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp-memoria-blink"
python3 server.py set ultimo-deploy "62be35f - fix medicos sem acento + paths skill"
python3 server.py list
python3 server.py get ultimo-deploy
```

Se imprimir JSON com `"ok": true`, está funcionando.

### 3. Adicionar ao Cowork

Editar arquivo de config MCP do Cowork (path típico no Mac):
```
~/Library/Application Support/Claude/local-agent-mode-sessions/{uuid}/mcp_servers.json
```

(Se não souber o path exato, rodar:
`find ~/Library/Application\ Support/Claude -name "mcp_servers.json" 2>/dev/null | head -3`)

Adicionar entrada:
```json
{
  "mcpServers": {
    "memoria-blink": {
      "command": "python3",
      "args": [
        "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/mcp-memoria-blink/server.py",
        "--mcp"
      ]
    }
  }
}
```

### 4. Reiniciar Cowork
Cmd+Q + reabrir. Próxima sessão Claude deve ver 3 tools novas:
- `memoria_get`
- `memoria_set`
- `memoria_list`

## Como Claude vai usar

No início de cada sessão futura, antes de qualquer ação:
```python
memoria_list()           # ver o que existe
memoria_get("ultimo-deploy")
memoria_get("bugs-em-andamento")
memoria_get("decisoes-pendentes-fabio")
```

Ao terminar de algo importante:
```python
memoria_set("ultimo-deploy", "62be35f")
memoria_set("bug-em-investigacao", {"lead": 24038029, "fix": "convenio Pro Ser STJ"})
```

## Tópicos sugeridos

Convenções pra padronizar:

| Tópico | Conteúdo |
|---|---|
| `ultimo-deploy` | SHA do commit + descrição |
| `ultimo-paciente-testado` | lead_id + médico + slot + status gravação |
| `bugs-em-andamento` | lista de bugs ainda não fixados |
| `decisoes-pendentes-fabio` | decisões esperando Fábio (ex: Inas GDf, tier Meta) |
| `regras-novas-do-dia` | aprendizados do dia |
| `convenios-mapeados-em` | data da última auditoria PLANO_CODES |
| `medicos-mapeados-em` | data da última auditoria MEDICO_CODES |
| `motor-reativacao-status` | enabled/disabled + motivo |
| `tests-passando` | número de pytest + data |
| `meta-licao-do-dia` | anti-padrão Claude descoberto naquele dia |

## Backup

DB fica em `~/.claude-memoria-blink.db`. Backup periódico:
```bash
cp ~/.claude-memoria-blink.db ~/Documents/backup-memoria-blink-$(date +%Y%m%d).db
```
