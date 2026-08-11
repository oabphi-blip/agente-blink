# Plano de Ação — Lovable Fase 2 em Produção

**Data:** 03/07/2026
**Meta:** subir Lovable Fase 2 pra prod dividindo trabalho entre você, Claude Chrome e Claude Code.
**Tempo total estimado:** 3h (com o trabalho paralelo).

---

## Divisão de responsabilidade

| Quem | O que faz | Por que |
|---|---|---|
| **Você (irredutível)** | Criar contas, ativar cartão, aprovar SMS/email | Só você tem CPF, telefone e cartão |
| **Claude Chrome** | Navegar em `lovable.dev` e `supabase.com` já logado, clicar em botões, colar prompt | Tem sessão do navegador do seu Mac |
| **Claude Code** | Rodar `supabase CLI`, aplicar migrations, adicionar endpoints no agent, commit, push | Tem terminal + acesso ao repo |

---

## Fase 0 — Pré-requisitos (VOCÊ, 15 min)

**Objetivo:** ter contas + credenciais prontas antes de acionar os Claudes.

1. Cria conta Supabase em https://supabase.com (email + telefone SMS)
2. Cria organização "Blink Oftalmologia"
3. Cria projeto novo: **nome** `blink-lovable-fase2` · **região** `sa-east-1` (São Paulo) · **senha DB** anota num lugar seguro
4. Aguarda ~2 min o projeto provisionar
5. Vai em **Settings → API** e copia:
   - `Project URL` (algo tipo `https://xxxxx.supabase.co`)
   - `service_role key` (secret, NÃO o anon)
6. Cria conta Lovable em https://lovable.dev (login com Google ou email)
7. Ativa plano Pro (US$ 20/mês) OU usa trial free 14 dias
8. **Ao terminar, cola essas 3 credenciais num arquivo `.env` local:**
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
   LOVABLE_ACCOUNT=seu_email@blink.com.br
   ```

---

## Fase 1 — Claude Code aplica schema Supabase (30 min, autônomo)

**Você abre Claude Code no Terminal e cola o prompt do arquivo:**
`PROMPT_CLAUDE_CODE_LOVABLE.md`

Ele vai:
1. Instalar Supabase CLI se não tiver
2. Fazer `supabase login` (pode pedir 1 confirmação sua)
3. Linkar ao projeto usando `SUPABASE_URL`
4. Aplicar migrations com as 6 tabelas do briefing (medware_agenda, medico_ferias, medware_sync_log, events, patients_cache, sync_lock)
5. Aplicar RLS policies restringindo acesso ao service_role
6. Verificar via `psql` que tabelas existem
7. Deploy função Edge `/receive_event` (opcional, se usar Supabase Edge Functions)
8. Confirmar tudo verde

**Saída esperada:** Claude Code responde "Schema aplicado. 6 tabelas criadas. RLS ativo. Fase 1 OK."

---

## Fase 2 — Claude Chrome cria projeto Lovable (30 min, semi-guiado)

**Você abre Claude Chrome (extensão) e cola o prompt do arquivo:**
`PROMPT_CLAUDE_CHROME_LOVABLE.md`

Ele vai:
1. Navegar em https://lovable.dev/dashboard
2. Clicar em "New Project"
3. Colar o prompt inicial já pronto (que descreve o dashboard Blink)
4. Aguardar Lovable gerar app (~5-10 min)
5. Ir na aba **Integrations → Supabase**
6. Colar `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` que você preparou
7. Ativar RLS bypass no lado Lovable
8. Publicar (`Deploy`)
9. Copiar URL final do app publicado

**Saída esperada:** Claude Chrome responde "Projeto Lovable publicado em `https://blink-fase2.lovable.app`. Integração Supabase OK."

**Ponto de intervenção sua:** se Lovable pedir confirmação de email ou 2FA, você aprova manualmente.

---

## Fase 3 — Claude Code adiciona endpoint no agent (20 min, autônomo)

**Você volta pro Claude Code e pede pra ele:**
"Adicionar endpoint /lovable/events no webhook.py conforme briefing, com HMAC signing. Configurar envs LOVABLE_ENDPOINT_URL e LOVABLE_SIGNING_KEY. Modificar pipeline.py pra emitir eventos após cada turn. Commit + push."

Ele vai:
1. Ler `BRIEFING_LOVABLE_FASE2_BLINK.md` seção 6
2. Implementar `POST /lovable/events` com validação HMAC-SHA256
3. Envs novas: `LOVABLE_ENDPOINT_URL`, `LOVABLE_SIGNING_KEY` (gera 64 chars hex)
4. Em `pipeline.py`, após cada turn, `POST` evento `turn_complete` pra `LOVABLE_ENDPOINT_URL`
5. Commit + push
6. Você adiciona as 2 envs no Easypanel

---

## Fase 4 — Sync Medware → Supabase (Claude Code, 30 min autônomo)

**Prompt continuidade:**
"Criar cron worker que a cada 5min chama Medware Agenda/Listar janela 30d e faz upsert em medware_agenda no Supabase. Log em medware_sync_log. Alerta Slack se 3 falhas seguidas."

Ele vai:
1. Criar `voice_agent/lovable_sync.py` com cliente Supabase
2. Cron interno (segue padrão de `cron_interno.py` que já existe)
3. Upsert com chave `(cod_medico, cod_unidade, data, hora)`
4. Alerta via `SLACK_WEBHOOK_BUGS_URL`
5. Commit + push

**Você faz:** duplo clique no `.command` de push que ele gera.

---

## Fase 5 — Shadow mode (48h automático)

Toggle `LIA_USA_LOVABLE=shadow` no Easypanel.

Nesse modo:
- Lia continua usando lógica atual pra decidir resposta
- MAS também consulta Supabase e loga o que TERIA respondido usando Lovable
- Comparação em `blink:shadow_diff:{lead_id}` no Redis
- Endpoint `/admin/shadow-diff-report` mostra top 20 discrepâncias

**Passa 48h monitorando o dashboard.** Se < 5% discrepâncias, pode ir pra Fase 6.

---

## Fase 6 — Switch on (15 min + monitoramento)

`LIA_USA_LOVABLE=1` no Easypanel. Implantar.

Monitor primeiros 2h no `/admin/dashboard` (que você acabou de subir).

**Rollback:** `LIA_USA_LOVABLE=0` → Implantar (30 seg).

---

## Métricas de sucesso pós-implementação

| Métrica | Antes | Alvo pós-Lovable |
|---|---|---|
| Latência "consultar disponibilidade" | 8-15 seg | < 200 ms |
| Taxa de "deixa eu reconsultar" / 1000 turns | ~6% | < 0.5% |
| Slots oferecidos por conversa AGENDA | ~0.3 | > 1.8 |
| Conversão "oferta → confirma slot" | ~28% | > 45% |
| Bug Thamilla/coerência pós-agendado | recorrente | 0 |
| Bug Victor/oferta de slot | recorrente | 0 |

---

## Checklist de handoff (o que passar pra cada Claude)

**Claude Code** precisa saber:
- Caminho do repo: `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`
- Credenciais Supabase: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
- Que já tem Anthropic API key configurada
- Que use `.env.local` (não commita)
- Padrão de commit já existente no repo (veja últimos)

**Claude Chrome** precisa saber:
- Já está logado no Chrome com sua conta Google/email
- Sessões Lovable e Supabase já ativas
- Prompt inicial já pronto (arquivo `PROMPT_CLAUDE_CHROME_LOVABLE.md`)
- Se pedir 2FA, pausa e chama você

---

## Riscos e mitigações

1. **Custo Lovable US$ 20/mês** — se preferir só testar, use trial 14 dias.
2. **Supabase free tier 500 MB** — suficiente pra Fase 1 + Fase 2 por ~6 meses.
3. **Race condition sync Medware** — mitigado por `medware_sync_log` + Slack alert.
4. **Lovable gera código bugado** — sempre revisar antes de publicar. Lovable pode gerar chumbo.

---

## Se algo travar

**Não me passa problema. Me passa o output do erro.** Exemplo:

- "Claude Code disse: `ERROR: relation medware_agenda already exists`"
  → Eu respondo: "Ok, tabela já existe. Peça pra ele rodar `DROP TABLE IF EXISTS` primeiro ou pular schema Fase 1."

- "Claude Chrome disse: `Lovable retornou 429 rate limit`"
  → Eu respondo: "Espera 5 min e pede pra tentar de novo."

---

**FIM DO PLANO MASTER.** Próximos 2 arquivos são os prompts prontos pra cada agent.
