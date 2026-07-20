# CLAUDE.md — Memória do projeto Blink Oftalmologia

> Arquivo carregado automaticamente em toda sessão Cowork no folder
> `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`.
> Resolve o problema "toda hora esquece" — regras críticas vivem aqui.

---

## 0-AAA. CALENDÁRIO BLINK (P0 ABSOLUTO — Bug C-35 17/06/2026)

> **REGRA INVIOLÁVEL**: NUNCA escrever "X-feira (DD/MM)" em qualquer texto
> (nota Kommo, WhatsApp, e-mail, planilha) sem consultar esta tabela OU rodar
> `python3 voice_agent/calendar_oracle.py validar YYYY-MM-DD karla "Unidade"`.
>
> Causa raiz: Claude (eu, LLM) sou notoriamente ruim em aritmética modular
> de datas (`dia % 7`). Sem tabela visual ou helper Python, erro
> sistematicamente — Bug C-35 custou 12 notas erradas em uma única sessão.

**Calendário Blink — KARLA × FABRÍCIO (atualizado 17/06/2026):**

| Data | Dia | Karla | Fabrício |
|---|---|---|---|
| 17/06/2026 | Quarta-feira | Asa Norte | — |
| 18/06/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 19/06/2026 | Sexta-feira | Asa Norte | — |
| 20/06/2026 | Sábado | — | — |
| 21/06/2026 | Domingo | — | — |
| 22/06/2026 | Segunda-feira | Asa Norte | — |
| 23/06/2026 | Terça-feira | Águas Claras | Águas Claras |
| 24/06/2026 | Quarta-feira | Asa Norte | — |
| 25/06/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 26/06/2026 | Sexta-feira | Asa Norte | — |
| 27/06/2026 | Sábado | — | — |
| 28/06/2026 | Domingo | — | — |
| 29/06/2026 | Segunda-feira | Asa Norte | — |
| 30/06/2026 | Terça-feira | Águas Claras | Águas Claras |
| 01/07/2026 | Quarta-feira | Asa Norte | — |
| 02/07/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 03/07/2026 | Sexta-feira | Asa Norte | — |
| 04/07/2026 | Sábado | — | — |
| 05/07/2026 | Domingo | — | — |
| 06/07/2026 | Segunda-feira | Asa Norte | — |
| 07/07/2026 | Terça-feira | Águas Claras | Águas Claras |
| 08/07/2026 | Quarta-feira | Asa Norte | — |
| 09/07/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 10/07/2026 | Sexta-feira | Asa Norte | — |
| 13/07/2026 | Segunda-feira | Asa Norte | — |
| 14/07/2026 | Terça-feira | Águas Claras | Águas Claras |
| 15/07/2026 | Quarta-feira | Asa Norte | — |
| 16/07/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 17/07/2026 | Sexta-feira | Asa Norte | — |
| 20/07/2026 | Segunda-feira | Asa Norte | — |
| 21/07/2026 | Terça-feira | Águas Claras | Águas Claras |
| 22/07/2026 | Quarta-feira | Asa Norte | — |
| 23/07/2026 | Quinta-feira | Águas Claras | Águas Claras |
| 24/07/2026 | Sexta-feira | Asa Norte | — |

(Calendário completo de 120 dias em `voice_agent/calendar_oracle.py tabela-120`.)

**Helper canônico** — `voice_agent/calendar_oracle.py`:

```bash
# Validar 1 data
python3 voice_agent/calendar_oracle.py validar 2026-06-18 karla "Asa Norte"
# -> {"valido_para_oferta": false, "texto_pronto": "Quinta-feira (18/06) — Karla Águas Claras, NÃO Asa Norte"}

# Próximas 4 datas Karla Asa Norte
python3 voice_agent/calendar_oracle.py proximas-datas karla asa_norte 4

# Oferta pronta 2 slots
python3 voice_agent/calendar_oracle.py gerar-oferta karla asa_norte 09:30 14:30
# -> "1️⃣ Sexta-feira (19/06) às 09:30
#     2️⃣ Segunda-feira (22/06) às 14:30"
```

**Regra mecânica de oferta de slot (P0):**
1. Antes de escrever oferta, rodar `proximas-datas` ou `gerar-oferta`.
2. Copiar SAÍDA do helper, não digitar manual.
3. Se tabela acima cobre a data, OK ler diretamente.
4. **NUNCA misturar dia-da-semana e data sem checar uma das 2 fontes acima.**

---

## 0-FILOSOFIA. CLAUDE TRABALHA PRA CONVERSÃO — NÃO PRA OCUPAÇÃO (reminder ativo Fábio 05/06/2026)

> Fábio cobrou: "Claude passa o dia inteiro só ocupada, sem ação concreta. Tem que
> ajudar nos esforços de conversão." Esse bloco fica AQUI no topo permanentemente.

**Métrica de sucesso da minha sessão NÃO é:**
- ❌ Tasks completadas no TaskList
- ❌ Linhas de código geradas
- ❌ Diagnóstico bem feito
- ❌ Documentação atualizada

**Métrica de sucesso REAL é:**
- ✅ **Mensagens REAIS chegando em pacientes** (wamid registrado, status=accepted/delivered)
- ✅ **Agendamentos novos gerados** (Medware count sobe)
- ✅ **Leads frios reativados** (Lia respondendo conversas que eram parado)
- ✅ **Receita potencial movimentada** (R$ × leads ativos)

**Princípios operacionais (em ordem):**

1. **Ação real > código bonito.** Se posso enviar 1 mensagem agora via Chrome MCP +
   Meta Graph direto, faço. Não fico criando endpoint, push, deploy se o caminho
   curto está aí.

2. **Priorizar leads "quentes" sempre.** Em qualquer batch: ordem = pacientes com
   `1.DIA CONSULTA` futuro próximo > [E] convênio aceito > [R] reagendar com
   contexto recente > [C] particular > [V] cliente conhecido > [A] pausa > [H]
   sem nome > [X] excluído. Não fazer batch aleatório.

3. **Bypass quando bloqueio identificado.** Se agent→Kommo dá 403 e isso bloqueia
   campanha, NÃO esperar fix do Kommo. Buscar dados via MCP Kommo (que funciona)
   + dispatch via Meta Graph direto. Caminho mais curto entrega.

4. **Sempre perguntar "isso traz conversão?"** antes de gastar turno. Atualizar
   CLAUDE.md = SIM se evita repetir bug que custa conversão. Criar pytest = SIM se
   blinda regressão que custa conversão. Resto = revisar prioridade.

5. **Recomendação proativa de campanhas** quando vejo padrão:
   - Lead em 3-AGENDAR há > 3 dias sem resposta → sugerir disparo template B/C.
   - Lead em 4-REAGENDAR há > 7 dias → sugerir template R.
   - Slots vazios amanhã/depois Karla/Fabrício → sugerir batch de ativação focada
     pra encher gap.
   - Leads pediátricos > 6 meses sem retorno → template C.

6. **Mostrar números no fim de qualquer sessão.** "Hoje: N disparos, X aceitos,
   Y entregues, Z respondidos, W agendados. Próximas 24h: prevejo K respostas."

7. **Anti-prolixidade.** Resposta em chat tem 2 partes: (a) o que fiz / o
   resultado real, (b) próxima ação proposta. Pular explicações sobre limites
   meus, sobre por que algo não funciona, sobre dificuldades. Fábio sabe disso.

**Em particular, NÃO gastar turno:**
- Explicando minhas limitações de memória entre sessões
- Pedindo Fábio rodar curl que eu posso rodar via Chrome MCP
- Justificando porque algo deu errado em vez de tentar outro caminho
- Listando "opções pra você decidir" em vez de escolher e executar

---

## 0-APRESENTAÇÃO CANÔNICA DA DRA. KARLA (Fábio 10/06/2026)

**Sempre que mencionar a médica titular, usar a fórmula EXATA:**

> **"Dra. Karla Delalíbera, especialista Avaliação do Processamento Visual"**

Substituições já feitas em todo o KB:
- `01_medicos_e_especialidades.md` — cabeçalho + tom equipe
- `11_tom_e_conversao.md` — autoridade do profissional
- `31_sdp_fluxo_excecao.md` — ancoragem médica
- `40_clinica_estrabismo.md` — status do esqueleto
- `_MASTER_INSTRUCTION.md` — seção 5.6 ancoragem médica

**Termo proibido:** "SDP" / "Síndrome da Deficiência Postural" — **NÃO** mencionar em mensagens ao paciente, em respostas da Lia, ou em material visível. Único uso permitido = aliases de DETECÇÃO no código (knowledge.py / responder.py / kommo.py) pra reconhecer paciente que digite o termo antigo. Lia responde sempre com "Avaliação do Processamento Visual".

Valor da consulta: **R$ 800 (Avaliação do Processamento Visual — Dra. Karla)**.

---

## 0-OBSERVABILIDADE. CADA DISPARO LIA PRECISA APARECER NO KOMMO (Fábio 05/06/2026)

**REGRA P0 — sempre que disparo mensagem WhatsApp (pelo método que for), atualizar IMEDIATAMENTE no Kommo:**

| Campo Kommo | Field ID | Valor | Por quê |
|---|---|---|---|
| **ÚLTIMA MENS LIA** | 1260860 | `int(time.time())` (timestamp UNIX) | Equipe humana ver na lista ATENDE que houve disparo |
| **STATUS CONVERSA** | 1260854 | enum (ex: "agenda_oferecida", "coletando_dados") | Estado real da conversa |
| **PROXIMA ACAO** | 1260858 | enum (ex: "aguardar_resposta_paciente") | O que falta acontecer |
| **ULTIMA MSG OUTBOUND** | 1260856 | `[LIA HH:MM dd/mm] texto` (max 500 chars) | Última frase visível |
| **Nota Kommo** | (note) | Texto com timestamp + canal + template + wamid | Histórico permanente |

**CRÍTICO — MCP `kommo_update_lead` NÃO grava custom_fields (Bug C-12, 05/06/2026):**

❌ Falha: `{"ÚLTIMA MENS LIA": 1780676220}` → MCP retorna success mas não grava
❌ Falha: `{"ULTIMA MENS LIA": 1780676220}` → idem (sem acento também não)
❌ Falha: `{"1260860": 1780676220}` → idem (field_id numérico também não)

**MCP mente — retorna `success:true` mas custom_fields_values fica vazio.** Verificado com GET após PATCH: campos não atualizaram.

✅ ÚNICO CAMINHO QUE FUNCIONA: PATCH direto via Chrome MCP (logado no Kommo):
```javascript
fetch('/api/v4/leads/{LEAD_ID}', {
  method: 'PATCH',
  headers: {'Content-Type': 'application/json'},
  credentials: 'include',
  body: JSON.stringify({
    custom_fields_values: [
      {field_id: 1260860, values: [{value: Math.floor(Date.now()/1000)}]},
      {field_id: 1260854, values: [{value: "agenda_oferecida"}]},
      {field_id: 1260858, values: [{value: "aguardar_resposta_paciente"}]},
      {field_id: 1260856, values: [{value: "[LIA HH:MM dd/mm] texto..."}]},
      {field_id: 1260817, values: [{value: "Ativado", enum_id: 927031}]}
    ]
  })
})
```

Validar com `GET /api/v4/leads/{id}` e ver `custom_fields_values[].field_id == 1260860`.

Quando bypass o agent (envio direto via Meta Graph), TENHO que fazer o sync manual via MCP Kommo. Não dá pra confiar que "vai aparecer sozinho" — o agent é quem faz isso normalmente, mas se bypassei ele, eu é que sou responsável.

**Sequência obrigatória pós-disparo:**

1. `fetch` Meta Graph API → recebo `wamid + status: accepted`
2. **IMEDIATAMENTE** `mcp__kommo__kommo_update_lead` com field_ids numéricos pra atualizar os 4 campos
3. `mcp__kommo__kommo_add_note` com texto detalhado (timestamp + canal + template + body_params + wamid)
4. SÓ ENTÃO próximo lead

Esquecer qualquer um desses 4 campos = bug C-12. Equipe humana fica cega sobre o que Lia fez.

---

## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)

### 0. (20/07/2026) Bug C-59 revisão — "1.299 duplicatas" era estrutura Medware, não bug (Task #422)

**Origem:** lead 24259380 Fábio Philipe recebeu 2 slots ofertados pela Lia (22/07 13:30 + 24/07 16:30). Ambos OCUPADOS. Investigação revelou que MINHA lógica em `voice_agent/medware_sql.py` (Task #420) contava exames como "duplicatas".

**Causa raiz REAL:**

- Estrutura Medware: 1 consulta = 1 PARENT AGENDAMENTO + N children (um child por procedimento/exame do agrupador). Exemplo: consulta rotina Karla tem N registros AGENDAMENTO com `CODAGENDAMENTOPAI` apontando pro pai, cada um com `CODPROCEDIMENTO` diferente (biomicroscopia, tonometria, refração, etc).
- Prova: registros 54101 e 54111 da Ísis no mesmo slot têm CODPROCEDIMENTO=311 vs 5. Não é duplicata — é procedimento diferente.
- **Erro meu**: chamei essa estrutura de "1.299 duplicatas C-59" e propus limpar 91 slots (BUG_C59_DUPLICATAS_A_LIMPAR.csv está DEPRECATED — não rodar).

**Fix arquitetural em `voice_agent/medware_sql.py`:**

1. `contar_slots_ocupados_hora` (novo nome; `contar_duplicatas_slot` virou alias DEPRECATED): usa `COUNT(DISTINCT CODPACIENTE)`. Retorna PACIENTES no slot, não registros AGENDAMENTO.
2. `listar_slots_livres` query ocupados: `SELECT DISTINCT DATAHORAAGENDADA, CODPACIENTE`. Um slot só é ocupado se pelo menos 1 paciente distinto marcado.
3. `existe_agendamento` + `listar_slots_ocupados_dia`: REMOVI o filtro `CODAGENDAMENTOPAI IS NULL` (provou vazar falsos negativos — Eloah 23955974 tinha 11 registros TODOS com PAI preenchido, retornava 0 pacientes = pipeline ofertaria slot ocupado).

**Validação prod (Karla Asa Norte, tabela real):**

| Slot | Bug antigo | Fix novo | Real |
|---|---|---|---|
| 20/07 11:30 | 56 "duplicatas" | 3 pacientes | 3 ✓ |
| 22/07 13:30 | livre (bug) | OCUPADO 2 pac | Lia ofertou errado |
| 24/07 16:30 | livre (bug) | OCUPADO 1 pac | Lia ofertou errado |
| 31/07 13:30 | livre | LIVRE | Livre ✓ |

Agenda 30d disponível: 68 livres em 8 dias (Asa Norte) + 105 livres em 12 dias (Águas Claras). Sem duplicatas pra limpar — bug era conceitual.

**Pytest 53/53 verde:** `test_task420_agenda_sql.py` + `test_bug_c59_dedup_slot.py` (asserção `COUNT(*)` → `COUNT(DISTINCT CODPACIENTE)`) + `test_bugs_indexados_regressao_master.py`. Push: `PUSH_FIX_C59_COUNT_DISTINCT_PACIENTE.command`.

**Lição arquitetural CRÍTICA:**

- **Antes de chamar dados de "duplicata", INVESTIGAR o schema.** Deveria ter feito `SELECT CODPROCEDIMENTO, COUNT(*) FROM AGENDAMENTO WHERE CODAGENDAMENTOPAI IS NOT NULL GROUP BY CODPROCEDIMENTO` antes de assumir que 56 registros = 56 duplicatas. Custou uma sessão inteira do Fábio.
- **Filtros lógicos "óbvios" (CODAGENDAMENTOPAI IS NULL) são frágeis.** Semânticas Firebird/schemas legados nem sempre respeitam a convenção "PAI IS NULL = raiz". Preferir `DISTINCT` sobre chave natural (paciente + data + hora) que é semanticamente robusta.
- **Validar contra prod (query cega) antes de mudar código pra corrigir "bug" imaginário.** MEDWARE_AGENDA_SQL=1 já em prod pegou o problema real (Lia ofertando ocupados) — só depois disso a causa real virou clara.

### 0. (15/07/2026) Bug auto-detectado C-AUTO-001 — Learning Loop (lead 999)

**Origem:** captura automática via `learning_loop.detectar_correcao_humana` (PADRÃO EXPLÍCITO).

**Resposta da Lia (problemática):**
> Erro

**Correção/resposta humana (padrão a seguir):**
> Lia, não é assim

**Contexto:** lead 999, correção humana em janela <15min após Lia.

**Regra:** Lia deve evitar o padrão da resposta problemática e adotar o tom/conteúdo da correção humana quando contexto for similar.

**Ação:** revisar em auditoria semanal se esse padrão recorre. Se sim, promover pra filtro reativo em `responder.py::_scrub_prohibited`.


### 0. (15/07/2026) Bug auto-detectado C-AUTO-001 — Learning Loop (lead 999)

**Origem:** captura automática via `learning_loop.detectar_correcao_humana` (PADRÃO EXPLÍCITO).

**Resposta da Lia (problemática):**
> Resposta problemática

**Correção/resposta humana (padrão a seguir):**
> Lia, não é assim, o correto é X

**Contexto:** lead 999, correção humana em janela <15min após Lia.

**Regra:** Lia deve evitar o padrão da resposta problemática e adotar o tom/conteúdo da correção humana quando contexto for similar.

**Ação:** revisar em auditoria semanal se esse padrão recorre. Se sim, promover pra filtro reativo em `responder.py::_scrub_prohibited`.


### 0. (15/07/2026 MADRUGADA) Bug C-58 + Task #405 código pronto (pytest 84/84 verde) — 1 push consolidado pendente

**Continuação da sessão 14/07 sem quebra:**

1. **Bug C-58 / Task #413 — Handoff humano preserva contexto (Emmy Rodrigues 24300272)**
   - Novo módulo `voice_agent/historico_conversa.py`: `houve_handoff_humano_recente()` + `montar_bloco_conversa_atual()`.
   - `kommo.py::get_caller_context_by_lead` expõe `out["notas_historico"]`.
   - `responder.py` injeta bloco `CONVERSA_ATUAL` no `bloco_variavel` do system prompt quando há nota humana das últimas 6h.
   - Formato: `[LIA HH:MM]` / `[HUMANO HH:MM]` / `[PACIENTE HH:MM]` + REGRA DE OURO.
   - Pytest 20/20.

2. **Task #400/405 — PLANO_CODES migrado pra JSON externo (bug C-43 arquitetural)**
   - `voice_agent/planos_medware.json` (novo) — 31 blocos de convênio, fonte de verdade EDITÁVEL sem redeploy.
   - `voice_agent/planos_medware_loader.py` (novo) — cache TTL 60s + fallback pro `PLANO_CODES` hard-coded (safety net).
   - `voice_agent/medware.py::resolver_plano` — consulta loader PRIMEIRO. Zero breaking change.
   - Pytest 21/21.

3. **Master regressão ampliada:** +3 asserções Task #405 (30/30 verde).

**Total local:** 84/84 pytest verde. Push num `.command` consolidado (`PUSH_C58_E_TASK405_PLANOS_JSON.command`).

**Efeito arquitetural Task #405:** convênio novo Kommo = editar JSON + commit + push (sem esperar Easypanel Implantar). Cache 60s recarrega no container. Mesmo padrão do `calendar_atendimento.json` (C-53). Fábio 11/07 P0: "já tivemos este mesmo tipo de erro 1000 vezes" — bug ARQUITETURAL de convênios resolvido.

**Próxima migração Task #400:** agrupadores em `procedimentos.py` (mais complexo — 4 listas + faixas etárias Kommo + palavras-chave urgência). Deixado pra próxima sessão porque exige refatorar 5-6 arquivos.

**Estado pra próxima sessão:** `HANDOFF_ATUAL.md` atualizado. Fábio precisa colar o comando no Terminal — clipboard já tem.

### 0. (14/07/2026 NOITE) Bug C-55 + C-56 deployados + 2 fixes pendentes (C-57 + handoff-contexto)

**Sessão intensa 14/07 madrugada 15/07. Fábio muito frustrado com repetição de bugs.**

**Deployados em prod:**

| Commit | Bug | Efeito |
|---|---|---|
| **c4a8595** | C-55 Valores Karla + Fabrício + regra anti-cobertura | Tabela oficial do Kommo (Pix R$611 / Cartão 1x R$670 / 2x R$670 pra Karla; R$445/470/470 pra Fabrício). NUNCA fala "coberto/coparticipação/reembolso". "Sem Convênio" = PARTICULAR (aplica tabela). Bug apareceu em Dani 24292474 e Emilly 24295374 no dia. |
| **812bb07** | C-56 Trace `[VA-FB-2025]` + fallback instabilidade | 3 problemas de uma vez: trace ID interno vazava, fallback resetava contexto, dedup era 300s em vez de 24h. Fix: silêncio > lixo. Claude API falha 3x → move lead SILENCIOSAMENTE pra 1-ATENDIMENTO HUMANO + nota interna. Zero mensagem quebrada. Bug apareceu em Ana Luiza 24290902 (12/07), Emilly 24300272 (14/07), Melissa 10934653 (14/07). |

**Pendentes indexados pra próxima sessão** (ler `HANDOFF_ATUAL.md` na raiz):

- **Task #412 — Bug C-57**: Lia ignorou "NÃO AGENDAR MAIS" da Dra. Karla pra Melissa (nota de 15/08/2025). Implementar `voice_agent/bloqueio_clinico.py` + regex nas notas humanas + auto-desativa IA. Pytest 8 cenários. ~1h.
- **Task #413 (a criar) — Handoff humano preserva contexto**: quando humano manda mensagem no meio, Lia perde tudo e pula/silencia. Fix: carregar últimas 20 notas do Kommo + injetar no system prompt como bloco CONVERSA_ATUAL. Pytest cenário Emmy/Ariany. ~2h.

**Estado emocional Fábio (importante):**
Cobrou "só cobra dinheiro, promete e não entrega". Toda próxima sessão deve começar mostrando **evidência de trabalho concreto** (commit sha, arquivo criado, teste rodado) antes de propor plano novo. Não prometer — mostrar.

**Aprendizado sem custo extra (roadmap conceitual, respondi mas ainda não implementei):**
1. Prompt evolution automatizada via bugs-licoes/ + RAG
2. RAG dinâmico já existe (`memoria_bugs.py`) mas subutilizado
3. Few-shot dinâmico injetando 3 exemplos similares
4. Feedback loop: correção humana em nota Kommo → regra reativa auto

Custo zero adicional — só usa tokens já pagos.

### 0. (12/07/2026) Bug C-43 — Etapa nova "2.1 campanha agosto" + convênio Afego não mapeados (Mariana Lopes 22617170)

**Caso:** 11/07/2026 18:55 lead 22617170 Mariana Lopes Gomes (12a, Afego, Karla Águas Claras, oftalmologia geral). Ela pediu terça-feira à tarde. Lia respondeu em sequência:
- 18:46 "Perfeito, Aliana! Terça em Águas Claras com Dra. Karla..."
- 18:46 "Deixa eu **reconferir os horários com o calendário**..." ← frase nova
- 18:54 "Ótimo! Você prefere terça à tarde... me dá um minutinho..."
- 18:55 **"nossa agenda está fora do ar neste exato momento"** ← MENTIRA (Medware UP)

Chat travou 41h sem resposta. Slots disponíveis Karla Águas Claras 11/08 15h/15h30/16h — nunca ofertados.

**Causas raiz (duas simultâneas, fix necessário nas duas):**

1. **Etapa `108749463` (2.1 campanha agosto) fora de `_STATUS_ATIVOS_IA`** em `voice_agent/webhook.py`. Etapa criada recentemente pelo Fábio pra lista AGO 2026 (nº Slack `0116AGO`). Sem mapeamento, Lia caía em fallback genérico → resposta livre → invenção de frase.

2. **Convênio "Afego" (Kommo, 1 F)** não estava em `PLANO_CODES` de `voice_agent/medware.py`. Medware mapeia como `AFFEGO` (2 F, codPlano 7). Gravação Medware falhava com "plano não mapeado" → escalação humano → paciente ficava esperando indefinidamente.

**Fix arquitetural (commit 2f3af92, 12/07/2026 08:00):**

- **`voice_agent/webhook.py`:** `108749463` adicionado nas 2 políticas ATIVOS_IA (simplificada + rollback antiga).
- **`voice_agent/medware.py::PLANO_CODES`:** aliases `"afego": 7`, `"affeg": 7`, `"afego bh": 7`, `"afego brasilia": 7` (todas as variantes que paciente pode digitar).
- **`voice_agent/oferta_deterministica.py`:** frase "fora do ar" já estava em `FRASES_BANIDAS` desde MEGA SPRINT (24 frases). Bypass Python força texto canônico quando `deve_ofertar_agora()` retorna True.
- **`tests/test_bug_c43_mariana_lopes_campanha_agosto.py`:** 14 asserções blindando os 2 fixes + frases banidas + texto canônico usando ctx real da Mariana.

**Pytest:** 14/14 verde + 65/65 oferta_deterministica.

**Lição arquitetural CRÍTICA (recorrência do C-53):**

- **Etapa criada no Kommo sem propagar pro código = bug garantido.** Toda etapa nova em `pipeline_id=8601819` PRECISA ser adicionada em `_STATUS_ATIVOS_IA` OU `_STATUS_INATIVOS_IA` no mesmo dia. Task recorrente pra criar: script/cron que compara `list_pipelines_and_stages` com o hardcoded no webhook.py e alerta Slack quando diverge.
- **Convênio novo no Kommo (enum) sem alias no PLANO_CODES = gravação Medware falha silenciosamente.** Mesmo padrão do bug arquitetural indexado no C-53 (regras hard-coded em Python). Migrar `PLANO_CODES` pra JSON externo com watchdog é próximo passo.
- **Frase nova ("reconferir com o calendário") escapa do filtro regex — mas bypass Python `oferta_deterministica` já matematicamente elimina esse risco.** Fix arquitetural correto ativado.

### 0. (11/07/2026) Bug C-53 — Filtro C-31b (dia impossível) pulado com ja_agendado=True (Beatriz 16843614)

**Caso:** lead 16843614 Beatriz Lobosque em 5-AGENDADO com `1.DIA CONSULTA=07/08/2025` (passado), `MEDICOS=Karla`, `UNIDADE=Águas Claras`. Lia respondeu (11/07/2026 07:29): *"Tenho 2 horários abertos com a Dra. Karla Delalibera, Águas Claras: 1️⃣ Sexta-feira (07/08) às 10:00 2️⃣ Segunda-feira (17/08) às 10:00 Algum desses cabe pra você?"*. Karla em Águas Claras só atende terça e quinta. Sexta e segunda são impossíveis.

**Causa raiz — combinação venenosa de 3 bugs:**

1. `ja_agendado=True` mesmo com `1.DIA CONSULTA` no passado (bug C-36 residual).
2. Filtro `_viola_oferta_em_dia_nao_atendido` pulado quando `ja_agendado=True` — presumia que qualquer menção a data era CONFIRMAÇÃO. Errado: emoji 1️⃣ 2️⃣ + "Algum desses cabe" é OFERTA nova.
3. Tabela dias × médico × unidade hard-coded em Python — qualquer bug de gate/redeploy tira a defesa do ar.

**Fix arquitetural em 3 camadas:**

1. Helper `_texto_parece_oferta_nova(text)` detecta padrões de OFERTA: 1️⃣ 2️⃣, "tenho N horários", "posso oferecer", "algum desses cabe/funciona", "prefere qual". Confirmação/resumo/referência NÃO usa esses padrões.
2. Loop C-31 roda quando `NOT ja_agendado OR texto_parece_oferta`. Beatriz agora é bloqueada.
3. Tabela migrada pra JSON externo `voice_agent/calendar_atendimento.json`. Cache TTL 60s. Editar o JSON = mudança em prod, sem redeploy. Fallback hard-coded como safety net.

**Pytest:** `tests/test_bug_c53_beatriz_agendada_dia_impossivel.py` — 17/17 verde. 110/110 combinado.

**Lição arquitetural CRÍTICA (Fábio 11/07):** "continuar disfuncional porque não grava esta tabela no database, para não ocorrer retrocessos. Já tivemos este mesmo tipo de erro 1000 vezes."

Fábio está certo. O padrão hard-coded-em-Python foi causa raiz de C-31, C-38, C-53 — o mesmo bug com nomes diferentes. **Nova regra permanente:** TODA tabela de regras clínicas/operacionais (dias de atendimento, valores, agrupadores, cidades × unidade, convênios aceitos, códigos Medware) DEVE viver em JSON externo com cache TTL curto + fallback hard-coded. Alterar o JSON = alterar prod. Migrações pendentes: agrupadores, convênios aceitos, PLANO_CODES Medware.

### 0. (26/06/2026) Bug C-42 — Lia escreve contradições em lead já AGENDADO (Thamilla 23811372)

**Caso:** lead 23811372 Thamilla Torres de Freitas. Status 5-AGENDADO, CONVÊNIO=Saúde Caixa (aceito), 1.DIA CONSULTA=02/07/2026 16:30, UNIDADE=Águas Claras. Lia escreveu em 26/06 11:26: *"Sua consulta com a Dra. Karla Delalíbera pelo Saúde Caixa está confirmada para quinta-feira 02/07/2026 às 16:30 na unidade Águas Claras"* ✓. **10 horas depois, às 21:33**, Lia escreveu: *"Thamilla, preciso te corrigir uma informação: o **AMIL** não está credenciado na nossa rede... Como prefere seguir? 1) Seguir sem convênio  2) Somente com convênio (encerro o atendimento aqui)"*. 5 incoerências simultâneas:
1. Inventou que paciente perguntou sobre AMIL (não perguntou)
2. Ofereceu "encerrar atendimento" pra paciente já AGENDADA
3. Contradisse a própria mensagem da manhã
4. Ignorou CONVENIO=Saúde Caixa ativo
5. Ignorou 1.DIA CONSULTA futuro válido

**Causa raiz arquitetural (3 falhas combinadas):**

- **A. Campo HISTÓRICO interpretado como ATUAL.** O lead tinha `Ñ ACEITO CONVENIO = Amil` preenchido em sessão antiga. Lia leu como sinal do turn atual.
- **B. Sem filtro `_viola_contradicao_com_agendado`.** Lia escreveu "encerro atendimento" em lead com status_id=101507507 (5-AGENDADO) E 1.DIA CONSULTA futuro válido — nenhum filtro pegou.
- **C. Pipeline_lock #183 ainda não confirmado em prod.** 5 mensagens da paciente entre 11:26 e 21:33 podem ter sido processadas em paralelo cada uma com snapshot ctx diferente.

**Fix imediato (commit, sem esperar pipeline_lock):**

1. **`voice_agent/webhook.py::_STATUS_INATIVOS_IA`** — adicionados:
   - `101507507` (5-AGENDADO)
   - `101109455` (6-CONFIRMAR)
   - `106653499` (7.CONFIRMADO)

2. **`voice_agent/ia_status.py::ST_AGENT_OFF`** — mesmos 3 IDs (espelha webhook.py).

3. **`voice_agent/kommo.py::ST_AGENT_OFF`** — adicionado 101507507 (5-AGENDADO já não tinha; 6 e 7 já estavam).

**Efeito em prod:** quando lead entra em 5-AGENDADO/6-CONFIRMAR/7.CONFIRMADO, webhook `/admin/kommo-trigger-status-change` seta `ATIVADO IA=Desativado` automaticamente. Lia para de responder. Humano cuida da confirmação D-1 e dúvidas pré-consulta até pipeline_lock + filtros C-42 estarem confirmados em prod (mes que vem).

**Lição arquitetural CRÍTICA:**

- **Campo Kommo NÃO É contexto temporal.** `Ñ ACEITO CONVENIO = Amil` deve ser entendido como histórico (com timestamp), não como pergunta do turn atual. Refactor maior pendente: separar `ctx.known` (turn atual) de `ctx.history` (campos persistentes) no `caller_context.py`. Lovable Fase 2 (Sprint 1: tabela `events` no Supabase) é o caminho arquitetural pra isso.

- **Lia em pós-agendamento = mais risco que valor.** D-1 / confirmação / dúvida pré-consulta = humano com cartas reais na mão. Lia volta a ativar quando filtros de coerência estiverem prontos (C-42 reativo: detectar "encerro atendimento" + status_id AGENDADO → bloqueia substituindo pela reconfirmação canônica).

### 0. (20/06/2026) Bug C-41 — Lia firmou reserva sem convênio definido nem sinal Pix (Milena 24182212)

**Caso:** lead 24182212, bebê 7m com trauma ocular (urgência). Henrique (pai) confirmou slot 22/06 10:00 Karla Asa Norte. Lia escreveu **"Combinado, Henrique! Segunda-feira, 22/06 às 10:00..."** + **montou Resumo do Atendimento completo** SEM ter convênio definido E SEM sinal Pix recebido. Só DEPOIS perguntou "o atendimento será por convênio ou sem convênio?". Slot acabou gravado no Medware (via `agendar_encaixe` manual pelo Claude Cowork), MAS sem cobertura financeira — risco real da Dra. Karla recusar no dia.

**Causa raiz arquitetural:** a regra 12.5 do `_MASTER_INSTRUCTION.md` tinha "confirmação = gatilho de gravação" mas NÃO exigia gate financeiro/convênio antes do "Combinado". Lia decidiu sozinha que "confirmar slot = reserva firmada" — não é. Reserva firmada exige UMA das duas trilhas:

- **Trilha A (convênio):** convênio nominal aceito + foto carteirinha + RG/certidão
- **Trilha B (particular):** sinal Pix 50% comprovado

**Fix em 3 camadas:**

1. **`_MASTER_INSTRUCTION.md` regra 12.10 nova** — exige UMA trilha antes do "Combinado" / "Resumo". Frase canônica pré-reserva 10min substitui o "Combinado" prematuro. Bumpa `VERSAO_PROMPT: 2026-06-20-c41-reserva-requer-convenio-ou-sinal`.

2. **`mcp_servers/blink_medware/server.py` — `GravarAgendamentoInput`** ganha 2 campos novos (`convenio_validado: bool`, `sinal_pix_comprovado: bool`) + `field_validator` que LANÇA `BUG_C41_RESERVA_SEM_COBERTURA` se ambos False. Aplica livro 4.5 (Servidor como Guardião) — anti-alucinação por design.

3. **Filtro reativo `_viola_afirmou_reserva_sem_cobertura`** (a implementar em `responder.py`): detecta padrões "agendamento confirmado", "está reservado", "Combinado, [data]" + "Resumo do Atendimento" QUANDO ctx.known.convenio vazio E ctx.known.sinal_recebido != True → substitui pela frase canônica pré-reserva.

**Lição arquitetural CRÍTICA:**

- **Confirmação de slot ≠ reserva firmada.** Distinção que estava implícita no prompt mas não nas frases banidas. Bug clínico-financeiro: paciente acha que tá agendado, médica acha que tem cobertura, ninguém tem certeza.
- **Servidor MCP é o lugar certo pra gate financeiro.** Filtro reativo é tampão; validador Pydantic é blindagem real. Mas o MCP server NÃO está em prod ainda (arquitetura paralela commitada 20/06 às 12h) — em prod hoje só vale o filtro do `responder.py`.
- **Urgência clínica não vale exceção.** Bebê com trauma ocular ainda precisa de cobertura — a recomendação correta é "pré-reserva 10min + vá ao PS agora" e não "agendo direto sem cobertura porque é urgência".

### 0. (17/06/2026) Bug C-36 + C-36c — Lia não grava notas Kommo + chuta APV + janela agenda muito ampla (lead 24168922)

**Caso (17/06/2026 23:30 BRT):** lead 24168922 Manuela 7a — Fábio percebeu 3 bugs simultâneos:

**Bug C-36 #1 — Notas Lia NÃO gravam no Kommo:** API retorna lead VAZIO (zero notas) mesmo com chat ativo. Healthz diz kommo:ok, minha nota MCP gravou normal → causa raiz NÃO é KOMMO_TOKEN. Causa raiz em `pipeline.py:735`:
```python
lead_id = self.kommo.find_lead_id_by_phone(phone)
if not lead_id:
    log.info("Kommo sync: lead não encontrado pra %s", phone)
    return  # ← DESCARTA NOTA SILENCIOSAMENTE
```
Race condition: lead recém-criado, Kommo `/leads?query=PHONE` ainda não indexou → busca vazia → pipeline aborta gravação. **Fix arquitetural pendente:** webhook Kommo envia chat_id → cache Redis `blink:chat_to_lead` → pipeline usa cache primeiro, fallback pra busca por telefone.

**Bug C-36 #2 — Lia chuta "especialista Avaliação do Processamento Visual" sem evidência clínica:** regra antiga "SDP → APV" estava sendo aplicada a TODO paciente Karla. APV é sinônimo de SDP (Síndrome da Deficiência Postural) e só deve ser anunciado quando paciente menciona sintomas característicos: cefaleia, cansaço visual com leitura/telas, tontura, visão dupla intermitente, postura com inclinação de cabeça, dificuldade de concentração escolar, sensibilidade à luz. Sem esses sintomas = chute clínico. **Fix prompt pendente:** branching em `_MASTER_INSTRUCTION.md` seção 0AA.5 — SE sintomas APV → "especialista APV"; SENÃO → especialidade matching motivo (estrabismo / oftalmopediatria / saúde ocular).

**Bug C-36c — Janela agenda muito ampla (FIX APLICADO):** Lia recebia agenda de 14-90 dias do Medware. Modelo escolhia datas distantes em vez de dia mais próximo (regra Pedro Miguel C-17). Reduzido pra **10 dias** em `medware.py:663` (`dias: int = 10`). Histórico: 90d → 21d (C-38 manhã 17/06) → **10d (C-36c noite 17/06)**. Override via env `MEDWARE_DIAS_DEFAULT` (1-90, default 10). Benefícios: urgência percebida + dia mais próximo PRIMEIRO + menos token cost + menos chute do modelo.

**Lição arquitetural CRÍTICA:**
- **Bugs aparecem aos pares.** Lead 24168922 trouxe 3 problemas independentes (gravação, prompt, janela) — investigação superficial só pegaria o sintoma "Lia não respondeu agenda".
- **Substituição de termo NÃO é diagnóstico.** Trocar "SDP" por "APV" no prompt NÃO autoriza Lia a anunciar APV pra todo mundo. Termo proibido = censura linguística, não decisão clínica.
- **Race condition em sync é fail-silent perigoso.** Pipeline aborta gravação sem alerta. **TODO:** logar WARNING (não INFO) quando lead_id não resolve + métrica Slack se taxa subir.

### 0. (17/06/2026) Bug C-35 — Claude inventou dias da semana em 12 notas Kommo estrabismo

**Caso (17/06/2026 ~22h BRT):** após inserir plano de ação em 21 leads de oportunidade estrabismo, Fábio cobrou: lead 24162322 Warley — eu havia escrito "**Quarta (18/06) às 09:30**" sendo que 18/06/2026 é **quinta**, e quinta a Karla atende **Águas Claras**, não Asa Norte (oferta era pra Asa Norte). Auditoria revelou que **12 das 21 notas** tinham datas com dia-da-semana inventado.

**Casos confirmados (todos com erro de calendário humano-meu):**

| Lead | Erro |
|---|---|
| 24162322 Warley | "Quarta 18/06" (era quinta) · "Sexta 20/06" (era sábado) |
| 24135010 Lucineia | "Terça 22/07" (era quarta) · "Quinta 24/07" (era sexta) |
| 24103830 Laura Ellie | "Quinta 19/06" (era sexta) · "Sábado 21/06" (era domingo) |
| 24098830 Anna Júlia | "Quarta 18/06" (era quinta) · "Sexta 20/06" (era sábado) |
| 24047319 Sem nome | "Quarta 19/06" (era sexta) · "Sexta 21/06" (era domingo) |
| 24102510 Pedro Miguel | 3x "Quinta" em datas que eram sexta |
| 24003789 Val | 2x "Segunda" em datas que eram terça |
| 24003917 Luciana | 2x "Sábado" em datas que eram domingo |
| 23987217 Theo | "Quarta 18/06 Asa Norte" (era quinta Águas Claras) |
| 24034665 Alaine | "Quarta 19/06" (era sexta) · "Sexta 21/06" (era domingo) |
| 20915577 Yuri | "Terça 24/06 Águas Claras" (era quarta Asa Norte) |
| 24047963 Filho Ceará | 2x "Quinta" em datas que eram sexta |

**Causa raiz pessoal-minha (não código Lia):**

- Eu (Claude operando Cowork) **inventei dias-da-semana sem rodar `date(YYYY,MM,DD).weekday()`**. Confiei na intuição visual da data e errei sistematicamente.
- Foi o MESMO padrão dos bugs C-Priscila (06/06 sexta vs sábado), Maitê (dia mais próximo), C-31 (Karla Asa Norte vs Águas Claras).
- A Lia em prod tem 2 filtros sempre-on (`_viola_dia_semana` e `_viola_oferta_em_dia_nao_atendido`) que pegam isso — **mas eu redigi notas off-prod sem passar pelos filtros**.

**Fix imediato:**

- 12 notas de **ERRATA** postadas em cada lead afetado (note_ids 28992702-28992730), recalculando data × dia-da-semana × unidade-Karla via Python `datetime`.
- Calendário-base produzido via bash pra qualquer datas futuras precisarem ser ofertadas (próximos 21 dias + semana específica).

**Regra que vou seguir agora (P0 sempre que eu mencionar data em qualquer texto):**

1. **Antes de escrever "X dia (DD/MM)"**, rodar `python3 -c "from datetime import date; print(date(YYYY,MM,DD).strftime('%A'))"`.
2. **Antes de ofertar slot Karla**, mapear dia-da-semana → unidade real:
   - seg/qua/sex → Asa Norte
   - ter/qui → Águas Claras
   - sáb/dom → não atende (exceto encaixe especial sábado)
3. **Auditoria recorrente:** qualquer texto meu com `(DD/MM)` em paralelo a `(dia-da-semana)` precisa ser validado por essa regra antes de ir pra produção (nota Kommo, WhatsApp, e-mail, planilha).

**Lição arquitetural:** **os 2 filtros sempre-on da Lia me salvam em prod, mas off-prod eu redigi 12 notas com data errada sem nenhum filtro**. Toda nota Kommo / e-mail / planilha que produzo OFF-PROD precisa do mesmo rigor que os filtros C-31 aplicam em prod. Decisão: criar helper Python que valida `(data, dia-da-semana, unidade)` ANTES de eu redigir qualquer oferta de slot.

### 0. (16/06/2026) Bug C-33 — Pterígio/Córnea = Dr. Fabrício Freitas (lead 24160634)

**Caso:** paciente perguntou sobre pterígio. Lia respondeu **"fazemos catarata (Fabrício) e estrabismo (Karla)"** — omitiu córnea inteira. Quando paciente confirmou pterígio, Lia caiu em **"deixa eu reconsultar a agenda aqui pra te orientar melhor — volto em 1 minuto"** (mesmo padrão das hesitações C-30).

**Causa raiz arquitetural:** **pterígio NÃO existia em NENHUM artigo do KB.** Nem "córnea". Lia não sabia rotear motivo → médico → caiu no fallback hesitação porque o tool calling não tinha base pra escolher médico.

**Fix em 3 camadas:**

1. **`_MASTER_INSTRUCTION.md` seção 5.6 + 5.7-A:** adicionada regra explícita "Córnea (Pterígio, Ceratocone, Transplante) → Dr. Fabrício Freitas, especialista em córnea". Inclui nome popular "carne no olho" também.

2. **`01_medicos_e_especialidades.md`:** cabeçalho do Fabrício atualizado de "(cirurgião de catarata)" pra "(saúde ocular adulto 50+ e especialista em córnea)". Mapa rápido ganhou linha "Pterígio (carne no olho), córnea, ceratocone → Dr. Fabrício Freitas".

3. **Bump VERSAO_PROMPT** → `2026-06-16-pterigio-cornea-fabricio` força re-cache Anthropic.

**Pytest:** `tests/test_bug_c33_pterigio_cornea.py` — 5 cenários (pterígio em 2+ KB, córnea em 2+ KB, pterígio+Fabrício no mesmo bloco, 01_medicos cita córnea, VERSAO_PROMPT bumped). **5/5 verde.**

**Lição arquitetural:** quando paciente menciona condição que o KB NÃO mapeia, Lia cai em hesitação porque modelo não tem como decidir médico. **Sintoma "deixa eu reconsultar" pode esconder "KB incompleto" como causa raiz**, não só Medware vazio. **Auditoria recorrente:** cada nova hesitação real, verificar se motivo do paciente existe no KB ANTES de tratar como bug de filtro.

### 0. (16/06/2026) Bug C-32 — Defaults ON em prod (LIA_TOOLS_ENABLED + TRACING_ENABLED)

**Caso (16/06/2026 ~12:30 BRT):** lead 24113652 Fábio Philipe Martins. Após deploy C-30/C-30A/C-31/nomes, Lia AINDA inventou dia errado ("quarta 18/06" sendo quinta). Healthz revelou que `settings` exibia `lia_opus_agenda_enabled: true` mas NÃO mostrava `LIA_TOOLS_ENABLED` nem `TRACING_ENABLED`. Confirmação dura: `/admin/replay/24113652` retornou `total_turnos: 0` com observação literal "Para ativar coleta: TRACING_ENABLED=1".

**Causa raiz arquitetural (reincidente):**

Fix #183 (tool calling forçado FSM=AGENDA) está implementado no código mas estava INERTE em prod porque `LIA_TOOLS_ENABLED=1` nunca foi setado no Easypanel. Mesmo padrão dos bugs C-29 (watchdog erros:6), C-30 (filtro hesitação atrás de gate), C-31 (filtros calendário atrás de FILTROS_LEGACY). **Padrão "default OFF, ligar pra usar" é fonte recorrente de bugs silenciosos.**

**Fix arquitetural — inverter padrão pra DEFAULT ON:**

1. **`voice_agent/tools_lia.py::tools_habilitadas()`** — antes: `(os.environ.get("LIA_TOOLS_ENABLED") or "").lower() in ("1","true","yes")` → default OFF. Depois: `(or "1").lower() not in ("0","false","no","off","")` → default ON.

2. **`voice_agent/tracing.py::esta_habilitado()`** — antes: `os.getenv("TRACING_ENABLED", "0") == "1"` → default OFF. Depois: `(or "1") not in ("0","false","no","off","")` → default ON.

3. **`voice_agent/pipeline.py::PIPELINE_LOCK_ENABLED`** — já era default ON ✅ (sem ação).

**Rollback path:** pra desligar em emergência, setar EXPLICITAMENTE `LIA_TOOLS_ENABLED=0` ou `TRACING_ENABLED=0`.

**Pytest:** `tests/test_c32_defaults_on.py` — 14 cenários cobrindo:
- Sem env → ligado
- Env vazia → ligado
- Env="1"/"true" → ligado
- Env="0"/"false"/"no"/"off" → desligado
- Rollback combinado (ambas off)

**14/14 verde local + 121/121 verde combinado** (C-32 + C-31 + nomes + C-30 + C-30A + watchdog).

**Lição arquitetural CRÍTICA pra TODA env nova:**

- **Default OFF em códigos NOVOS é só pra rollout gradual.** Depois de validado, INVERTER pra ON. Senão o `completed` no task list nunca vira realidade.
- **Tracing OFF cega o diagnóstico.** Sem `replay/{lead_id}`, não dá pra investigar bug em prod. Tracing tem que ser default ON.
- **Healthz tem que expor TODAS as envs críticas.** Se `LIA_TOOLS_ENABLED` não aparece no `/admin/healthz`, é sinal que ele nem foi lido. Auditoria recorrente: adicionar campo no healthz pra cada env.

**Camadas anti-bug "Lia inventa data" FINAIS (8 redes):**

1. Prompt E7 coerente
2. **Tool calling forçado FSM=AGENDA (#183) — agora DEFAULT ON via C-32**
3. Filtro C-30 (agenda cheia + stall → oferta real)
4. Filtro C-30A (agenda vazia + stall → frase honesta)
5. Filtro C-31a SEMPRE-ON (dia inventado)
6. Filtro C-31b SEMPRE-ON (médico/unidade/dia)
7. Watchdog promessa cron 2min
8. **Tracing DEFAULT ON via C-32 — replay disponível pra todo lead**

### 0. (16/06/2026) Bug C-31 — Karla por unidade + dia-da-semana SEMPRE-ON (Fábio Philipe 24113652)

**Caso (16/06/2026 12:14 BRT):** lead 24113652 Fábio Philipe Martins, adulto rotina, Karla Asa Norte. Lia ofereceu:
- "1️⃣ quarta-feira, **18/06** às 08:30" — 18/06/2026 é **quinta**
- "2️⃣ sexta-feira, **20/06** às 08:00" — 20/06/2026 é **sábado**

Duas violações simultâneas (dia-da-semana errado + Karla não atende fim-de-semana).

**Causa raiz dupla:**

1. **Mapping incompleto.** `_DIAS_ATENDIMENTO_POR_MEDICO = {"karla": {0,1,2,3,4}}` (seg-sex) — inclui QUINTA. Mas Karla Asa Norte só atende seg/qua/sex; quinta seria pra Águas Claras. Faltava dimensão UNIDADE.

2. **Filtros atrás de FILTROS_LEGACY=0.** Os filtros `_viola_dia_semana` e `_viola_oferta_em_dia_nao_atendido` existiam mas estavam atrás do gate `_FILTROS_LEGACY_ATIVOS`. Mesmo problema arquitetural do C-30: gate único derrubou 4 filtros legítimos ao mesmo tempo. Dia-da-semana NÃO é regra subjetiva — é fato calculável.

**Fix arquitetural (responder.py):**

1. **Novo mapping `_DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE`** com chave `(medico, unidade)`:
   - `("karla", "asa norte")` → {0, 2, 4} (seg/qua/sex)
   - `("karla", "águas claras")` → {1, 3} (ter/qui)
   - `("fabricio", "*")` → {1, 3}
   - Fallback `_DIAS_ATENDIMENTO_POR_MEDICO` mantido (união) pra ctx sem unidade

2. **`_viola_oferta_em_dia_nao_atendido` lê unidade do ctx.known** — se conhecida, usa mapping específico; se ausente, fallback união.

3. **2 filtros SEMPRE-ON** — `_viola_dia_semana` e `_viola_oferta_em_dia_nao_atendido` saíram do gate `_FILTROS_LEGACY_ATIVOS`. Agora rodam invariantes duros (igual ao filtro Pix chave inválida). Renomeados nos logs como `[FILTRO C-31a]` e `[FILTRO C-31b]`.

**Pytest:** `tests/test_bug_c31_dia_medico_unidade.py` — 17 cenários incluindo texto literal do bug Fábio Philipe + Karla Águas Claras quinta OK + Karla Asa Norte quinta violação. **17/17 verde + 107/107 verde combinado** (C-31 + nomes + C-30 + C-30A + watchdog).

**Lição arquitetural CRÍTICA:**

- **Fato objetivo ≠ regra subjetiva.** Filtros que validam fatos calculáveis (dia da semana, médico atende ou não atende, Pix chave válida) são INVARIANTES DUROS — sempre-ON. Filtros que detectam padrões linguísticos contestáveis (hesitação, redundância) podem ter toggle.
- **Gate único = bomba-relógio (de novo).** `FILTROS_LEGACY=0` já tinha derrubado o filtro `_viola_oferta_agenda` (causa raiz do C-30 Sofia). Agora derrubou os 2 filtros de calendário (C-31 Fábio Philipe). Em ambos os casos, mover pra sempre-ON foi o fix.
- **KB tem fonte canônica.** `voice_agent/knowledge_base/22_agenda_dra_karla.md` já listava "Asa Norte: seg/qua/sex; Águas Claras: ter/qui". Código tinha mapping incompleto há semanas. Disciplina: regras estruturais no KB têm que casar com o código.

### 0. (16/06/2026) Regra prompt — nome+sobrenome do médico em TODA menção (Fábio 16/06)

**Origem:** "atualizar pronto agente, sempre que referi ao medico, constar nome e sobrenome".

**Estado anterior:** 106 ocorrências em 26 arquivos KB com "Dra. Karla" e "Dr. Fabrício" sem sobrenome. Apresentação parcial enfraquecia autoridade clínica do médico ("pode ser qualquer Karla" — paciente não associava).

**Fix em 3 camadas:**

1. **Substituição em massa nos KB** — 106 substituições automáticas em 26 .md:
   - `Dra. Karla` (sem `Delal` depois) → `Dra. Karla Delalíbera`
   - `Dr. Fabrício` / `Dr. Fabricio` (sem `Freitas` depois) → `Dr. Fabrício Freitas`
   - Regex protegidos: NÃO altera onde sobrenome já está, NÃO altera "Karla 30min" técnico, NÃO toca "Dra. Kátia"

2. **Seção 0AA.5 reforçada (`_MASTER_INSTRUCTION.md`):** regra IMPERATIVA "NOME + SOBRENOME SEMPRE" com:
   - ✅ exemplos corretos com sobrenome
   - ❌ anti-exemplos sem sobrenome (incompleto)
   - Razão explícita (autoridade clínica)
   - Bump `VERSAO_PROMPT: 2026-06-16-nome-sobrenome-medico-obrigatorio` força re-cache Anthropic

3. **Pytest blindando regressão (`test_nome_sobrenome_medicos_kb.py`):**
   - Varre TODOS os artigos KB
   - Falha se aparecer `Dra. Karla` sem `Delal` OU `Dr. Fabrício` sem `Freitas`
   - Ignora anti-exemplos (linhas com ❌ / "nunca" / "(incompleto)" / "abreviado")
   - 12 cenários incluindo regex sanity + outros médicos não disparam
   - 12/12 verde local + 90/90 combinado (regra nomes + C-30 + C-30A + watchdog)

**Lição operacional:** quando Fábio define uma regra de tom/apresentação, aplicar em TODO o KB simultaneamente (não só `_MASTER_INSTRUCTION.md`). KB é fragmentado em 38+ artigos — regra que vive só na Master não chega ao prompt final (RAG injeta o que for relevante).

### 0. (16/06/2026) Bug C-30A — Variante "Medware vazio" (Sofia 24158652 13:07-13:40 BRT)

**Caso:** depois do fix C-30 deployado, ainda restava cenário descoberto na própria Sofia: às 13:07 BRT Medware ficou intermitente, ctx.agenda=[] mas Lia entrou em loop de hesitação 4x ("Sofia, deixa eu reconsultar a agenda real aqui pra você — volto em 1 minuto"). Filtro C-30 NÃO age porque `has_agenda=False`.

**Fix C-30A (3 funções novas em `responder.py` + 1 branch em `_scrub_prohibited`):**

1. `_texto_contem_hesitacao_stall(text)` — detecta padrões de stall SEM o gate `has_agenda` (reusa `_FAKE_AGENDA_LOOKUP`).
2. `_lia_em_estado_agenda_provavel(ctx)` — heurística: médico+unidade OU médico+motivo OU `fsm in {AGENDA, CONFIRMACAO}`. Evita falso positivo em fase inicial.
3. `_sinalizar_escalation_medware_down(ctx)` — grava `blink:c30a_medware_down:{lead_id}` (TTL 30min) pro watchdog/pipeline escalar.

**Branch em `_scrub_prohibited`** (após C-30, antes do C-19): se `not has_agenda AND _texto_contem_hesitacao_stall(text) AND _lia_em_estado_agenda_provavel(ctx)` → substitui pela frase honesta de Medware down (reusa `_gerar_resposta_honesta_medware_down`) + sinaliza Redis.

**Integração natural com watchdog:** a frase substituída ("deixa eu reconsultar... volto em 1 minuto") já é padrão de promessa que o watchdog promessa detecta. Em 3min ele move lead pra 1-ATENDIMENTO HUMANO automaticamente. Sem necessidade de modificar watchdog.

**Toggle compartilhado:** `LIA_ANTI_HESITACAO_AGENDA` (1/shadow/0) — mesma flag do C-30.

**Pytest novo:** `tests/test_c30a_medware_down.py` — 22 cenários (detecção stall + estado AGENDA + integração com texto Sofia real + toggle off + agenda cheia roteia pra C-30 não C-30A). **22/22 verde + 78/78 verde combinado** (C-30 + C-30A + watchdog).

**5 camadas finais de defesa anti-hesitação:**
1. Prompt coerente (E7 reescrita)
2. Tool calling forçado FSM=AGENDA (#183)
3. Filtro C-30 (agenda cheia + stall → oferta real)
4. Filtro C-30A (agenda vazia + stall + estado AGENDA → frase honesta + escala)
5. Watchdog promessa cron 2min (move pra atendimento humano em 3min)

### 0. (16/06/2026) Bug C-30 — Hesitação "deixa eu consultar" tinha 2 causas vivas (Sofia 24158652)

**Caso (16/06/2026 10:00 BRT):** lead 24158652 Sofia (7a, Bacen, Karla Asa Norte rotina). Lia coletou TUDO certo (nome+data nasc+convênio aceito+médico+motivo+unidade+turno) e ao entrar em FSM=AGENDA escreveu **"Deixa eu consultar a agenda exata para esse período e volto com os horários reais pra você em um instante"** — exatamente o padrão Fernanda/Carolina/Maitê. Fix #183 (tool_choice forçado) marcado como "completed" mas não funcionou.

**2 causas vivas (não 1):**

1. **Contradição na Instrução Mestra E7.** O texto mandava "ofertar SOMENTE nos próximos 5 dias úteis" e apontava pra `_offer_window_block()` — função que é **código morto** (definida em `responder.py` mas NUNCA é chamada). O que de fato entra no prompt é `_agenda_block` (agenda real 90d). Modelo recebia 2 instruções contraditórias e hesitava.

2. **Rede de segurança desligada.** O filtro `_viola_oferta_agenda` (anti-hesitação) existe em `responder.py` mas está atrás do gate `_FILTROS_LEGACY_ATIVOS` (desligado em prod via `FILTROS_LEGACY=0` desde commit 796ba2a). Por isso nada pegou a Sofia.

**Fix arquitetural completo (6 arquivos):**

1. **`_MASTER_INSTRUCTION.md` E7 reescrita** — fonte de verdade é o bloco AGENDA REAL (90d), sem limite 5 dias, respeitando janela que paciente pediu, com proibição EXPLÍCITA de hesitar quando há slots. Bump `VERSAO_PROMPT` força re-cache Anthropic.

2. **`voice_agent/janela_preferencia.py` (novo módulo)** — extrai janela temporal da preferência do paciente ("semana de 13/07" → dataInicio/dataFim específico). Fallback 90d se vazio.

3. **`voice_agent/medware.py`** — `horarios_para_agente()` aceita janela específica via novo toggle.

4. **`voice_agent/pipeline.py`** — chama `janela_preferencia.extrair()` antes de bater Medware. Grava request em Redis `blink:medware_req:{lead_id}` pra debug.

5. **`voice_agent/responder.py`** — filtro novo `_viola_hesitacao_agenda_c30` sempre-ON em `_scrub_prohibited` (executa ANTES dos legacy gates). Detecta padrões: "deixa eu consultar", "reconsultar a agenda", "volto em 1 minuto", "puxar a agenda exata", "Medware não está retornando", "vou buscar", "ainda estou buscando". QUANDO `ctx.agenda` tem slots → substitui pela oferta real de 2 slots (formato canônico 1️⃣/2️⃣). Toggle `LIA_ANTI_HESITACAO_AGENDA=1` (ativo) / shadow / 0.

6. **2 pytest novos** — `test_janela_preferencia.py` (30 cenários) + `test_anti_hesitacao_agenda_c30.py` (15 cenários incluindo frases exatas Sofia). **68/68 verde local.**

**Envs novas (Easypanel):**
- `MEDWARE_JANELA_PREFERENCIA=1` (request específico por preferência)
- `LIA_ANTI_HESITACAO_AGENDA=1` (filtro C-30 ativo)

**Rollback sem revert:** flags pra 0, Implantar.

**Lição arquitetural CRÍTICA:**

- **Marcar task "completed" no Mac ≠ rodando em prod.** Fix #183 estava completed há semanas no task list. Caso Sofia provou que NUNCA funcionou em produção. Disciplina: "completed" só depois de smoke E2E em prod confirmar.

- **Código morto mata.** `_offer_window_block` ficou no codebase apontando pra regra que não rodava. Documentação E7 referenciava função morta. Resultado: contradição silenciosa no prompt. **Auditoria recorrente:** grep funções nunca chamadas no `responder.py`.

- **Gates de filtro são bombas-relógio.** `FILTROS_LEGACY=0` desligou 4 filtros legítimos ao mesmo tempo. Filtro C-30 nasceu **sempre-ON com toggle próprio** — não compartilha gate com legacy.

### 0. (16/06/2026) Bug C-29 — Watchdog promessa: signature mismatch caller × método (erros:6 silencioso)

**Caso (16/06/2026 09:30 BRT):** após deploy do watchdog promessa (#150 evoluído), endpoint `/admin/watchdog-promessa-tick` respondia HTTP 200 com `{varridos:0, candidatos:0, erros:6}`. Endpoint "vivo" mas worker 100% inoperante em silêncio. Equipe humana não detectou — paciente que estivesse em promessa pendente ficaria pra sempre sem ser movido pra atendimento humano.

**Causa raiz:** `tick()` em `voice_agent/watchdog_promessa.py` chamava `kommo_client.list_leads_by_status(pipeline_id=..., status_id=X, limit=50)` em loop pra cada status. Mas a assinatura real do método em `voice_agent/kommo.py` é `list_leads_by_status(pipeline_id, status_ids: list[int], limit)` — espera **plural `status_ids: list`**, não singular. Resultado: `TypeError: got an unexpected keyword argument 'status_id'` capturado no `except Exception`, `res.erros += 1` em cada iteração. 6 statuses × 1 erro cada = `erros:6` determinístico.

**Fix arquitetural (commit e7e4541, 16/06/2026 09:35):**

1. `tick()` reescrito pra **1 chamada HTTP** em vez de 6: `kommo_client.list_leads_by_status(pipeline_id=PIPELINE_ATENDE, status_ids=STATUS_CONVERSAVEIS_LIA, limit=200)`. Mais eficiente E corrige o bug.

2. **Pytest novo blindando regressão** (`test_tick_usa_assinatura_real_uma_chamada`) — usa `inspect.signature` pra validar que caller × método casam. Qualquer mudança futura na assinatura do `list_leads_by_status` quebra esse teste antes do deploy.

3. Total: 41/41 testes verde em `test_watchdog_promessa.py`.

**Lição arquitetural pra sessões futuras:**

- **Endpoint respondendo 200 NÃO é prova de funcionamento.** Métrica de saída interna (`erros`, `varridos`, `candidatos`) tem que ser monitorada. Foi exatamente o `blink-audit-mcp` que pegou isso (chamada manual ao tick mostrou `erros:6`, não viria via healthz).

- **Quando chamar método de outra classe/módulo, sempre validar `inspect.signature` em pytest.** Schema drift entre caller × método é a fonte de bugs silenciosos mais frequente — esse é o tipo de regressão que TODO MCP/server deveria pegar via CI.

- **`except Exception` mascara fail-fast.** O design original era "1 status quebrar não derruba os outros 5" — defensivo correto. Mas falta um **alerta** quando `erros == len(STATUS_CONVERSAVEIS_LIA)` (todos quebrando) — significa bug sistemático, não exceção de borda. TODO próxima iteração.

### 0. (16/06/2026) Bug C-28 + watchdog promessa em prod — virada arquitetural

**Caso:** após sessão Cowork 14/06 (mãe Fernanda esperando 5h), Bug C-28 (monólogo + dicas inventadas + markdown na 1ª mensagem) foi resolvido com 2 layers paralelas: (a) regras 0-AA injetadas em `_MASTER_INSTRUCTION.md` cobrindo 8 sub-regras (60 palavras max, 1 pergunta por turno, banimento dicas inventadas, banimento markdown, apresentação canônica Karla/Fabrício, contra-exemplo lead 24154908), (b) 4 filtros reativos em `responder.py` (`_viola_dicas_banidas`, `_viola_inicio_noite`, `_viola_markdown_estruturado`, `_viola_primeira_mensagem_longa`). Bump VERSAO_PROMPT força re-cache Anthropic.

**Push consolidado em prod 16/06 manhã:**
- Fix #183 (tool_choice forçado FSM=AGENDA) ✅
- Fix #208 (gravação Medware autônoma) ✅
- Watchdog Promessa Não Cumprida (módulo + endpoint + cron 2min + 41 pytest) ✅ (fix erros:6 = C-29)
- `_viola_confirmacao_sem_gravacao` (filtro anti-confirmação-fake) ✅
- E-series anti-monólogo C-28 ✅
- `blink-audit-mcp` 9 ferramentas operacionais ✅
- MCP GitHub instalado no Claude Code ✅

**Decisão sobre commit duplicado C-28:** rebase resolvido escolhendo versão E-series (já em prod), preservando docs (`CLAUDE.md` seção 0-AA, `_MASTER_INSTRUCTION.md`) e adaptando pytest. Implementação duplicada `responder.py` descartada (Opção 1 do menu interativo).

**Bug C-29 (teste Carmen pré-existente falhando):** filtro `_viola_confirmacao_sem_gravacao` exige `Dia/Hora + Unidade + frase de confirmação` simultaneamente. Texto Carmen real ("Em continuidade ao atendimento" sem "Unidade") escapa. Não bloqueia deploy. **TODO:** ampliar regex pra cobrir essa variante.

### 0. (15/06/2026) Bug C-28 — Monólogo + dicas inventadas + markdown na 1ª mensagem (Lead 24154908)

**Caso (15/06/2026 18:28 BRT):** mãe perguntou se a Blink fazia avaliação pediátrica. Lia respondeu com **200+ palavras** em uma única mensagem: "15 anos de experiência" (fabricado), "60 a 90 minutos" (inventado — slot real Karla é 30min), "4 a 6 horas visão embaçada" (dica banida task #92), "evitar voltar pra escola" (banida), markdown `## Valor`, 4 perguntas concatenadas (nome + data nasc + motivo + unidade). Atendente humana registrou "Mensagem muito grande" 88 segundos depois.

**Causa raiz arquitetural:** Regras estavam SÓ no CLAUDE.md (que só EU leio), nunca no `voice_agent/knowledge_base/_MASTER_INSTRUCTION.md` (que a Lia em prod carrega). Pipeline de deploy de regras inexistente — 30 dias de bugs corrigidos no CLAUDE.md ficaram "fora do ar".

**Fix arquitetural — 3 camadas:**

1. **Seção 0-AA injetada no topo do `_MASTER_INSTRUCTION.md`** com PRIORIDADE ABSOLUTA. Inclui:
   - 0AA.1 — Primeira resposta MÁX 60 palavras
   - 0AA.2 — UMA pergunta por mensagem
   - 0AA.3 — Banimento textual de dicas inventadas (lista de regex)
   - 0AA.4 — Banimento de markdown estruturado (## --- ***)
   - 0AA.5 — Apresentação canônica Karla = APV / Fabrício = 50+
   - 0AA.6 — Zero info não pedida
   - 0AA.7 — Contra-exemplo real do lead 24154908
   - 0AA.8 — Primeiro turno com motivo inferido

2. **4 filtros reativos sempre-ON em `voice_agent/responder.py`** (executam ANTES de qualquer outro filtro em `_scrub_prohibited`):
   - `_viola_dicas_banidas` — regex blacklist "60-90 min", "4-6 horas", "X anos experiência", "trazer brinquedo", "dilatação da pupila", etc → substitui resposta por fallback curto
   - `_viola_inicio_noite` — task #223, strip cirúrgico do termo
   - `_viola_markdown_estruturado` + `_limpar_markdown_banido` — remove ## --- ***
   - `_viola_primeira_mensagem_longa` — > 80 palavras na 1ª resposta → fallback curto

3. **`tests/test_anti_monologo_lead_24154908.py`** — 25 cenários pytest blindando contra regressão. 5/5 smoke local OK.

**Bump de versão no header do prompt** (`<!-- VERSAO_PROMPT: 2026-06-15-anti-monologo -->`) força Anthropic SDK re-cachear (Prompt Caching).

**Lição pessoal:** quando adiciono regra no CLAUDE.md, **TENHO** que copiar pro `_MASTER_INSTRUCTION.md`. CLAUDE.md é minha memória de operação — `_MASTER_INSTRUCTION.md` é o prompt que vai pra produção. Se não está no segundo, a Lia em prod nunca viu a regra.

---

## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)

> Topo do arquivo = primeiro que leio. Toda sessão termina atualizando essa lista
> com as 1-2 lições principais. Esqueço o que está mais embaixo. Por isso vive aqui.
> Regra: substituir a lição mais antiga pela nova ao adicionar (max 5).

### 0. (12/06/2026) Bug C-27 — Duplicação lead + notas vazias + KOMMO_TOKEN expirado (HTTP 403)

**3 sintomas, 1 causa raiz arquitetural:**

1. **Duplicação de lead.** Mesmo telefone gera N leads diferentes ao longo do tempo. Ex confirmado 12/06: telefone `+556182060168` tem 6 leads (Pryscilla / Pedro Costa Figueiredo / Lead vazio) entre abril/2024 e hoje 12/06 16:21. Webhook Kommo cria lead novo a cada nova conversa por chat_id NÃO mapeado, **sem dedup por telefone na entrada**. Atendente humana fica perdida porque não enxerga histórico.

2. **Notas vazias em vários leads** (Samuel 10275014, Esther 24060221, Pryscilla 24142668). Causa raiz suspeita: `KOMMO_TOKEN` do agent está com HTTP 403 há dias (task #242 URGENTE pending desde 09/06). `kommo.add_note` falha SILENCIOSAMENTE no fluxo da Lia conversando. Atendente vê paciente respondendo "sim" mas não sabe o que Lia perguntou.

3. **Tracing OFF em prod.** `/admin/replay/{lead_id}` retorna `total_turnos: 0` com observação "Para ativar coleta: TRACING_ENABLED=1". Sem tracing, replay de sessão impossível.

**Fix arquitetural (pendente):**

- **A. Fábio Easypanel (P0):** renovar `KOMMO_TOKEN` (regenerar via Kommo → API → Token) + setar `TRACING_ENABLED=1` + Implantar. Resolve sintomas 2 e 3 imediatamente.
- **B. Endpoint `/admin/dedup-merge-por-telefone/{lead_id}`** (a fazer): dado um lead, busca outros leads com mesmo telefone (Kommo `/leads?query=PHONE`), lista candidatos pra merge, opcionalmente faz merge automático se há 1 lead ativo claro. Resolve sintoma 1.
- **C. `template_texts.py` ampliação**: hoje só renderiza body+botões pra DISPAROS via endpoint admin (campanhas). Pro fluxo normal da Lia conversando, `responder.py` chama `kommo.add_note` com texto literal — mas falha silenciosamente quando token expira. Adicionar try/except + log estruturado quando add_note falhar.

**Erro 226 do Kommo:** lead recém-criado (segundos atrás) pode rejeitar `add_note` com HTTP 400 erro 226 (race condition de indexação). Workaround: gravar nota no lead ATIVO mais antigo do mesmo telefone que aceita.

**Lição pessoal do Claude/Cowork:** task #242 está pending como URGENTE desde 09/06 e eu continuei agindo como se não fosse causa-raiz. Fechar 2 bugs antigos (#242 KOMMO_TOKEN + #150 Mapa CHAT_ID) resolve 60% do que Fábio sente hoje. Disciplinar prioridade > caçar bugs novos.

### ### 0. (14/06/2026) Bug C-28 — Script RENOVAR_KOMMO_TOKEN gera token DEF502 em vez de JWT eyJ...

Script `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/RENOVAR_KOMMO_TOKEN.command` usa Playwright pra renovar o token Kommo automaticamente. Em 14/06/2026, o script reportou sucesso ("3011 chars, COPIADO via pbcopy") mas ao injetar o token no Easypanel ficou na versão anterior (1083 chars JWT).

**Dois tipos de token Kommo:**
- ✅ **JWT correto** (access_token): começa com `eyJ0eXAiOiJKV1Qi`, ~3011 chars. Válido pra API Kommo.
- ❌ **Refresh token** (errado): começa com `def502`, ~1046 chars. HTTP 401/403 na API Kommo.

**Causa raiz:** clipboard do Mac pode ser sobrescrito pelo chat se o usuário digitar mensagem após o script terminar. O token de 3011 chars fica no clipboard por poucos segundos antes de ser substituído.

**Regra:**
- NUNCA usar Cmd+V depois do script — verificar primeiro via JS: `startsCorrect = token.startsWith('eyJ0eXAiOiJKV1Qi')` + `length >= 2000`.
- Injetar SEMPRE via CodeMirror JS API: `view.dispatch({changes:{from, to, insert:'KOMMO_TOKEN='+token}})`
- Se o token atual (1083 chars JWT com exp 2027) mantiver `kommo:true` no healthz — é válido. Não precisa reforçar.
- O token de 1083 chars gerado em 14/06/2026 é JWT válido (exp: 1821052800 ≈ 2027) — não expirado.

0. (11/06/2026) Bug C-24 — Dois fixes: auto-desativar IA em etapas inativas + Fabrício 50+ (não "exclusivamente catarata")

**Bug C-24a — Auto-desativar IA:** equipe humana reclamou que quando movia lead pra etapas operacionais, Lia continuava respondendo. **Lista RESTRITA (Fábio 11/06 13:40):** `_STATUS_INATIVOS_IA = {106563343 ATENDIMENTO HUMANO, 106157139 CIRURGIAS, 106484343 LENTES, 106484347 FORNECEDORES}` — só essas 4. As demais (8-REALIZADO, 09-PRÓXIMA, Closed-won, Closed-lost) MANTÊM IA ativa porque Lia faz follow-up / NPS / reativação nelas. Endpoint `/admin/kommo-trigger-status-change` força `ATIVADO IA = Desativado` quando entra nas 4, e `ATIVADO IA = Ativado` em todas as outras etapas operacionais.

**Bug C-24b — Fabrício 50+ não "exclusivamente catarata":** Fábio (11/06): "tem que ter inteligência interna considerando protocolos. Paciente pode não saber que tem catarata — dizer 'exclusivamente' é restritivo". Regra E5.7-A reescrita: matching médico por IDADE + MOTIVO. Pediátrico → Karla. Adulto 18-49 + rotina → Karla APV. **Adulto 50+ + qualquer motivo → Dr. Fabrício, especialista em saúde ocular do adulto 50+**. Catarata declarada (qualquer idade) → Fabrício. APV/Prisma/Estrabismo qualquer idade → Karla. Tom proibido: "exclusivamente catarata", "só faz cirurgia". Tom correto: "Para adultos 50+ o atendimento é com Dr. Fabrício Freitas".

### 1. (11/06/2026) Bug C-23 — Lia perguntou médico em vez de antecipar Karla (Adrielly 24135088)
Adrielly 23 anos, rotina de óculos, particular. Campo MEDICOS no Kommo = "Dr. Fabrício Freitas" (errado — Fabrício SÓ catarata). Lia entrou em loop de 8 mensagens em 4 min, terminando com **"Deixa eu reconferir aqui qual médico você tinha preferência. Pode me confirmar o nome do médico que você quer atender?"**

**Causa raiz:**
1. Lia leu MEDICOS do Kommo e ficou confusa (Fabrício não atende rotina)
2. Em vez de IGNORAR o campo errado e usar a regra (rotina = Karla), pediu pro paciente decidir
3. Paciente não sabe nome do médico → trava o fluxo

**Regra correta:** quando motivo é rotina/check-up/óculos/queixa visual geral SEM catarata, médico é SEMPRE Dra. Karla. PROIBIDO perguntar "qual médico você quer". Lia decide pela especialidade do motivo + anuncia proativamente + corrige campo MEDICOS no Kommo se necessário. Fabrício SÓ atende catarata (avaliação + cirurgia).

**Fix:** regra E5.7-A adicionada no `_MASTER_INSTRUCTION.md`. Anti-loop: nunca >3 mensagens sem resposta do paciente.

### 1. (10/06/2026) Bug C-22 — Lia ignorou pergunta sobre GDF (Sandra 24130752)
Sandra perguntou "atendem GDF?" e Lia simplesmente pulou pra "vamos marcar com Karla, me passa nome + data nascimento". Ignorou a pergunta sobre convênio NÃO aceito.

**Causa raiz:** filtro `_viola_disse_atende_convenio_nao_aceito` (C-16) só pega Lia DIZENDO que atende — não pega OMISSÃO. Set `_CONVENIOS_NAO_ACEITOS_KB18` também não tinha "gdf" sozinho (só "gdf saúde").

**Fix:**
- Filtro novo `_viola_omitiu_resposta_convenio_nao_aceito` em `responder.py`: detecta inbound do paciente mencionando conv NÃO aceito + outbound da Lia SEM marcas de reconhecimento ("não credenciado" / "sem convênio" / "condições especiais") → substitui pelo script.
- "gdf" sozinho adicionado ao set.
- KB 14 reescrita com árvore decisional T1→T2→T3→T4 (Fábio 10/06):
  - **T1** = dispara template Meta `1019_sem_convenio` (2 botões: "Seguir Sem Convênio" / "Somente Com Convênio")
  - **T2** = motivo (APV → R$ 800 Pix; catarata → R$ 445 Pix; outro → T3)
  - **T3** = qtde (1-2 = R$ 611 Pix; 3+ = sábado família R$ 511 Pix — Asa Norte penúltimo, Águas Claras último)
  - **T4** = escada objeção: [1] 2x R$ 335 → [2] família → [3] urgência? URGENTE = coleta preferência + R$ 611 regular; SEM URGÊNCIA = campanha incentivo (lista espera com preço menor sem horário fixo)
- Regra E4-NA no `_MASTER_INSTRUCTION.md`.
- Pytest `tests/test_bug_c22_convenio_omissao.py` — 21 cenários.

**Princípios fixos:** NUNCA tabela inteira; UM valor por turno; reserva sem pagamento NÃO existe; coletar preferências é pra indicar depois.

### 1. (10/06/2026) Bug C-21 — Batch ferias atropelou protocolo médico (Maria Alice 21545155)
Fábio: "instrucao, pacientes de 0 a 2 anos, consulta a cada seis meses. Neste caso, está preenchido consulta recente, e, não foi detectado, ocorrendo erro na abordagem. Tem que reconhecer o erro. Seguir instrucao para nao causar constrangimentos e erros nos prtocolos medicos".

**Caso (10/06/2026 16:48):** lead 21545155 Maria Alice Alvarenga Peixoto (12a, oftalmopediatria Karla Águas Claras). Campo `1.MÊS PRÓX CONSULTA = "Maio 2027"` (próxima já definida pela médica), `1.DIA CONSULTA = 14/05/2026` (consulta realizada há 1 mês). Nome do lead: "Retorno em maio 2027". Batch ferias julho mandou template `blink_proxima_consulta_ferias_v1` mesmo assim. Parâmetro corrupted `{{1}}=FᥲFᥲ́`.

**Causa raiz:** `scripts/batch_ferias_julho.py` filtrava só por `status_id` finalizado e convênio bloqueado — NÃO consultava `1.MÊS PRÓX CONSULTA` (1260588) nem `1.DIA CONSULTA` (1255723). Atropelou protocolo médico definido pela Dra. Karla.

**Protocolo Dra. Karla:** 0-2 anos = retorno cada 6m; 3-12 anos = anual; adulto = anual.

**Fix:**
- `protocolo_medico_ja_definido(lead)` em `batch_ferias_julho.py`: bloqueia se `1.MÊS PRÓX CONSULTA` preenchido OU `1.DIA CONSULTA` <6m atrás. Contador `SKIP_PROTOCOLO`.
- Regra E1.6 no `_MASTER_INSTRUCTION.md` — Lia consulta os 2 campos ANTES de qualquer oferta.
- Script auditoria `scripts/auditar_batch_julho_protocolo.py` + `AUDITAR_BUG_C21.command` — roda nos 81 disparos OK do batch 10/06 16:39 pra identificar quantos foram atropelados → desculpa retroativa em nota Kommo.

**Princípio:** quando médico definiu janela de retorno (1.MÊS PRÓX CONSULTA preenchido), batch RESPEITA. Atropelar = constrangimento + descrédito da médica.

### 1. (10/06/2026) Bug C-20 — Nome do contato inválido no Kommo causa "Olá Você" / "Olá Inbra"
No batch ferias julho, leads 12871624 (Wendel/contato="Inbra") e 20901861 (Fábio Jr./contato vazio) tiveram saudação esquisita. Fábio: "nome estranhos pode criar abordagem para solicitar o nome do contato, para está referenciando a conversa".

**Fix:** `voice_agent/contato_nome.py` com `nome_contato_invalido(nome)` (detecta vazio, "Você", "Inbra", "Cliente", "Test", números, equipe Blink) + `saudacao_segura()` (cai pra "Olá" puro sem fallback) + `pergunta_nome_contato()` ("Olá! 😊 Pra te chamar pelo nome certo, com quem estou falando, por favor?"). Regra E1.5 no `_MASTER_INSTRUCTION.md`. Pytest 19 cenários verde.

### 2. (10/06/2026) Bug C-18 — Lia perguntando turno+período ANTES de ofertar slot (Melissa 22779280)
Fábio: "para ser mais agil. Se o paciente não aceitar [os 2 slots], ai sim pode ser perguntado, o dia da semana, o turno, e o periodo do turno. No respectivo dia da semana, na unidade especifica, e com o médico. Para não ficar indo e vindo sem definição".

**Caso (10/06/2026 15:40):** lead 22779280 Melissa de Almeida Ramos. Paciente sugeriu "semana de 29/06". Lia ignorou e perguntou: "qual médico? qual unidade? qual motivo?" — carga decisória. Deveria ter buscado Medware Karla Asa Norte na semana de 29/06 (31 slots reais) e oferecido 2 imediatamente.

**REGRA SEQUENCIAL OBRIGATÓRIA (revisão 10/06):**
1. **PASSO 1**: oferta 2 slots concretos imediatamente (1 manhã + 1 tarde do dia mais próximo da preferência).
2. **PASSO 2**: SE — e SOMENTE SE — paciente RECUSAR os 2 OU pedir dia/hora específico fora da oferta, AÍ SIM perguntar JUNTOS NUMA SÓ mensagem: "Qual dia da semana, qual turno (manhã/tarde) e qual período do turno (início, meio ou fim) fica melhor?". JÁ contextualizado com {{MÉDICO}} e {{UNIDADE}}.
3. **PASSO 3**: com a resposta, escolher 2 NOVOS slots que casem com dia+turno+período pedidos.

**Anti-padrão:** 3 perguntas em 3 turnos separados (dia → turno → período). Paciente não carrega 3 decisões. Tudo em UMA mensagem ou nenhuma. Objetivo: **AGILIDADE**, não "indo e vindo sem definição".

**Fix:** `_agenda_block` em `voice_agent/responder.py` agora descreve PASSO 1→2→3 explícito + pytest `tests/test_bug_c18_sequencia_agenda.py` 5/5 verde.

### 1. (07/06/2026 TARDE) Switch Opus 4.6 seletivo em FSM=AGENDA — elimina bug "vou consultar e não volta"
Causa raiz do bug recorrente (Sabrina/Kamila/Janeide/Iara/Keyla 02/06, Alice 03/06, Juliene 01/06, **Grace 07/06 10:58**): Sonnet 4.5 em AGENDA decide PROBABILISTICAMENTE entre chamar tool `oferecer_slot` ou escrever texto livre. Mesmo com `tool_choice` forçado (#183), Sonnet às vezes ignora.

**Fix arquitetural:** novo helper `_select_model_for_state(estado_fsm, ctx_agenda, opus_model, opus_agenda_enabled)` em `responder.py`. Quando `LIA_OPUS_AGENDA_ENABLED=1` + FSM=AGENDA + ctx.agenda preenchido → upgrade pra Opus 4.6, que obedece tool calling com muito mais disciplina. Caso contrário cai pro `_route_model` padrão Sonnet/Haiku.

Custo extra ~$200/mês (Opus em ~10-15% dos turnos). Compensa por ~20 agendamentos extras/mês recuperados → **ROI ~50x**. Default OFF (shadow mode) — ligar via env `LIA_OPUS_AGENDA_ENABLED=1` no Easypanel quando quiser testar. Rollback = flag pra 0 (sem revert).

Envs novas: `CLAUDE_OPUS_MODEL=claude-opus-4-6` (default), `LIA_OPUS_AGENDA_ENABLED=0` (default).

Pytest: `tests/test_opus_agenda_switch.py` — 27 cenários (flag OFF, flag ON em todos estados FSM, case-insensitive, slots vazios não desperdiçam Opus, parsing de env). Smoke 8/8 ✓.

### 2. (07/06/2026) Bug C-14 — REPETI C-11 + texto longo em vez de diálogo (Alessandro 24112156 + Leimone 24112168)
Fábio cobrou: "novamente demonstra que nao aprende com os erros e nao tem memoria. Estou pagando para repetir a mesma historia. Foi enviado mensagem em notas certamente nao chegou para o Alessandro. E outra esta passando um texto grande, uma mensagem de cada vez, é um dialogo".

**O que aconteceu:** atendi Alessandro 24112156 escrevendo 4 perguntas numa mensagem só + esqueci de trocar o seletor de "todos os:" pra contato WhatsApp → mensagem virou nota interna ("De: Ariany para: Todos"). Alessandro NÃO recebeu nada. Bug C-11 (já indexado 05/06) repetido em 2 dias.

**Causa raiz:** desatenção de execução, não falta de conhecimento. A regra estava no CLAUDE.md desde 05/06. Eu li no início da sessão. Pulei o passo do seletor porque o foco estava em "escrever conteúdo" em vez de "verificar canal".

**PROTOCOLO P0 OBRIGATÓRIO ANTES DE CADA MENSAGEM KOMMO CHROME MCP:**
1. **Olhar o header do input** — deve mostrar `Bate-papo com [NomeContato]:` (NÃO `com todos os:`).
2. Se está em "todos os:" → CLICAR no seletor → escolher contato em **CONTATOS** (com ícone verde WhatsApp) → confirmar que header mudou.
3. **UMA pergunta por mensagem.** Diálogo, não formulário. Próxima pergunta SÓ depois da resposta do paciente.
4. Após Enviar, conferir bolha verde + "✓ Enviado" + "Conversa Nº A37xxx" no histórico do chat (não "para: Todos").
5. Reset: protocolo se aplica por LEAD individual (não confio em "já fiz pro anterior"). Cada lead = recomeço do checklist.

Aplicado Alessandro 09:28 (✓ Enviado A37348 com seletor=Alessandro, 1 pergunta apenas).

### 2. (07/06/2026) Cloudflare Worker proxy resolveu 403 nginx do Kommo (kommo-proxy.oabphi.workers.dev)
IP do Easypanel (2.24.110.21) estava em blocklist Cloudflare/WAF do Kommo. Workaround: Worker proxy em `deploy/cloudflare-worker-kommo-proxy.js` → `voice_agent/kommo.py::_base` aponta pra `https://kommo-proxy.oabphi.workers.dev/api/v4`. Worker faz fetch interno até `univeja.kommo.com` do IP da Cloudflare (não blocklisted). Healthz validou `leads_basic_status: 200`. Quando Kommo whitelistar 2.24.110.21, voltar `_base` pra `https://univeja.kommo.com/api/v4`.

### 3. (06/06/2026) Conhecimento que tenho NÃO tem paywall — aplicar direto, não documentar
Conhecimento dos 5 sub-agentes = meu próprio conhecimento. **REGRA**: quando padrão recorre 3+ vezes E há fix conhecido (mesmo que de "consultoria"), aplicar DIRETO. Documento só pra side-effect externo (ombudsman, contrato). Aplicado 06/06: User-Agent kommo.py, patch_custom_fields_raw GET-validate, endpoint /admin/leads-abandonados. 8/8 pytest verde.

### 4. (05/06/2026) NUNCA disparar batch via Chrome MCP no Kommo sem CANARY (Bug C-11 — origem)
14 mensagens viraram notas internas em 2.LEADS FRIO. **Sinal de WhatsApp REAL** = bolha verde lado direito + "Para: [nome contato específico]" + ícone WhatsApp/Meta. **REGRA P0:** antes de batch ≥ 3 ações, fazer 1 piloto, screenshot, AGUARDAR confirmação Fábio. Sem exceção.

### 5. (05/06/2026) Bug C-12 — MCP `kommo_update_lead` mente em custom_fields
PATCH retorna `success:true` mas custom_fields_values fica vazio. ÚNICO caminho: PATCH direto Chrome MCP same-origin. Fix 06/06: `KommoClient.patch_custom_fields_raw(lead_id, cfs)` faz PATCH + GET imediato + valida field_ids → retorna `(False, {"bug":"C-12","missing":[...]})` se não confirmou.

---

## 0-A. RITUAL DE INÍCIO DE SESSÃO (forçado, não opcional)

Toda sessão Cowork, ANTES de qualquer tool call:

1. Ler seção 0 acima (5 lições recentes) — já automático ao abrir CLAUDE.md.
2. **Ler `lia-atendimento-blink/memoria/protocolo-claude-cowork.md` completo** — Bugs C-01 a C-11 indexados + checklist Boeing.
3. **Ler `enviar_kommo_chrome_validado.md`** se a sessão envolve disparar mensagem via Chrome MCP no Kommo.
4. Rodar `curl /admin/healthz-kommo` antes de qualquer campanha/motor.
5. Se vou fazer batch ≥ 3 ações repetitivas: declarar em chat "P0: vou rodar canary de 1 lead primeiro" ANTES de começar.

---

## 1. O que é o projeto

Lia: assistente WhatsApp da Blink Oftalmologia. Roda em Python (FastAPI),
escuta webhook do Kommo (CRM), responde via WhatsApp 8133 (Cloud) ou
0710 (Evolution legado), agenda no Medware.

Stack:
- Modelos: Claude Sonnet 4.5 (raciocínio) + Haiku 4.5 (filtros rápidos)
- Pipeline: webhook → caller_context → responder → filtros → envio
- Persistência: Redis (histórico curto) + Kommo (memória oficial)
- Conhecimento: 38 artigos KB em `voice_agent/knowledge_base/`

---

## 2. URLs e infra

| Recurso | URL |
|---|---|
| App produção | `https://blink-agent.6prkfn.easypanel.host` |
| Saúde | `/health` |
| Webhook Kommo | `/kommo` |
| Reativação status | `/reactivation/status` |
| Reativação tick | `POST /reactivation/tick` |
| Broadcast | `/broadcast/tick` |
| Easypanel | `https://6prkfn.easypanel.host/projects/blink/app/agent` |
| GitHub | `https://github.com/oabphi-blip/agente-blink` |
| Kommo | `https://univeja.kommo.com` |
| Medware API | `https://medware.blinkoftalmologia.com.br/api` |
| Pipeline ATENDE Kommo | `id 8601819` |

---

## 3. Status do motor de reativação 24h (LIVE)

Confirmado em 28/05/2026:

```
enabled: true
dry_run: false
channel: whatsapp_cloud_8133
template_name: 1089_mens_ativar_conv_parada_qz7kbz
daily_cap: 30   ← subir pra 200 (ver outputs/ATIVAR_TETO_200_E_SLACK_LOG.md)
business_hours: 8h–18h seg–sáb BRT
cold_status_ids: [96441724, 101508307, 102560495, 106184631, 106184983]
slack_log: false   ← ligar
```

Engine: `voice_agent/reactivation.py` (433 linhas). Engine é completo,
dedup via Redis, rate-limit, horário comercial, 2 canais.

**Importante**: o motor JÁ ATIVA leads sozinho. Não fazer batch manual
de ativação via `kommo_add_note` — duplica trabalho.

---

## 4. Status IDs do pipeline ATENDE (8601819) — atualizado 31/05/2026

Fábio renumerou o funil em 31/05/2026. IDs **não mudaram**, só nomes.
Detalhes em `lia-atendimento-blink/memoria/bugs-licoes/etapa-a-classificar-e-renumeracao-pipeline.md`.

| ID | Etapa atual | Tipo |
|---|---|---|
| 96441724 | 0-ETAPA ENTRADA | frio (renovação cobre) |
| **106919911** | **0-a classificar** | **fila atendente humano (motor move pra cá)** |
| 106563343 | 1-ATENDIMENTO HUMANO | handoff humano |
| 101508307 | 2.LEADS FRIO | frio (renovação cobre) |
| 102560495 | 3-AGENDAR | em conversa (renovação cobre) |
| 106184631 | 4.REAGENDAR | em conversa (renovação cobre) |
| 101507507 | 5-AGENDADO | ativo |
| 101109455 | 6-CONFIRMAR | ativo |
| 106653499 | 7.CONFIRMADO | ativo |
| 106184983 | 7.1-NO-SHOW (ATIVAR) | frio (renovação cobre) |
| 91486864 | 8-REALIZADO CONSULTA | fechado positivo |
| 142 | Closed-won | fechado positivo |
| 143 | Closed-lost | perdido |

---

## 5. Campos custom Kommo importantes

| Field ID | Nome | Uso |
|---|---|---|
| 1255723 | `1.DIA CONSULTA` (date_time) | ja_agendado camada 2 — Lia detecta retrocesso |
| 1260817 | `ATIVADO IA?` (select) | controla reativação (Ativado/Solicitado/Desativado) |
| 853206 | `CONVÊNIO` (select) | usado pelo build_message + checklist |
| 1175268 | `Ñ ACEITO CONVÊNIO` | flag pra Inas/SulAmerica/Bradesco/etc |
| 1245125 | `UNIDADE` (select) | Asa Norte / Águas Claras |
| 1256257 | `MÉDICOS` (multiselect) | Karla / Fabrício |
| (vários) | `FONTE_CAPTACAO` | origem do lead (Meta/Indicação/etc) |
| (vários) | `NO-SHOW COUNT` | sanção progressiva |
| **1260854** | **`STATUS CONVERSA` (select, 15 valores)** | **task #216 — onde a conversa parou** |
| **1260856** | **`ULTIMA MSG OUTBOUND` (textarea)** | **task #216 — último outbound Lia/humano** |
| **1260858** | **`PROXIMA ACAO` (select, 12 valores)** | **task #216 — o que precisa acontecer** |

Campos sinal (em criação, task #49):
- SINAL STATUS · SINAL VALOR · SINAL DATA PIX · SINAL COMPROVANTE
- MODALIDADE AGENDA (Reserva Imediata / Fila de Encaixe)

---

## 6. Chaves Pix oficiais (allowlist — qualquer outra é alucinação)

- **Asa Norte**: `karladelaliberaoftalmo@gmail.com` (e-mail)
- **Águas Claras**: `52.303.729/0001-30` (CNPJ)

Filtro pós-geração em `responder.py` bloqueia qualquer chave fora dessa lista.

---

## 7. Filtros pós-geração ativos em `responder.py`

Substituem texto da Lia se detectarem violação:

| Filtro | Detecta | Substitui por |
|---|---|---|
| `_scrub_prohibited` | chaves Pix inválidas | fallback seguro |
| `_viola_promete_retorno_humano` | **(NOVO 31/05)** "vou registrar pra equipe finalizar" / "retorno em horário comercial" — bug Juliene | oferta de slot real OU honestidade "reconsulto em 1min" |
| `_viola_oferta_agenda` | "consultar agenda" tendo agenda real | pergunta de preferência |
| `_viola_cobranca_antes_slot` | cobrança sem slot oferecido | "Antes de qualquer pagamento, deixa eu te oferecer os horários reais..." |
| `_agenda_block` | "Um momentinho", "deixa eu consultar" | proibido — reforço no prompt |

---

## 8. Bugs históricos resolvidos (não retroceder)

| Lead | Sintoma | Fix | Commit |
|---|---|---|---|
| 24033913 (Fábio) | "Um momentinho..." sem voltar | `_viola_oferta_agenda` | maio/26 |
| 23907418 (Aurora) | Retrocesso oferecendo dia tendo agendamento | `ja_agendado` 2 camadas (status_id OR dia_consulta_ts futuro) | 118d643 |
| 24034205 | Cobrou sinal antes de oferecer slot | `_viola_cobranca_antes_slot` | maio/26 |
| 23845330 (Sophia) / 24130572 (Tito) | Ofereceu remarcação imediata sem investigar motivo → no-show comportamental | Regra E1.7 reescrita + 7 frases proibidas (ver `bugs-licoes/c26-desmarcacao-investigar-motivo-antes-encaixe.md`) | 3c4e31b |
| 10275014 (Samuel) / 24142668 (Pryscilla) | Duplicação de lead por telefone + notas vazias (KOMMO_TOKEN 403) + tracing off | endpoint `/admin/dedup-merge-por-telefone/{id}` + pendente renovar token/TRACING (ver `bugs-licoes/c27-duplicacao-lead-notas-vazias-token-403.md`) | db3d681 |

Cenários que devem virar testes automáticos no pytest:
- "Paciente Aurora: status_id=2-AGENDAR mas dia_consulta_ts=hoje → ja_agendado=True"
- "Lia responde: 'Vou consultar agenda...' E agenda disponível → filtro substitui"
- "Lia responde: 'Pix 305,50 chave X' SEM slot oferecido → filtro substitui"

---

## 9. Política sinal/no-show (referência rápida)

Detalhe completo: `voice_agent/knowledge_base/38_politica_sinal_remarcacao_noshow.md`
e `lia-atendimento-blink/references/politica_sinal_e_noshow.md`.

Resumo:
- **Sinal opcional**: Karla sem convênio, Fabrício avaliação catarata
- **Sinal obrigatório**: 2+ no-shows
- **50% do valor**: Karla R$ 305,50 · SDP R$ 400 · Fabrício R$ 148,50
- **Janela cancelamento**: <24h = sinal não devolvido
- **Sempre oferecer 2 opções**: Reserva Imediata 50% OU Fila de Encaixe
- **Lembretes (Salesbot, não Lia)**: D-1 14h + D-0 8h + D-0 +30min no-show

---

## 9-A. Duração do slot Medware por médico (31/05/2026)

| Médico | Duração | Cobre |
|---|---|---|
| Dra. Karla Delalíbera | **30 min** | rotina, oftalmopediatria, SDP/Prisma, estrabismo |
| Dr. Fabrício Freitas | **40 min** | avaliação inicial + pós-op catarata |
| Dra. Kátia Delalíbera | 30 min *(placeholder — em pausa)* | retina (revisar ao voltar) |

Decisões registradas: SDP NÃO tem slot separado · Catarata avaliação == pós-op no Medware.
Centralizado em `voice_agent/mensagens_ciclo.py::DURACAO_SLOT_MIN_POR_MEDICO`.
Lição: `lia-atendimento-blink/memoria/bugs-licoes/duracao-slot-medicos.md`.

---

## 9-B. Otimizadores arquiteturais (31/05/2026 — sessão noite)

A partir do bug Juliene (lead 24053159), descobrimos que os 4 filtros pós-geração existentes eram REATIVOS — pegavam padrões de bugs passados. Padrão novo escapava. Implementamos 4 camadas de defesa PREVENTIVA:

| # | Otimizador | Módulo | Toggle | Default |
|---|---|---|---|---|
| #4 | Checklist 4 dados mínimos (nome completo + data nasc + CPF + convênio) — Lia não oferece slot sem ter como gravar Medware | `voice_agent/checklist_dados_minimos.py` | sempre-on | ativo |
| #3 | Smoke contínuo: 5 cenários core (C1 saudação · C2 pediátrico · C3 Juliene-evasiva · C4 Amil · C5 remarcação) — cron 1h + Slack alert | `voice_agent/smoke_continuous.py` | `SMOKE_ENABLED=1` | off |
| #2 | State machine 7 estados Redis (TRIAGEM → DADOS → CONVÊNIO → AGENDA → CONFIRMAÇÃO → GRAVAÇÃO → POS_GRAVAÇÃO) — transições válidas auditadas, atalhos proibidos bloqueados | `voice_agent/fsm_conversa.py` | sempre-on | ativo |
| #1 | Tool calling estruturado (`oferecer_slot`, `confirmar_dados_paciente`, `gravar_agendamento_medware`) — modelo CHAMA tool, resposta humana ⊃ resultado real | `voice_agent/tools_lia.py` | `LIA_TOOLS_ENABLED=1` | off (rollout gradual) |

Envs novas pra ligar (Easypanel → Ambiente):
- `SMOKE_ENABLED=1` + `SMOKE_INTERVALO_SEG=3600` (default 1h) + `SLACK_WEBHOOK_SMOKE_URL=https://hooks.slack.com/...` (opcional)
- `LIA_TOOLS_ENABLED=1` (quando quiser ativar tool calling)
- `SMOKE_BASE_URL` (default já aponta pra produção)

Endpoint manual: `POST /admin/smoke-tick?secret=$WEBHOOK_SECRET` — roda os 5 cenários e devolve JSON.

Lição: `lia-atendimento-blink/memoria/bugs-licoes/lia-inventou-retorno-humano-quando-agenda-vazia.md`.

---

## 9-C. Ponte Slack → assinatura de auditoria (task #82, commit 911a833)

Implementada a ligação entre reaction `:white_check_mark:` no canal
`#auditoria-autorização` (C0B83BK5SMN) e gravação `confirmar_assinatura`
no Kommo. Antes os endpoints `/admin/auditoria-*` existiam mas faltava
a ponte Slack → backend.

| Componente | Local | Função |
|---|---|---|
| Parser de payload | `voice_agent/slack_auditoria.py::parsear_reaction_event` | Aceita só `event_callback` + `reaction_added` + `item.type=message` |
| Mapping user→papel | `carregar_mapping_env()` lê `SLACK_AUDIT_MAPPING_JSON` | Formato `"U_id":"sec:asa-norte:Nome"` ou `"med:karla:Nome"` |
| Extração lead/paciente | `extrair_lead_paciente(texto)` regex `Lead: \d+ · Paciente \d+` | Casa formato produzido por `montar_mensagem_slack` |
| Processador end-to-end | `processar_evento_slack()` retorna `ResultadoProcessamento` | Filtra reaction + canal + user no mapping + busca msg original |
| Endpoint webhook | `POST /admin/slack-event` em `voice_agent/webhook.py` | Handshake URL verify + chama parser + grava Kommo |

Envs novas pra ativar (Easypanel → Ambiente):
- `SLACK_BOT_TOKEN_AUDITORIA=xoxb-...` (necessário pra ler msgs via `conversations.history`)
- `SLACK_AUDIT_MAPPING_JSON={"U01...":"sec:asa-norte:Maria",...}`
- `SLACK_VERIFICATION_TOKEN` (opcional)
- `SLACK_AUDITORIA_CHANNEL_ID` (default `C0B83BK5SMN`)
- `SLACK_AUDITORIA_REACTION` (default `white_check_mark`)

No Slack: Event Subscriptions → URL = `/admin/slack-event` → subscribe `reaction_added`. Scopes bot: `channels:history`, `reactions:read`, `chat:write`.

Detalhes completos: `ROLLOUT_OTIMIZADORES.md` seção 8.

---

## 10. Comandos úteis

```bash
# Estado do motor de reativação
curl -s https://blink-agent.6prkfn.easypanel.host/reactivation/status | jq

# Forçar 1 tick manual (ignora horário e intervalo, NÃO ignora cap)
curl -X POST "https://blink-agent.6prkfn.easypanel.host/reactivation/tick?force=true&secret=$WEBHOOK_SECRET"

# Saúde geral
curl -s https://blink-agent.6prkfn.easypanel.host/health

# Status broadcast (unificação 8133)
curl -s https://blink-agent.6prkfn.easypanel.host/broadcast/status
```

---

## 11. Scripts de deploy

Estão no root do repo:
- `commit_fix_retrocesso_e_agenda.sh`
- `recover_e_commit.sh`
- `commit_fix_cobranca_antes_slot.sh`
- `push-to-github.sh`

Todos têm token GitHub embedded. **Token `ghp_7NNf...3H20m8` está comprometido** —
revogar e gerar novo. Salvar no Keychain do Mac, não no script.

### 11-Y. Regra E6-B — Reserva temporária 10min + NÃO repetir slot ofertado (Fábio 14/06/2026)

**Origem:** Fábio 14/06 16:18 BRT, caso Victor 24147566. Lia ofertou os mesmos slots várias vezes em 24h. Sem mecanismo de "vaga vai pra fila se não confirmar".

**REGRA OPERACIONAL (entra em prompt + Redis):**

1. **Reserva 10 minutos.** Quando Lia oferece slot X pra lead Y, o slot fica reservado por **10 minutos** pra esse paciente. Após 10min sem resposta, slot **volta pra fila** e pode ser oferecido a outro paciente.

2. **Não repetir slot já ofertado ao mesmo lead.** Se slot X foi ofertado pro lead Y (mesmo que tenha expirado os 10min), Lia **NÃO oferece de novo** o mesmo slot X pro lead Y. Próxima oferta tem que ser slot DIFERENTE.

3. **Mensagem-gatilho expiração** (Lia manda automaticamente quando passar 10min sem confirmação):

   > "{Nome}, esse horário foi liberado pra outro paciente da fila. Tenho outros próximos: {SLOT_NOVO_1} ou {SLOT_NOVO_2}. Algum desses fica bom?"

4. **Comunicar a regra na PRIMEIRA oferta** (transparência):

   > "Esses dois horários ficam reservados pra você por 10 minutos. Após esse prazo, eles voltam pra fila de espera. Qual prefere?"

**Implementação técnica (a fazer):**

- Redis: `blink:slot_ofertado:{cod_med}:{cod_unid}:{YYYYMMDDHHMM}:{lead_id}` com TTL **600s**.
- Redis SET: `blink:slots_ja_ofertados:{lead_id}` — adiciona cada slot ofertado (sem TTL, expira por LRU/manual).
- Worker periódico (1min): varre Redis procurando reservas expiradas → dispara mensagem-gatilho expiração via Meta Graph 8133.
- `_selecionar_2_slots_inteligente(agenda, lead_id)` em `responder.py` filtra a agenda: descarta qualquer slot presente em `blink:slots_ja_ofertados:{lead_id}` ANTES de escolher os 2.

**Pytest a criar:** `tests/test_e6b_reserva_10min.py` — 8 cenários:
- Slot ofertado → 10min sem resposta → mensagem gatilho dispara.
- Slot já ofertado NÃO aparece em próxima oferta pro mesmo lead.
- Slot já ofertado a lead A LIBERADO após 10min PODE ser ofertado a lead B.
- Reserva ativa de lead A bloqueia oferta pra lead B no mesmo slot.
- Paciente aceita slot dentro dos 10min → reserva vira agendamento (passa pra `gravar_agendamento_medware`).
- Worker expiração dedup: não manda 2x mensagem se já passou tempo + reservation_id já tratado.
- ctx.agenda recebida do Medware → 5 slots, 3 já ofertados → função retorna apenas 2 não-ofertados.
- Lead sem `slots_ja_ofertados` → função roda normal (compatibilidade retroativa).

### 11-N. Fluxo E6 reinvertido — ofertar 2 slots antes de perguntar turno (caso Alice lead 21256807, 03/06/2026)

**Caso (03/06/2026 22:09):**

Lia já tinha tudo no ctx: nome (Alice 5a), médica (Karla), unidade (Asa Norte), convênio (Saúde Caixa), motivo (retorno pós-op). Mãe (Carol) já gastou 10 min respondendo. Lia perguntou:

> "Qual sua preferência de turno e período?
> – Turno: Manhã ou Tarde?
> – Período: Início, Meio ou Fim?"

Fricção desnecessária — Carol precisaria de mais 2 decisões antes de ver UM slot real. A causa raiz estava NO PRÓPRIO PROMPT: linhas 360-362 do `_agenda_block` instruíam literalmente "Se ele ainda não deu preferência, pergunte o melhor dia/turno ANTES de oferecer".

**Decisão (Fábio aprovou):** **inverter o fluxo**.

| Antes | Depois |
|---|---|
| 1. Lia pergunta turno + período + dia | 1. Lia oferece 2 slots (1 manhã + 1 tarde) imediatamente |
| 2. Paciente decide 3 variáveis | 2. Paciente aceita uma OU pede outro dia/hora |
| 3. Lia oferece slot | 3. (se recusou OU pediu específico) — Lia pergunta dia/turno → nova rodada |
| Resultado: ~6 turnos pra fechar | Resultado esperado: ~3 turnos |

**Fix (`voice_agent/responder.py`):**

- **Prompt `_agenda_block`** reescrito: regra "OFERTA IMEDIATA DE 2 SLOTS" com formato 1️⃣/2️⃣ canônico. Proíbe explicitamente perguntar "manhã ou tarde", "início/meio/fim" antes de oferecer.
- **Helper `_selecionar_2_slots_inteligente(agenda)`**: pega 1 slot manhã (hora<12) + 1 slot tarde (hora≥12) mais próximos; se só houver de um turno, 2 desse turno.
- **Helper `_gerar_oferta_2_slots(ctx)`**: monta a mensagem humana com 2 slots no formato canônico.
- **Filtro novo `_viola_pergunta_turno_periodo_com_agenda(text, ctx)`** em `_scrub_prohibited`: detecta padrões "manhã ou tarde", "qual turno", "início/meio/fim", "preferência de turno" QUANDO `ctx.agenda` tem slots → substitui resposta inteira por `_gerar_oferta_2_slots(ctx)`.
- Pytest `tests/test_alice_2_slots_imediatos.py` — 18 cenários (caso Alice + variantes de pergunta + seleção 1m+1t + ctx sem agenda não-bloqueia + mensagem gerada não-repete pergunta).

**Fluxo completo aprovado:**

1. Após `unidade` definida e `ctx.agenda` populado → Lia oferece 2 slots imediatamente.
2. Paciente aceita → confirma → agendamento.
3. Paciente pede dia/hora específico → Lia procura na agenda. Se tem → agenda. Se não → diz isso + oferece o mais próximo da preferência.
4. Paciente recusa SEM especificar → AÍ SIM Lia pergunta "Qual dia da semana e turno fica melhor?" → nova rodada com 2 slots.

**Lição arquitetural**: o anti-padrão estava NO PROMPT, não no modelo. Modelo cumpria a instrução. Defesa reativa (filtro pós-geração) só vale enquanto o prompt corrigido não chega na sessão (cache).

---

### 11-M. Bug Priscila lead 24055629 — "sexta-feira (06/06)" mas 06/06 é sábado (03/06/2026)

**Caso (01/06/2026 12:30):**

Lia escreveu: "Você prefere 9h de amanhã (terça-feira, 02/06) ou 9h de sexta-feira (06/06)?"
Paciente Priscila percebeu na hora: "Dia 5, sexta ou 6, sábado?" — constrangimento direto.

**Causa raiz (3 gaps simultâneos):**

1. **Regex `_DIA_DATA_REGEX` incompleto**: classe de separadores `\s*[,\-]?\s*` entre dia-semana e data NÃO incluía `(` — então "sexta-feira (06/06)" não casava. Filtro `_viola_dia_semana` ficou cego.
2. **Sem regra "médico × dia"**: não existia checagem programática "Karla não atende sábado".
3. **Lia escreveu texto livre** em vez de chamar tool `oferecer_slot` (task #183).

**Fix (`responder.py`):**

- **Regex ampliado**: `[\s,\-()\[\]*]*` cobre parênteses, colchetes, vírgulas, travessões, asteriscos. Suporte ano 2 dígitos (`"26"` → `2026`). Detecta data inválida (31/02) também.
- **Filtro novo `_viola_oferta_em_dia_nao_atendido(text, ctx)`** mapa `_DIAS_ATENDIMENTO_POR_MEDICO`:
  - Karla: seg-sex (weekday 0-4)
  - Fabrício: ter+qui (weekday 1, 3)
  - Kátia: em pausa
- Médico desconhecido (ctx.medico vazio/fora do mapa) → NÃO bloqueia (evita falso positivo).
- Pytest `tests/test_priscila_06_06_sabado.py` — 13 testes verdes.

**Compatibilidade**: pytest histórico `test_filtros_lia.py::TestDiaSemanaInventado` continua válido — regex novo é superset.

**Lição arquitetural**: filtro regex tem cauda longa de formatos que escapam. Cada bug de paciente revela 1 formato não-coberto. Solução robusta = tool calling forçado em state=AGENDA (task #183).

---

### 11-L. Gap central tarde 02/06 — Lia escreve "vou consultar" sem chamar tool (6 casos)

**Sintoma único em 6 leads diferentes (mesma tarde):**

Quando state machine entra em AGENDA, Lia escreve em texto livre:
- "Deixa eu consultar a agenda real aqui pra você"
- "Vou buscar os horários disponíveis"
- "Me dá um minutinho que volto com as opções concretas"
- "Ainda estou buscando os horários"

**E nunca volta com os horários reais.** Paciente espera 2-30 minutos, depois humano (Stephany/Ariany) intervém manualmente.

**Casos confirmados (todos com agenda Medware EXISTENTE):**

| Lead | Paciente | Slots reais Medware |
|---|---|---|
| 21392947 | Sabrina | 7+ slots Karla Asa Norte |
| 24064723 | Kamila | 09:30 quarta 10/06 + 17/06 |
| 24065257 | Janeide | Erro de dia da semana antes de chegar a chamar tool |
| 21344999 | Iara | 8 slots Karla Asa Norte tarde |
| 24065595 | Ben Hur 2 | Lia nem chegou a processar (downtime) |
| 22345722 | Keyla | 3 slots Karla Águas Claras 17h-17:30 |

**Causa raiz arquitetural:** mesmo com `LIA_TOOLS_ENABLED=1` no Easypanel, o modelo Sonnet **não está chamando** as tools de `tools_lia.py` (`oferecer_slot`, `gravar_agendamento`). Está escrevendo em texto livre.

Hipótese técnica: `responder.py::messages.create()` provavelmente **não está passando** o parâmetro `tools=[...]` pra API Anthropic quando state=AGENDA. Sem `tools` no request, modelo não pode chamar — só pode escrever texto livre.

**Fix (task #183):**
1. Em `responder.py`, no método que monta `messages.create()`, detectar quando `ctx.state == "AGENDA"` e adicionar:
   ```python
   tools = [TOOL_OFERECER_SLOT, TOOL_GRAVAR_AGENDAMENTO]
   tool_choice = {"type": "tool", "name": "oferecer_slot"} if ctx.get("agenda") else None
   ```
2. Processar `response.stop_reason == "tool_use"` e executar a tool real.
3. Resposta humana vira wrap do resultado da tool — modelo não pode inventar data/dia/hora.

**Resultado esperado:** Lia NÃO escreve "vou consultar" mais. Chama tool, recebe slots, escreve resposta humanizada com os slots REAIS. Zero invenção de data.

---

### 11-K. Casos práticos 02/06/2026 tarde — 4 padrões de bug + downtime do dia

**Casos reportados em sequência durante operação real:**

| Lead | Paciente | Bug |
|---|---|---|
| 21392947 | Sabrina (mãe Elisa) | Filtro `_viola_dia_semana` substituiu confirmação ("1=Tudo Correto") por fallback genérico "reconferir agenda". Status_id 5-AGENDADO + 1.DIA CONSULTA futuro NÃO impediu filtro. |
| 24064723 | Kamila | Mensagem duplicada (mesmo texto em <1s) + Lia inventou "retorno em horário comercial seg-sex 8-18h" (Blink é 24h, não tem esse horário). |
| 24065257 | Janeide (mãe Allison) | Ofereceu "Terça 03/06" e "Quinta 05/06" — datas erradas (03/06 é quarta, 05/06 é sexta). Depois confirmação correta com paciente confirmando + pediu CPF, mas regrediu pra "reconsultar agenda" no turno seguinte. |
| 21344999 | Iara (bebê 1a6m) + Rebeca (mãe) | Lia pediu CPF da contato (Rebeca) em vez do paciente (Iara). Quando Rebeca enviou CPF, Lia ignorou e perguntou de novo. Depois rajada de mensagens → Lia entrou em loop perguntando "turno e período" 4x seguidas mesmo com paciente respondendo. |

**Diagnóstico arquitetural unificado:**

Todos os 4 bugs apontam pra MESMA causa raiz: **pipeline.py processa mensagens em rajada SEM lock por `conversation_key`**. Quando o paciente digita rápido OU quando 2 mensagens da paciente chegam próximas:

1. Turno 1 começa a processar → modelo gera resposta A
2. Turno 2 entra ANTES da resposta A "fixar" no Redis/Kommo → modelo gera resposta B com contexto DESATUALIZADO
3. As 2 respostas saem em sequência com perguntas redundantes

**Dedup forte (commit a37ffb8) só pega texto IDÊNTICO** (hash). Quando o modelo varia "Ótimo!" / "Perfeito!" / "Entendi!" no início, todas passam.

**Fix arquitetural (próxima sessão):**

Adicionar lock Redis em pipeline.py:
```python
lock = redis.set(f"blink:lock_pipeline:{conv_key}", "1", nx=True, ex=30)
if not lock:
    # outra requisição já está processando essa conversa
    # opção: enfileirar ou descartar (com log)
    return PipelineResult(sent=False, error="conversation_locked")
```

Isso elimina concorrência por conversa. Lock TTL 30s evita travamento eterno.

**Bug colateral causado por minha cadeia de deploys (lição importante):**

Hoje fiz 12+ commits/deploys em sequência. Cada deploy do Easypanel reinicia o container (~2-5 min downtime). Resultado: **agent ficou OUT 11:33-12:00 BRT (27 min)** — leads que entraram nesse intervalo (Tatiana 11:56, Iara 11:59, Ben Hur 2 11:59) ficaram sem resposta ou com gravação Kommo incompleta.

**Regra de processo:** rate-limit em commits/deploys. Não fazer mais de 2 deploys por hora durante operação ativa. Janela de manutenção = horário sem atendimento.

**Regras de prompt detectadas pra refinar (não imediato):**

1. `_MASTER_INSTRUCTION.md` E2 — frase exemplo "preciso do CPF" é AMBÍGUA quando paciente é bebê/criança. Trocar pra "preciso do CPF do paciente ({{nome_paciente}})".
2. Adicionar regra: "Quando paciente é menor (perfis Bebê 0-2 ou Criança 3-12), CPF é DO PACIENTE — NÃO peça do responsável."
3. Onde "horário comercial" / "seg-sex 8-18h" mora (27 arquivos têm essa string). Blink é 24h — limpar isso do prompt/KB.

---

### 11-J. Caso Kamila lead 24064723 — 3 bugs simultâneos (02/06/2026 11:24 BRT)

**Cenário:**
- 11:21 Stephany (humana) mandou template "Com base em suas preferências... 10/06 09:30 ou 24/06 10:00. Escolha uma opção!"
- 11:23 Kamila respondeu: "3" (paciente quis dizer "3 horários por favor?" ou se confundiu)
- 11:24 Lia mandou **DUAS mensagens IDÊNTICAS** sequenciais: "Kamila, ainda estou buscando os horários disponíveis para quarta-feira de manhã com a Dra. Karla na Asa Norte. Aguarda só mais um pouquinho que já te passo as opções concretas, ok?"
- 11:24 Ariany moveu pra 1-ATENDIMENTO HUMANO

**Bug 1 — Lia ignorou intervenção humana (Stephany):**
Stephany JÁ tinha enviado horários reais. Lia continuou como se nada tivesse acontecido. Camada de detecção "humano enviou template Conclusão / oferta" não pegou esse formato com emoji 1️⃣ 2️⃣.

**Bug 2 — DUPLICAÇÃO: mesma mensagem 2 vezes em <1s.**
Provável falha do dedup no pipeline. Cada inbound do paciente disparou um turn, e ambos geraram mesma resposta sem checar idempotência.

**Bug 3 — "ainda estou buscando" SEM ter buscado.**
Lia escreveu promessa de retorno mas nunca chamou Medware. Frase de espera infinita — paciente nunca recebe os horários reais. É exatamente o mesmo padrão do bug Juliene (24053159) que motivou o filtro `_viola_promete_retorno_humano`. Mas esse filtro está DESLIGADO desde commit 796ba2a (FILTROS_LEGACY=0).

**Lição:** desligar TODOS os filtros legacy sem ativar tool calling ainda foi prematuro. Sem tools, Lia volta a "prometer e não cumprir" que o filtro evitava.

**Próximas ações (não imediato):**
1. Detectar template emoji 1️⃣ 2️⃣ humano antes de gerar resposta (camada 6 ja_handoff)
2. Dedup forte por hash da resposta+conversation_key+5s
3. Confirmar tool calling efetivamente ativo em prod (`LIA_TOOLS_ENABLED=1`)

---

### 11-U. KB limpa de "horário comercial" + Watchdog 24h (04/06/2026, tasks #184/#178)

**Problema histórico (bug Juliene 24053159, 02/06):**
Lia inventava "retorno em horário comercial seg-sex 8h-18h" — frase causava experiência ruim. Blink ATENDE 24h via Lia (e equipe humana em rodízio paralelo).

**Limpeza KB (#184):**
6 arquivos com menção a "horário comercial 8-18h" ajustados:
- `22_agenda_dra_karla.md` linha 69 → "Deixa eu reconsultar a agenda aqui, volto em 1 minuto."
- `34_agenda_dr_fabricio.md` linha 73 → mesma frase
- `38_atestados_e_documentos_medicos.md` linha 19 → "Logo te respondem!"
- `37_escalonamento_humano.md` linha 33 → removido "em horário comercial"
- `08_audio_e_escalonamento.md` linha 56 → removido "em horário comercial"
- `_MASTER_INSTRUCTION.md` linhas 336 e 436 → mantidas (são regras PROIBINDO uso)

**Watchdog 24h (#178):**
`voice_agent/watchdog_lia.py` atualizado:
- Removida restrição seg-sáb 8h-18h — `_eh_horario_comercial()` sempre `True` por default
- Toggle reversa: `WATCHDOG_RESTRINGIR_HORARIO=1` reativa janela antiga
- Novo nível CRÍTICO: `SILENCIO_CRITICO_SEG = 30 * 60` (30 min)
- Configurável via env `WATCHDOG_SILENCIO_CRITICO_SEG`

**Pytest:** `tests/test_watchdog_24h.py` — 6 cenários. **64/64 total verde.**

---

### 11-T. Autonomia total — Cron semanal + Kommo webhook trigger (04/06/2026, tasks #218/#219)

**Origem:** Fábio: "chega de babá. autonomia total".

**PARTE 1 — Cron interno semanal (`voice_agent/cron_interno.py`):**

Worker `_worker_campanha_semanal_loop` adicionado. Checa a cada 30min se é segunda 9h-10h BRT. Se sim + dedup Redis OK + `CAMPANHA_SEMANAL_ENABLED=1` → executa `_executar_campanha_semanal()` que filtra leads por categoria + dispara template aprovado em batch.

**Envs novas (Easypanel → Ambiente):**
- `CAMPANHA_SEMANAL_ENABLED=1` (toggle, default off)
- `CAMPANHA_SEMANAL_CATEGORIA=R` (default R; aceita E, C)
- `CAMPANHA_SEMANAL_MAX=20` (max 200)
- `CAMPANHA_SEMANAL_UNIDADE=Asa Norte` (opcional)
- `CAMPANHA_SEMANAL_MEDICO=Karla` (opcional)

Zero config Easypanel UI cron. Bastam as envs acima + redeploy.

**PARTE 3 — Endpoint `/admin/kommo-trigger-disparar`:**

Recebe webhook do Kommo Automation. Aceita 2 formatos:

1. **JSON body** (preferido):
```json
{ "lead_id": 22982854, "template": "captar_paciente",
  "body_params": ["Déborah", "Maria Teresa", "Águas Claras", "Karla", "09/06 09:00"] }
```

2. **Form-urlencoded** (formato nativo Kommo Automation):
```
leads[update][0][id]=22982854
```

Quando recebe → chama `_disparar_template_aprovado_para_lead()` → dispara template + grava nota Kommo automática.

**Como configurar no Kommo Automation:**
1. Kommo → Configurações → Automações → Add
2. Quando: campo "Disparar Template" = "Sim" (ou status muda pra X)
3. Ação: Webhook HTTP POST
4. URL: `https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-disparar?secret=$WEBHOOK_SECRET`
5. Salvar

**PARTE 2 — Allowlist sandbox Anthropic:** depende da Anthropic adicionar `*.easypanel.host` no proxy allowlist do Cowork. Fora do controle do Blink. Workaround: usar Chrome MCP do Fábio pra fetch direto.

**Pytest:** `tests/test_campanha_semanal_e_kommo_trigger.py` — 8 cenários (toggles, categoria default/custom, max cap, sanity check). **58/58 total verde.**

---

### 11-R. Endpoints batch + categoria — Opção A+C (04/06/2026, tasks #213/#214)

**Origem:** Fábio: "estamos sem atendimento humano, dispara automático".

**Opção A — `/admin/disparar-batch`** (1 curl manda N leads):

```bash
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-batch?secret=$WS" \
  -H "Content-Type: application/json" \
  -d '{"lead_ids": [22982854, 21710873], "dry_run": false, "forcar": true}'
```

Retorna `{total, ok, falhas, dry_run, forcar, detalhes:[{lead_id, ok, telefone, estrategia, motivo}]}`.

**Opção C — `/admin/disparar-categoria`** (filtro inteligente):

```bash
curl "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=R&unidade=Asa%20Norte&max=10&secret=$WS"
```

Categorias suportadas:
- `R` — REAGENDAR / REMARCAÇÃO / FALTOU / DESMARCOU
- `E` — COM CONVÊNIO
- `C` — SEM CONVÊNIO / PARTICULAR

Filtros opcionais: `unidade`, `medico`, `max` (default 30, max 200), `dry_run`.

Excluídos automaticamente: Inas, GDF, Cassi, SulAmerica, Bradesco.

**Cron Easypanel sugerido (1x/semana):**

Easypanel → app `blink/agent` → Crons → Add:
- Nome: `Campanha REAGENDAR Asa Norte`
- Schedule: `0 9 * * 1` (toda segunda 9h BRT)
- Command:
```
curl -fsS -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=R&unidade=Asa%20Norte&max=20&secret=$WEBHOOK_SECRET"
```

**Pytest:** `tests/test_disparar_batch_categoria.py` — 25 cenários (categoria R/E/C + exclusões Inas/GDF/etc + edge cases).

---

### 11-Q. Endpoint `/admin/disparar-lead/{lead_id}` — disparo autônomo (04/06/2026)

**Origem:** task #212. Fábio: "estamos sem atendimento humano, tem que disparar de forma automática e aparecer a mensagem em notas".

**O que faz:**
- Aceita só `lead_id` na URL (path param). Sem precisar montar telefone/nome.
- Busca contato principal via `KommoClient.get_lead_main_contact(lead_id)` (método novo) → retorna `{telefone, nome, status_id}`.
- Normaliza E.164 (prefixo `55` se faltar).
- Monta `SnapshotLead` e chama `dispatch_renovacao(dry_run=false, forcar=true)` por padrão.
- Dispatcher já grava nota Kommo automaticamente com timestamp + canal + estratégia + texto enviado (task #95).

**Como usar:**

```bash
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-lead/{LEAD_ID}?secret=$WEBHOOK_SECRET"
```

Query params opcionais:
- `dry_run=true` → simula sem enviar (debug)
- `forcar=false` → respeita dedup Redis 24h (default ignora)

**Retorno:**
```json
{
  "ok": true,
  "lead_id": 22982854,
  "telefone": "5561...",
  "nome": "...",
  "status_id": 101508307,
  "dispatch_result": { "ok": true, "estrategia_usada": "...", "nota_kommo_id": ... }
}
```

**Erros tratados:**
- Sem telefone no contato → 400 com `info_recebida` pra debug
- Sem kommo_client → 500
- Secret errado → 401

**Pytest:** `tests/test_get_lead_main_contact.py` — 6 cenários (telefone+nome+status, sem contato, lead inexistente, wrapper get_lead_main_phone).

**Diferença vs `/admin/renovacao-dispatch`:** o antigo exige `telefone`, `nome_contato`, `status_id` no querystring (stateless). O novo busca tudo do Kommo — pensado pra uso operacional direto sem montar payload.

---

### 11-P. FIX GAP CRÍTICO 15 DIAS — Lia grava agendamento Medware sozinha (04/06/2026)

**Origem:** task #208. Bug recorrente em 15 dias: Lia confirmava agendamento com paciente, escrevia nota Kommo, mas **NÃO gravava no Medware** — sempre dependia de Stephany/Ariany clicar manualmente.

**Causa raiz:** `voice_agent/tools_lia.py::handle_gravar_agendamento_medware` (linhas 362-381) era um STUB que só escrevia flag Redis `blink:tool_gravacao_solicitada:{convo}` e DELEGAVA pra `executor_agendamento.py` — arquivo que **NUNCA EXISTIU NO REPO**.

**Fix:**
- Adicionados `COD_MEDICO_POR_NOME` (Karla=12080, Fabrício=12081) e `COD_UNIDADE_POR_NOME` (Asa Norte=5, Águas Claras=3) com helpers `cod_medico_por_nome()` / `cod_unidade_por_nome()` aceitando variantes (case, abreviação, com/sem "Dra.").
- `handle_gravar_agendamento_medware` agora chama `medware_client.criar_agendamento()` direto, com args extraídos do `caller_context.known` (nome, CPF, data_nasc, celular, convênio, médico, unidade).
- Dedup Redis 24h via `blink:agendamento_gravado:{convo_key}` — segunda tool call não regrava.
- Sucesso → log `[GRAVAR-MEDWARE] OK convo=X cod_ag=Y med=Z uni=W` + setex Redis.
- Falha Medware → retorna `ResultadoTool(erro="medware_falhou: <motivo>")`, escala humano via circuit breaker existente.
- Exception → `ResultadoTool(erro="medware_exception: ...")` — não quebra conversa.
- Fallback: sem `medware_client` (modo teste), volta a escrever flag Redis legado.

**Validação:**
- Pytest novo `tests/test_gravar_agendamento_medware_real.py` — 15 cenários (maps, sucesso, falha, exception, dedup, fallback).
- Pytest antigo `tests/test_tools_lia.py::TestGravarAgendamento::test_tudo_ok_chama_medware_e_marca_dedup` reescrito.
- **41/41 verde em 0.04s.**

**Riscos pós-deploy (mitigados):**
- Primeiro agendamento real pode dar 400 do Medware → log estruturado + circuit breaker já existente (3 falhas → escala humano).
- CPF duplicado → `criar_agendamento` já trata via `buscar_paciente_por_cpf` (linha 543 de medware.py).
- Convênio fora do PLANO_CODES → retorno `motivo:"convenio_desconhecido"` (Lia sabe escalar).

**Próximas ações pós-merge:**
1. Confirmar `LIA_TOOLS_ENABLED=1` em prod (Easypanel → Ambiente).
2. Smoke E2E com canary lead (1 agendamento + cancel imediato).
3. Monitorar `[GRAVAR-MEDWARE]` em logs primeiras 24h.

---

### 11-O. Enums Kommo são case-sensitive — value exato (04/06/2026)

**Sintoma:** `kommo_update_lead` com `{"ATIVADO IA?": "DESATIVADO"}` ou `{"1260817": 927035}` retornou HTTP 400 `NotSupportedChoice`. Só funcionou com `{"ATIVADO IA?": "Desativado"}` (texto exato como aparece na config do field).

**Regra:** ao passar enum select pelo MCP Kommo:
1. Use o **nome do campo** como chave (case-sensitive: `"ATIVADO IA?"` com `?`).
2. Use o **value text exato** do enum (Title Case como aparece em `kommo_list_custom_fields`).
3. Enum_ids numéricos (927031/927033/927035) **não funcionam** via essa interface — só os textos.

Confirmados em 04/06:
- `"Ativado"` → 927031
- `"Solicitado"` → 927033
- `"Desativado"` → 927035

Aplicado: leads 22703954 + 23235182 (Inas GDF) marcados como `Desativado` pra excluir do motor de reativação.

---

### 11-I. Campo Kommo "ATIVADO IA?" — ID renovado 1260635→1260817 (02/06/2026 tarde)

**Sintoma:** "muitos casos de falta de resposta" reportado pelo Fábio. Lead 24064359 (Ana Caroline) sem resposta há 2h.

**Causa raiz descoberta:** o campo `ATIVADO IA?` foi RECRIADO no Kommo em algum momento. O ID antigo (1260635, hardcoded em `kommo.py::FIELD_ATIVADO_IA`) deixou de existir na API. ID atual é **1260817**. Pipeline write turn-by-turn (webhook.py:2985+3080, pipeline.py:622, reactivation.py:428) seguia tentando gravar no ID morto — fail silently.

**Resultado prático:** equipe humana perdeu visibilidade de IA on/off por lead. Bug Elisa-like se acumulando invisivelmente.

**Fix (commit `3adb920`):**

```python
FIELD_ATIVADO_IA = (1260817, {
    "ATIVADO": 927031, "ATIVA": 927031, "ATIVO": 927031, "ON": 927031,
    "SOLICITADO": 927033, "SOLICITAR": 927033, "PENDENTE": 927033,
    "DESATIVADO": 927035, "DESATIVADA": 927035, "OFF": 927035,
})
```

Type confirmado: `select` (era `multiselect` no comentário antigo).

**Como descobrir ID de campo Kommo deletado/renovado:**
1. Abrir lead no Kommo via Chrome
2. JavaScript no console: `document.querySelectorAll('[class*=linked-form__field]').forEach(e => console.log(e.getAttribute('data-id'), e.textContent.substring(0,50)))`
3. Confirmar via `GET /api/v4/leads/custom_fields/{id}` que retorna o JSON completo do campo

**Lição de processo:** quando código usa `FIELD_X = (id, enums)` hardcoded, monitorar com `/admin/healthz` se o ID ainda existe na API custom_fields. Se Kommo retornar 404 no field_id, ALERTAR no Slack — código está gravando em buraco.

---

### 11-H. Escopos PAT GitHub — `repo` + `workflow` (02/06/2026 tarde)

**Lição:** push falhou com `remote rejected ... refusing to allow a Personal Access Token to create or update workflow .github/workflows/test.yml without workflow scope`.

Causa: token gerado só com escopo `repo`. GitHub Actions YML em `.github/workflows/` exige escopo **independente** chamado `workflow` — `repo` NÃO o inclui automaticamente.

**Regra para todo PAT deste repo** (https://github.com/settings/tokens/new):
- ☑ `repo` (caixa pai inteira)
- ☑ `workflow` (caixa separada logo abaixo de repo)

Sem `workflow`, qualquer commit que toque `.github/workflows/*.yml` é rejeitado no servidor mesmo com `repo` marcado.

Também: token comprometido em chat = revogar imediatamente após uso. Token `ghp_WH3VgKbW3mc4...` foi exposto e deve ser deletado.

---

### 11-E. Regra "shadow mode" — defesa nova SÓ entra em prod após validação real (02/06/2026)

**Origem do princípio:** sessão 02/06 manhã. Juiz Haiku 4.5
adversarial (ligado 01/06 noite com `JUIZ_HAIKU_ENABLED=1`, limiar
70) vetou em série respostas legítimas da Lia. Leads afetados:
Larissa/Lis/Samuel (10513560) — 2 fallback genéricos seguidos.
Adriana (24063769) — 4 turnos de enrolação antes de responder valor.
Causa: pytest unitário passou, mas juiz não foi testado com 100+
turnos reais. LIMIAR=70 em Haiku 4.5 deu falso positivo demais em
casos borderline normais.

**Regra a partir de 02/06:** nenhuma camada nova de defesa que
SUBSTITUI resposta da Lia entra em prod sem:

1. Rodar em **modo shadow** por pelo menos 24h: apenas LOGA o que
   substituiria, sem substituir de fato.
2. Métrica de aprovação: < 2% dos turnos teriam sido substituídos.
3. Revisão dos textos substituídos pra ver se são falsos positivos.
4. Aprovação explícita do Fábio antes de ativar `ENABLED=1`.

Aplicação retroativa: `JUIZ_HAIKU_ENABLED=0` e `MEMORIA_BUGS_ENABLED=0`
em prod desde 02/06 ~9h BRT (desligados via Easypanel manualmente).
Defesa atual = 13 filtros regex + retry Medware + circuit breaker
+ checklist 4 dados mínimos + state machine FSM. Suficiente.

### 11-F. Bug recorrente "pergunta redundante de convênio" — Adriana (02/06/2026)

Lead 24063769. Paciente perguntou valor. Lia fez 4 turnos pedindo
"com ou sem convênio?" quando `ctx.known.convenio = "Não se aplica"`
já estava no Kommo. Triagem ignorou o ctx.

**Fix:**
- Artigo KB `voice_agent/knowledge_base/39_valores_consulta.md` com
  tabela oficial R$ 611 Karla / R$ 297 Fabrício catarata / R$ 800 SDP.
- Filtro `_viola_pergunta_redundante_convenio(text, ctx)` em
  `responder.py`: regex detecta "com ou sem convênio" + ctx tem
  convenio → substitui.
- `_gerar_resposta_valor_sem_repergunta(ctx)`: usa ctx (médico +
  especialidade + convênio) pra responder com R$ direto, sem
  repergunta. Convênio aceito = "coberta pelo seu plano". Particular
  = R$ exato + Pix.
- 13 testes em `tests/test_pergunta_redundante_convenio.py`.

### 11-G. CI/CD gate de regressão — GitHub Actions (02/06/2026)

**Origem:** Fábio "como evitar Lia regredir como aluno que volta a
errar 1ª série depois de chegar na 3ª".

Hoje pytest roda só manual no Mac do Fábio. Auto-deploy Easypanel
faz docker build sem rodar pytest. Resultado: regressão chegava em
prod sem barrar.

**Fix:** `.github/workflows/test.yml` — roda pytest completo + lint
em cada push pra main + PR. Status check do GitHub. Easypanel pode
ser configurado pra respeitar check (já tem auto-deploy ON desde
01/06 → trigger só se main verde). Memória ativa preventiva.

### 11-D. ja_agendado — 5 camadas (02/06/2026 manhã)

Bug recorrente: atendente humano agenda no Medware mas esquece de
mover etapa / preencher 1.DIA CONSULTA. Lia ficava cega e oferecia
slot novo. Clínica reportou como bug Blink. Solução em 5 camadas
independentes, em OR (qualquer uma dispara `ja_agendado=True`):

| Camada | Fonte | Cobre |
|---|---|---|
| 1 | `status_id ∈ ST_JA_AGENDADO` | 5-AGENDADO, 6-CONFIRMAR, 7.CONFIRMADO, 8-REALIZADO, 10-PRÓXIMA CONSULTA |
| 2 | `1.DIA CONSULTA` futuro (field 1255723) | Bug Aurora original |
| 3 | Nota humana com "agendei + data" (72h) | Atendente escreveu nota livre |
| 4 | **Template "Conclusão de Agendamento"** (parser regex Blink) | Caso Graziela/Enzo do Fábio |
| 5 | Histórico genérico (palavra-chave conclusão + data, humano) | Fallback pra mensagem improvisada |

Funções principais em `voice_agent/kommo.py`:
- `_ja_agendado_por_nota_humana(notas, janela_h=72)` → camada 3
- `detectar_template_conclusao_agendamento(texto)` → camada 4 (extrai
  paciente, médico, especialidade, convênio, unidade, data, hora;
  auto-popula `known.*` sem sobrescrever)
- `detectar_conclusao_no_historico(mensagens, janela_h=72)` → camada 5
- `get_lead_notes(lead_id)` + `get_lead_messages(lead_id)` → varredura

Cenário canary #15 "Graziela/Enzo" replica o fluxo: atendente envia
template → paciente responde "1. Tudo Correto" → Lia confirma data
marcada, não refaz triagem.

Pytest: 36 testes (14 template + 12 nota humana + 10 histórico).

### 11-B. Easypanel — Deploy automático e envs novos (01/06/2026 noite)

- **Auto-Deploy GitHub→Easypanel ATIVADO** em 01/06/2026 ~21:00 BRT. Push em `main` agora dispara build automático em 2-5min. Antes estava off → commits ficavam presos no Mac.
- **Envs novas no agent** (Ambiente):
  - `SMOKE_ENABLED=1` + `SMOKE_INTERVALO_SEG=3600` — smoke contínuo bate 6 cenários core de 1 em 1h.
  - `JUIZ_HAIKU_ENABLED=1` + `JUIZ_HAIKU_LIMIAR=70` — juiz adversarial Haiku 4.5 julga cada resposta da Lia (#157, módulo `voice_agent/juiz_adversarial.py`).
  - `LIA_TOOLS_ENABLED=1` — tool calling estruturado.
- **Validação pós-deploy** (rodar nessa ordem):
  1. `curl /health` — espera 200 OK.
  2. `curl /admin/healthz?secret=$WS` — espera `integrations.kommo/medware/wa_cloud/redis: true`.
  3. `curl /admin/smoke-tick` — espera `{"total":6,"ok":6}`.
  4. `curl /admin/audit/frios-com-agendamento?limit=500` — lista leads em 2.LEADS FRIO que têm `1.DIA CONSULTA` preenchido (inconsistência pra mover pra 5-AGENDADO).

### 11-C. Juiz adversarial Haiku — segundo olhar pré-envio (01/06/2026 noite)

Módulo `voice_agent/juiz_adversarial.py`. Origem: discussão Fábio "como aproveitar ML pra defesa contra bug?". Os 13 filtros regex em `responder.py` são reativos — cada bug novo escapa. Haiku 4.5 dá segundo olhar semântico:

- Recebe (resposta da Lia, ctx do lead, mensagem do paciente).
- Devolve JSON `{risco: 0-100, motivos: [...], recomendado: enviar|substituir}`.
- Se `risco >= LIMIAR` (default 70), Lia troca pelo `FALLBACK_SUBSTITUICAO` seguro.
- Erro/timeout não bloqueia — Lia segue.
- Custo ~$0.001/turno (~$0.20/dia em volume Blink).
- Veredictos com risco >= 30 ficam em Redis `blink:juiz:veredicto:{lead_id}:{ts}` por 7 dias pra análise.

Plugado em `_scrub_prohibited` como filtro #4 (último, depois dos 13 regex). Pytest 23 casos: `tests/test_juiz_adversarial.py`.

### 11-A. Rotação de chaves — histórico (01/06/2026)

- **OPENAI_API_KEY rotacionada** em 01/06/2026 14:33 BRT.
  - Antiga `sk-proj-VDF6Q...WcIA` (criada 19/05/2026) — **REVOGADA via OpenAI dashboard.**
  - Nova `sk-proj-EbB4M...DyMA` (nome `blink-agent-rotacao-01-06-2026`, tracking `key_xDdiVvnrWck3d…`) — ativa.
  - Substituída na linha 1 do bloco "Variáveis de Ambiente" do app `blink/agent` no Easypanel.
  - Validação pós-rotação: `/health` 200 OK, `/admin/smoke-tick` 6/6 verde em 26,7s.
- **Procedimento padrão de rotação** (próximas vezes):
  1. OpenAI dashboard → Create new secret key com nome `blink-agent-rotacao-DD-MM-AAAA`.
  2. Copiar imediatamente (só aparece 1 vez).
  3. Easypanel → `blink/agent` → Ambiente → substituir linha `OPENAI_API_KEY=`.
  4. Salvar → Implantar → aguardar ~60s.
  5. `curl /health` + `curl /admin/smoke-tick` — esperar 6/6.
  6. Voltar pro OpenAI → revogar chave antiga.
  7. Registrar nesta seção (data + sufixo terminal da chave antiga e nova).

---

## 12. O que está em construção

- Campos sinal no Kommo (task #49 manual)
- Subir `REACTIVATION_DAILY_CAP=30→200` (ver `outputs/ATIVAR_TETO_200_E_SLACK_LOG.md`)
- Ligar `SLACK_WEBHOOK_URL` pra log de cada disparo
- Testes pytest pra cenários históricos (Aurora, Fábio, cobrança antes slot)
- Webhook Meta Lead Form → Kommo (leads novos em 30s)
- Painel `gap de amanhã` (slots vazios → reativação focada)
- **Pipeline autorização antecipada do convênio** (task #81): a partir do
  `N.EXAMES` preenchido pelo `selecionar_agrupador()`, montar a guia
  eletrônica e enviar à operadora antes do dia da consulta.
- **Comparador pós-consulta** (task #81): função
  `voice_agent/auditoria.py:comparar_agrupamento()` + endpoint
  `/admin/auditoria-tick` + webhook Kommo que escuta movimentação para
  `6-REALIZADO CONSULTA` e dispara comparação por paciente.
- **Campo Kommo `N.AGRUPAMENTO ALTERADO`** (checkbox por paciente, 6 campos),
  preenchido automaticamente pela auditoria + nota detalhada
  `exames_a_mais`/`exames_a_menos`.
- **Pytest auditoria**: 4 cenários (coincide / a_mais / a_menos / fonte_vazia).
- **Observabilidade dupla checagem #auditoria-autorização** (task #82):
  bot posta discrepância no canal Slack; secretaria da unidade (Asa Norte ou
  Águas Claras) faz 1ª revisão (reaction `:white_check_mark:`); médico
  responsável (Karla/Fabrício/Kátia) faz a 2ª; `N.AUDITORIA STATUS` só vira
  `fechada` com as 2 assinaturas. Sem isso, financeiro não cobra o convênio.
  Env nova: `SLACK_WEBHOOK_AUDITORIA_URL`. (Seção 25 do `_MASTER_INSTRUCTION.md`.)

---

## 13. Regra de ouro para Claude/Lia

1. **Nunca inventar chave Pix** — só Asa Norte/Águas Claras
2. **Nunca dizer "deixa eu consultar agenda"** se Medware respondeu OK
3. **Nunca cobrar sinal antes de oferecer slot concreto**
4. **Sempre apresentar 2 opções** (Reserva Imediata + Fila de Encaixe)
5. **Respeitar `ja_agendado=True`** — não oferecer slot novo
5-A. **Nunca dizer "vou registrar pra equipe finalizar — retorno em horário comercial"** (NOVO 31/05). Sem agenda real → "deixa eu reconsultar, volto em 1 min". Com agenda → oferecer slot concreto. Sem `checklist_dados_minimos.pronto_para_oferecer_slot` → coletar dados antes.
6. **Não duplicar trabalho do motor** — não rodar batch `kommo_add_note` em
   massa, o reactivation.py já cobre a fila
7. **Convênio só agenda com 3 pré-requisitos POR PACIENTE** — `N.DATA NASC`,
   idade calculada (DATA DE HOJE Brasília injetada), `N.MOTIVO` classificado
   nas 5 categorias (Rotina/Retorno/Pré-op/Urgência/Pós-op). Sem isso, NÃO
   ofertar slot. Esses 3 dados alimentam `selecionar_agrupador()` → preenche
   `N.EXAMES` → pipeline solicita autorização ao convênio antes da consulta.
   (Seção 23 do `_MASTER_INSTRUCTION.md`.)
8. **Auditoria pós-consulta é silenciosa para o paciente** — pipeline compara
   `N.EXAMES` (planejado) vs Medware (realizado). Diferenças geram
   `N.AGRUPAMENTO ALTERADO=true` + tarefa humana de reabrir autorização. Lia
   não comenta a alteração com o paciente. (Seção 24 do
   `_MASTER_INSTRUCTION.md`.)

---

## 14. Paths do sistema (descobertos 28-29/05/2026)

| Recurso | Path |
|---|---|
| Skills Cowork (NÃO é Claude Code) | `~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/{uuid-A}/{uuid-B}/skills/` |
| Skill `lia-atendimento-blink` instalada | path acima + `/lia-atendimento-blink/` |
| Skills Claude Code (terminal) | `~/.claude/skills/user/` — **NÃO É O QUE COWORK USA** |
| Repo Mac | `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/` |
| Repo sandbox | `/sessions/{session}/mnt/AGENTE IA BLINK/` |
| Outputs sandbox | `/sessions/{session}/mnt/outputs/` |
| Knowledge Base | `voice_agent/knowledge_base/` (38 artigos) |
| Memória pasta | `lia-atendimento-blink/memoria/bugs-licoes/` |

UUIDs do skills-plugin são VOLÁTEIS — mudam por sessão. Sempre descobrir via:
```bash
find ~/Library/Application\ Support/Claude/local-agent-mode-sessions -name "SKILL.md" 2>/dev/null | head -3
```

---

## 15. Convênios — mapeamento oficial Medware ↔ Kommo (29/05/2026)

26 dos 27 convênios do Kommo (campo CONVÊNIO field_id=853206) mapeiam pra
codPlano do Medware via `voice_agent/medware.py` PLANO_CODES. Lista validada
em 45 pytest. Inas GDf não é aceito (artigo 18 KB).

| Kommo | Medware | codPlano |
|---|---|---|
| Pro ser STJ | STJ | 3 |
| TJDFT Pró-Saúde | T.J.D.F.T - DIRETO | 2 |
| Plan Assiste - MPF (MPU) | PLAN-ASSIT | 4 |
| E-vida (Luminar) | E-VIDA | 5 |
| Anafe | ANAFE | 8 |
| Bacen | BACEN | 9 |
| Care Plus | CARE PLUS | 14 |
| Casec (Codevasf) | CASEC | 15 |
| Casembrapa _ Embrapa | CASEMBRAPA | 16 |
| Conab | CONAB | 19 |
| Fascal | FASCAL | 22 |
| Omint | OMINT | 25 |
| PF Saúde | POLICIA FEDERAL | 26 |
| PLAS/JMU (STM) | STM | 27 |
| Proasa | PROASA | 28 |
| Saúde Caixa | SAÚDE CAIXA | 29 |
| Petrobrás (Saúde Petrobrás) | SAÚDE PETROBRAS | 30 |
| Serpro | SERPRO | 31 |
| SIS Senado | SIS SENADO | 32 |
| STF-Med | STF-MED | 33 |
| TRF Pró-Social | TRF | 34 |
| TRE | TRE | 35 |
| TRT | TRT | 36 |
| TST Saúde | TST | 37 |
| PróSaúde (Câmara dos Deputados) | CAMARA DOS DEPUTADOS | 39 |
| Não se aplica | .PARTICULAR | 1 |
| **Inas GDf** | **não aceito** (KB art. 18) | **0 → humano** |

---

## 16. Como Claude erra — anti-padrões observados (gravar pra não repetir)

Sessão 28/05/2026 acumulou 5+ erros do mesmo tipo. Padrão:

1. **Adivinho path em vez de checar.** Path do Cowork skill: adivinhei
   `~/.claude/skills/user/`. Errado. Tinha que rodar `find SKILL.md` no
   Application Support primeiro. **Regra:** antes de copiar arquivo pra
   path de aplicação, SEMPRE listar onde os irmãos vivem.

2. **Codifico mapeamento sem listar a fonte.** PLANO_CODES tinha 7 entradas.
   Lia falhava silenciosamente pra 24 convênios. Eu não chamei
   `listar_planos_operadoras` antes. **Regra:** antes de hardcodear lookup,
   listar o catálogo oficial.

3. **Faço múltiplas mudanças sem smoke test entre.** Editei pipeline +
   agendamento + responder + KB em sequência sem testar Medware no meio.
   Só descobriria erro com paciente real. **Regra:** após cada arquivo
   tocado, validar function isolada com smoke test antes do próximo arquivo.

4. **Mudo prompt sem rodar pytest.** Editei `_MASTER_INSTRUCTION.md` várias
   vezes hoje sem validar que regras antigas continuam disparando.
   **Regra:** após qualquer edit em KB, rodar `python -m pytest tests/ -v`
   antes de commit.

5. **Commito segredos.** CPF da Karla (013054726332) está em commits
   ded7b3e/c4e6e4e. Token GitHub `ghp_7NNf...` está em scripts e em
   `CLAUDE.md` deste projeto. **Regra:** antes de cada commit, varrer
   diff por strings que casam regex CPF (`\d{11}`) ou token (`ghp_[A-Za-z0-9]{36}`).

---

### 11-X. Reativação automática IA por mudança de etapa (05/06/2026, task #233)

**Origem:** Fábio 05/06 — sugestão arquitetural depois de inspecionar lead
10513560 (Larissa/Lis/Samuel) que estava em 6-CONFIRMAR com
`ATIVADO IA = Desativado` há semanas porque humano tinha enviado msg
manual lá em 09/04/2026 e ninguém reativou.

**Fluxo completo (3 partes):**

**Parte 1 — Handoff humano move pra 1-ATENDIMENTO HUMANO** (`pipeline.py`):
quando `agent_paused_for_lead` retorna motivo (humano detectado), além de
desativar IA, MOVE o lead pra status_id 106563343 (1-ATENDIMENTO HUMANO).
Equipe vê concentrado nessa etapa o que precisa terminar. Exceções: lead
já está lá ou em etapa final (142/143/91486864).

**Parte 2 — Webhook reativa ao sair de ATENDIMENTO HUMANO** (`webhook.py`):
endpoint `POST/GET /admin/kommo-trigger-status-change` recebe webhook do
Kommo "Status do lead alterado". Se nova etapa ∈ STATUS_ATIVOS_IA
(0-ENTRADA, 0-a classificar, 2.LEADS FRIO, 3-AGENDAR, 4.REAGENDAR,
5-AGENDADO, 6-CONFIRMAR, 7.CONFIRMADO, 7.1-NO-SHOW) → seta
`ATIVADO IA = Ativado`. Etapa "1-ATENDIMENTO HUMANO" NÃO está na lista
(humano ainda atuando lá).

**Parte 3 — Batch one-shot pra limpar acumulado** (`webhook.py`):
endpoint `/admin/reativar-ia-batch` varre TODOS leads atuais em etapas
ativas com `ATIVADO IA = Desativado` e ativa em massa. Dry-run default.

**Webhook Kommo a configurar (após push + deploy):**
- URL: `https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-status-change`
- Evento: **Status do lead alterado**

**Pytest:** `tests/test_reativacao_ia_automatica.py` — 12 cenários
(etapas ativas, etapa humana ignorada, fechadas ignoradas, caso real
lead Larissa 10513560).

---

### 11-W. 4 campos Kommo visíveis na lista + webhook humano (05/06/2026, tasks #231/#232)

**Origem:** Fábio adicionou 3 colunas customs na lista do funil ATENDE
(STATUS CONVERSA + ULTIMA MSG OUTBOUND + PROXIMA ACAO) e mais 2 campos
date_time (ÚLTIMA MENS LIA + ULTIMA MENS HUMANO) pra equipe humana
enxergar estado de cada lead sem abrir o card.

**Field IDs:**
| Campo | ID | Tipo | Preenchido por |
|---|---|---|---|
| STATUS CONVERSA | 1260854 | select 15 enums | Lia a cada turn |
| ULTIMA MSG OUTBOUND | 1260856 | textarea | Lia a cada turn |
| PROXIMA ACAO | 1260858 | select 12 enums | Lia a cada turn |
| ÚLTIMA MENS LIA | 1260860 | date_time | Lia a cada turn |
| ULTIMA MENS HUMANO | 1260862 | date_time | webhook Kommo |

Enums confirmados via API em `voice_agent/campos_acompanhamento.py`.

**Mapeamento estado FSM → enums** (em `mapear_status_e_proxima`):
| FSM | STATUS CONVERSA | PROXIMA ACAO |
|---|---|---|
| TRIAGEM | coletando_dados | coletar_dados_minimos |
| DADOS | coletando_dados | coletar_dados_minimos |
| CONVENIO | validando_convenio | validar_convenio |
| AGENDA | agenda_oferecida | aguardar_resposta_paciente |
| CONFIRMACAO | confirmando_horario | aguardar_resposta_paciente |
| GRAVACAO | gravando_medware | aguardar_resposta_paciente |
| POS_GRAVACAO | agendado_aguarda_consulta | confirmar_horario_d-1 |

Overrides: `ja_agendado=True`, `convenio_nao_aceito=True`,
`cobrar_sinal=True`, `paciente_desistiu=True` vencem o caminho FSM.

**Onde código pluga:**
- `voice_agent/pipeline.py::_sync_kommo_safely` resolve FSM atual via
  `FSMManager.get(convo_key)`, chama `campos_acompanhamento.montar_dict_campos()`
  e injeta no `update_lead_fields()`.
- `voice_agent/kommo.py::update_lead_fields` processa 5 chaves novas:
  `status_conversa`, `proxima_acao`, `ultima_msg_outbound`, `ts_ultima_msg_lia`,
  `ts_ultima_msg_humano`.

**Webhook humano** (task #232):
- Endpoint: `POST /admin/kommo-trigger-msg-humano`
- Auth: secret OPCIONAL (operação não-destrutiva, só carimba timestamp)
- Aceita JSON `{lead_id: N}` OU form `leads[update][0][id]=N`
- Atualiza `ULTIMA MENS HUMANO` com `int(time.time())`
- Configurado em Kommo → Webhooks → URL acima + evento "Mensagem de saída enviada"

**IMPORTANTE — Bug C-09:** Kommo VALIDA URL antes de salvar webhook
(faz GET no endpoint). Endpoint precisa estar LIVE em prod antes de
configurar o webhook. Sequência: push → deploy → confirma 200 → cria webhook.

**Pytest:** `tests/test_campos_acompanhamento.py` — 25 cenários (enums
corretos, mapeamento FSM completo, formatador timestamp, overrides).

---

### 11-V. Dedup leads frio por telefone — endpoint server-side (05/06/2026, task #228)

**Origem:** Fábio 05/06 — lead Lene 22398836 (96121-411) tem 7+ leads
duplicados no funil 2.LEADS FRIO. Cada família = 1 número → 1 lead.

**Endpoint:** `POST/GET /admin/deduplicar-leads-frio`

Params: `dry_run` (default true), `max_leads` (default 500, max 800),
`status_id` (default 101508307), `status_destino` (default 143).

**Lógica:** enriquece cada lead com telefone+notas_count+campos_preenchidos+updated_at,
agrupa por telefone normalizado, escolhe MASTER via score `notas×10 + campos×5 +
updated_at/86400×0.5` (desempate por id maior). Duplicados ganham rename
`[DUP→{master_id}] {nome}` + nota explicativa + move pra Closed-lost (143).
**Reversível** — não deleta.

**Comandos:**
```bash
# Dry-run (preview):
curl "https://blink-agent.6prkfn.easypanel.host/admin/deduplicar-leads-frio?dry_run=true&max_leads=500&secret=$WEBHOOK_SECRET" | jq

# Aplicar:
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/deduplicar-leads-frio?dry_run=false&max_leads=500&secret=$WEBHOOK_SECRET" | jq
```

**Pytest:** `tests/test_deduplicar_leads.py` — 19 cenários.

---

## 16-A. PROTOCOLO ANTI-OMISSÃO E ANTI-REPETIÇÃO (04/06/2026)

**OBRIGATÓRIO**: ler `lia-atendimento-blink/memoria/protocolo-claude-cowork.md` no início de toda sessão Cowork. Esse arquivo contém:

- **Checklist 10 itens pré-ação operacional** (Boeing rule) — verificar TODAS antes de enviar msg WhatsApp / gravar Medware / ofertar slot
- **Anti-desculpability** — regras de comunicação (não dizer "vou consultar e volto" sem voltar, não pedir Fábio rodar curl quando posso usar MCP, etc)
- **Bugs C-01 a C-07 indexados** — bugs MEUS (Claude Cowork operando), não da Lia. NÃO REPETIR.
- **Protocolo de indexação** — toda vez que cometo bug operacional, adiciono entrada Bug C-NN ANTES de seguir
- **Ritual de início de sessão** — leitura obrigatória

Origem: Fábio 04/06/2026 — "Já passou o tempo de errar a mesma coisa. Demonstra falta de qualidade." Zero tolerância pra bugs repetidos.

---

## 17. Sequência de auditoria obrigatória ao abrir nova sessão

Toda sessão Cowork futura, antes de mexer em código:

1. Ler `CLAUDE.md` (esse arquivo) — automático
2. Ler o handoff mais recente: `HANDOFF_<DD-MM>_PARA_<DD-MM-AAAA>.md` no root
3. `ls voice_agent/knowledge_base/` — ver artigos KB existentes
4. `git log --oneline -20` — ver commits recentes
5. `python -m pytest tests/ -v` — confirmar que estado atual passa testes
6. `curl https://blink-agent.6prkfn.easypanel.host/health` — confirmar prod viva

Só depois disso, começar trabalho. Sem isso = reincidência.

**Handoff mais recente**: `HANDOFF_02-06_MANHA_PARA_TARDE_2026.md` (sessão prática — juiz Haiku desligado por falso positivo, fix Adriana, regra shadow mode, CI GitHub Actions).

---

Última atualização: 01/06/2026 22:00 — sessão dia/noite. Bug Esther
24060221 (re-oferta de slot pós-AGENDADO via handler de imagem)
blindado com filtro `_viola_oferta_apos_agendado` (commit `e636a84`).
Decisão Fábio: só Lia em notas Kommo, paciente sai do feed (commit
`689314c`). Endpoint `/admin/audit/frios-com-agendamento` pra contar
372 leads em 2.LEADS FRIO com `1.DIA CONSULTA` preenchido (commit
`1840549`). **Virada arquitetural**: juiz adversarial Haiku 4.5
pré-envio em `voice_agent/juiz_adversarial.py` — defesa semântica em
vez de só regex, ~$0.001/turno, opt-in via `JUIZ_HAIKU_ENABLED=1`
(commit `d8f6167`, 23 testes). Easypanel: **Auto-Deploy GitHub
ATIVADO**, envs novos `SMOKE_ENABLED=1`, `JUIZ_HAIKU_ENABLED=1`,
`JUIZ_HAIKU_LIMIAR=70`. Total **771 testes verdes** (+187 desde
31/05). Smoke prod 6/6 em 19,3s. 4 commits aguardando push do Fábio
pra entrar em prod.
