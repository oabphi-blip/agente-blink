# Rollout dos 4 otimizadores — passo a passo

> Use este doc na 1ª sessão após `git push` dos commits 39fc250 + 3a5564f + ef15a26.

---

## 1. Validação antes de deployar

```bash
cd ~/Documents/Claude/Projects/AGENTE\ IA\ BLINK
python3 -m pytest tests/ -q
# Esperado: 584 passed (ou mais)
```

Se < 584, NÃO deployar. Investigar.

---

## 2. Deploy no Easypanel

Acesse: https://6prkfn.easypanel.host/projects/blink/app/agent

Clique no botão verde **Implantar** (canto superior esquerdo do app).
Aguarde toast "Aplicativo implantado" + logs:

```
INFO: Started server process [1]
INFO: Application startup complete
INFO: Uvicorn running on http://0.0.0.0:8000
INFO voice_agent.webhook [CRON BOOT] {'started': True, 'workers': [...]}
INFO voice_agent.webhook [SMOKE BOOT] worker_iniciado=False  ← (esperado, off por default)
```

Se `[SMOKE BOOT] worker_iniciado=False` aparecer, **deploy correto** —
o smoke worker está off (precisa ligar via env).

---

## 3. Validação pós-deploy (smoke manual contra prod)

```bash
SECRET="$(cat .env | grep WEBHOOK_SECRET | cut -d= -f2)"
curl -s "https://blink-agent.6prkfn.easypanel.host/admin/smoke-tick?secret=$SECRET" | python3 -m json.tool
```

Esperado: JSON com `ok: 5, total: 5, falhas: []`.

Se vier `ok: 4`, identificar qual cenário falhou e por quê (motivo no JSON).
Cenários: C1-saudacao, C2-pediatrico, C3-juliene-evasiva, C4-convenio-nao-aceito, C5-remarcacao.

---

## 4. Ligar otimizador #3 (Smoke contínuo) — RECOMENDADO

Easypanel → Ambiente:

```
SMOKE_ENABLED=1
SMOKE_INTERVALO_SEG=3600
```

(Opcional) Pra alertar no Slack quando smoke quebrar:

```
SLACK_WEBHOOK_SMOKE_URL=https://hooks.slack.com/services/...
```

Salvar → Implantar. No log aparece:

```
INFO voice_agent.webhook [SMOKE BOOT] worker_iniciado=True
INFO voice_agent.smoke_continuous [SMOKE] worker iniciado — intervalo=3600s cenarios=5
```

A partir daqui, a cada 1h o sistema roda os 5 cenários e alerta se algum quebrar.

---

## 5. Ligar otimizador #1 (Tool calling) — CUIDADOSO

**NÃO** ligar antes de observar a Lia respondendo bem por 24h com #2, #3, #4 ativos.

Quando virar:

```
LIA_TOOLS_ENABLED=1
```

A partir desse momento, a Lia usa tool calling estruturado em vez de
detector Haiku. O loop tem máximo 4 iterações por turno — se a Lia
ficar travada em tool_use repetido, sai e devolve a última resposta texto.

Como verificar se está usando tools? Procurar no log do Easypanel:

```
INFO voice_agent.responder [TOOLS] convo=... iters=N log=[{'name': 'oferecer_slot', ...}]
```

---

## 6. Rollback se algo der errado

```bash
cd ~/Documents/Claude/Projects/AGENTE\ IA\ BLINK
git revert HEAD~3..HEAD --no-edit  # reverte ef15a26 + 3a5564f + 39fc250
git push origin main
```

Depois clicar Implantar no Easypanel. Volta ao estado `234d4c1` (fix bug Juliene reativo mantido).

Para rollback PARCIAL (ex: só desligar tool calling):

```
LIA_TOOLS_ENABLED=0  # Easypanel env
```

---

## 7. Próximos passos depois do rollout

1. Acompanhar log do Easypanel pra ver alertas `[SMOKE BATCH] FALHOU`
2. Acompanhar Slack (se ligado) pra alertas em tempo real
3. Em 24h, decidir se vira `LIA_TOOLS_ENABLED=1`
4. Catalogar novos bugs em `lia-atendimento-blink/memoria/bugs-licoes/`
5. Adicionar cenário smoke a cada bug novo (`smoke_continuous.py::CENARIOS_CORE`)
