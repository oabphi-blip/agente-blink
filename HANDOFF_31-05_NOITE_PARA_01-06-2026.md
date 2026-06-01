# Handoff — Sessão noite 31/05/2026 → 01/06/2026

> Continuação do dia que começou com `HANDOFF_31-05_PARA_01-06-2026.md`.
> Esta sessão noturna foi disparada pelo bug do **lead 24053159 Juliene**
> e terminou com 4 otimizadores arquiteturais commitados.

---

## TL;DR — o que foi feito hoje à noite

1. **Bug Juliene investigado, mitigado, blindado** — `_viola_promete_retorno_humano` no `responder.py` + bloco AGENDA INDISPONÍVEL no system prompt + log.ERROR em `pipeline.py`. Commit `234d4c1` (fix reativo), deployado e validado em prod (5/5 smoke cenários verdes).
2. **4 otimizadores arquiteturais codados** (commits `39fc250` e `3a5564f`, ainda **NÃO deployados**):
   - #4 Checklist dados mínimos (always-on)
   - #3 Smoke contínuo (opt-in `SMOKE_ENABLED=1`)
   - #2 State machine Redis (always-on)
   - #1 Tool calling estruturado (opt-in `LIA_TOOLS_ENABLED=1`)
3. **24 áudios Karla pausados** — descobrimos que `Dra.` virava "DOUTOR" no TTS; roteiros reescritos com "Doutora Karla" por extenso; persona mudou pra **Ariany (secretária)** com voz `alloy`. Comando no clipboard do Fábio, ele decidiu rodar amanhã.
4. **Intervenção manual no lead Juliene** — mensagem enviada via Kommo Chat às 21:56 oferecendo 02/06 09:00 e 09/06 09:30 + pedindo nome completo Daniel + CPFs. Pipeline auto-preencheu `1.DIA SEM CONVÊNIO` e `2.DIA SEM CONVÊNIO`. Lia respondeu por cima com os mesmos slots — confirma que era intermitência Medware, não quebra permanente.

**584 testes pytest passando, +129 vs início da sessão noite.**

---

## Lead 24053159 — Juliene Siman (Daniel, 3 anos, estrabismo)

- Etapa: **3-AGENDAR** (102560495)
- Médico: Dra. Karla Delalíbera
- Unidade: Águas Claras (cod 3)
- Convênio: Não se aplica (.PARTICULAR, codPlano 1)
- Pagamento escolhido: Cartão 2x R$ 335
- Preferência: Terça-feira manhã, meio (9h-10h30)

**Bug original (20:43)**: Lia respondeu "Vou registrar sua preferência para a equipe finalizar — retorno em horário comercial (seg–sex, 8h–18h)". Frase **não existia em nenhum arquivo**. Causa: `ctx["agenda"]` chegou vazio (Medware intermitente) e os 4 filtros pós-geração não cobrem esse padrão de evasão.

**Status atual**: aguardando resposta da Juliene. Quando ela mandar nome completo Daniel + CPFs + escolher 1 dos 2 slots, gravar via `salvar_agendamento` Medware + mover lead pra 5-AGENDADO (101507507).

---

## Commits da sessão (ordem cronológica)

```
234d4c1 fix(responder): bloquear alucinação 'vou registrar pra equipe finalizar' (bug Juliene)
39fc250 feat: otimizadores arquiteturais #2 #3 #4 (defesa preventiva)
3a5564f feat: otimizador arquitetural #1 — tool calling estruturado (opt-in)
```

`234d4c1` **JÁ está em prod** (Easypanel pegou via Implantar).
`39fc250` + `3a5564f` **AINDA NÃO** — depende do git push do Fábio.

---

## O que está em PROD agora (validado por smoke manual)

5 cenários testados via `/admin/simulate-inbound?dry_run=true`:

| Cenário | Resultado | Resposta da Lia |
|---|---|---|
| C1 saudação `"oi"` | ✅ | "Olá! 👋 Eu sou a Lia, da Blink Oftalmologia. Como prefere conversar?" |
| C2 pediátrico estrabismo | ✅ | Coleta motivo da consulta (rotina x sintoma) |
| C3 **frase Juliene** `"prefiro terca de manha meio"` | ✅ | "Antes de qualquer pagamento, deixa eu te oferecer os horários reais..." — **bug bloqueado** |
| C4 `"voces aceitam Amil"` | ✅ | "Amil ainda não está credenciado... incentivos especiais... 1️⃣ sem convênio 2️⃣ somente convênio" |
| C5 `"preciso remarcar"` | ✅ | "Sem problemas! Antes de te oferecer novos horários, me confirma data atual" |

---

## Pendências pra você (Fábio)

### 1. Push + deploy dos otimizadores (2 minutos)

```bash
cd ~/Documents/Claude/Projects/AGENTE\ IA\ BLINK && git push origin main
```

Sobe `39fc250` + `3a5564f`. Depois clicar **Implantar** em https://6prkfn.easypanel.host/projects/blink/app/agent.

### 2. Envs novas no Easypanel → Ambiente (opcionais — só pra ativar otimizadores)

| Env | Valor | Efeito |
|---|---|---|
| `SMOKE_ENABLED` | `1` | Liga worker que valida 5 cenários a cada 1h. Slack alerta se algum quebrar |
| `SMOKE_INTERVALO_SEG` | `3600` (default) | Periodicidade do smoke |
| `SLACK_WEBHOOK_SMOKE_URL` | `https://hooks.slack.com/...` | Canal pra alertas (silencioso se vazio) |
| `LIA_TOOLS_ENABLED` | `0` (default) | Quando virar `1`, Lia usa tool calling estruturado. Recomendado deixar `0` por 1-2 dias e observar smoke antes de virar `1` |

### 3. Gerar 24 áudios Ariany (5 segundos + 2 min)

Comando no clipboard (Cmd+V no Terminal):
```
cd ~/Documents/Claude/Projects/AGENTE\ IA\ BLINK/outputs/audios_karla && rm -f AMOSTRA_*.mp3 audio_*.mp3 && OPENAI_API_KEY=sk-proj-... TTS_VOZ=alloy python3 gerar_audios.py
```

Voz `alloy` (você escolheu), persona Ariany secretária, "Doutora Karla" por extenso (bug Dra→Doutor blindado).

### 4. Rotacionar OPENAI_API_KEY

A chave `sk-proj-VDF6Q…` ficou exposta no chat. Revoga em https://platform.openai.com/api-keys e gera nova. Atualiza no Easypanel env `OPENAI_API_KEY`.

### 5. Acompanhar Juliene

Quando ela responder no WhatsApp, o pipeline da Lia continua. Se faltar dado, o checklist (otimizador #4) já vai forçar coleta antes de oferecer slot. Quando todos os dados chegarem + ela escolher 1 slot, o `salvar_agendamento` Medware é disparado (detector Haiku) — mover lead pra 5-AGENDADO (101507507).

---

## Estado dos otimizadores (pra próxima sessão verificar)

### #4 Checklist dados mínimos — `voice_agent/checklist_dados_minimos.py`
Validação: nome completo (≥3 tokens fortes) + data nasc + CPF + convênio definido. Se faltar algum, injeta bloco PRÉ-AGENDA no system prompt PROIBINDO oferta de slot e listando exatamente o que coletar. Integração: `pipeline.py:2d-bis` + `responder.py::_caller_context_block`. Toggle: always-on.

### #3 Smoke contínuo — `voice_agent/smoke_continuous.py`
Worker daemon roda 5 cenários core a cada `SMOKE_INTERVALO_SEG` (default 3600s). Cada cenário valida `must_contain` + `must_not_contain` na resposta. Endpoint manual: `POST /admin/smoke-tick?secret=$WEBHOOK_SECRET`. Slack alert via `SLACK_WEBHOOK_SMOKE_URL`. Toggle: opt-in `SMOKE_ENABLED=1`.

### #2 State machine Redis — `voice_agent/fsm_conversa.py`
7 estados: TRIAGEM → DADOS → CONVÊNIO → AGENDA → CONFIRMAÇÃO → GRAVAÇÃO → POS_GRAVAÇÃO. Snapshot persistido por `convo_key` (TTL 30 dias). Bloco descritivo injetado no system prompt — Claude sabe seu estado + next_action. Inferência inicial a partir de `caller_context.status_id` + `ja_agendado` + checklist. Degrada silenciosa se Redis indisponível. Toggle: always-on.

### #1 Tool calling estruturado — `voice_agent/tools_lia.py`
3 tools: `oferecer_slot` (slots[1..2], valida contra agenda real), `confirmar_dados_paciente` (valida CPF/data/nome + grava Kommo), `gravar_agendamento_medware` (pré-condição checklist + slot real). Integração: loop em `responder.py:5` máximo 4 iterações. Toggle: opt-in `LIA_TOOLS_ENABLED=1`.

---

## Lições gravadas

- `lia-atendimento-blink/memoria/bugs-licoes/lia-inventou-retorno-humano-quando-agenda-vazia.md` — bug Juliene completo, causa raiz, 4 fixes, otimizadores faltantes
- `lia-atendimento-blink/memoria/bugs-licoes/tts-abreviacao-dra-vira-doutor.md` — TTS lê "Dra." como "Doutor" (masculino); sempre escrever por extenso em roteiros de áudio

---

## Métricas finais da sessão

| Métrica | Antes | Depois |
|---|---|---|
| Testes pytest | 455 | **584** (+129) |
| Filtros pós-geração responder.py | 4 | **5** (`_viola_promete_retorno_humano`) |
| Camadas de defesa preventiva | 0 | **4** (checklist + smoke + FSM + tool calling) |
| Endpoints `/admin/*` | 14 | **15** (`/admin/smoke-tick`) |
| Workers cron embutidos | 2 (classificar + renovacao) | **3** (+ smoke se ligado) |
| Estados FSM | 0 | **7** |
| Tools Claude estruturadas | 0 | **3** |

---

Última atualização: **31/05/2026 23:45 BRT**.
Próximo handoff a criar: `HANDOFF_01-06-2026.md` no início da próxima sessão.
