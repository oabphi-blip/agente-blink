# Prompt pronto pra Claude Chrome — Lovable Fase 2

**Como usar:** abre Claude Chrome (extensão), cola o bloco abaixo. Ele navega pelo browser já logado com sua conta.

**IMPORTANTE ANTES DE COMEÇAR:**
- Você já criou conta Supabase e Lovable manualmente (Fase 0)
- Você tem em mãos: `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`
- Claude Chrome vai pausar e pedir esses valores quando precisar

---

```
Você vai criar um projeto Lovable pra Blink Oftalmologia usando meu Chrome já logado.

CONTEXTO:
- Já tenho conta em lovable.dev (login com email/Google já feito)
- Já tenho conta Supabase criada (Fase 0 concluída)
- Projeto Supabase provisionado: nome "blink-lovable-fase2", região sa-east-1
- SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY vou colar quando você pedir
- Objetivo: criar dashboard Lovable que consulta Supabase pra mostrar estado dos leads Blink em tempo real

FASE 2 — CRIAÇÃO DO PROJETO LOVABLE:

PASSO 1 — Verificar login Lovable
- Navega em https://lovable.dev/dashboard
- Se pedir login, pausa e chama Fábio (ele faz login manual)
- Se logado, prossegue

PASSO 2 — Criar novo projeto
- Clica em "New Project" ou botão equivalente
- Nome: "Blink Fase 2 Dashboard"

PASSO 3 — Colar prompt inicial
Quando Lovable pedir "Descreva seu app", cola EXATAMENTE isto:

"""
Preciso de um dashboard operacional pra clínica de oftalmologia com 4 áreas:

1. VISÃO GERAL — cards com:
   - Total de leads em atendimento hoje
   - Última resposta da Lia (agente WhatsApp) em minutos atrás
   - Slots ofertados nas últimas 24h vs confirmados
   - Semáforo de integrações: Kommo, Medware, WhatsApp

2. LISTA DE LEADS ATIVOS — tabela com filtro por etapa do funil:
   Colunas: nome_paciente, motivo_consulta, medico, unidade, convenio,
   status_conversa, proxima_acao, ultima_msg_lia_ts, link_kommo
   Filtros: etapa (3-AGENDAR / 4-APRESENTADO / 5-REAGENDAR / 6-AGENDADO / 7-CONFIRMAR), convênio, médico
   Ordenação padrão: mais recente primeiro

3. AGENDA POR MÉDICO — visão semanal:
   Colunas dias, linhas horários (08h-18h)
   Cores: verde=disponível, amarelo=reservado 10min, vermelho=ocupado, cinza=fora de expediente
   Filtro por médico (Karla / Fabrício) e unidade (Asa Norte / Águas Claras)

4. LOG DE EVENTOS — timeline dos últimos 100 eventos:
   Colunas timestamp, tipo (turn_complete, agendou, cancelou, no_show, escalou_humano), lead_id, resumo
   Filtro por tipo

DADOS vêm de tabelas Supabase:
- medware_agenda (colunas: cod_medico, cod_unidade, data, hora, status)
- events (event_id, timestamp, tipo, lead_id, pacient_ref, payload)
- patients_cache (paciente_id, nome, convenio_atual)

Auth: só usuários logados. Passa via Supabase Auth.

Layout: dashboard denso profissional, tipo Retool/Metabase, não landing page. Cores neutras (cinza, azul escuro).

Framework: React + Tailwind. Componentes shadcn/ui. Refresh automático a cada 30s.
"""

PASSO 4 — Aguardar geração
- Lovable vai gerar o app (5-10 min)
- Enquanto isso, verifica se aparece progress bar
- Se demorar mais que 15 min, screenshot e me avisa

PASSO 5 — Conectar Supabase
- No painel Lovable, procura aba "Integrations" ou "Settings → Supabase"
- Se pedir SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY, PAUSA e pede pro Fábio colar
- Cola as credenciais quando ele mandar
- Salva

PASSO 6 — Preview do app
- Clica em "Preview" pra ver se está funcionando
- Se aparecer erro de RLS ou permissão, screenshot e me manda o erro exato
- Se aparecer tela vazia (sem dados), tudo bem — vamos popular depois no shadow mode

PASSO 7 — Publicar
- Clica em "Publish" ou "Deploy"
- Aguarda deploy (2-3 min)
- Copia URL final publicada (algo tipo https://blink-fase2-dashboard.lovable.app)

PASSO 8 — Screenshot final
- Tira screenshot da tela final do dashboard preview
- Me manda a URL publicada

ENTREGA:
- URL Lovable publicada
- Screenshot do dashboard funcionando
- Confirmação que Supabase conectou

REGRAS:
- Se pedir 2FA/SMS/aprovação email → PAUSA e chama Fábio
- Se Lovable der erro 429 rate limit → espera 5 min e tenta de novo
- NÃO gasta créditos com edições estéticas — só cria estrutura base
- Se prompt inicial der errado (Lovable não entendeu), pergunta pro Fábio antes de editar
```

---

## Após Fase 2 concluída, mande pro Claude Code:

```
Claude Chrome terminou Fase 2. URL publicada: <copiar URL aqui>
Prossegue pra Fase 3 (endpoint agent) com essa URL como LOVABLE_ENDPOINT_URL.
```

---

## Se algo der errado

- **"Lovable não entendeu meu prompt"** → cola pra mim o que ele gerou, eu ajusto
- **"Supabase RLS bloqueou consulta"** → me passa erro exato, eu corrijo policies
- **"App Lovable ficou 404 depois do deploy"** → me passa URL e resposta HTTP
