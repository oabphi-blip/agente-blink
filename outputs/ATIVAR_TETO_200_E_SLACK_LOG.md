# Ajustar motor de reativação — passo a passo Easypanel

Status atual confirmado em `https://blink-agent.6prkfn.easypanel.host/reactivation/status`:

| Parâmetro | Hoje | Alvo |
|---|---|---|
| enabled | ✅ true | manter |
| dry_run | ✅ false | manter |
| channel | whatsapp_cloud_8133 | manter |
| template_name | 1089_mens_ativar_conv_parada_qz7kbz | manter |
| **daily_cap** | **30** ← TETO | **200** |
| daily_count | 30 / 30 (atingiu) | resetar amanhã 0h |
| min_interval_min | 8 | manter (ou baixar pra 4) |
| business_hours | 8h–18h seg–sáb | manter |
| **slack_log** | ❌ false | **true (ligar)** |

---

## Passos (5 minutos no Easypanel)

### 1. Login
- Abrir `https://6prkfn.easypanel.host`
- Logar com email + senha do Easypanel (só você tem)

### 2. Navegar pro app
- Projetos → `blink` → `agent`
- URL final: `https://6prkfn.easypanel.host/projects/blink/app/agent`

### 3. Aba "Environment"
- Clicar na aba **Environment** (ou Variables / Env)

### 4. Editar/adicionar variáveis

**REACTIVATION_DAILY_CAP**
- Procurar a linha existente
- Mudar valor de `30` pra `200`
- Se não existir, adicionar: `REACTIVATION_DAILY_CAP=200`

**SLACK_WEBHOOK_URL** (nova)
- Adicionar linha: `SLACK_WEBHOOK_URL=<webhook>`
- O webhook vem do Slack → Apps → Incoming Webhooks → criar pro canal `#ativação-de-leads-de-forma-continua`
- Exemplo de formato: `https://hooks.slack.com/services/T.../B.../...`

**(Opcional) REACTIVATION_MIN_INTERVAL_MIN**
- Se quiser disparo mais rápido: mudar de `8` pra `4` (dispara cada 4 min)
- Com cap=200 e intervalo=4min, em 8h dispara até 120 — folga em relação ao cap

### 5. Salvar + Restart
- Botão **Save** (ou Apply)
- Botão **Restart** ou **Redeploy**
- Aguardar ~30s

### 6. Validar
- Abrir em outra aba: `https://blink-agent.6prkfn.easypanel.host/reactivation/status`
- Confirmar:
  - `"daily_cap": 200`
  - `"slack_log": true`
- Aguardar próximo ciclo do cron (10 min) — deve aparecer mensagem no Slack quando disparar

---

## O que isso destrava

| Hoje | Depois |
|---|---|
| 30 ativações/dia | 200 ativações/dia (6,6x) |
| Fila de ~200 leads varrida em 7 dias | Varrida em ~1 dia |
| Você não vê o que ele faz | Log no Slack a cada disparo |
| Atinge teto e para | Folga 100+/dia pra leads novos |

---

## Cuidados

- **Limite Meta WhatsApp Business**: contas novas têm limite de ~250 conversas/24h. Se você tem conta com tier maior (1k+), seguro. Se não, começar com 100 e ir subindo.
- **Conta da clínica**: o cap considera o conjunto de templates disparados pelo 8133. Se o Salesbot (lembretes D-1/D-0) também dispara via 8133, somar tudo.
- **Backup**: anota o valor antigo (`30`) antes de mudar — se algo der errado, reverte.

---

## Se quiser fazer ainda mais

Próximo round depois de ligar o cap:

- **Adicionar status `5.1-NO-SHOW` separado**: pacientes no-show recebem template diferente (mais acolhedor)
- **Webhook Meta Lead Form → Kommo**: leads do Meta entram em 30s
- **Painel `gap de amanhã`**: cron 18h lê agenda Medware, vê slots vazios, dispara reativação focada

Salvo em: `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/outputs/ATIVAR_TETO_200_E_SLACK_LOG.md`
