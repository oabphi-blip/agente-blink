# Blink Bridge MCP

Servidor MCP local que dá ao Claude (rodando no sandbox Cowork) acesso aos endpoints do `blink-agent.6prkfn.easypanel.host` — bypassando a allowlist do proxy do sandbox.

## Por quê existe

O sandbox do Cowork bloqueia `*.easypanel.host` no proxy HTTP. Isso impede o Claude de chamar endpoints admin do app blink-agent diretamente. A solução é rodar um servidor MCP no Mac do Fábio que age como ponte:

```
Claude (sandbox bloqueado)
  ↓ MCP protocol (stdio, sem rede)
blink-bridge (este servidor, no Mac)
  ↓ HTTP normal
blink-agent.6prkfn.easypanel.host ✅
```

Resultado: Claude executa qualquer operação autônoma, sem Fábio rodar curl/terminal.

## Setup (1 vez só, ~5 min)

```bash
cd /Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE\ IA\ BLINK/mcp/blink-bridge
bash install.sh
```

O instalador:
1. Cria venv isolado
2. Instala dependências (mcp, httpx, python-dotenv)
3. Cria `.env.mcp` a partir do template
4. Imprime o snippet pra adicionar ao Claude Desktop config

Depois:
1. **Edita `.env.mcp`** e cola o `WEBHOOK_SECRET` real (pega do Easypanel → Ambiente)
2. **Adiciona ao Claude Desktop config**: `~/Library/Application Support/Claude/claude_desktop_config.json`
3. **Reinicia Claude Desktop** (Cmd+Q + reabrir)
4. Confirma carregamento: nova sessão, "list mcps disponíveis"

## Ferramentas expostas

| Tool | O que faz |
|---|---|
| `health()` | Verifica saúde do app blink-agent |
| `reactivation_status()` | Status do motor de reativação 24h |
| `disparar_lead(lead_id)` | Dispara template padrão (1089) pra 1 lead |
| `disparar_batch(lead_ids, dry_run)` | Dispara N leads de uma vez |
| `disparar_categoria(categoria, unidade, medico, max_leads, dry_run)` | Filtro inteligente R/E/C + dispara |
| `disparar_template(lead_id, template, body_params, dry_run)` | Template Meta custom com N variáveis |
| `setup_campos_acompanhamento()` | Cria os 3 campos de acompanhamento no Kommo |

## Como usar daqui em diante

Em qualquer sessão Cowork, eu posso chamar diretamente:

```
mcp__blink-bridge__disparar_template(
  lead_id=21203181,
  template="captar_paciente",
  body_params=["Déborah", "Maria Teresa", "Águas Claras", "Dra. Karla Delalibera", "09/06 09:00"]
)
```

E o MCP dispara o template via WhatsApp Cloud + grava nota Kommo + retorna resultado pra mim. **Zero curl, zero terminal, zero browser.**

## Segurança

- `WEBHOOK_SECRET` fica só no `.env.mcp` local (não vai pro git — já adicionado ao `.gitignore`)
- MCP só aceita conexão local via stdio (não expõe porta de rede)
- Cada chamada usa o secret como autenticação no app
- Se quiser revogar acesso: deleta `.env.mcp` ou troca o secret no Easypanel

## Troubleshooting

**MCP não aparece no Claude Desktop após reiniciar:**
- Confere que o JSON em `~/Library/Application Support/Claude/claude_desktop_config.json` é válido (use jq)
- Confere que os paths absolutos no JSON existem
- Roda o servidor manualmente pra ver erros: `venv/bin/python blink_bridge_mcp.py`

**`Unauthorized` em todas as chamadas:**
- `WEBHOOK_SECRET` no `.env.mcp` está vazio ou errado
- Pega o valor correto no Easypanel → app agent → Ambiente
