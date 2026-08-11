# Handoff — 01/06/2026 noite → 02/06/2026

## TL;DR

A sessão de 01/06 trouxe 4 fixes blindados + virada arquitetural com **juiz adversarial Haiku 4.5** (ML semântico em vez de só regex). Estado prod: 771/771 testes verdes, smoke 6/6, juiz e smoke contínuo já ligados via env. **4 commits ainda não chegaram ao GitHub** — push do Fábio está no clipboard, basta `Cmd+V` no Terminal.

## O que está pronto

| # | Commit | Significado |
|---|---|---|
| 1 | `689314c` | `feat(notas)`: só Lia em notas Kommo (paciente sai do feed) — decisão Fábio 17:39 |
| 2 | `e636a84` | `fix(scrub)`: bloqueia re-oferta de slot quando lead em 5-AGENDADO (bug Esther 24060221) |
| 3 | `1840549` | `feat(audit)`: endpoint `/admin/audit/frios-com-agendamento` (auditoria 372 leads frios) |
| 4 | `d8f6167` | `feat(juiz)`: juiz adversarial Haiku 4.5 pré-envio (defesa semântica, +23 testes) |

Tudo em `main` local. Sem regressão (771/771 testes).

## Easypanel — config atual (01/06 noite)

| Item | Estado |
|---|---|
| Auto-Deploy GitHub → Easypanel | **ATIVADO** (push dispara build em 2-5min) |
| `SMOKE_ENABLED=1` + `SMOKE_INTERVALO_SEG=3600` | **ON** |
| `JUIZ_HAIKU_ENABLED=1` + `JUIZ_HAIKU_LIMIAR=70` | **ON** (vai operar quando código `d8f6167` chegar via push) |
| `LIA_TOOLS_ENABLED=1` | ON (já estava) |
| `OPENAI_API_KEY` | rotacionada hoje 14:33, chave antiga `sk-...WcIA` revogada |
| `REACTIVATION_ENABLED=false` | mantém OFF |

## Bugs blindados hoje

### Bug Esther — re-oferta de slot pós-AGENDADO (lead 24060221, 17:39 BRT)

Lead estava em `5-AGENDADO` com consulta marcada (09/06 18:30 com Karla, Águas Claras). Paciente enviou foto da carteirinha. Handler de imagem em `webhook.py:1127` injetou `user_text` sintético:

> "[O paciente enviou uma imagem... siga o atendimento normalmente.]"

Sonnet interpretou "siga normalmente" como permissão e mandou: *"deixa eu trazer os horários disponíveis para a Esther..."*. A TRAVA `🚨 JÁ AGENDADO` no system prompt **não segurou** — LLM priorizou a instrução do user_text.

**Fix `e636a84`**: filtro pós-geração `_viola_oferta_apos_agendado(text, ctx)`. Dispara se `ctx.ja_agendado=True` E texto bate em padrão de oferta (`deixa eu trazer`, `vou buscar/consultar agenda`, `tenho essas opções`, `1️⃣ ... 2️⃣`, `qual dia prefere/gostaria`, `manhã ou tarde`, `quer agendar`). Substitui pelo fallback humanizado com a data marcada. **17 testes** em `tests/test_oferta_pos_agendado.py`.

### Bug Fábio (UX) — notas Kommo poluídas

Tinha implementado de manhã gravação dupla (paciente + Lia). Fábio reverteu 17:39: "as mensagens do paciente não precisa constar em notas. Precisa constar em notas somente as mensagens da Lia (agente)".

**Fix `689314c`**: removida gravação inbound em `pipeline.py:_sync_kommo_safely`. 8 testes em `tests/test_pipeline_notas_inbound.py` lockam a nova política.

## Virada arquitetural — juiz adversarial Haiku

**Motivo:** os 13 filtros regex em `responder.py` são reativos — cada bug é um regex novo. O **próximo** bug é uma frase que nenhum regex pega. ML semântico generaliza padrão sem precisar nomear cada caso.

**Como funciona:**
1. `_scrub_prohibited` roda os 13 filtros regex existentes.
2. Se passou, chama `JuizAdversarial.julgar(lia_text, ctx, user_text)`.
3. Haiku recebe prompt com as **9 regras de ouro Blink** + resumo do ctx + texto da Lia.
4. Devolve JSON `{risco: 0-100, motivos: [...], recomendado: enviar|substituir}`.
5. Se `risco >= 70`, substitui pelo `FALLBACK_SUBSTITUICAO` seguro.
6. Veredictos com risco >= 30 ficam em Redis (`blink:juiz:veredicto:{lead_id}:{ts}`, TTL 7 dias).
7. Erro/timeout do Haiku **não bloqueia** — Lia segue.

**Custo:** ~$0.001/turno (Haiku 4.5). Volume Blink: ~$0.20/dia. Vale qualquer 1 bug evitado.

**Config:** opt-in via `JUIZ_HAIKU_ENABLED=1` (já ON). Limiar via `JUIZ_HAIKU_LIMIAR` (default 70, baixar pra 50 = mais conservador).

**Testes:** 23 em `tests/test_juiz_adversarial.py` (parsing JSON, ctx, threshold, erro não bloqueia, env on/off).

## Pendências reais pra próxima sessão

1. **Push dos 4 commits** — sem isso, juiz não opera de fato em prod (o env está ON mas o código não chegou). Comando pronto no clipboard do Fábio:
   ```bash
   cd "$HOME/Documents/Claude/Projects/AGENTE IA BLINK"
   git log --oneline -5
   git push origin main
   ```
   Auto-deploy puxa rebuild em 2-5min.

2. **Validar pós-deploy:**
   ```bash
   curl -s https://blink-agent.6prkfn.easypanel.host/health
   curl -s https://blink-agent.6prkfn.easypanel.host/admin/smoke-tick
   curl -s "https://blink-agent.6prkfn.easypanel.host/admin/audit/frios-com-agendamento?limit=500" | python3 -m json.tool | head -30
   ```

3. **Pilares #149-153 ainda pendentes** (telemetria proativa):
   - #149 Detector leads-fantasma (cron 5min varre Kommo, alerta Slack)
   - #150 Mapa de canais (CHAT_ID → CANAL, alerta novo canal)
   - #151 Endpoint `/admin/replay/{lead_id}` (diagnóstico 1-click)
   - #152 Watchdog "Lia muda" (inbound > 5min sem outbound)
   - #153 Canary lead diário

4. **Auditoria 2.LEADS FRIO** (#156) — depende do endpoint `/admin/audit/frios-com-agendamento` chegar via push. Aí dá pra contar os 372 e mover em batch os com `1.DIA CONSULTA futuro` pra `5-AGENDADO`.

## Anti-padrões pra próxima sessão evitar

1. **Não confiar que Fábio "deu pronto" = push feito** — sempre validar pelo GitHub commits page antes de assumir.
2. **Auto-Deploy precisa estar ON no Easypanel** — se desligar, commits ficam presos no main sem rebuild.
3. **Cada filtro regex é tampão** — quando bater bug novo, a primeira pergunta é: "o juiz Haiku pegou esse caso?". Se não pegou, ajustar o prompt do juiz antes de criar mais um regex.
4. **Cada bug histórico** (Aurora, Juliene, Adelia, Diones, Esther) deve virar **payload JSON congelado** num pytest E2E que reroda contra o código novo antes do deploy. Hoje só temos testes unitários (mockados). O pilar #4 (replay) cobre isso.

## Estado consolidado prod (01/06 22h)

```
{
  "status": "ok",
  "smoke": "6/6 verde, 19.3s",
  "integrations": {"kommo": true, "medware": true, "wa_cloud": true, "redis": true},
  "settings": {
    "auto_deploy": true,
    "smoke_continuous": true,
    "juiz_haiku": "env ON, código aguardando push",
    "lia_tools": true,
    "reactivation": false
  }
}
```

## Lições

1. **ML > regex pra defesa contra bug novo.** 13 regex protegem o passado; Haiku protege o futuro.
2. **Auto-deploy off é vetor de falha invisível** — Fábio acreditou que push = deploy por 4+ horas hoje. Bloqueio na origem.
3. **A Lia funciona 95% bem.** Esther foi prova: 0-ENTRADA → 5-AGENDADO em 13min, todos campos preenchidos. Bug aparece quando user_text traz instrução estranha (imagem, áudio mal transcrito). Filtro semântico cobre essa categoria toda.

— Sessão 01/06/2026 noite encerrada com sistema vivo, 771 testes verdes, 4 commits aguardando push do Fábio.
