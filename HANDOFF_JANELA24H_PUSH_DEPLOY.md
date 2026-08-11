# Handoff — Deploy da observabilidade JANELA 24H

> Feature **pronta e commitada localmente**. Falta só **push + deploy**.
> Este arquivo é um plano de ação para o **Claude Code** (terminal) concluir,
> ou para o Fábio rodar manualmente. Gerado em 05/07/2026 (sessão Cowork).

---

## PROMPT PRONTO PRA COLAR NO CLAUDE CODE

Copie tudo abaixo e cole no Claude Code aberto na pasta do projeto:

```
Estou na pasta do repo agente-blink. Já existe um commit local (feature
"janela24h" — observabilidade do prazo de 24h do WhatsApp) que NÃO foi
enviado pro GitHub por falha de autenticação.

Tarefa:
1. Confirme o commit local: `git log --oneline -3` (deve haver um commit
   "feat(janela24h): observabilidade do prazo de 24h WhatsApp").
2. Faça o push pra origin/main. O repo é privado
   (https://github.com/oabphi-blip/agente-blink.git). Se a autenticação
   HTTPS falhar, me oriente a rodar `gh auth login` (device flow no
   navegador) ou a criar um PAT classic com escopo `repo` — mas NÃO peça
   pra colar token invisível no prompt; prefira gh auth login.
3. Depois do push, confirme que `git status` está limpo e que o commit
   aparece em origin/main.
4. Rode a suíte de testes da feature:
   `python3 -m pytest tests/test_janela_24h_observabilidade.py -q`
   (deve dar 23 passed).

Não altere nenhum arquivo — só push + validação.
```

---

## O QUE JÁ ESTÁ FEITO (não refazer)

**Campos criados no Kommo (via API, já visíveis no card do lead):**

| Campo | Field ID | Tipo | Enums |
|---|---|---|---|
| ÚLTIMA MENS PACIENTE | 1260984 | date_time | — |
| JANELA 24H | 1260986 | select | Aberta=927302 · Expirando=927304 · Fechada=927306 |

**Commit local (6 arquivos, +481 linhas) — feature `janela24h`:**

- `voice_agent/campos_acompanhamento.py` — `classificar_janela_24h`,
  `segundos_restantes_janela`, `campos_janela_24h` + IDs reais dos campos.
- `voice_agent/kommo.py::update_lead_fields` — grava os 2 campos novos
  (guardado por id>0).
- `voice_agent/pipeline.py::_sync_kommo_safely` — a cada inbound carimba o
  timestamp no Kommo E no Redis (`blink:janela:ultima_msg_paciente:{lead}`).
- `voice_agent/cron_interno.py` — worker `janela24h` (15min, 24h) que
  recalcula o status durante o silêncio do paciente (aberta→expirando→fechada)
  + registrado em `iniciar_cron`.
- `voice_agent/webhook.py` — endpoint `/admin/janela-24h-tick` (trigger manual).
- `tests/test_janela_24h_observabilidade.py` — 23 testes (todos verdes local).

**Régua de classificação:** <22h = Aberta · 22–24h = Expirando · ≥24h = Fechada.

---

## DEPOIS DO PUSH — DEPLOY (Easypanel)

1. O push em `main` dispara **auto-deploy** no Easypanel (2–5 min).
   App: https://6prkfn.easypanel.host/projects/blink/app/agent
2. Na aba **Ambiente**, garantir:
   ```
   BLINK_CRON_ENABLED=1
   ```
   (opcionais, já têm default: `JANELA24H_TICK_ENABLED=1`,
   `JANELA24H_CADA_MIN=15`, `JANELA24H_LIMITE_LEADS=200`)
3. **Implantar**.
4. Validar:
   ```
   curl "https://blink-agent.6prkfn.easypanel.host/admin/janela-24h-tick?secret=$WEBHOOK_SECRET"
   ```
   Esperado: `{"ok":true,"varridos":N,"atualizados":M,...}`

---

## COMANDOS DE PUSH (se rodar manual)

```bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

# recomendado: autenticar sem digitar token invisível
gh auth login          # GitHub.com → HTTPS → Login with a web browser

git push origin main
```

Se não tiver `gh`, use um PAT classic com escopo **`repo`**
(github.com/settings/tokens/new) no prompt de Password.

---

## POR QUE NÃO SAIU NESTA SESSÃO

O ambiente Cowork bloqueia digitação em Terminal (tier de segurança) e a
inserção de tokens — por isso o push precisa sair do Claude Code (terminal
nativo) ou da mão do Fábio. Todo o resto (código, campos Kommo, testes) já
está pronto e testado.
