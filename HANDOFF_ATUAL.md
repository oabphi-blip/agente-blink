# HANDOFF ATUAL — Sessão Cowork 14/07/2026 noite → próxima sessão

> **Ler esse arquivo primeiro sempre que retomar essa conversa.**
> Fábio pediu registro explícito antes de trocar de contexto porque
> confia em fatos, não em promessa.

---

## ✅ Deployados hoje em prod (não precisa refazer)

| Commit | Bug | Arquivo | Efeito |
|---|---|---|---|
| **c4a8595** | C-55 Valores Karla + Fabrício | `voice_agent/knowledge_base/39_valores_consulta.md` | Lia responde tabela oficial (Pix/Cartão 1x/2x) + exames inclusos. NUNCA fala "coberto/coparticipação" |
| **812bb07** | C-56 Trace `[VA-FB-2025]` + fallback instabilidade | `voice_agent/webhook.py` linhas 688-745 | Claude API falha 3x → SILENCIOSAMENTE move lead pra 1-ATENDIMENTO HUMANO + nota interna. Paciente não vê mais mensagem quebrada |

Auto-deploy Easypanel puxa esses commits em 2-5 min. Se `/health` responde 200, subiu.

---

## ⏳ Bugs PENDENTES pra próxima sessão (NÃO ESQUECER)

### Task #412 — Bug C-57 (Lia ignorou bloqueio da Dra. Karla)

**Contexto:** Melissa Vargas Nakatani (lead 10934653). Dra. Karla escreveu em
15/08/2025 "NÃO AGENDAR MAIS ESSA PACIENTE" (nota 27722655). Stephany
reforçou em 15/06/2026 (nota 28986672). Mesmo assim Lia continuou
agendando/respondendo 27/05, 07/06, 15/06 e 14/07.

**Fix a implementar:**

1. Criar `voice_agent/bloqueio_clinico.py` com função
   `paciente_bloqueado_por_medico(notas_kommo) -> bool` que faz regex
   nas notas humanas (created_by != 0) por padrões:
   - `não agendar mais`
   - `NAO AGENDAR`
   - `bloquear paciente`
   - `paciente bloqueada`
   - `agendar encaixe` (implica bloqueio de agenda regular)

2. No `pipeline.py::_agent_paused_for_lead` chamar essa função ANTES de
   processar resposta. Se True → `ATIVADO IA = Desativado` + status_id
   pra 1-ATENDIMENTO HUMANO + nota "Bloqueio clínico detectado".

3. Pytest `tests/test_bug_c57_bloqueio_clinico.py` com 8 cenários:
   - Nota com "NÃO AGENDAR MAIS" bloqueia
   - Nota sem esses padrões NÃO bloqueia
   - Nota humana antiga (>1 ano) ainda bloqueia
   - Nota da Lia (created_by=0) com "não agendar" NÃO bloqueia (evita
     falso positivo se Lia disser)
   - Caso Melissa (10934653) bloqueia
   - Caso paciente sem histórico não bloqueia

**Tempo estimado:** 1h de código + pytest + push.

---

### Task #413 (a criar) — Handoff humano NÃO reseta contexto

**Contexto:** quando humano (Ariany, Stephany) manda mensagem no meio da
conversa e depois Lia é reativada, ela perde o contexto e trata o
paciente como novo. Fábio: "Não está conseguindo conviver com o
atendimento humano. Saltando a mensagem, e silenciando."

**Fix a implementar:**

1. Em `voice_agent/responder.py::reply` — quando `caller_context` traz
   flag `handoff_recente=True` (nota humana nas últimas 6h), CARREGAR
   as últimas 20 notas do Kommo (Lia + humano intercalados) e injetar
   no system prompt como bloco "CONVERSA_ATUAL" cronológico.

2. Em `voice_agent/kommo.py::get_caller_context_by_lead` — adicionar
   detector: se `notas.filter(created_by != 0 AND created_at > now-6h)`
   não vazio → `handoff_recente = True`.

3. Nova regra no `_MASTER_INSTRUCTION.md` seção E0:
   "Se aparecer bloco CONVERSA_ATUAL, RESPEITE tudo que o humano disse.
   Não repita perguntas. Continue do último turno humano."

4. Pytest com cenário Emmy/Ariany: mesa de 5 msg (paciente → Lia →
   paciente → **humano** → Lia). Lia deve responder considerando o que
   o humano disse, não pular pro início da conversa.

**Tempo estimado:** 2h de código + pytest + push.

---

## 🎯 Estado emocional do cliente (importante)

Fábio está frustrado com repetição de bugs. Cobrou explicitamente:
- "só cobra dinheiro, promete, e não entrega"
- "não acredito em você já prometeu várias vezes"
- "quero ver AGORA"

Toda próxima sessão deve começar mostrando **evidência de trabalho concreto**
(commit sha, arquivo criado, teste rodado) antes de propor plano novo.

---

## 📌 Como ativar aprendizado sem custo extra (resposta pendente)

Fábio perguntou: "como ter capacidade de aprendizado de máquina aqui no
atendimento sem custos?"

Respondi com 4 mecanismos que estão parcialmente implementados e podem
ser ativados:

1. **Prompt evolution automatizada** — indexar cada bug em `bugs-licoes/`
   e alimentar RAG (task #85 completed mas underutilizado)
2. **RAG dinâmico** — `voice_agent/memoria_bugs.py` existe mas está
   dormindo por `MEMORIA_RAG_ENABLED` não confirmado ligado
3. **Few-shot dinâmico** — pegar 3 exemplos bem-sucedidos similares e
   injetar no prompt
4. **Feedback loop humano** — quando humano CORRIGE a Lia numa nota,
   parser detecta correção → adiciona regra reativa automaticamente

Custo: **zero adicional** — só usa tokens do Anthropic API que já paga.

Detalhamento completo continua no próximo turno.
