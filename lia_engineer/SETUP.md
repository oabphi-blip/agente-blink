# Setup do Lia Engineer Autônomo

Tempo total: ~30 minutos. Pode rodar **local no Mac** OU **em servidor Easypanel**.

## Pré-requisitos

- ✅ Repo Git Blink já clonado (você já tem)
- ✅ `ANTHROPIC_API_KEY` válida (já tem, mesmo da Lia)
- ✅ `WEBHOOK_SECRET` Blink agent (você tem)
- ⏳ **Novo:** GitHub Personal Access Token com escopos `repo` + `workflow`
- ⏳ **Novo:** Slack webhook pra canal `#lia-engineer`
- ⏳ **Novo:** Token Kommo (você já gerou no #242)

## Opção A — Rodar local no Mac (mais simples pra testar)

```bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

# 1. Instalar deps (já vem no pyproject.toml — anthropic, requests)
pip install -e .

# 2. Setup env vars
cat > lia_engineer/.env <<EOF
ANTHROPIC_API_KEY=sk-ant-...
LIA_ENGINEER_GH_USER=oabphi-blip
LIA_ENGINEER_GH_TOKEN=ghp_...
LIA_ENGINEER_REPO_ROOT=/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK
WEBHOOK_SECRET=...
SLACK_WEBHOOK_LIA_ENGINEER_URL=https://hooks.slack.com/...
KOMMO_API_BASE=https://univeja.kommo.com/api/v4
KOMMO_TOKEN=...
LIA_ENGINEER_PROD_URL=https://blink-agent.6prkfn.easypanel.host
LIA_ENGINEER_MAX_FIXES_DIA=3
LIA_ENGINEER_LIMIAR_CONFIANCA=70
LIA_ENGINEER_LOOKBACK_MIN=30
EOF

# 3. Rodar 1 tick manual (dry run)
python3 -m lia_engineer.cli tick --dry-run

# 4. Se OK, rodar contínuo (loop infinito 5min)
nohup python3 -m lia_engineer.cli daemon > /tmp/lia_engineer.log 2>&1 &
```

## Opção B — Rodar no Easypanel como app separado

Mais robusto, fica 24/7 sem depender do Mac estar ligado.

```bash
# 1. Build container
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
docker build -f lia_engineer/Dockerfile -t blink-engineer:latest .

# 2. No Easypanel UI:
#    Projects → blink → Services → New App "blink-engineer"
#    Source: GitHub oabphi-blip/agente-blink branch main
#    Build: Dockerfile path = lia_engineer/Dockerfile
#    Env vars: copiar todas do bloco acima
#    Cron: */5 * * * *  python -m lia_engineer.cli tick
```

## Validar funcionamento

```bash
# 1. Forçar 1 tick manual contra produção (lê notas reais Kommo)
python3 -m lia_engineer.cli tick

# Esperado:
# {
#   "tick_em": "2026-06-09T20:50:00Z",
#   "bugs_detectados": 0-5,
#   "resultados": {
#     "fix_aplicado": 0,
#     "escalado": 1,   ← bugs novos vão pra revisão humana
#     ...
#   }
# }

# 2. Slack deve ter recebido 1 alerta pra cada bug detectado

# 3. Endpoint de status (se rodando como app)
curl https://blink-engineer.6prkfn.easypanel.host/status
```

## Configurar Slack #lia-engineer

1. https://api.slack.com/apps → seu app Blink → Incoming Webhooks
2. Activate → Add New Webhook to Workspace → escolher `#lia-engineer`
3. Copiar URL → setar `SLACK_WEBHOOK_LIA_ENGINEER_URL`

## Reverter / pausar manual

```bash
# Pausar engineer
curl -X POST $PROD/admin/engineer/pause?secret=$WS

# Resumir
curl -X POST $PROD/admin/engineer/resume?secret=$WS

# Status
curl $PROD/admin/engineer/status?secret=$WS
```

## Limites cobertos pelos guardrails

| Risco | Mitigação |
|---|---|
| Opus propõe fix ruim | Pytest local antes do push (rejeita se vermelho) |
| Fix passa pytest mas quebra prod | Smoke test pós-deploy + rollback automático |
| Engineer entra em loop de fix-revert | MAX 3 rollbacks consecutivos → pausa total |
| Custo de tokens explode | MAX 3 fixes/dia + cooldown 30min entre fixes |
| Bug muito complexo (precisa humano) | Limiar confiança 70 — abaixo escala humano |
| GitHub token vaza | Fica só em env Easypanel (não em código) |
| Engineer faz mudança em horário ruim | Configurável via cron (ex: só 02-06h BRT) |

## Quanto economiza vs Cowork

- Sessão Cowork pra fix médio = ~30min + custo Claude.ai
- Lia Engineer fix médio = ~5min + ~$0.20 em tokens
- Volume estimado: 5-10 bugs/dia detectáveis automaticamente
- **Economia: 2-5h/dia do seu tempo + ~$200/mês em custo Cowork**

## O que o engineer NÃO faz (limites honestos)

- Não decide trade-offs de produto (mudança no fluxo Blink, novos templates Meta)
- Não corrige bugs em infra (Easypanel caiu, Redis OOM)
- Não cria features novas — só corrige bugs indexados em padrões
- Não substitui revisão humana pra fixes high-risk (escala)
- Não aprende prompts da Lia sozinho (você ainda decide o que ela diz)
