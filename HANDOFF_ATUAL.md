# HANDOFF ATUAL — Sessão 26/07/2026 → próxima sessão

> **Ler esse arquivo primeiro sempre que retomar essa conversa.**

---

## ✅ Deployados anteriormente em prod (não refazer)

| Commit | Bug | Efeito |
|---|---|---|
| **c4a8595** | C-55 Valores Karla + Fabrício | Tabela oficial Pix/Cartão. NUNCA fala "coberto/coparticipação". |
| **812bb07** | C-56 Trace vazando + fallback instabilidade | Claude API falha 3x → silenciosa pra 1-ATENDIMENTO HUMANO. |
| **3482f9f** | Pytest MASTER regressão | 22 asserções blindando 16 bugs indexados. |
| **f23797a** | C-70 (detalhes no commit) | Commitado, push pendente. |

---

## ⏸ Aguardando push — C-70 + C-71 + C-72 + C-73

**Rodar NESSA ORDEM (duplo-clique):**

1. `PUSH_CONSOLIDADO_C70_C71_C72.command` — C-70 + C-71 + C-72 (commits mais antigos)
2. `PUSH_BUG_C73_AGENDA_MINIMA.command` — C-73 (commit mais recente)
3. `VALIDAR_DEPLOY.command` — health check + pytest

---

### Bug C-73 — Agenda com requisitos mínimos (26/07/2026)

**Caso:** Lia bloqueava exibição de horários até ter nome+data_nasc+convênio. Isso gerava conversas longas sem valor percebido pra o paciente.

**Novo fluxo:** mostrar slots imediatamente com apenas médico + unidade + 1 data. Nome/data_nasc/convênio coletados DEPOIS que paciente escolher horário.

**Fix:**
- `voice_agent/medware_sql.py` — `horarios_livres_dia(medico, unidade, data_iso)` usa SQL WITH RECURSIVE + CONTAINING (Firebird case-insensitive). Normalização remove Dr./Dra. + acentos. Query exclui almoço 12h-13h.
- `voice_agent/pipeline.py` — bloco C-73: quando janela é 1 data específica, tenta SQL single-date ANTES do fallback REST. Converte `list[str]` HH:MM em formato slot dict.
- `voice_agent/responder.py` — gate checklist não bloqueia quando `ctx.agenda` tem slots.
- `tests/test_bug_c73_horarios_livres_dia.py` — 22/22 verde.

**Pytest:** 22 + regressão 82/82 verde.

### Bug C-71 — Unidade defasada no ctx causa loop infinito com C-31b

**Caso:** lead 22557778 Adriana. Paciente pediu "03/08/2026" (segunda = Karla Asa Norte). `ctx.unidade = "Águas Claras"` (stale). LLM gerava oferta correta (Asa Norte); C-31b bloqueava; Lia retornava "Qual turno?"; paciente respondia "manhã"; ciclo indefinidamente.

**Fix:**
- `voice_agent/responder.py` — `_inferir_unidade_por_dia(medico, weekday)` lê `calendar_atendimento.json`. Guarda 1: se LLM escreveu unidade correta → cancela C-31b + atualiza ctx. Guarda 2: anti-loop quando última msg foi "Qual turno?" + paciente respondeu manhã/tarde.
- `voice_agent/pipeline.py` — inferência proativa: se janela é dia único, infere unidade pelo weekday ANTES de consultar Medware.
- `tests/test_bug_c71_unidade_stale_loop.py` — 22/22 verde.

### Bug C-72 — Histórico chat sem janela de tempo: Chats API Kommo (lead 15321519 Ana Beatriz)

**Caso:** humano enviou template em 22/07, paciente respondeu em 26/07 (gap 96h). C-58 tem janela 6h → não cobria. Etapa 1 (MENS HUMANO field 1261148) só guardava última msg. Lia respondeu como se fosse conversa nova.

**Fix — Etapa 2 (prioridade abaixo de C-58):**
- `voice_agent/kommo.py` — `get_chat_id_for_lead(lead_id)` + `get_chat_messages_raw(chat_id, limit=50)`. Field 1260160 `url_da_conversa` no `id_to_label`.
- `voice_agent/historico_conversa.py` — `extrair_chat_id_da_url(url)` + `montar_bloco_historico_chat(messages, max_msgs=30)`.
- `voice_agent/pipeline.py` — seção 2f pré-carrega histórico ANTES de `responder.reply()`, injeta em `caller_context["historico_chat_msgs"]`.
- `voice_agent/responder.py` — prioridade: C-58 (6h notas) > Etapa 2 (Chats API completo) > Etapa 1 (MENS HUMANO).
- `tests/test_bug_c72_mens_humano.py` — 42/42 verde.

---

## 🔑 Ação necessária do Fábio

**Duplo-clique no arquivo:**
```
PUSH_CONSOLIDADO_C70_C71_C72.command
```
(está no root do projeto — `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/`)

Após auto-deploy Easypanel (2-5 min):
```bash
curl https://blink-agent.6prkfn.easypanel.host/health
```

---

## ⏳ Pendentes pra próxima sessão

- **Task #400** — Migrar agrupadores de procedimentos pra JSON externo (mais complexo, 4 listas + faixas etárias)
- **Task #403/404** — Métrica live: taxa de fallback + watchdog Medware down
- **Task #402** — Endpoint /admin/agenda-atendimento (auditoria humana)
- **Bug C-58 + Task #405** — ainda aguardando push também (foi sobreposto pelo push consolidado; verificar se C-58 já estava deployado)

---

## 📊 Sessão 26/07/2026

- **Bugs corrigidos:** C-70 (commitado local), C-71 (22/22 pytest), C-72 (42/42 pytest)
- **Módulos alterados:** `responder.py`, `pipeline.py`, `historico_conversa.py`, `kommo.py`
- **CLAUDE.md:** rolling log atualizado (C-72 + C-71 adicionados, duplicatas C-AUTO-001 removidas)
- **Pytest total C-71+C-72:** 64/64 verde

---

_Sessão 26/07/2026. Fábio autorizou modo autônomo._
