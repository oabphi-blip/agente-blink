# Agente IA Easypanel

Agente conversacional em Python que gerencia uma instância Easypanel via linguagem
natural. Você fala em português ("lista os projetos", "reinicia o n8n", "mostra
o env da evolution-api") e o agente Claude usa a API tRPC do Easypanel para executar.

Construído sobre o SDK oficial `anthropic` com o padrão tool_use/tool_result —
mesma base usada pelo Claude Agent SDK, mas sem depender do CLI do Claude Code
(roda standalone em qualquer container Python).

## Capacidades

| Categoria       | Tools                                                                 |
|-----------------|-----------------------------------------------------------------------|
| Projetos        | listar, inspecionar, criar, destruir                                  |
| Apps            | inspecionar, deploy, start/stop/restart, destroy, atualizar env/imagem |
| Bancos          | inspecionar Postgres / MySQL / MariaDB / Mongo / Redis                |
| Domínios        | listar, criar                                                         |
| Monitor         | stats do sistema, do serviço, de storage                              |
| Sistema         | usuários, certificados, containers Docker                             |
| Escape hatch    | `trpc_raw` — chama qualquer uma das 341 procedures da API             |

Para operações destrutivas (destroy, troca de env, troca de imagem) o agente
**sempre confirma com você antes** de executar.

## Como rodar local

```bash
# 1. Configurar
cp .env.example .env
# preencha ANTHROPIC_API_KEY, EASYPANEL_URL, EASYPANEL_TOKEN

# 2. Instalar dependências (venv recomendado)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Modo chat interativo
python -m easypanel_agent.cli

# Ou one-shot
python -m easypanel_agent.cli "lista todos os projetos e quais serviços estão em cada um"
```

## Como conseguir um token permanente do Easypanel

Tokens de sessão (do login normal) expiram em 30 dias. Para um token permanente:

```bash
# 1. Login para pegar um token de sessão
curl -X POST http://2.24.110.21:3000/api/trpc/auth.login \
  -H "Content-Type: application/json" \
  -d '{"json":{"email":"seu@email.com","password":"sua-senha"}}'
# resposta tem "token":"xxx" — copia

# 2. Listar usuários para pegar seu ID
curl http://2.24.110.21:3000/api/trpc/users.listUsers \
  -H "Authorization: Bearer SEU_TOKEN_DE_SESSAO"
# acha seu email, copia o "id"

# 3. Gerar token permanente
curl -X POST http://2.24.110.21:3000/api/trpc/users.generateApiToken \
  -H "Authorization: Bearer SEU_TOKEN_DE_SESSAO" \
  -H "Content-Type: application/json" \
  -d '{"json":{"id":"SEU_USER_ID"}}'

# 4. Listar usuários de novo — agora seu usuário tem "apiToken"
curl http://2.24.110.21:3000/api/trpc/users.listUsers \
  -H "Authorization: Bearer SEU_TOKEN_DE_SESSAO"
```

## Deploy na própria instância Easypanel

A forma mais limpa de hospedar é como um serviço App dentro do próprio Easypanel.
Como o agente é um CLI interativo, você pode subi-lo de duas formas:

### Opção A — Container "always-on" para uso via Docker exec

1. Suba a imagem para um registry (GHCR, Docker Hub, ou builda direto no Easypanel via GitHub).
2. No Easypanel: **Criar Serviço → App**, source = imagem Docker ou GitHub.
3. Defina as envs:
   - `ANTHROPIC_API_KEY=sk-ant-...`
   - `EASYPANEL_URL=http://easypanel:3000`  ← URL interna do Docker network
   - `EASYPANEL_TOKEN=...` (o token permanente)
4. Sobrescreva o CMD para `tail -f /dev/null` (manter container vivo).
5. Use `docker exec -it <container> python -m easypanel_agent.cli` pra conversar.

### Opção B — Schedule de tarefas / chamadas one-shot

Use one-shot via `docker exec` ou crie um endpoint HTTP wrapper. O modo
one-shot já está pronto: `python -m easypanel_agent.cli "seu comando"`.

> Importante: dentro do Easypanel, use `http://easypanel:3000` como
> `EASYPANEL_URL` — esse é o hostname interno do container do painel na rede
> Docker do swarm. URLs externas (via IP público) não funcionam de dentro.

## Estrutura

```
easypanel_agent/
├── __init__.py
├── client.py      # wrapper HTTP da API tRPC do Easypanel
├── tools.py       # specs JSON-Schema das tools + dispatcher
├── agent.py       # loop tool_use/tool_result com Anthropic SDK
└── cli.py         # entrada CLI (chat interativo ou one-shot)
Dockerfile         # imagem Python 3.12 slim
requirements.txt   # anthropic, requests, rich, python-dotenv
.env.example
config.json        # tokens (ignorado pelo git via .gitignore)
```

## Exemplos de prompts

- "mostra status geral do servidor e dos meus projetos"
- "reinicia o n8n no projeto blink"
- "adiciona a env `OPENAI_API_KEY=sk-...` no evolution-api preservando o resto"
- "qual a imagem atual do n8n? tem versão mais nova?"
- "cria um projeto chamado `staging` e adiciona um Postgres dentro"
- "monitora CPU e memória de todos os apps e me alerta o que tá pesado"

## Segurança

- O token do Easypanel concede acesso total à instância — proteja como senha.
- `config.json` e `.env` estão no `.gitignore`.
- Operações destrutivas pedem confirmação no chat.
- Não há autenticação no agente em si — se você expuser o CLI por HTTP, adicione
  sua própria camada de auth.

---

# Voice Agent (WhatsApp → Whisper → GPT → WhatsApp)

Serviço HTTP separado, no mesmo repositório, que:

1. Recebe webhook da Evolution API quando um paciente manda áudio no WhatsApp.
2. Baixa o áudio (base64 do payload, ou via `/chat/getBase64FromMediaMessage`).
3. Transcreve com **OpenAI Whisper** (`whisper-1`).
4. Gera resposta com **GPT-4o-mini** usando um system prompt orientado para
   clínica/atendimento ao paciente (não dá diagnóstico, encaminha para
   recepção, escalona emergências).
5. Envia a resposta em texto de volta pelo mesmo número via Evolution.

Mantém histórico curto de conversa por contato (8 turnos, expira em 6h).

## Estrutura

```
voice_agent/
├── __init__.py
├── settings.py     # carrega env vars + config.json
├── evolution.py    # cliente da Evolution API (send_text, get_audio_bytes)
├── transcribe.py   # OpenAI Whisper
├── responder.py    # OpenAI GPT + memória de conversa por número
├── pipeline.py     # orquestrador stateless (audio → transcript → answer → send)
├── webhook.py      # FastAPI app (POST /webhook + /health)
└── cli.py          # teste local: python -m voice_agent.cli arquivo.ogg
Dockerfile.voice    # imagem do voice_agent (uvicorn na :8000)
```

## Testando local com um áudio

```bash
# transcreve só, sem chamar GPT
python -m voice_agent.cli paciente.ogg --no-reply

# transcreve + gera resposta (não envia)
python -m voice_agent.cli paciente.ogg

# transcreve + responde + ENVIA para um número
python -m voice_agent.cli paciente.ogg --send 5561996630710
```

## Subindo o servidor webhook local

```bash
uvicorn voice_agent.webhook:app --host 0.0.0.0 --port 8000
```

## Deploy no Easypanel (mesma instância da Evolution)

1. **Build da imagem** (use GitHub source ou faça push pra um registry):
   - `Dockerfile.voice` é o Dockerfile a apontar.
2. **Criar serviço App no Easypanel** dentro do projeto `blink`:
   - Source: GitHub ou imagem.
   - Build → Dockerfile: `Dockerfile.voice`
3. **Variáveis de ambiente** (use o .env.example como base):
   - `OPENAI_API_KEY=sk-proj-...`
   - `EVOLUTION_BASE_URL=http://blink_evolution-api:8080`   ← URL interna
   - `EVOLUTION_API_KEY=429683C4C977415CAAFCCE10F7D57E11`
   - `EVOLUTION_INSTANCE=blink-0710`
   - `WEBHOOK_SECRET=<algo aleatório>`   ← protege o endpoint
4. **Adicione um domínio** (ex: `voz.seu-dominio.com.br`) apontando para porta 8000.
5. **Configure o webhook na Evolution** apontando para
   `https://voz.seu-dominio.com.br/webhook` (Evolution Manager → sua instância
   → Settings → Webhook). Ative o evento `MESSAGES_UPSERT`. Se você setou
   `WEBHOOK_SECRET`, adicione no header `X-Webhook-Secret`.

> Dica: dentro da rede Docker do Easypanel, o hostname do serviço Evolution
> é `<projeto>_<serviço>` — no seu caso `blink_evolution-api`. Use isso ao
> invés do domínio público pra evitar saída → entrada na internet.

## Fluxo no WhatsApp

```
Paciente grava áudio  →  Evolution recebe e dispara webhook
                      →  Voice Agent transcreve com Whisper
                      →  GPT gera resposta
                      →  Voice Agent chama Evolution sendText
                      →  Paciente recebe texto de volta
```

## Customização do prompt

Edite `DEFAULT_SYSTEM_PROMPT` em `voice_agent/responder.py` para ajustar tom,
escopo de atendimento e regras de escalonamento da sua clínica. Você também
pode passar `system_prompt` direto ao instanciar `Responder` (por exemplo,
carregando de um arquivo `.txt` editável).

## Custo aproximado (referência maio/2026)

- Whisper: ~$0.006 / minuto de áudio
- GPT-4o-mini: ~$0.15 por 1M tokens input, $0.60 por 1M output

Para uma clínica de porte pequeno, gira em centavos por conversa.
