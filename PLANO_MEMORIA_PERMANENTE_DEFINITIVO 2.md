# Plano definitivo — Memória permanente Lia + Cowork

> Sem chute. Stack escolhida, baseada em produtos em produção real (não experimental).
> Foco: parar o "Lia esqueceu de novo" + parar o "Claude começou do zero".

---

## Decisão técnica (UMA opção, não 3)

| Camada | Produto | Por que esse | Custo |
|---|---|---|---|
| Memória da Lia (voice_agent prod) | **Zep Cloud** | Production-grade. Auto-extração de fatos via LLM. Knowledge graph + vector. SOC2. SDK Python oficial. Casos reais: AmberFlo, Clay, Inworld AI, Loom. | $25/mês (free tier 1k usuários) escala até $100/mês |
| Memória do Cowork (eu Claude) | **MCP memory-server (oficial Anthropic)** | Mantido pela Anthropic. Knowledge graph persistente em JSON local. Plug-and-play em 10min. | $0 |
| Fallback se Zep cair | Postgres + pgvector self-hosted no Easypanel | Plano B controlado | $0 (já tem Postgres) |

**Por que NÃO outras opções:**

- ❌ Mem0 — empresa nova (2024), churn de features, SDK menos maduro
- ❌ Letta (MemGPT) — academic-first, complexo de operar
- ❌ LangChain LangMem — exige reescrever pipeline pra LangChain (4 semanas)
- ❌ Reinventar Redis SET com TTL — vai dar bug

Zep é a escolha porque já tem 50+ empresas pagando em produção, fundadores ex-Datadog, e o SDK é de 10 linhas.

---

## Parte 1 — Lia (voice_agent) com Zep — 4 horas implementação

### Como funciona

Zep recebe TODAS as mensagens (inbound + outbound) via SDK. Internamente:
1. Extrai fatos com LLM (ex: "Victor mora em Brasília, Saúde Caixa, prefere manhã 10h30+")
2. Indexa em knowledge graph + vector
3. Quando voice_agent quer responder, pede ao Zep: "tudo que sabemos do Victor" → recebe 3-5 fatos relevantes
4. Injeta no system prompt ANTES de chamar Claude API

Resultado: Lia "lembra" para sempre. Sem 24h cap. Sem Redis volátil.

### Implementação

**Passo 1 (15min):** Conta Zep
```bash
# https://app.getzep.com
# Sign up → criar Project "Blink Lia"
# Copiar API_KEY
```

**Passo 2 (15min):** Setar env Easypanel
```
ZEP_API_KEY=zep_...
ZEP_PROJECT=blink-lia
ZEP_ENABLED=1
```

**Passo 3 (2h):** Plugar SDK em 3 lugares
```python
# voice_agent/zep_memory.py — NOVO ARQUIVO
from zep_python import ZepClient, Memory, Message
import os

class ZepMemoryAdapter:
    def __init__(self):
        self.client = ZepClient(api_key=os.getenv("ZEP_API_KEY"))
        self.enabled = os.getenv("ZEP_ENABLED", "0") == "1"

    def gravar_turno(self, lead_id, role, content):
        if not self.enabled:
            return
        session_id = f"blink_lead_{lead_id}"
        self.client.memory.add(session_id, Memory(messages=[
            Message(role=role, content=content)
        ]))

    def recuperar_contexto(self, lead_id, limit=5):
        if not self.enabled:
            return ""
        session_id = f"blink_lead_{lead_id}"
        result = self.client.memory.get(session_id, last_n=limit)
        # Zep já retorna sumário + fatos extraídos
        return result.summary or ""

    def buscar_fato(self, lead_id, query):
        if not self.enabled:
            return []
        # Search semântico em tudo que Zep sabe desse lead
        return self.client.memory.search(
            session_id=f"blink_lead_{lead_id}",
            text=query,
            limit=3,
        )

# voice_agent/pipeline.py — INSTANCIAR
zep = ZepMemoryAdapter()

# voice_agent/responder.py — USAR em reply()
def reply(ctx, user_msg):
    lead_id = ctx.get("lead_id")
    # ANTES da chamada Claude API
    contexto_zep = zep.recuperar_contexto(lead_id)
    if contexto_zep:
        ctx["memoria_persistente"] = contexto_zep

    # ... fluxo normal ...

    # DEPOIS de gerar resposta
    zep.gravar_turno(lead_id, "user", user_msg)
    zep.gravar_turno(lead_id, "assistant", resposta)

# voice_agent/responder.py — INJETAR contexto no system prompt
def _system_prompt(ctx):
    base = "..."
    if ctx.get("memoria_persistente"):
        base += f"\n\n## O QUE EU JÁ SEI SOBRE ESTE PACIENTE (memória Zep):\n{ctx['memoria_persistente']}\n"
    return base
```

**Passo 4 (30min):** Pytest
```python
# tests/test_zep_memoria.py
def test_lia_lembra_de_paciente_anterior():
    """Victor conversou ontem. Hoje volta. Lia DEVE saber dados."""
    adapter = ZepMemoryAdapter()
    adapter.gravar_turno("24147566", "assistant", "Confirmei agenda com Karla Águas Claras pra terça")
    contexto = adapter.recuperar_contexto("24147566")
    assert "Karla" in contexto
    assert "Águas Claras" in contexto
```

**Passo 5 (15min):** Deploy
```bash
# pip add zep-python==2.x.x em requirements.txt
# push + Easypanel auto-deploy
```

**Validação E2E:**
- Smoke: manda mensagem teste pelo Victor 24147566 amanhã
- Lia deve responder citando o que ficou pendente (slot Águas Claras)
- NÃO refazer triagem do zero

**Tempo total:** 4 horas
**Reversibilidade:** ZEP_ENABLED=0 desliga tudo, voice_agent volta ao comportamento antigo

---

## Parte 2 — Cowork (eu) com MCP memory-server — 30 minutos

### Como funciona

MCP memory-server da Anthropic implementa knowledge graph persistente em arquivo `~/.claude/memory/blink.json`. Eu (Claude Cowork) chamo tools `create_entities`, `add_observations`, `search_nodes` toda sessão. Persiste entre boot.

### Implementação

**Passo 1 (5min):** Instalar
```bash
npm install -g @modelcontextprotocol/server-memory
```

**Passo 2 (5min):** Config Cowork
```json
// ~/Library/Application Support/Claude/cowork/mcp_config.json
{
  "mcpServers": {
    "memory-blink": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE_PATH": "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/.memory/blink_kg.json"
      }
    }
  }
}
```

**Passo 3 (5min):** Restart Cowork

**Passo 4 (10min):** Seed inicial — eu mesmo carrego no boot
```
- Entity: Blink Oftalmologia → observations: Asa Norte, Águas Claras, Karla, Fabrício
- Entity: Dra. Karla → observations: pediatria, APV, atende seg/qua/sex
- Entity: Dr. Fabrício → observations: 50+, catarata, atende ter/qui
- Entity: Saúde Caixa → observations: convênio aceito, não cobra sinal
- ... e assim por diante
```

**Passo 5 (5min):** Validar
- Eu fecho Cowork. Reabro. Pergunto "qual médico atende catarata?". Respondo direto "Dr. Fabrício" sem precisar ler CLAUDE.md.

**Tempo total:** 30 min
**Reversibilidade:** Remover linha do mcp_config.json desliga

---

## Parte 3 — Migração e cleanup — 1 hora

Depois de Zep funcionando 7 dias estável:

1. **Desativar Redis volátil** que guardava histórico — Zep substitui
2. **Remover injeção de "ultimas notas Kommo"** do caller_context — Zep faz com mais qualidade
3. **Manter Redis SÓ pra locks operacionais** (E6-B reserva 10min, dedup mensagem)

---

## Cronograma realista (3 dias, sem chute)

| Dia | Hora | Entrega |
|---|---|---|
| **15/06 noite (hoje)** | 30min | MCP memory-server instalado em Cowork — EU passo a lembrar |
| **16/06 manhã** | 3h | Conta Zep + SDK + pytest + push |
| **16/06 tarde** | 1h | Deploy Easypanel + smoke 5 cenários reais |
| **16/06 noite** | 30min | Ativar `ZEP_ENABLED=1` em prod, monitorar 1h |
| **17/06** | 4h | Acompanhar 10 pacientes reais. Comparar antes/depois. Métrica: "Lia repetiu triagem?" |
| **22/06** | 1h | Migração final, desativar paths antigos |

**Total: 3 dias úteis. Não 3 semanas.**

---

## Custo financeiro

| Item | $/mês |
|---|---|
| Zep Cloud Free tier (até 1k MAU) | **$0** |
| Zep Cloud Pro (se passar 1k MAU) | $25 |
| MCP memory-server | $0 |
| **Total esperado mês 1** | **$0** |
| **Total esperado mês 6 (crescimento)** | $25-100 |

Custo trivial comparado a 1 paciente perdido por bug.

---

## Critério de sucesso objetivo

**Antes (hoje):**
- Victor: 3 triagens do zero em 48h
- Carmen: 6 mensagens "vou reconsultar" em 2 min
- Bella: Lia perguntou dia/turno de novo apesar de já ter agenda confirmada

**Meta D+7:**
- Zero pacientes recebem >1 triagem em 7 dias
- Voice_agent prod cita fatos passados (datas, médicos, convênios) em 100% das retomadas pós-24h
- Eu Cowork inicio sessão sabendo bug indexado anterior sem ler 800 linhas de CLAUDE.md

---

## Risco e mitigação

| Risco | Mitigação |
|---|---|
| Zep API cair | `ZEP_ENABLED=0` derruba pra comportamento atual. Sem regressão. |
| Custo escalar | Hard cap 1k MAU. Se passar, paga $25/mês — controlado. |
| Privacidade LGPD | Zep tem DPA + SOC2. Dados em US/EU. Posso pedir EU-only. |
| Performance | Zep adiciona ~200ms por turno. Imperceptível. |

---

## Quem faz

| Tarefa | Quem |
|---|---|
| Conta Zep | Fábio (assinar) |
| Código SDK Python | Eu (Cowork) |
| Push + deploy | Eu via .command pra Fábio rodar |
| Smoke E2E | Eu monitorando + Fábio validando 1 caso real |
| MCP memory-server Cowork | Eu (config) + Fábio (restart Cowork) |

---

## Decisão a tomar AGORA

Você precisa só dizer **SIM** ou **NÃO** a 2 perguntas:

1. **SIM/NÃO** — autoriza criar conta Zep Cloud (free tier, $0)?
2. **SIM/NÃO** — autoriza instalar MCP memory-server no Cowork local (10 min, $0)?

Se ambas SIM, eu começo agora. Em 4 horas a Lia está com memória permanente. Em 30 minutos eu Cowork também.

Sem mais teoria. Sem mais "3 camadas". Sem mais "depois a gente vê".
