# SETUP GUIADO — LIA ENGINEER AUTÔNOMO

> Trabalhando juntos. **Você clica e assina, eu prossigo.**
> Tempo estimado: 25-35 minutos.
> A cada passo: você executa → me devolve o resultado → eu valido e sigo.

---

## PASSO 0 — PUSH do código (5 min) — VOCÊ FAZ SOZINHO

Antes de qualquer setup novo, o código de hoje precisa estar no GitHub.

**Ação:**
1. Abra o Finder → `Documents > Claude > Projects > AGENTE IA BLINK`
2. Duplo-clique em `PUSH_AUTONOMO_09-06.command`
3. Quando o macOS perguntar se quer abrir, clique **Abrir**
4. Aguarde aparecer `✅ PUSH CONCLUÍDO COM SUCESSO` no Terminal
5. Pode fechar a janela

**Me devolve:** print do final do Terminal OU só "ok push feito"

---

## PASSO 1 — GitHub Personal Access Token (3 min)

O token permite o Lia Engineer fazer git push automático quando aplica um fix.

### 1.1 Abrir a tela de gerar token (com escopos já pré-marcados)

🔗 **[Clique aqui pra abrir GitHub Tokens já preenchido](https://github.com/settings/tokens/new?description=Lia+Engineer+Autonomous+24h7&scopes=repo,workflow)**

A tela já vai vir com:
- ✅ Description: `Lia Engineer Autonomous 24h7`
- ✅ Escopo `repo` marcado
- ✅ Escopo `workflow` marcado

### 1.2 Configurar expiração

Em **Expiration**, escolhe **No expiration** (token permanente — Engineer roda 24/7).

Sim, eu sei — token permanente parece arriscado. Por isso:
- O Engineer SÓ usa esse token pra push de fixes em branches `lia-engineer/fix-*`
- GH Actions valida pytest antes de merge na main
- Você pode revogar a qualquer momento em https://github.com/settings/tokens

Se preferir mais conservador: 90 dias. Você renova trimestralmente.

### 1.3 Clicar em **Generate token** (botão verde no rodapé)

Vai aparecer um token começando com `ghp_...`.

### 1.4 Copiar e me passar

⚠️ Token aparece UMA VEZ. Se fechar a aba, perde.

**Me devolve:** cola o token aqui no chat assim:

```
GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Eu prossigo:**
- Salvo em `~/Documents/Claude/Projects/AGENTE IA BLINK/lia_engineer/.env.local` (arquivo local seu — gitignored, nunca vai pro repo)
- Configuro `git remote` pra usar HTTPS com token embutido no env
- Verifico push pode acontecer com `git ls-remote`

---

## PASSO 2 — Slack Webhook (5 min)

### 2.1 Criar o canal `#lia-engineer` no Slack

1. Abre Slack do Blink
2. Painel esquerdo → ➕ → **Criar canal**
3. Nome: `lia-engineer`
4. Tipo: público (recomendado) OU privado se preferir
5. Convidar apenas você no início

**Me devolve:** "ok canal criado"

### 2.2 Criar Incoming Webhook

🔗 **[Clique aqui pra abrir Slack Apps — Manage Apps](https://api.slack.com/apps)**

1. Clique no app **Blink** (se já tem) OU **Create New App** → **From scratch** → nome "Lia Engineer" → workspace Blink
2. Menu esquerdo → **Incoming Webhooks**
3. Toggle **Activate Incoming Webhooks** = ON
4. Botão **Add New Webhook to Workspace** (rodapé)
5. Selecione o canal **#lia-engineer**
6. **Allow**
7. Volta na tela com a lista — copie a URL da nova webhook (começa com `https://hooks.slack.com/services/T.../B.../...`)

**Me devolve:** cola a URL aqui assim:

```
SLACK_WEBHOOK_LIA_ENGINEER_URL=https://hooks.slack.com/services/T.../B.../...
```

**Eu prossigo:**
- Salvo em `.env.local`
- Disparo 1 mensagem de teste no canal pra confirmar funciona

---

## PASSO 3 — Easypanel — criar app `blink-engineer` (10 min)

### 3.1 Abrir Easypanel projeto Blink

🔗 **[Clique aqui pra abrir Easypanel — projeto blink](https://6prkfn.easypanel.host/projects/blink)**

### 3.2 Criar novo serviço

1. No projeto blink, botão **+ Service** (canto direito)
2. Escolha **App**
3. Nome: `engineer`
4. Source: **GitHub**
5. Owner: `oabphi-blip`
6. Repo: `agente-blink`
7. Branch: `main`
8. Build Type: **Dockerfile**
9. Dockerfile Path: `lia_engineer/Dockerfile`
10. Build Context: `.` (raiz do repo)
11. Salvar

**Me devolve:** "ok serviço criado"

### 3.3 Setar Envs

Vai em **Environment** desse serviço novo. Cole as 10 envs abaixo de uma vez (formato `KEY=VALUE` por linha — Easypanel aceita):

```
ANTHROPIC_API_KEY=<vou te passar — me responde "ok envs prontas" que eu te falo qual usar>
CLAUDE_OPUS_MODEL=claude-opus-4-6
GITHUB_USER=oabphi-blip
GITHUB_TOKEN=<o ghp_... do Passo 1>
LIA_ENGINEER_REPO_ROOT=/app
LIA_ENGINEER_PROD_URL=https://blink-agent.6prkfn.easypanel.host
LIA_ENGINEER_MAX_FIXES_DIA=3
LIA_ENGINEER_LIMIAR_CONFIANCA=70
LIA_ENGINEER_LOOKBACK_MIN=30
LIA_ENGINEER_INTERVAL_SEG=300
WEBHOOK_SECRET=<vou te falar qual — mesmo do agent atual>
SLACK_WEBHOOK_LIA_ENGINEER_URL=<o https://hooks.slack.com/... do Passo 2>
KOMMO_TOKEN=<mesmo KOMMO_TOKEN do agent atual — eu confirmo depois>
KOMMO_API_BASE=https://kommo-proxy.oabphi.workers.dev/api/v4
LIA_ENGINEER_ENABLED=0
```

⚠️ A última env (`LIA_ENGINEER_ENABLED=0`) deixa o agente **desligado** até a gente validar tudo em dry-run. Depois muda pra `1`.

**Me devolve:** "ok envs coladas, faltando X, Y, Z" — eu te passo os valores que faltam um por um.

### 3.4 Salvar + Deploy

Botão **Save** → **Deploy** (build leva ~3-5 min).

**Me devolve:** print da tela de logs quando build virar `Deployed` (verde)

---

## PASSO 4 — Validar 1 tick dry-run (3 min)

### 4.1 Pelo Easypanel

1. Vai no serviço `engineer` → aba **Console** ou **Terminal**
2. Digita:

```bash
python -m lia_engineer.cli tick --dry-run
```

3. Vai imprimir JSON tipo:

```json
{
  "tick_em": "...",
  "bugs_detectados": 0,
  "resultados": {"escalado": 0, "fix_aplicado": 0, ...}
}
```

**Me devolve:** cola o JSON aqui (pode ser parcial)

### 4.2 Eu valido

Verifico:
- Conectou no Kommo (sem erro 403)
- Conectou no Anthropic (token válido)
- Slack recebeu mensagem (pode até ser "0 bugs detectados — Engineer arrancou")
- State persistiu em /tmp/lia_engineer_state.json

Se 100% OK → mudamos `LIA_ENGINEER_ENABLED=1` e ele entra em produção 24/7.

---

## PASSO 5 — Ligar produção (1 min)

Após dry-run OK:

1. Easypanel → blink-engineer → Environment
2. Editar `LIA_ENGINEER_ENABLED=0` → **mudar pra 1**
3. Save → Redeploy (rápido, só env reload)

A partir de agora:
- Tick a cada 5 min
- Detecta bug → propõe fix Opus → testa → push → smoke → Slack
- Se ruim → rollback automático

---

## RESUMO ENXUTO DO QUE VOCÊ FAZ vs EU FAÇO

| Passo | VOCÊ | EU |
|---|---|---|
| 0. Push código | Duplo-clique `.command` | Já preparei o script |
| 1. GitHub PAT | Clica link → Generate → cola | Salvo em `.env.local` + testo push |
| 2. Slack webhook | Cria canal + webhook → cola URL | Disparo msg teste |
| 3. Easypanel envs | Cria app + cola 15 envs | Te passo os 4-5 valores que faltam |
| 4. Build + deploy | Save + aguardar build | Monitoro logs |
| 5. Dry-run | Roda comando no console | Valido JSON e libero produção |
| 6. Ligar prod | Muda 0→1 | Vejo primeiro tick real |

---

## SE ALGO DER ERRADO

**Push falhou** → me passa output do Terminal, eu diagnostico
**Token PAT não funciona** → testo `git ls-remote https://USER:TOKEN@github.com/...` e te falo qual escopo faltou
**Slack webhook 404** → URL pode ter expirado, refaço passo 2.2
**Easypanel build vermelho** → leio o log, ajusto Dockerfile ou pyproject, novo push
**Dry-run dá erro de KOMMO_TOKEN** → renovo Kommo OAuth (#242 já estava pendente — resolveria 2 coisas de uma vez)

---

**Última atualização:** 09/06/2026 noite.
