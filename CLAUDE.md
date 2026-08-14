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

### 0. (14/08/2026) Bug C-146 — Pergunta fora do escopo Python → escalação imediata (financeiro/reembolso)

**Origem:** lead 24328426 (Alice Tavares). Paciente pagou Pix sinal + depois conseguiu vaga pelo convênio. Perguntou: "gostaria de saber se o valor enviado poderia ser reembolsado, pois consegui uma vaga no meu convênio." Lia inventou: "a consulta com a Doutora Karla cobre a avaliação" — completamente fora do escopo.

**Causa raiz (2 pontos simultâneos):**
1. C-129 tinha `r"reembolso\b"` (substantivo apenas). "reembolsado" (particípio verbal) não casava — `reembolsa[dr]?\b` falha porque após `d` vem `o` (char de palavra), `\b` não encontra fronteira.
2. Padrão "consegui vaga no convênio" não detectava "meu" entre "no" e "convênio".

**Regra Fábio (P0 permanente):** "somente responder se tiver o código determinístico do Python. Se não tiver, transfere para atendimento humano, muda etapa pro atendimento humano, e o campo ativado IA, desativa IA."

**Fix em 4 arquivos:**

1. **`voice_agent/fora_escopo.py` (NOVO):**
   - Tier 1 FINANCEIRO UNIVERSAL: reembolso/estorno/devolução em TODAS as formas verbais e nominais.
     Fix regex: `reembolsa(?:r|do[sa]?|da[s]?)?` cobre reembolsar/reembolsado/reembolsada.
     Padrão "consegui vaga": `(?:(?:no|pelo|com)\s+)?(?:meu\s+|seu\s+|o\s+)?conv[eê]nio`.
   - Tier 2 ESCOPO FECHADO (ja_agendado=True): pergunta ≥4 palavras + não whitelistada → escalar.
     Min 4 palavras exclui "Tudo bem?", "Oi", "Ok".
   - Toggle: `FORA_ESCOPO_C146_ATIVADO` (default ON). Fail-open. Redis flag TTL 24h.

2. **`voice_agent/blindagens_deterministicas.py`**: C-146 wired ANTES de C-129.

3. **`voice_agent/pipeline.py`**: Hook lê flag Redis → desativa IA + move para 1-ATENDIMENTO HUMANO + nota Kommo.

**Pytest:** `tests/test_bug_c146_fora_escopo.py` — 38/38 verde.
**Push:** `PUSH_C146_FORA_ESCOPO.command`

**Lição arquitetural CRÍTICA:**
- **Regex com `[dr]?\b` em português falha em particípios.** "reembolsado" = reembolsa + **d** + **o**. Após `d`, próximo char é `o` (palavra), então `\b` não encontra fronteira. Padrão correto: usar `\w*` ou listar formas explicitamente: `(?:r|do[sa]?|da[s]?)`.
- **C-129 era defesa de um único substantivo.** C-146 generaliza para TODA a família semântica (substantivo + verbo + particípio + compostos). Regra permanente: ao criar regex para palavra-raiz em PT-BR, sempre incluir: `(substantivo)\b`, `(verbo infinitivo)\b`, `(particípio_masc)\b`, `(particípio_fem)\b`.
- **"meu", "seu", "o" entre preposição e substantivo é PT-BR normal.** "no convênio" vs "no meu convênio" — o artigo possessivo quebrou o padrão. Regra: usar `(?:\w+\s+){0,2}` ou listar artigos possessivos explicitamente quando o contexto tem posse.
- **Pergunta sem código Python determinístico = escalar.** Fábio estabeleceu a regra arquitetural: se Python não tem a resposta, não deixar o LLM inventar. C-146 implementa essa regra como norma permanente.
- **Rollback:** `FORA_ESCOPO_C146_ATIVADO=0` em Easypanel → Implantar.

### 0. (14/08/2026) Bug C-144 — TODA CONVERSA não gravada no canal WA Cloud (8133) — Lia cega e repetindo perguntas

**Origem:** leads 24456556 e 24456706 — paciente disse "8 anos e 5 anos" → Lia confirmou → próximo turno perguntou de novo "consulta é para bebê, criança, adolescente ou adulto?" Campo TODA CONVERSA (1261206) permanecia vazio para leads do canal WA Cloud (8133).

**Causa raiz:** O bloco de gravação de TODA CONVERSA (C-133) estava em `pipeline.run()`. Mas mensagens do canal WA Cloud (8133) passam por `_process_whatsapp_cloud → responder.reply()` diretamente, **sem chamar `pipeline.run()`**. Resultado: campo 1261206 nunca era escrito para leads 8133 → Lia não tinha memória do turno anterior → repetia perguntas já respondidas.

**Os 3 caminhos de webhook:**
- Evolution (0710): `pipeline.run()` → C-133 escrevia TODA CONVERSA ✅
- WA Cloud (8133): `_process_whatsapp_cloud` → `responder.reply()` → ❌ NUNCA passava por `pipeline.run()`
- Salesbot/Kommo: `_process_kommo` → ❌ não chamava nem `pipeline.run()` nem `_sync_kommo_safely`

**Fix em 3 partes:**

1. **`pipeline.py`**: Removeu bloco C-133 ativo de `pipeline.run()` (evita double-write para Evolution). Substituiu por comentário explicativo. Adicionou bloco C-144 dentro de `_sync_kommo_safely` — cobrindo tanto Evolution quanto WA Cloud, pois ambos chamam `_sync_kommo_safely` em background thread.

2. **`_sync_kommo_safely`**: Usa `ctx["toda_conversa"]` lido do Kommo nesta própria função (estado mais fresco), não o snapshot estale do início do turno.

3. **`webhook.py` (`_process_kommo`)**: Adicionou write direto de TODA CONVERSA após o bloco de auto-fill existente, cobrindo o caminho Salesbot que não chama `_sync_kommo_safely`.

**Pytest:** `tests/test_bug_c144_toda_conversa_wa_cloud.py` — 16/16 verde.
**Push:** `PUSH_C144_TODA_CONVERSA_WA_CLOUD.command`

**Lição arquitetural CRÍTICA:**
- **Múltiplos caminhos de webhook = múltiplos locais que precisam de cada write crítico.** Adicionar escrita em apenas UM caminho deixa os outros cegos. Regra permanente: ao centralizar qualquer lógica de escrita/read Kommo, verificar via `grep` se todos os 3 caminhos (Evolution, WA Cloud, Salesbot) chamam o código novo.
- **`_sync_kommo_safely` é o único ponto compartilhado entre Evolution e WA Cloud.** É o lugar canônico para qualquer operação que deve rodar em todos os turnos, independente do canal.
- **Campo write-only sem read-back = Lia cega.** TODA CONVERSA que não é lida de volta em `get_caller_context_by_lead` é como escrever num papel que ninguém vai ler. A leitura (C-143) sem a escrita completa (C-144) não resolve nada.

### 0. (14/08/2026) Bug C-143 — Campo ULTIMA MSG OUTBOUND excluído: TODA CONVERSA como fonte única

**Origem:** Fábio excluiu o campo 1260856 (ULTIMA MSG OUTBOUND) do Kommo — "não estava adiantando de nada". Substituído pelo campo 1261206 (TODA CONVERSA), que acumula todo o histórico no formato `[P HH:MM DD/MM] paciente\n[L HH:MM DD/MM] lia`.

**3 mudanças arquiteturais aplicadas:**

1. **`campos_acompanhamento.py`**: `FIELD_ULTIMA_MSG_OUTBOUND = 0` (sentinela). Guard em `update_lead_fields` ignora field_id=0 silenciosamente. Imports antigos não quebram.

2. **`kommo.py::get_caller_context_by_lead`**: ao ler TODA CONVERSA (fid==1261206), extrai a última linha `[L ...]` → popula `ctx.known["ultima_msg_outbound"]`. Resolve C-139 definitivamente **sem Redis** — todo módulo que ler `ctx.known["ultima_msg_outbound"]` vê dados reais da leitura do Kommo.

3. **`watchdog_promessa.py`**: nova constante `FIELD_TODA_CONVERSA = 1261206` + helper `_extrair_ultima_lia_de_toda_conversa(lead)` + `avaliar_lead` usa o helper.

**Efeito cascata em C-139:** com `ultima_msg_outbound` agora populado por leitura real do Kommo, `_repete_ultima_outbound` (C-127) e `_inbound_responde_ultima_pergunta_c130` (C-130) passam a funcionar sem depender de Redis como workaround. C-139a/b continuam ativos como defesa extra.

**Pytest:** `tests/test_bug_c143_toda_conversa_fonte_unica.py` — 17/17 verde. Watchdog: 41/41. C-141/C-142/C-133: 26/26.
**Push:** `PUSH_C143_TODA_CONVERSA_FONTE_UNICA.command`

**Lição arquitetural CRÍTICA:**
- **Campo Kommo excluído sem aviso = bug silencioso imediato.** Toda dependência em field_id hardcoded é ponto frágil. Fix: sentinela 0 + migrar lógica pra campo ativo imediatamente.
- **TODA CONVERSA como fonte de verdade é mais robusta que campo isolado.** Um único campo acumula o contexto completo; extrair a última linha `[L ...]` é determinístico e sem efeitos colaterais.
- **Watchdog que lia campo deletado retornava `tratar=False` para TODOS os leads** — promessas não cumpridas ficaram invisíveis até o fix. Padrão permanente: quando um campo é excluído, auditar imediatamente todos os consumidores via `grep -r "field_id.*1260856"`.

### 0. (14/08/2026) Bug C-139 — Loop "Qual o nome completo do paciente?" 6x + valor "tá custando" ignorado

**Origem:** lead 24455626 Heytor Rodrigues de Godoi (Iporã/GO — geograficamente incompatível, ~400km de Brasília). "Quanto que tá custando o exame de vista em criança" não casava em `_PADROES_PERGUNTA_VALOR` → fall-through para C-125 → C-125 perguntou "Qual o nome completo do paciente?" 6x consecutivas sem parar.

**Causa raiz arquitetural PERMANENTE (não resolvida completamente):**
Campo Kommo **1260856 (ULTIMA MSG OUTBOUND)** é ESCRITO pelo pipeline a cada turno (visibilidade para equipe humana), mas **NÃO É LIDO DE VOLTA** durante o build do `caller_context`. `ctx.known["ultima_msg_outbound"]` fica sempre vazio. Resultado: todos os mecanismos que dependem do campo ficam cegos:
- `_repete_ultima_outbound` → sempre `False` → C-125 nunca suprime duplicata
- `_inbound_responde_ultima_pergunta_c130` → `if not ultima: return False` → C-130 nunca suprime C-125

**Fix C-139 em 3 camadas (`blindagens_deterministicas.py`):**

1. **C-139a — Contador Redis anti-loop:** `blink:c139_count:{lead_id}:{campo}` (TTL 10min). Após >2 asks do mesmo campo → `return None` → fall-through ao LLM. Também escreve `blink:c125_asked:{lead_id}` = nome do campo.

2. **C-139b — Fallback Redis em C-130:** quando `ultima_msg_outbound` está vazio, C-130 lê `blink:c125_asked:{lead_id}` (escrito por C-139a) para determinar qual campo foi perguntado. Cobre: nome (≥2 palavras alfa, sem `?`) / data_nasc / cpf / convenio. Fail-open: Redis indisponível → `return False`.

3. **C-139c — "tá custando" em `_PADROES_PERGUNTA_VALOR`:** 4 padrões novos — `tá custando`, `está custando`, `quanto que tá/está`, `custando` standalone.

**Fix definitivo pendente:** ler `field_id=1260856` em `kommo.py::get_caller_context_by_lead` e popular `ctx.known["ultima_msg_outbound"]`. C-139a/b são workaround Redis fail-open enquanto isso não é implementado.

**Pytest:** `tests/test_bug_c139_loop_nome_valor.py` — 36/36 verde. Push: `PUSH_C139_LOOP_NOME_VALOR.command`.

**Rollback:** `BLINDAGEM_DADOS_PENDENTES_ATIVADO=0` → desliga C-139a + C-125 inteiro.

**Lição arquitetural CRÍTICA:**
- **Campo Kommo WRITE-ONLY desde a perspectiva do pipeline.** Qualquer campo que o pipeline escreve mas não lê de volta é uma armadilha silenciosa. Regra permanente: **todo campo Kommo escrito pelo pipeline DEVE ser lido de volta em `get_caller_context_by_lead`**. Não há garantia de que `ctx.known["X"]` corresponde ao campo K no Kommo se nenhum código faz esse mapeamento na leitura.
- **Regex PT-BR coloquial tem formas contraídas.** "tá" = "está" em WhatsApp informal. Todo padrão que detecta um verbo conjugado deve incluir a contração coloquial: `est[aá]` cobre "está" e "esta" mas não "tá". Usar `(?:est[aá]|t[aá])` ou padrão standalone `\bt[aá]\b`.
- **Contador Redis por (lead, campo) é defesa arquitetural contra qualquer loop de formulário.** Não depende do texto da última mensagem — depende apenas de quantas vezes o campo X foi perguntado para o lead Y. Funciona mesmo com `ultima_msg_outbound` vazio.

### 0. (14/08/2026) Bug C-145 — Convênio verificado ANTES dos dados do paciente (norma determinística)

**Origem:** lead 24456884 (Beatriz/Amil). Fábio: "perdeu a logica de saber primeiro o convenio, para saber se atendemos. No caso Amil nao atendemos e a conversa estendeu. Inserir como norma deterministica antes de comecar perguntar os dados do paciente. Porque a conversa pode ir para valor de consulta se nao tem convenio. Inserir como norma deterministica."

Paciente Beatriz disse "Vocês aceitam o plano de saúde Amil?" na 1ª mensagem. C-136 (pergunta_perfil) disparou ANTES de `faq_convenio_aceito` e retornou "bebê, criança, adolescente ou adulto?" — a recusa do Amil nunca foi entregue. 5 turnos desperdiçados.

**Causa raiz:** na chain `tentar_bypass_deterministico`, C-136 estava posicionado ANTES de `faq_convenio_aceito`. Qualquer mensagem onde perfil era desconhecido (incluindo "Vocês aceitam Amil?") fazia C-136 disparar primeiro.

**Fix em 3 camadas:**

1. **`voice_agent/convenio_primeiro.py` (NOVO):**
   - `deve_perguntar_convenio_primeiro_c145(ctx, user_text)` → quando convênio desconhecido E texto não menciona nome de plano E não é FAQ de convênio → retorna "a consulta seria pelo seu plano de saúde ou sem convênio? 😊"
   - Não dispara quando: nome de plano no texto (Amil, Bacen etc.) → `faq_convenio_aceito` trata; FAQ genérico ("vocês aceitam?") → `faq_convenio_aceito` trata; convênio já resolvido; `ja_agendado=True`; anti-loop (última outbound já perguntou).
   - Toggle: `BLINDAGEM_CONVENIO_PRIMEIRO_C145_ATIVADO` (default ON). Fail-open. `ctx is None` → None.

2. **`voice_agent/pergunta_perfil.py` — guard C-145:**
   - C-136 retorna None quando `not known["convenio"] AND convenio_aceito is None AND not sem_convenio`.
   - C-136 só dispara quando convênio já resolvido (aceito OU sem convênio).

3. **`voice_agent/blindagens_deterministicas.py` — nova ordem:**
   - ANTES: FAQs → C-136 → escolha_convenio → faq_convenio_aceito → ...
   - DEPOIS: FAQs → escolha_convenio → faq_convenio_aceito → **C-145** → **C-136** → ...

**Fluxo correto após fix:**
- "Vocês aceitam Amil?" → `faq_convenio_aceito` → recusa imediata ✅
- "Quero marcar consulta" → C-145 → "plano ou sem convênio?" ✅
- Paciente: "sem convênio" → C-145 não dispara → C-136 → "bebê, criança...?" ✅
- Paciente: "Bacen" → `faq_convenio_aceito` → aceito → C-136 → "bebê, criança...?" ✅

**Pytest:** `tests/test_bug_c145_convenio_primeiro.py` — 40/40 verde.
**Push:** `PUSH_C145_CONVENIO_PRIMEIRO.command`

**Lição arquitetural CRÍTICA:**
- **Ordem da chain deterministíca define qual bypass "ganha".** O primeiro bypass que retorna não-None vence. Posicionar C-136 antes de `faq_convenio_aceito` era um bug de ordenação puro — C-136 intercepava qualquer 1ª mensagem antes que `faq_convenio_aceito` tivesse chance de rodar.
- **Convênio é GATEWAY, não dado de coleta.** Se convênio não for aceito, todo dado coletado antes (perfil, nome, data nasc) foi desperdiçado. Ordem correta: aceita? → SIM: coleta dados → NÃO: informa recusa. C-145 é a norma determinística que garante essa sequência.
- **Guard em C-136 + reordenação = defesa dupla.** Mesmo que a ordem mude por acidente, o guard em C-136 (`if not convenio resolved → return None`) evita regressão. Dois mecanismos independentes protegem o mesmo invariante.
- **Rollback:** `BLINDAGEM_CONVENIO_PRIMEIRO_C145_ATIVADO=0` + `PERGUNTA_PERFIL_ATIVADA=0` em Easypanel → Implantar.

### 0. (12/08/2026) Bug C-128 — Recusa convênio: tom genérico sem nome do paciente, "condições diferenciadas", ordem invertida errada

**Origem:** lead 24446300 (Juliene = contato/mãe, Daniel = paciente, Amil = convênio não aceito). `_montar_recusa_convenio` gerava mensagem genérica sem personalização — não abria com nome do contato, não citava o paciente pelo nome, usava "condições diferenciadas" em vez de "incentivos especiais", e colocava opção de conversão (seguir sem convênio) em segundo lugar.

**Fix em `voice_agent/blindagens_deterministicas.py`:**

1. **`_montar_recusa_convenio(conv_display, saud, escuta_pfx, ctx)`** — reescrita total (C-128):
   - Extrai `nome_contato` (quem está no WhatsApp) e `nome_paciente` (quem vai consultar) de `ctx.known`
   - Abre com `"Entendi, {nome_contato}. "` quando nome disponível
   - Referencia paciente: `"não quero deixar o {nome_paciente} sem solução"` ou `"você"` como fallback
   - `"incentivos especiais"` (era `"condições diferenciadas"`)
   - `"Como prefere seguir?"` (era `"Qual a sua preferência?"`)
   - Ordem: `1️⃣ Seguir sem convênio` / `2️⃣ Somente com convênio` (era invertida)

2. **`_RE_ESCOLHA_SEM_CONVENIO_C123`** — agora casa `1️⃣`/`"1"` (Seguir sem convênio = opção 1)
3. **`_RE_ESCOLHA_SO_CONVENIO_C123`** — agora casa `2️⃣`/`"2"` (Somente com convênio = opção 2)
4. **`_ultima_msg_era_recusa_convenio`** — atualizada de match exato para `re.search` regex — compatível com formato antigo (C-123) e novo (C-128)

**Pytest:** `tests/test_bug_c123_convenio_recusado.py` — 57/57 verde.

**Rollback:** revert commit (não há toggle separado).

**Lição arquitetural CRÍTICA:**
- **Opção de conversão positiva SEMPRE em primeiro lugar.** Paciente que quer continuar sem convênio clica `1`. Colocar somente-convênio como `1` priorizava o caminho que encerra a conversa.
- **Nome do contato ≠ nome do paciente.** Em consultas pediátricas, `nome_contato` = mãe/pai, `nome_paciente` = filho. Citar o filho pelo nome cria empatia real: "não quero deixar o Daniel sem solução".
- **"incentivos especiais" > "condições diferenciadas".** Tom mais positivo e menos burocrático.
- **`_ultima_msg_era_recusa_convenio` com regex vs exact match.** Leads em mid-conversation têm o formato antigo em `ultima_msg_outbound` — regex garante backward compatibility.

### 0. (12/08/2026) Bug C-127 — Tom robótico: mensagens em bloco + repetição + bypasses ignoravam o que paciente disse

**Origem:** Fábio: "está enviando mensagens em bloco, e mensagens repetidas, sem considerar o que os pacientes enviaram antes."

**3 causas simultâneas:**

1. **Mensagens em bloco**: Python bypasses geravam 1 string longa → pipeline mandava tudo de uma vez → WhatsApp mostrava como "parede de texto". Parecia robô.

2. **Repetição**: quando bypass disparava, não verificava se a resposta era idêntica ao `ultima_msg_outbound`. Paciente perguntava endereço 2x → recebia o mesmo texto palavra por palavra.

3. **Ignorava contexto do paciente**: bypasses de valor e convênio não reconheciam o que o paciente havia dito ("meu filho de 7 meses", "Bacen", "Asa Norte"). Resposta começava direto no conteúdo sem nenhum "Anotado — ...".

**Fix em 3 camadas (commit C-127, 12/08/2026):**

1. **`voice_agent/message_splitter.py` (NOVO):**
   - `split_message()` divide em 2-3 partes em pontos naturais (fim de frase, linha em branco)
   - Protege blocos `1️⃣/2️⃣` (menu nunca cortado)
   - `send_split()` envia com delay 1.2s entre chunks
   - Toggle: `MESSAGE_SPLIT_ENABLED=0` desliga (default ON)
   - Plugado em `pipeline.py` no caminho Evolution

2. **Anti-repetição universal em `tentar_bypass_deterministico()`:**
   - Closure `_repete_ultima_outbound()`: overlap ≥ 70% de palavras relevantes → suprime bypass
   - Aplicado em: `faq_endereco`, `faq_especialidade`, `faq_convenio_aceito`, `convenio`, `objecao_preco`, `valor`, `endereco_pos_agenda`, `sinal_particular_c114`, `dados_pendentes_c120`
   - NUNCA suprime: `aceite_slot`, `escolha_convenio_c123`, `cancelamento_24h`, `desistencia`, `urgencia`, `comprovante_pix_c116`, `sinal_noshow` (ações críticas)

3. **`_escuta_universal(user_text, ctx)` (NOVO):**
   - Extrai elementos mencionados pelo paciente que NÃO estão em `ctx.known`: filho/bebê com idade, convênio, unidade
   - Retorna `"Anotado — bebê de 7 meses! "` ou `""` se nada novo
   - Injetado em `deve_responder_valor()` (no abertura) e `_montar_recusa_convenio()` (antes do corpo)

**Pytest:** `tests/test_bug_c127_tom_conversacional.py` — 32/32 verde.

**Rollback:** `MESSAGE_SPLIT_ENABLED=0` em Easypanel → Implantar (desliga Fix 1). Fix 2/3 = revert commit.

**Lição arquitetural CRÍTICA:**
- **"Parece robô" = 3 sintomas diferentes com 3 causas raiz.** Não basta corrigir o LLM — os bypasses Python também precisam ser conversacionais.
- **Split de mensagem é UX obrigatória em WhatsApp.** Mensagem de 400 chars com 4 frases = 2-3 mensagens de 130-200 chars cada, com delay. Parece digitação humana.
- **Anti-repetição via overlap léxico é mais robusto que hash.** Hash exato falha quando o mesmo conteúdo muda uma palavra. Overlap 70% captura o caso real sem falso positivo.
- **`_escuta_universal` é mais leve que `_prova_de_escuta_c125`.** C-125 é para formulário de dados (extração detalhada). C-127 é para cualquer bypass (só extrai o que o paciente mencionou E ainda não está em `ctx.known`).

### 0. (11/08/2026) Bug C-125 — Regressão C-120: formulário multi-campo sem "prova de escuta" (lead 24441434 Janaina Melo)

**Origem:** lead 24441434 Janaina Melo. Paciente disse: "Gostaria de agendar com a Dra. Karla. É para o meu filho de 7 meses. Consulta de rotina solicitada pelo pediatra." — Lia despejou TODOS os campos pendentes em uma mensagem sem reconhecer o que a paciente havia informado: "me passa: nome completo, data de nascimento, convênio, médico e unidade?" Fábio: *"não ouviu o que o paciente disse, faltando a prova da escuta... passar solicitações de forma gradual e atômica."*

**Causa raiz — C-120 gerava formulário sem contexto:**
`_montar_pergunta_dados_c120` listava todos os `campos_pendentes` de uma vez, sem:
1. Reconhecer o que o paciente já havia dito (médico, perfil, motivo)
2. Perguntar apenas 1 campo por vez
3. Personalizar a pergunta pelo contexto (bebê, criança, adulto)

**Fix — 3 funções novas em `blindagens_deterministicas.py`:**

1. **`_prova_de_escuta_c125(user_text, known)`** — extrai e reformula o que o paciente informou:
   - Médico mencionado ("Karla" → "Dra. Karla Delalíbera")
   - Perfil do paciente ("filho de 7 meses" → "bebê de 7 meses"; "filha de 5 anos" → "criança de 5 anos")
   - Motivo ("rotina", "retorno")
   - Encaminhamento/pediatra → "com encaminhamento"
   - Retorna "Anotado — [elementos]" ou "" se nada identificado

2. **`_campo_prioritario_c125(pendentes)`** — retorna APENAS 1 campo (nunca "médico"):
   - Prioridade: nome → data_nasc → convênio → cpf → unidade
   - "médico" é pulado — Python deriva via C-101/enriquecimento_ctx
   - Retorna None se só médico restava → fail-open, LLM continua

3. **`_montar_pergunta_dados_c125(resultado, ctx, user_text)`** — combina escuta + pergunta atômica:
   - Pergunta personalizada por campo + contexto (bebê/criança/adulto)
   - Com escuta: "Anotado — Dra. Karla Delalíbera, bebê de 7 meses, consulta de rotina! 😊 Qual o nome completo do bebê?"
   - Sem escuta + nome coletado: "Maria, qual a data de nascimento de Maria?" (evita repetição)
   - `deve_perguntar_dados_pendentes()` agora chama `_montar_pergunta_dados_c125()` em vez de `_montar_pergunta_dados_c120()`

**Pytest:** `tests/test_bug_c125_prova_escuta_uma_pergunta.py` — 60/60 verde. Cobre: caso real Janaina 24441434, 13 padrões `_prova_de_escuta_c125`, `_campo_prioritario_c125` nunca pergunta médico, 1 campo por turno, formulário banido, C-120 retrocompat 75/75.

**Rollback:** `BLINDAGEM_DADOS_PENDENTES_ATIVADO=0` em Easypanel → Implantar (mesmo toggle de C-120).

**Lição arquitetural CRÍTICA:**
- **"Prova de escuta" é UX obrigatória em WhatsApp.** Paciente que forneceu 4 informações e recebe "me passa nome, data, convênio e médico?" sente que foi ignorada. O padrão correto: acknowledge → 1 pergunta. Não é cosmético — é taxa de conversão.
- **`campos_pendentes` como lista de perguntas = anti-padrão.** C-120 criou a lista corretamente mas errou ao despejá-la inteira. A lista é para SEQUÊNCIA — perguntar item[0] agora, item[1] após resposta, etc.
- **Personalização por perfil é esperada pelo usuário.** "Qual o nome completo do paciente?" é frio. "Qual o nome completo do bebê?" é natural. O contexto (bebê/criança/adulto) já está no `user_text` — extrair e usar é zero custo extra.
- **Nunca perguntar médico via Python.** C-101 deriva médico por idade/motivo. Se C-125 perguntasse "Dra. Karla ou Dr. Fabrício?", conflitaria com C-101. Regra: se só médico está pendente → None → LLM (ou C-101 derivou e não propagou ainda).


### 0. (11/08/2026) Bug C-123 — Convênio não aceito: tom seco + "particular" + valor prematuro + Kommo não atualizado

**Origem:** lead 24441038 — paciente perguntou Bradesco. Lia respondeu "infelizmente não está na nossa rede credenciada" + "Mas atendemos como **particular**: R$ 611 Pix / R$ 670 cartão". 4 falhas simultâneas:

1. **Tom seco** — "não está na rede" → correto: "ainda estamos em processo de credenciamento"
2. **"particular"** — termo proibido; usar "sem convênio"
3. **Valor prematuro** — R$ 611/670 sem saber motivo/médico ainda
4. **Campo Kommo não gravado** — quando paciente escolhia "Seguir Sem Convênio", campo CONVÊNIO (field 853206) ficava vazio

**Fix em 3 arquivos:**

- **`blindagens_deterministicas.py`** — `_montar_recusa_convenio()` helper com tom canônico ("processo de credenciamento", sem valor, ordem 1️⃣ Somente / 2️⃣ Seguir). Ambas as instâncias de recusa em `deve_responder_faq_convenio_aceito` (Caminho A + B) usam o helper. Bypass novo `deve_responder_escolha_convenio` gateado em `_ultima_msg_era_recusa_convenio` (detecta quando Lia já apresentou as 2 opções). Posição na chain: ANTES de `faq_convenio_aceito`.

- **`responder.py`** — `_gerar_script_convenio_nao_aceito` (filtro quando Lia erroneamente disse que aceita): removido "(te apresento valor + parcelamento)", ordem 1️⃣ Somente / 2️⃣ Seguir corrigida.

- **`pipeline.py`** — Hook C-123: lê `c123_marcar_sem_convenio` → `patch_custom_fields_raw` CONVÊNIO = Não se aplica (field 853206, enum 906979) + Ñ ACEITO CONVÊNIO com o plano recusado. Lê `c123_encerrar_so_convenio` → 2.LEADS FRIO + desativa IA.

**Pytest:** 52/52 verde.

**Lição arquitetural CRÍTICA:**
- **Regra de apresentação ("sem convênio" ≠ "particular") deve estar no helper, não espalhada em múltiplos return statements.** `_montar_recusa_convenio()` é a fonte de verdade — mudança em um lugar propaga para Caminho A, B, e filtro de responder.py.
- **"Processo de credenciamento" vs "não credenciado" é diferença de relacionamento.** "Não credenciado" fecha a porta; "em processo" mantém o lead ativo e ainda pode converter.
- **Bypass de resposta a oferta SEMPRE antes do bypass de FAQ.** Paciente respondendo "2" a uma oferta apresentada ≠ fazendo pergunta nova. Gate `_ultima_msg_era_recusa_convenio` é o discriminador correto.
- **Rollback:** `BLINDAGEM_ESCOLHA_CONVENIO_ATIVADO=0` em Easypanel → Implantar.

### 0. (11/08/2026) Bug C-116 — Comprovante Pix enviado: Lia ficava em silêncio (imagem não detectada)

**Origem:** auditoria arquitetural (sessão 11/08/2026). Paciente que escolhia "1️⃣ Reserva garantida" (C-114) enviava comprovante Pix como imagem WhatsApp — webhook convertia para texto sintético (`[O paciente enviou uma imagem pelo WhatsApp]`), mas NENHUM bypass tratava esse texto quando havia flag `blink:c114_aguardando_comprovante:{lead_id}` ativo. Resultado: Lia não confirmava recebimento; paciente ficava sem resposta; equipe humana não recebia alerta.

**Decisão arquitetural (P0):** Texto sintético de imagem + flag aguardando_comprovante = fato objetivo — Python detecta, confirma ao paciente, e alerta Kommo.

**3 arquivos criados/modificados (11/08/2026):**

1. **`voice_agent/comprovante_pix.py` (NOVO):**
   - `deve_confirmar_comprovante_pix(ctx, user_text)` — regex detecta texto sintético de imagem (paths Evolution + WA Cloud).
   - Gate Redis: `blink:c114_aguardando_comprovante:{lead_id}` (TTL 7d, set pelo pipeline C-114 branch "reserva").
   - Confirmação: mensagem ✅ informando que comprovante chegou + aguarda validação humana.
   - Grava `blink:c116_comprovante_detectado:{lead_id}` (TTL 2h) para pipeline adicionar nota Kommo.
   - NÃO repete chave Pix na confirmação (já foi mostrada no C-114).
   - Toggle: `COMPROVANTE_PIX_ATIVADO` (default ON); fail-open: Redis=None/exceção → None.

2. **`voice_agent/pipeline.py` — bloco C-114 reserva:** `setex blink:c114_aguardando_comprovante:{lead_id}` (TTL 7d) quando paciente escolhe "reserva".

3. **`voice_agent/pipeline.py` — bloco C-116:** lê `blink:c116_comprovante_detectado:{lead_id}` → nota Kommo `📲 [LIA C-116] Comprovante Pix recebido via WhatsApp` + limpa ambos os flags Redis.

4. **`voice_agent/blindagens_deterministicas.py`:** bypass C-116 APÓS C-115, ANTES de `faq_endereco`.

**Pytest:** `tests/test_bug_c116_comprovante_pix.py` — 37/37 verde.

**Lição arquitetural CRÍTICA:**
- **Webhook transforma imagem em texto sintético — não é mensagem vazia.** `[O paciente enviou uma imagem pelo WhatsApp]` é a forma do texto e deve ser detectada explicitamente. Texto diferente por canal (Evolution vs WA Cloud) → dois padrões regex.
- **Flag Redis conecta dois momentos desacoplados no tempo.** C-114 (oferta) grava o flag; C-116 (imagem enviada) lê o flag. Sem a flag, qualquer imagem dispararia a confirmação, com falsos positivos. Com a flag, só dispara quando há contexto correto.
- **Confirmação de comprovante ≠ validação de pagamento.** Lia confirma RECEBIMENTO; humano valida se o valor/dados estão corretos. A mensagem é explícita sobre isso.
- **Rollback:** `COMPROVANTE_PIX_ATIVADO=0` em Easypanel → Implantar.

### 0. (11/08/2026) Bug C-114 — PARTICULAR confirmava agendamento e não recebia política de comparecimento (poltrona de avião)

**Origem:** auditoria arquitetural (sessão 11/08/2026). Pacientes PARTICULARES (sem convênio) confirmavam dados do agendamento ("sim, correto") e não recebiam nenhuma oferta de reserva com sinal. Pipeline ia para o LLM sem script determinístico — resultado: paciente agendava sem nenhum comprometimento financeiro, aumentando risco de no-show.

**Decisão arquitetural (P0):** Confirmação de agendamento PARTICULAR é fato objetivo detectável — Python entrega as 2 opções antes do LLM. Momento correto: APÓS conclusão de agendamento enviada E paciente confirmar os dados. Tom: leve, incentivo ao comparecimento, não coercitivo.

**4 arquivos criados/modificados total (11/08/2026):**

1. **`voice_agent/politica_comparecimento.py` (NOVO):** `deve_solicitar_sinal_particular(ctx, user_text, redis)` — 4 gates: (1) texto confirma dados (13 padrões: "sim", "dados corretos", 👍, ✅), (2) convênio = PARTICULAR, (3) última outbound era conclusão de agendamento, (4) Redis flag TTL 24h não ativo. Valores: Karla APV R$400, Karla outros R$305,50, Fabrício catarata R$222,50.
2. **`voice_agent/campos_acompanhamento.py`:** `"fila_encaixe": 927866` adicionado ao campo A FAZER (field_id 1259312).
3. **`voice_agent/blindagens_deterministicas.py`:** bypass C-114 DEPOIS de `endereco_pos_agenda`.
4. **`voice_agent/pipeline.py` — bloco C-114 loop:** detecta escolha do paciente ("reserva" vs "fila") → `patch_custom_fields_raw` no campo A FAZER + nota Kommo.

**Kommo (live 11/08/2026):** "Fila Encaixe" adicionado ao campo "A FAZER" (field_id 1259312, enum_id 927866).

**Pytest:** `tests/test_bug_c114_politica_comparecimento.py` 47/47 + `tests/test_bug_c114_pipeline_loop.py` 26/26 = **73/73 verde**.

**Lição arquitetural CRÍTICA:**
- **Sinal de comparecimento não é cobrança — é redução de risco para ambos os lados.** Paciente que escolhe "reserva garantida" tem slot assegurado; quem escolhe "fila" sabe que pode perder o horário.
- **O momento certo é DEPOIS da confirmação de dados.** Perguntar sobre sinal antes de confirmar os dados é pressão indevida.
- **`_ultima_msg_era_conclusao` é a guarda essencial.** Sem ela, qualquer "sim" dispararia a mensagem em qualquer contexto.
- **Rollback:** `POLITICA_COMPARECIMENTO_ATIVADO=0` em Easypanel → Implantar.

### 0. (11/08/2026) Bug C-111 — Race condition: agendamento.py gravava no Medware sem re-verificar se slot ainda estava livre

**Origem:** auditoria arquitetural (sessão 11/08/2026). `tools_lia.py::handle_gravar_agendamento_medware` já tinha chamada a `medware.slot_ainda_disponivel` antes de `criar_agendamento`. Mas `agendamento.py::executar_agendamento` é o segundo caminho pra gravação e chamava `criar_agendamento` DIRETAMENTE sem a verificação. Lia podia ofertar slot às 10h, paciente confirmar às 18h, e nesse intervalo outro paciente ocupar — mas o agendamento gravava no slot ocupado.

**Decisão arquitetural (P0):** slot_ainda_disponivel é verificação de integridade, não de lógica de negócio. Deve existir em TODOS os caminhos que chamam criar_agendamento. Fail-open: se Medware falhar na verificação → prossegue (não bloqueia conversa).

**1 arquivo modificado:**

- **`voice_agent/agendamento.py` — bloco C-111 antes de `criar_agendamento`:**
  - Se `medware.slot_ainda_disponivel` existe: chama com `data_iso`, `hora`, `cod_medico`, `cod_unidade`
  - Slot livre → prossegue normalmente
  - Slot ocupado → retorna `{ok:False, motivo:"slot_ocupado_race_condition", msg_para_paciente, slots_alternativos}`
  - Mensagem para paciente: emojis 1️⃣/2️⃣ com alternativas reais ou fallback genérico se sem alternativas
  - Fail-open: `except Exception` → log WARNING + prossegue (preserva conversa)
  - Guard: sem `data_iso` ou `hora` → não chama (compatibilidade com decisões sem horário)

**Pytest:** `tests/test_bug_c111_reverificar_slot.py` — 18/18 verde. Cobre: slot livre (verifica antes de gravar), slot ocupado (não chama criar, retorna alternativas), fail-open (timeout/exceção/método ausente), guards sem data_iso/hora, estrutura arquivo.

**Lição arquitetural CRÍTICA:**
- **Dois caminhos pro Medware = dois locais que precisam do guard.** tools_lia.py e agendamento.py são caminhos independentes. Adicionar verificação em UM não protege o OUTRO. Regra permanente: ao adicionar verificação de integridade em um caminho de entrada, auditar TODOS os outros caminhos com grep.
- **Slot ofertado ≠ slot reservado.** Sem Redis lock explícito (E6-B), há janela entre oferta e gravação. Re-verificar no momento da gravação é a última linha de defesa.
- **Fail-open é obrigatório em verificações de disponibilidade.** Se Medware está lento e a verificação falha, o correto é prosseguir com risco baixo de duplicação (recuperável) — não bloquear a conversa do paciente (irrecuperável).

### 0. (11/08/2026) Bug C-109 — NO-SHOW COUNT >= 2 ignorado: LLM ofertava slot sem exigir sinal Pix

**Origem:** auditoria arquitetural (sessão 11/08/2026). Pipeline injetava `noshow_count` em `caller_context.known` mas NUNCA verificava esse campo antes de ofertar slots. Pacientes com 2+ no-shows recebiam oferta idêntica a novatos — sem exigência de sinal. Grade ficava bloqueada por pacientes que não compareceriam.

**Decisão arquitetural (P0):** Noshow count é fato objetivo em Kommo — Python detecta, exige sinal antes de mostrar qualquer slot. LLM não decide se exige sinal.

**4 arquivos criados/modificados (11/08/2026):**

1. **`voice_agent/sinal_noshow.py` (NOVO):**
   - `deve_exigir_sinal_noshow(ctx, user_text, redis_client)` — dispara quando `sinal_obrigatorio=True` E há agenda OU aceite no texto
   - Chaves Pix por unidade: Asa Norte → `28.655.944/0001-16`; Águas Claras → `52.303.729/0001-30`
   - Valor sinal por médico/motivo: Karla APV → R$ 400; Karla rotina → R$ 305,50; Fabrício catarata → R$ 222,50
   - noshow=2 → `_mensagem_sinal_obrigatorio` (Pix + reserva 50%)
   - noshow≥3 → `_mensagem_escalar_noshow` + grava `blink:c109_move_humano:{lead_id}` (TTL 24h)
   - Redis flag `blink:c109_sinal_cobrado:{lead_id}` (TTL 8h) impede repetição a cada turno
   - Toggle: `SINAL_NOSHOW_ATIVADO` (default ON); fail-open: exceção → None

2. **`voice_agent/kommo.py`** — NO-SHOW COUNT lido por `field_name` scan (não field_id, que não foi confirmado): detecta nomes `"NO-SHOW COUNT"`, `"NOSHOW"`, etc → injeta `known["noshow_count"]`

3. **`voice_agent/enriquecimento_ctx.py` — step 15 (C-109):** `noshow_count >= 2` → `known["sinal_obrigatorio"]=True`; `>= 3` → `known["escalar_noshow"]=True`

4. **`voice_agent/blindagens_deterministicas.py`:** bypass C-109 DEPOIS de C-108 (desistência), ANTES de urgência

5. **`voice_agent/pipeline.py`:** bloco C-109 lê `blink:c109_move_humano:{lead_id}` → desativa IA + move lead → 1-ATENDIMENTO HUMANO (106563343) + nota Kommo

**Pytest:** `tests/test_bug_c109_sinal_noshow.py` — 40/40 verde.

**Lição arquitetural CRÍTICA:**
- **Campo Kommo com field_id desconhecido → ler por `field_name`.** Kommo API inclui `field_name` em `custom_fields_values`. Mais robusto que field_id hardcoded que quebra quando campo é recriado (ver Bug C-12 e C-27).
- **Redis flag por sessão (TTL 8h) = a defesa certa para mensagens que não devem repetir.** Sem o flag, o bypass dispararia todo turno — pior que não ter bypass.
- **Rollback:** `SINAL_NOSHOW_ATIVADO=0` em Easypanel → Implantar.

### 0. (11/08/2026) Bug C-108 — Desistência explícita: LLM continuava tentando agendar mesmo após "não quero mais"

**Origem:** auditoria arquitetural (sessão 11/08/2026). Paciente dizia "desisti", "vou em outra clínica", "não quero mais" → LLM continuava fluxo de agendamento sem reconhecer o encerramento. Lead ficava em 3-AGENDAR consumindo cota de mensagens sem possibilidade de conversão.

**Decisão arquitetural (P0):** Desistência explícita é fato objetivo detectável por regex — Python encerra, move lead, desativa IA. LLM não tenta reconquistar.

**3 arquivos criados/modificados (11/08/2026):**

1. **`voice_agent/desistencia.py` (NOVO):**
   - `_RE_DESISTENCIA`: 15+ padrões PT-BR — "desisti", "não quero mais", "vou em outra clínica" (`outr[ao]`), "prefiro outro lugar" (`pref[ei]r[io]`), "cancela tudo", "esqueça", etc.
   - `_RE_NAO_DESISTENCIA`: guarda falso-positivo — "não quero mais esse horário/slot" → não dispara
   - `deve_responder_desistencia(ctx, user_text, redis_client)`: mensagem de encerramento gracioso + grava `blink:c108_desistencia:{lead_id}` (TTL 24h)
   - Toggle: `DESISTENCIA_ATIVADO` (default ON); fail-open: exceção → None

2. **`voice_agent/enriquecimento_ctx.py` — step 14 (C-108):** regex detecta desistência → `known["desistencia_explicita"]=True`

3. **`voice_agent/blindagens_deterministicas.py`:** bypass C-108 PRIMEIRO na chain (antes de urgência, convênio, valor)

4. **`voice_agent/pipeline.py`:** bloco C-108 lê `blink:c108_desistencia:{lead_id}` → desativa IA + move → 2.LEADS FRIO (101508307) + nota Kommo

**Pytest:** `tests/test_bug_c108_desistencia_explicita.py` — 39/39 verde.

**Lição arquitetural CRÍTICA:**
- **Desistência vai para 2.LEADS FRIO, não Closed-lost.** Paciente pode voltar. Desativar IA + mover para frio = preserva histórico e permite reativação humana.
- **Anti-falso-positivo é obrigatório.** "Não quero mais esse horário" ≠ desistência — paciente está pedindo alternativa. Regex negativo (`_RE_NAO_DESISTENCIA`) protege esse caso.
- **Rollback:** `DESISTENCIA_ATIVADO=0` em Easypanel → Implantar.

### 0. (11/08/2026) Bug C-107 — Lia não tinha resposta para "está caro" / "encontrei mais barato" (lead 24436018 Gael)

**Origem:** lead 24436018 Gael, bebê 8 meses, conjuntivite 3 semanas, Karla Asa Norte. Paciente informou que encontrou consulta por R$ 170 em outra clínica. Lia ficou sem resposta — pipeline foi para o LLM sem script de objeção. Atendente humana soube oferecer alternativa (desconto sábado), mas só por telefone depois que o paciente já tinha decidido ir embora.

**Decisão arquitetural (P0):** Objeção de preço é fato objetivo detectável por regex — Python deve entregar o script antes do LLM. O script correto: (1) reconhece a objeção sem dismissar, (2) ancora no VALOR da especialidade (diferencial Blink vs clínica genérica), (3) usa urgência clínica REAL do ctx (nunca fabrica), (4) apresenta 3 alternativas: parcelamento 2x, fila de encaixe, escalar humano.

**3 arquivos criados/modificados (commit 69e593f):**

1. **`voice_agent/objecao_preco.py` (NOVO):**
   - `detectar_objecao_preco(user_text)` — 16 padrões PT-BR ("caro", "mais barato", "não tenho esse valor", "por menos de R$ N", etc.)
   - `_ancoragem_clinica(ctx)` — usa sintoma + semanas/dias REAIS do ctx. "3 semanas" → "— e com o sintoma há 3 semanas, uma avaliação especializada faz diferença no diagnóstico correto". Nunca inventa.
   - `_alternativas(parcela_1, parcela_2)` → "1️⃣ Parcelamento 2x, 2️⃣ Fila de encaixe, 3️⃣ Falar com equipe"
   - Templates por contexto:
     * `_objecao_karla_pediatrico`: oftalmopediatria + R$ 611 sem conv / 2x R$ 335
     * `_objecao_karla_apv`: 2-3h avaliação APV + R$ 800 / 2x R$ 435
     * `_objecao_karla_adulto`: retina + tonometria + R$ 611 / 2x R$ 335
     * `_objecao_fabricio_catarata`: biometria inclusa + R$ 445 / 2x R$ 235
     * `_objecao_fabricio_geral`: saúde ocular 50+ + R$ 611 / 2x R$ 335
     * `_objecao_geral`: fallback sem médico
   - Toggle: `OBJECAO_PRECO_ATIVADO` (default ON); fail-open: exceção → None

2. **`voice_agent/enriquecimento_ctx.py` — step 13 (C-107):**
   - Detecta objeção em `user_text` via regex → injeta `known["objecao_preco"]=True`
   - Roda antes do LLM, fail-open

3. **`voice_agent/blindagens_deterministicas.py`:**
   - Bypass C-107 adicionado ANTES de `deve_responder_valor`
   - Objeção de preço tem prioridade sobre primeira consulta de valor

**Pytest:** `tests/test_bug_c107_objecao_preco.py` — 59/59 verde. Cobre: 16 padrões detecção, negação protege, ctx=None, toggle OFF, âncora com/sem tempo, todos templates, regras universais (sem "particular", sem dismissar, pergunta final), caso real Gael 24436018, flag known ativa sem regex.

**Lição arquitetural CRÍTICA:**
- **Objeção de preço é fato objetivo detectável — não é nuance que o LLM deve "sentir".** "Encontrei mais barato" é inequívoco. Regex detecta, Python entrega o script certo, LLM não precisa improvisar.
- **Valor antes do preço é regra universal.** O script abre com diferencial da especialidade (o que a consulta ENTREGA) e só depois apresenta o parcelamento. Paciente que entende o valor não compara com R$ 170 de clínica genérica.
- **Âncora clínica real > urgência fabricada.** "3 semanas com conjuntivite" é factual e persuasivo. Fabricar urgência seria desonesto e seria detectado pelo paciente.
- **Rollback:** `OBJECAO_PRECO_ATIVADO=0` em Easypanel → Implantar.

### 0. (07/08/2026) Bug C-97 — "Disco furado" perguntando dia/turno mesmo após paciente responder 3x (Zoé 24424208 + Lavinia 24424544)

**Origem:** lead 24424208 Zoé — Lia repetiu "Qual dia da semana e turno funcionam melhor pra vocês?" 3 vezes após paciente responder "Segunda à tarde" 3 vezes. Lead 24424544 Lavinia — mesma falha estrutural. Fábio: *"continuar perguntando sobre turno, a partir de agora tornou desnecessário, pois esta abordagem é para atendimento humano."*

**Decisão arquitetural (P0):** Com médico + unidade + convênio + motivo definidos → ir direto ao Medware e oferecer 2 slots concretos. NUNCA perguntar "qual dia da semana" ou "qual turno". Preferência de dia/turno é papel do atendimento HUMANO.

**10 mudanças em `voice_agent/responder.py`:**
- `_DIA_SEMANA_FALLBACK`, `_DIA_NAO_ATENDIDO_FALLBACK`, `_DIA_SEM_DATA_FALLBACK`, `_COBRANCA_ANTECIPADA_FALLBACK` → mensagens neutras "Vou verificar..."
- `_gerar_proxima_pergunta_sem_convenio()` + `_gerar_reconhecimento_curto_e_avanca()` → removidos branches que pediam preferência dia/turno
- Call sites C-31a, C-31b, C-54 → `_gerar_oferta_2_slots(ctx)` quando há agenda, fallback neutro quando não há
- `_PERGUNTA_TURNO_PERIODO_PATTERNS` → adicionado `"qual dia da semana"` standalone

**Pytest:** `tests/test_bug_c97_eliminar_pergunta_turno.py` — 20/20 verde.
**Push:** `PUSH_C97_ELIMINAR_PERGUNTA_TURNO.command`
**DOCX:** S17 em `RESPOSTAS_CANONICAS_LIA.docx` → ✅ IMPLEMENTADO (C-97).

**Lição arquitetural CRÍTICA:**
- **Perguntar turno antes de oferecer slot é fricção desnecessária.** Lia tem acesso ao Medware em tempo real — oferta 2 slots e paciente escolhe. Não precisa de preferência prévia.
- **Call sites de filtros que detectam violação devem também OFERECER alternativa real**, não apenas bloquear com texto neutro. C-31a/C-31b/C-54 agora chamam `_gerar_oferta_2_slots`.
- **Regex de detecção deve incluir forma mais curta em PT-BR informal.** "Qual dia da semana" (sem "e turno") é a forma mais comum — estava faltando no padrão.
- **Regra permanente: atendimento humano decide turno, Lia decide slot** consultando Medware em tempo real.


### 0. (05/08/2026) Bug C-90 — P0: agente respondia mesmo com ATIVADO IA = Desativado ou 1-ATENDIMENTO HUMANO

**Origem:** Fábio 05/08/2026: "por favor resolver agora quando transferir para atendimento humano ou preencher o campo desativar. O agente nao responder. Isto é mandatorio." Qualquer mensagem nova após atendente desativar IA → Lia respondia na 2ª mensagem.

**Causa raiz — bloco C-49 em `pipeline.py` (linhas 210-245):**
- C-49 foi criado em 02/07/2026 para recuperar leads que ficavam presos com `Desativado` quando o webhook `/admin/kommo-trigger-status-change` não estava configurado em todas as etapas.
- O bloco rodava em CADA mensagem, ANTES de `agent_paused_for_lead()`: se `status_id ∈ _STATUS_ATIVOS_IA_PIPELINE` AND `ativado_ia == "desativado"` → chamava `update_lead_fields(lid, {"ativado_ia": "Ativado"})`.
- Sequência do bug: (1) Atendente seta Desativado. (2) Paciente manda mensagem. (3) Pipeline lê ctx: `ativado_ia="Desativado"`. (4) **C-49 grava "Ativado" no Kommo imediatamente.** (5) `agent_paused_for_lead()` ainda vê o ctx antigo → Lia fica silenciosa DESTA VEZ. (6) Paciente manda 2ª mensagem. (7) Pipeline lê ctx novo: `ativado_ia="Ativado"` (C-49 já sobrescreveu). (8) **Lia responde — bug.**

**Fix — remoção completa do bloco C-49 (`pipeline.py`):**
- O webhook `/admin/kommo-trigger-status-change` já está configurado e cuida de reativar IA quando o lead muda de etapa legitimamente.
- Desativação manual por atendente DEVE ser respeitada permanentemente.
- Para reativar: atendente move lead para etapa ativa no Kommo → webhook dispara automaticamente → ATIVADO IA volta a "Ativado".

**Pytest:** `tests/test_bug_c90_ia_desativada_respeita.py` — 16/16 verde. Cobre: bloco C-49 ausente no arquivo, ST_AGENT_OFF correto, variantes Desativado/DESATIVADO/off, decay 30min humano-recente.
**Push:** `PUSH_C90_IA_DESATIVADA_RESPEITA.command`

**Lição arquitetural CRÍTICA:**
- **Mecanismo de auto-recuperação pode destruir mecanismo de controle manual.** C-49 era um workaround para webhook não configurado — correto no contexto de 02/07. Mas com o webhook em prod, C-49 passou a combater o controle explícito do atendente.
- **Regra permanente: NUNCA sobrescrever campo de controle manual sem verificar se a operação foi iniciada por um humano.** Auto-reset de campos "Desativado" é sempre perigoso. O correto é: humano desativa → permanece desativado até humano reativar (ou webhook de mudança de etapa).
- **Verificar sempre se workaround antigo ainda é necessário.** C-49 tinha comentário "webhook não configurado em todas as etapas". Quando o webhook ficou configurado (tarefa completada), C-49 deveria ter sido removido imediatamente. Não foi — e virou bug meses depois.

### 0. (05/08/2026) Bug C-86 — "Valores" standalone ignorado pelo bypass + C-56 "sem exc" (lead 24413976)

**Origem:** lead 24413976 Cecília/Cristina, 04/08/2026. Paciente digitou "Valores" (palavra única) 2 vezes → Lia ignorou e continuou pedindo preferência de slot. Na 3ª mensagem ("Quero saber valores") o `responder.reply()` retornou vazio (sem exception) → C-56 moveu pra 1-ATENDIMENTO HUMANO.

**2 causas simultâneas:**

1. **`_PADROES_PERGUNTA_VALOR` regex incompleto:** exigia frases compostas ("qual o valor", "quanto custa", "quanto pago"). Standalone `"Valores"` ou `"Preço"` não casava com nenhum padrão → `deve_responder_valor()` retornava None → bypass não ativava → LLM (em FSM=AGENDA) interpretou "Valores" como input de agendamento → respondeu "Anotado. Qual dia da semana e turno funcionam melhor pra vocês?".

2. **C-56 "sem exc" = `responder.reply()` retornou answer vazio sem exception:** o loop `for _tent in range(3)` faz `break` após a 1ª chamada bem-sucedida de `responder.reply()` — mesmo com answer vazio. Então o "Claude API falhou 3x" na nota é hardcoded enganoso (foi 1 tentativa). A causa do answer vazio pode ser filtro (C-30/C-60) scrubbing a resposta pra empty string quando o LLM gerou algo que ativou um stall detector.

**Fix em `voice_agent/blindagens_deterministicas.py`:**
```python
# ANTES (não capturava standalone):
r"|(?:tem|qual)\s+desconto"
r")"

# DEPOIS (Bug C-86 — 3 padrões adicionados):
r"|(?:tem|qual)\s+desconto"
r"|\bvalor(?:es)?\b"      # "Valor"/"Valores" standalone
r"|\bpre[cç]os?\b"        # "Preço"/"Preços" standalone
r"|\bpagamento\b"         # "formas de pagamento"
r")"
```

**Pytest:** `tests/test_bug_c86_valores_standalone.py` — 19/19 verde. Master regressão: 54/54 verde.
**Push:** `PUSH_C86_VALORES_STANDALONE.command`

**Lição arquitetural CRÍTICA:**
- **FAQ bypass de valor estava cego para perguntas de 1 palavra.** Em PT-BR informal, "Valores" sozinho é a forma mais comum de perguntar preço — mais comum que "qual o valor". Regex FAQ deve sempre incluir a forma mais curta/direta.
- **"sem exc" em C-56 ≠ "Claude API falhou".** Quando `responder.reply()` retorna `{"answer": ""}` sem exception, o loop quebra na 1ª tentativa — não 3. O texto "falhou 3x" na nota Kommo é hardcoded e enganoso. A causa real é algum filtro pós-geração scrubbing a resposta pra string vazia.
- **LLM em FSM=AGENDA não pivota para FAQ espontaneamente.** Quando em AGENDA, o LLM trata qualquer input como preferência de horário. A defesa correta é bypass deterministico ANTES do LLM — não instruções no prompt.

### 0. (04/08/2026) Bug C-84 — Loop 11x + paciente pediu atendente e Lia ignorou (lead 24413852 Juliana)

**Origem:** lead 24413852 Juliana. Lia perguntou "Qual turno funciona melhor pra você — manhã ou tarde?" 11 vezes seguidas (39 minutos) mesmo depois da paciente responder "Manhã" e "Segunda ou quarta de manhã" múltiplas vezes. Paciente disse "Não sai disso / Meu Deus" e depois "Desisto." + "Falar com atendente".

**3 causas simultâneas (todos bloqueantes):**

1. **TTL dedup anti-loop muito curto (5min):** `dedup_outbound.py::TTL_JANELA_SEG = 300`. Loop durou 39 min → contador Redis resetou 7+ vezes sem nunca acumular ≥ LIMITE_LOOP (2). Resultado: C-62 nunca detectou o loop.

2. **Filtro C-54 sem guarda anti-loop (equivalente ao C-71):** `_viola_dia_sem_data_incompativel_unidade` (C-54) disparava quando paciente dizia dia da semana sem DD/MM. Quando C-54 retornava `_DIA_NAO_ATENDIDO_FALLBACK` = "Qual turno funciona melhor...", e paciente respondia "Manhã", nenhuma guarda impedia C-54 de disparar de novo. O C-71 (Bug C-71 22/07) tinha adicionado guarda equivalente só no C-31b (com DD/MM), não no C-54.

3. **Nenhum filtro detectava inbound "Atendente" / "Falar com atendente":** Filtro C-66 só pegava remarcação/cancelamento. Filtro C-47 bloqueava Lia de DIZER "atendente humano" no outbound — mas não detectava o PACIENTE pedindo atendente no inbound. Resultado: Juliana pediu atendente e Lia continuou normalmente.

**Fix em 3 arquivos:**

1. **`voice_agent/dedup_outbound.py`** — `TTL_JANELA_SEG: 300 → 1800` (30min). Loop de 39min agora cabe dentro de uma janela.

2. **`voice_agent/responder.py` (C-54 block)** — guarda C-84a: quando `_ultima_msg_outbound` contém "turno funciona melhor|manhã ou tarde" AND `user_text` contém "manhã|tarde" → suprime o fallback C-54 (deixa texto passar) em vez de criar loop infinito.

3. **`voice_agent/responder.py` (início de `_scrub_prohibited`)** — novo FILTRO C-84b SEMPRE-ON: detecta inbound do paciente pedindo atendente via regex (`\batendente\b`, `falar\s+com\s+(um\s+)?atendente`, `falar\s+com\s+pessoa`, etc.) → retorna mensagem canônica de handoff + grava flag Redis `blink:c84_pede_atendente:{lead_id}` (TTL 86400).

4. **`voice_agent/pipeline.py` (pós-responder, pré-envio)** — verifica flag `blink:c84_pede_atendente:{lead_id}`: se ativo, move lead pra 1-ATENDIMENTO HUMANO (106563343) + desativa IA + adiciona nota Kommo + limpa o flag.

**Pytest:** `tests/test_bug_c84_loop_escalar_atendente.py` — 126/126 verde (combinado).
**Push:** `PUSH_C84_LOOP_ESCALAR_ATENDENTE.command`

**Lição arquitetural CRÍTICA:**

- **TTL de dedup precisa ser ≥ duração esperada do loop.** `300s` (5min) era razoável pra loops rápidos (bug Ângela), mas não pra loops que duram 39min com paciente respondendo devagar. Regra: calibrar TTL pela duração do caso extremo real observado, não pelo caso feliz.
- **Guarda anti-loop precisa existir EM CADA FILTRO que retorna fallback repetível.** C-71 adicionou guarda no C-31b mas esqueceu o C-54 (mesma família de filtro, mesmo tipo de fallback). Regra permanente: ao adicionar guarda em um filtro X, verificar todos os filtros irmãos com o mesmo padrão de fallback.
- **Inbound do paciente pedindo atendente é sinal de emergência social** — não é informação para processar, é sinal para PARAR e escalar. Nenhum filtro existente pegava isso. C-84b resolve: qualquer "atendente"/"falar com humano" no inbound → handoff imediato, sem processar o turno.
- **"Vergonha" do agente = escalação proativa.** Fábio perguntou "porque o agente não tem vergonha?". Resposta arquitetural: o agente precisa detectar insatisfação acumulada (loop detectado + paciente pedindo humano) e escalar proativamente — sem esperar que a conversa quebre completamente.

### 0. (02/08/2026) Bug C-82 — Urgência priority detectada pelo C-81 mas NUNCA chegava ao LLM (3 conflitos arquiteturais)

**Origem:** auditoria arquitetural pós-C-81. O classificador C-81 detectava corretamente urgência "priority" (olho inchado, remela, vermelho) e injetava `urgency_level=priority` + `skip_convenio=True` em `ctx.known`. Porém o LLM continuava executando triagem normal de convênio — a detecção existia, o path não.

**3 conflitos simultâneos (todos bloqueantes):**

1. **`responder.py::_caller_context_block()` nunca lia `urgency_level`** — flags injetados pelo C-81 ficavam em `ctx.known` mas o system prompt montado para o LLM não tinha nenhum bloco de urgência. LLM recebia prompt normal de 120K chars sem nenhuma instrução de urgência.

2. **Checklist gate bloqueava oferta de encaixe** — `voice_agent/checklist_dados_minimos.py` exigia convênio definido antes de apresentar slots. Com `skip_convenio=True` no ctx, o gate deveria ser bypassado, mas não havia lógica para isso.

3. **FSM sem atalho TRIAGEM→AGENDA para urgência** — `inferir_estado_inicial()` ignorava `urgency_level`. Lead priority com slots disponíveis ainda começava em TRIAGEM, que proíbe oferta de slot. FSM vencia a instrução de urgência.

**Fix em 3 arquivos (commit C-82):**

1. **`voice_agent/responder.py::_caller_context_block()`** — novo bloco `urgency_block`: quando `known["urgency_level"] == "priority"`, injeta bloco `🚨 URGÊNCIA PRIORITÁRIA — MODO ENCAIXE IMEDIATO` com 5 regras (pula convênio, pula turno, oferta imediata, escala se sem slots, coleta dados depois).

2. **`voice_agent/responder.py` (checklist gate linha 614)** — adiciona condição `and not _skip_convenio_c82` ao gate: quando `known["skip_convenio"] = True`, bypassa coleta de convênio e vai direto para agenda.

3. **`voice_agent/fsm_conversa.py::inferir_estado_inicial()`** — novo atalho: `urgency_level == "priority"` AND `caller_context["agenda"]` populado → retorna `EstadoConversa.AGENDA` diretamente. Funciona tanto para leads novos (`found=False`) quanto existentes.

**Pytest:** `tests/test_bug_c82_urgency_llm_path.py` — 23/23 verde. 126/126 combinado (C-80 + C-81 + C-82).
**Push:** `PUSH_C82_URGENCY_LLM_PATH.command`

**Lição arquitetural CRÍTICA:**
- **Detectar ≠ agir.** C-81 detectava urgência e injetava flags. C-82 é a ponte entre detecção e ação. Sem C-82, a detecção era uma no-op. Padrão: sempre rastrear cada flag injetado em ctx até o lugar onde ele é CONSUMIDO. Se ninguém consome, a detecção não existe.
- **Auditoria de flags não consumidos deve ser tarefa recorrente.** Qualquer flag injetado em `ctx.known` que não tem grep em `responder.py` ou `fsm_conversa.py` é suspeito.
- **System prompt assembly é o ponto de integração.** A cola entre classificação (C-81) e comportamento LLM é o `_caller_context_block()`. Qualquer novo módulo que altera decisão de roteamento DEVE injetar bloco no system prompt via essa função.

### 0. (02/08/2026) Bug C-81 — Pipeline monolítico: Isabella teve olhos inchados + remelando e recebeu triagem de convênio em vez de encaixe urgente

**Origem:** lead 22335902 Isabella — "olho do meu filho está inchado e remelando desde ontem". Lia foi para triagem normal (convênio, dados) em vez de oferecer encaixe urgente imediatamente.

**Causa raiz — prompt de 120K chars para TUDO:** pipeline carregava `_MASTER_INSTRUCTION.md` completo para toda mensagem, sem distinguir urgência antes do LLM. Resultado: casos prioritários como conjuntivite/olho vermelho/remela esperavam o mesmo fluxo de um agendamento de rotina.

**Fix — `voice_agent/intent_classifier.py` (novo módulo, Zero custo API):**

1. **Classificação determinística por regex** ANTES do Medware lookup (pipeline.py ~linha 474):
   - `critical`: perda visão / trauma / bateu no olho / perfuração / descolamento → escala humano imediato + PS
   - `priority`: inchado / remela / vermelho / ardor / dor / conjuntivite / urgente → encaixe + skip_convenio
   - `routine`: fluxo normal

2. **Pré-extração de slots da 1ª mensagem** → injetado em `ctx.known` ANTES do Medware:
   - `unidade` ("Asa Norte" / "Águas Claras") — reduz 1 pergunta
   - `n_patients` ("2 filhos", "nós dois") — reduz 1 pergunta
   - `day_pref` ("segunda", "amanhã", "semana que vem") — reduz 1 pergunta
   - `turno` ("manhã" / "tarde") — reduz 1 pergunta
   - `medico` (Karla / Fabrício mencionado explicitamente) — reduz 1 pergunta
   **Efeito:** fluxo que precisava de 4-5 turnos de coleta cai para 0-2.

3. **Urgência CRÍTICA**: sem LLM, responde canônico ("emergência — vá ao PS + SAMU") + move para ATENDIMENTO HUMANO + nota Kommo.
4. **Urgência PRIORITÁRIA**: flag `urgency_level=priority` + `skip_convenio=True` injetados em ctx → Lia salta coleta de convênio e vai direto para encaixe.

**Toggle**: `INTENT_CLASSIFIER_ENABLED=0` desliga (default ON). **Fail-open**: se classificador falhar, pipeline continua normalmente.

**Pytest:** `tests/test_intent_classifier.py` — 70/70 verde. Suites chave C-80 + master regressão: 138/138.
**Push:** `PUSH_C81_INTENT_CLASSIFIER.command`

**Lição arquitetural CRÍTICA:**
- **Prompt monolítico 120K chars = cegueira para urgência.** Solução não é mais filtro reativo — é classificação upfront que altera o caminho antes do LLM.
- **Regex é mais confiável que LLM para detecção de urgência.** Zero custo, zero alucinação, zero latência. Haiku/Sonnet para urgência é pior — pode dizer "não é urgente" por contexto.
- **Pré-extração em toda 1ª mensagem.** "Quero consultar na Asa Norte segunda de manhã" já dá unidade + dia + turno. Perguntar de novo é fricção desnecessária.
- **Padrão estabelecido:** classificar → sub-caminho → prompt focado. Próximos candidatos: FAQ (valor/local/convênio) → resposta determinística sem Medware, cancelamento → C-68 direto.

### 0. (10/08/2026) Bug C-100 — /kommo Salesbot path não verificava agent_paused_for_lead (lead 24411978)

**Origem:** Fábio 10/08/2026. Lead 24411978 com status_id=106563343 (1-ATENDIMENTO HUMANO) E ATIVADO IA=Desativado. Lia continuava respondendo pelo canal Salesbot (/kommo) ignorando os dois bloqueios.

**Causa raiz:** Dois caminhos de webhook processam mensagens do paciente:
1. `/whatsapp` → `_process_whatsapp_cloud` → ✅ verifica `agent_paused_for_lead` corretamente
2. `/kommo` → `_process_kommo` → ❌ chamava `responder.reply()` DIRETAMENTE sem nenhuma verificação

Resultado: quando a mensagem chegava pelo Salesbot do Kommo, `agent_paused_for_lead` nunca era chamado. Lia respondia mesmo com lead em 1-ATENDIMENTO HUMANO e ATIVADO IA = Desativado.

**Fix em `voice_agent/webhook.py` — bloco C-100 em `_process_kommo`:**
- Após buscar `caller_context_by_lead`, verifica `agent_paused_for_lead`
- Se bloqueado: carimba DESATIVADO no Kommo + posta `agent_answer=""` no return_url (Salesbot não fica pendurado) + return early
- Fail-open: exceção em agent_paused → motivo=None → pipeline continua

**Pytest:** `tests/test_bug_c100_salesbot_agent_paused.py` — 16/16 verde.
**Push:** `PUSH_C100_SALESBOT_AGENT_PAUSED.command`

**Lição arquitetural CRÍTICA:**
- **Qualquer caminho que chama `responder.reply()` DEVE verificar `agent_paused_for_lead` antes.** O check não existe apenas no pipeline.run() — existe também em cada webhook handler. Quando foi adicionado em `_process_whatsapp_cloud`, não foi espelhado em `_process_kommo`.
- **Regra permanente: ao adicionar verificação de segurança em UM caminho de entrada, auditar TODOS os outros caminhos** (whatsapp, kommo, evolution, admin, replay) para garantir que têm a mesma proteção.
- **Testes de integração por caminho.** Cada endpoint de webhook precisa de pytest próprio que cubra: paused=True → silencia, paused=None → responde. Sem isso, caminhos secundários ficam descobertos.

### 0. (08/08/2026) Bug C-98 — FSM Redis CONVENIO bloqueava oferta determinística mesmo com checklist completo + slots

**Origem:** lead 24430558 Edivá + padrão recorrente em múltiplos leads. Paciente envia último dado necessário (ex: "asa norte"). C-81 injeta `unidade` em `ctx.known`. Checklist vira `pronto_para_oferecer_slot=True`. Medware retorna slots. MAS `deve_ofertar_agora()` exige `fsm.estado==AGENDA` — e o FSM Redis snapshot do turno ANTERIOR ainda é `CONVENIO`. Resultado: `deve_ofertar_agora()` retorna `False` → LLM chamado → stall "Vou verificar os horários disponíveis...".

**Causa raiz arquitetural:** `inferir_estado_inicial()` só roda quando `_snap is None` (sem Redis). Com snapshot existente do turno anterior (CONVENIO), `deve_ofertar_agora()` nunca via AGENDA naquele turno mesmo que o checklist tivesse acabado de ficar completo.

**Fix — bloco C-98 em `pipeline.py`** (dentro de `if _snap and caller_context is not None:`, após metrics):
```python
_fsm_estado_c98 = (caller_context.get("fsm") or {}).get("estado", "")
_chk_c98 = caller_context.get("checklist_dados_minimos") or {}
if (
    _fsm_estado_c98 in {"TRIAGEM", "DADOS", "CONVENIO"}
    and _chk_c98.get("pronto_para_oferecer_slot")
    and caller_context.get("agenda")
    and not caller_context.get("ja_agendado")
):
    _snap_c98, _ok_c98 = _fsm_mgr.transicionar(conversation_key, EstadoConversa.AGENDA, motivo="C-98 auto-advance")
    if _ok_c98:
        caller_context["fsm"]["estado"] = _snap_c98.estado.value
```

**Pytest:** `tests/test_bug_c98_fsm_advance_agenda.py` — 17/17 verde. Cobre: CONVENIO→AGENDA, DADOS→AGENDA, TRIAGEM→AGENDA, guard checklist pendente, guard agenda vazia, guard ja_agendado, idempotência AGENDA→AGENDA, proteção CONFIRMACAO/GRAVACAO/POS_GRAVACAO, integração com `deve_ofertar_agora()`.
**Push:** `PUSH_C98_FSM_ADVANCE_AGENDA.command`

**Lição arquitetural CRÍTICA:**
- **FSM Redis snapshot do turno anterior é o único estado vivo.** `inferir_estado_inicial()` é no-op quando snapshot existe. O problema não é a inferência — é que nenhum código atualizava o snapshot no mesmo turno em que o checklist ficava completo.
- **"O Medware precisa ser chamado antes do LLM, não dentro da resposta do LLM."** C-98 é a ponte: garante que quando Medware retornou slots E checklist está completo, FSM avança pra AGENDA no mesmo turno, permitindo que `deve_ofertar_agora()` retorne True sem precisar de um turno extra.
- **Regra permanente:** qualquer dado novo injetado em `ctx.known` que possa completar o checklist (unidade, médico, convênio via C-81) deve ser seguido de verificação se FSM precisa avançar. C-98 generaliza esse trigger pra todos os 3 estados pré-AGENDA.

### 0. (01/08/2026) Bug C-78 — FAQ "está atendendo hoje?" causou loop stall via sábado sem agenda (lead 23456132)

**Origem:** lead 23456132 João (8-REALIZADO CONSULTA), sábado 02/08/2026. Paciente perguntou "A Dra Karla está atendendo hj?". Pipeline foi ao Medware → retornou vazio (sábado = sem atendimento) → `ctx.agenda=[]` → filtro C-30 pulado (`has_agenda=False`) → filtro C-30A disparou "Medware instável" (ERRADO — Medware estava UP, o problema era o calendário) → LLM entrou em loop stall 3x: "reconferir os horários exatos com a agenda do Medware pra te passar as opções corretas".

**Bug C-78b simultâneo:** regex linha 813 do `_FAKE_AGENDA_LOOKUP` só pegava `correto` (singular masculino) — não pegava `corretas` (plural feminino) nem `Medware` como âncora.

**Fix em 2 camadas (`blindagens_deterministicas.py` + `responder.py`):**

1. **`deve_responder_faq_disponibilidade_hoje(ctx, user_text)`** — intercept ANTES de Medware:
   - Regex `_FAQ_DISP_HOJE`: detecta "está atendendo hj/hoje", "tem horário hoje", "atende sábado/domingo", etc.
   - Consulta escala real dos médicos (frozensets por dia da semana PT-BR):
     - Karla Asa Norte: seg/qua/sex (weekday 0/2/4)
     - Karla Águas Claras: ter/qui (weekday 1/3)
     - Fabrício: ter/qui (weekday 1/3)
   - `_proxima_data_no_plano(hoje, dias_plano)`: itera até próxima data disponível
   - Se atende hoje → "Sim! Hoje é [dia] — [médico] tem atendimento em [unidade]..."
   - Se não atende hoje → "Hoje é [dia] — não tem atendimento. Próxima data: [dia/dd/mm]"
   - Karla sem unidade definida → mostra AMBAS as próximas datas
   - Médico desconhecido → `None` (fail-open, LLM continua)
   - Toggle: `BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO` (default ON)
   - Plugado em `tentar_bypass_deterministico()` ANTES de `faq_especialidade`

2. **`responder.py` linha 813 stall regex:**
   - `correto` → `correto[sa]?` (cobre "corretos" e "corretas")
   - Adicionado padrão `reconferir.{0,30}(?:horários|calendário|agenda)\s+do\s+medware`

**Pytest:** `test_bug_c78_faq_disponibilidade_hoje.py` — 39/39 verde. Push: `PUSH_C78_FAQ_DISPONIBILIDADE.command`.

**Lição arquitetural CRÍTICA:**
- **Quando Medware retorna vazio por calendário, C-30 fica cego (gate `has_agenda=False`).** A defesa certa é interceptar ANTES de consultar Medware — não tentar corrigir o que C-30/C-30A fazem com contexto vazio.
- **C-30A "Medware instável" é mentira quando a razão real é "sábado sem atendimento".** Mensagem errada = paciente confuso + confiança perdida. FAQ bypass evita ambos.
- **Stall regex com âncora singular falha em PT-BR** onde adjetivos concordam em gênero e número. Sempre usar `[oa]?s?` ou equivalente nas âncoras de stall.
- **`tentar_bypass_deterministico()` é o lugar certo pra FAQs de calendário.** Padrão estabelecido com C-74 (especialidade) e agora C-78 (disponibilidade). Próximos candidatos: endereço da clínica, formas de pagamento, horário de atendimento.

### 0. (30/07/2026) Bug C-77 — CTX-GUARD token ratio errado: // 4 nunca disparava (lead 24381272)

**Origem:** lead 24381272 Jose Victor (bebê 1 mês, Oftalmopediatria, Karla Asa Norte, particular). C-56 disparou na PRIMEIRA mensagem ("Bom dia") — lead criado há 23 segundos, zero histórico Zep, zero notas Kommo. C-76d + C-76e deveriam ter evitado, mas não evitaram.

**Causa raiz — divisor `// 4` sistematicamente errado para PT-BR:**
- `_MASTER_INSTRUCTION.md` = 120.271 chars
- Com `// 4`: estimativa = 30.068 tokens (ERRADO)
- Real tokens PT-BR + emojis + JSON: ~60-80K tokens (ratio ~1.5-2 chars/token)
- Threshold de 160K tokens = precisaria de 640K chars para disparar → NUNCA acionava
- System prompt sozinho (~60-80K tokens reais) já come 30-40% da janela de 200K antes de qualquer histórico

**Fix (`voice_agent/responder.py` linhas 4577-4583):**
```python
# ANTES (nunca disparava):
_ctx_tokens_est = (_sys_chars + _chars_msgs(messages)) // 4
_CTX_WARN_TOKENS = 160_000
_CTX_CRIT_TOKENS = 170_000

# DEPOIS (corrigido Bug C-77):
_ctx_tokens_est = (_sys_chars + _chars_msgs(messages)) // 2
_CTX_WARN_TOKENS = 80_000
_CTX_CRIT_TOKENS = 90_000
```

**Push:** `PUSH_C77_CTX_GUARD_TOKEN_RATIO.command`

**Lead 24381272 reativado:** ATIVADO IA = "Ativado" (confirmado GET, enum_id 927031). Nota: campo 1.DIA CONSULTA = ~10/08/2026 já preenchido — lead pode estar em ja_agendado, verificar antes de responder ao paciente.

**Lição arquitetural CRÍTICA:**
- **`// N` em estimativa de tokens depende do idioma.** EN: ~4 chars/token. PT-BR com emojis, JSON e caracteres especiais: ~1.5-2 chars/token. Assumir 4 foi erro de calibração.
- **Threshold deve refletir janela real do modelo menos margem.** claude-sonnet-4-5 tem 200K tokens. System prompt real ~60-80K. Margem adequada = threshold em 80K tokens estimados (conservador com `// 2`), não 160K.
- **CTX-GUARD que NUNCA dispara = não existe.** O guard existia no código mas era ineficaz. Validar sempre: "qual é o pior caso que faz o guard disparar?" Se a resposta é "640K chars de texto" para um sistema com prompt de 120K chars, o guard está errado.
- **Regra permanente:** todo estimador de tokens em código deve ser calibrado contra o idioma real. Logar `total_tokens_est` em PROD e comparar com tokens reais via tracing sempre que C-56 disparar.

### 0. (30/07/2026) Bug C-76e — Anti-loop C-56: flag Redis permanente bloqueia reativação automática (lead 23327112 Cecília)

**Origem:** lead 23327112 Cecília Pacheco de Souza (Oftalmopediatria, Karla Asa Norte, Sem Convênio, consulta 31/07). C-56 disparou 3x (28/07 ×2, 30/07 ×1) por BadRequestError 400 context overflow. A cada disparo: C-56 desativa IA + move lead pra ATENDIMENTO HUMANO → trigger `kommo-trigger-status-change` detecta mudança de etapa → **reativa IA automaticamente** → próxima mensagem causa overflow → C-56 → loop infinito. Paciente ficou sem resposta às perguntas "Bom dia", "Mas já está marcado, correto?" e "O valor da consulta é essa mesmo?".

**Causa raiz — ciclo perfeito de reativação automática:** o trigger `kommo-trigger-status-change` (Bug C-24a, reativa IA ao mover lead entre etapas ativas) foi desenhado pra recuperar leads de ATENDIMENTO HUMANO. Mas se o C-56 está movendo pra ATENDIMENTO HUMANO POR causa de overflow, e a raiz (overflow) não foi resolvida, a reativação automática apenas reinicia o ciclo imediatamente.

**Fix em 2 camadas (`webhook.py`, commit `daae81a..366d1e8`):**

1. **Quando C-56 dispara** (bloco `_fallback_instabilidade_pipeline` que move o lead e desativa IA): grava flag Redis:
   ```python
   redis_client.setex(f"blink:c56:{lead_id}", 30 * 24 * 3600, "1")  # TTL 30 dias
   ```

2. **`kommo-trigger-status-change` verifica o flag antes de reativar:**
   ```python
   flag = redis_client.get(f"blink:c56:{lead_id}")
   if flag:
       return {"acao": "bloqueado_c56", "motivo": "lead teve C-56 recente — reativar manualmente via /admin/reativar-lead/{id}"}
   ```

3. **Novo endpoint `/admin/reativar-lead/{lead_id}`** (GET ou POST + secret):
   - Limpa `blink:c56:{lead_id}` no Redis
   - Chama `kommo_client.update_lead_fields(lead_id, {"ativado_ia": "Ativado"})`
   - Retorna `{ok, flag_c56_removido, acao: "ia_reativada_manual"}`
   - Usar SOMENTE após confirmar que a causa raiz do overflow foi resolvida (ex: C-76d ativo)

**Resultado para Cecília 23327112:** GET para `/admin/reativar-lead/23327112?secret=...` executado pós-deploy. ATIVADO IA voltou para "Ativado" (confirmado via `kommo_get_lead` field_id 1260817). Consulta hoje 31/07 às 10:00. Nota de alerta humano gravada (note_id 29112894) pedindo resposta à pergunta de valor.

**Resposta às 2 questões pendentes de Fábio:**
- **"Este deploy resolve o caso específico?"** → SIM: Cecília 23327112 está com IA reativada, C-76d + C-76e protegem futuras mensagens dela.
- **"Resolve os outros casos posteriores?"** → SIM: qualquer lead que acionar C-56 no futuro vai ter flag Redis por 30 dias, bloqueando o loop. Manual reactivation via endpoint garante que humano revisa antes de reativar. C-76d (context guard) previne o overflow desde a raiz — C-76e é a rede de segurança se o overflow acontecer mesmo assim.

**Lição arquitetural CRÍTICA:**
- **Automação de recuperação pode criar loops perversos.** C-24a (reativa IA ao mudar etapa) + C-56 (move pra ATENDIMENTO HUMANO quando falha) são dois mecanismos corretos individualmente que em combinação criaram loop infinito.
- **Regra permanente: qualquer automação de reativação deve verificar se a CAUSA DA DESATIVAÇÃO foi resolvida.** Flag Redis com TTL 30d é o mecanismo canônico: C-56 grava o flag → trigger lê o flag → bloqueia → humano confirma resolução → chama endpoint de reativação manual.
- **Para reativar qualquer lead com C-56 histórico:** `curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/reativar-lead/{LEAD_ID}?secret=blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a"`. Só chamar após confirmar C-76d ativo em prod.

### 0. (29/07/2026) Bug C-76d — Context Guard + Zep limit=20 (lead 24374118 novo lead ainda overflow após C-76c)

**Origem:** após fixes C-76 (limit=15 notas) e C-76c (chat msgs limit=15), lead 24374118 (novo, primeira mensagem, chatId=null, zero notas Kommo) AINDA causava `BadRequestError 400 'maximum context length'`. Paradoxo: lead novo não deveria ter histórico suficiente para overflow.

**Causa raiz — `zep_adapter.recuperar_contexto()` sem limite:** função retornava TODOS os mensagens do Zep para o `session_id` (= `conversation_key` = derivado do número do telefone). Se o número de telefone foi usado em sessões anteriores (paciente retornando, lead duplicado, teste), o Zep tem o histórico completo de TODAS as sessões. 80-500 mensagens de histórico Zep = 24K-150K chars extras = 6K-37K tokens de surpresa.

**Fix em 2 camadas (`zep_adapter.py` + `responder.py`):**

1. **`zep_adapter.py::recuperar_contexto(limit=20)`** — hard cap: `msgs = msgs[-limit:]`. Se Zep retornar 500 msgs, só os últimas 20 passam. Loga WARNING quando trunca.

2. **`responder.py` CTX-GUARD** (após assembly de messages, antes do loop API):
   - Estima total de tokens: `(_sys_chars + _chars_msgs) // 4`
   - Loga SEMPRE: `[CTX-GUARD] system_chars=... msgs=... total_tokens_est=...` → diagnóstico permanente
   - Nível 1 (>160K tokens): trunca Zep para últimas 10 msgs, reconstrói messages
   - Nível 2 (>170K tokens): trunca Redis history para últimas 12 msgs, reconstrói
   - Modelo `claude-sonnet-4-5` tem 200K janela; thresholds dão margem de ~30-40K

**Pytest:** `test_bug_c76d_context_guard.py` — 24/24 verde. Push: `PUSH_C76D_CONTEXT_GUARD.command`.

**Lição arquitetural CRÍTICA:**
- **`conversation_key` é derivado do TELEFONE, não do lead_id.** Um número de telefone que apareceu em múltiplos leads ou sessões de teste acumula histórico Zep ilimitado sob a mesma session_id. Lead "novo" no Kommo pode ser um número ANTIGO no Zep.
- **Toda fonte de histórico injetada em messages[] precisa de limite explícito:** Zep (fix C-76d), notas (fix C-76), chat msgs (fix C-76c), Redis history (store.py max_turns=12 via append). O Redis é o único que já tinha cap por design; os outros precisaram de fix.
- **CTX-GUARD com logging sempre-on é diagnóstico de baixo custo.** `[CTX-GUARD] total_tokens_est=42000` em todo lead — custo zero, revela imediatamente quando o contexto está crescendo perigosamente antes de estourar.
- **Regra permanente:** qualquer `for m in lista_externa_sem_limite` que injeta em messages[] = bomba-relógio. Sempre passar `limit` explícito ou aplicar `[-N:]` no resultado.

### 0. (29/07/2026) Bug C-76 — Overflow contexto Claude API em leads com histórico longo (lead 24259380 Fábio Philipe)

**Origem:** lead 24259380 ativo desde 06/07/2026 (~3 semanas, 5 conversas A40337/A40624/A40697/A41822/A42547). Ao responder "Oi" em 29/07, pipeline gerou `BadRequestError 400 'You have reached the maximum context length'` → circuit breaker C-56 moveu lead pra ATENDIMENTO HUMANO.

**Causa raiz:** `get_caller_context_by_lead` (kommo.py linha 2201) chamava `get_lead_notes(lead_id)` sem limite → carregava todas as notas (default 50) sem truncar. Leads com semanas de histórico acumulam dezenas de notas longas → overflow da janela de contexto Claude API.

**Fix em 2 camadas (`kommo.py` commit 68a4114):**

1. **Linha 2201** — `get_lead_notes(lead_id, limit=15)` — limita a 15 notas mais recentes (suficiente para camadas 3-5 de ja_agendado + bloco CONVERSA_ATUAL).
2. **Linha 2378** — antes de atribuir `notas_historico`, trunca `text` de cada nota a 500 chars: `nota_copy["text"] = txt[:497] + "…"`.

**Push:** `PUSH_C76_LIMIT_NOTAS_CONTEXT_OVERFLOW.command`

**Lição arquitetural CRÍTICA:**
- **Leads de longa duração acumulam contexto ilimitado** — qualquer lista sem `limit` vira bomba-relógio em leads com semanas de histórico.
- **`get_lead_notes` já aceitava `limit` (default 50)** — bastava passar `limit=15`. Bug era de omissão, não de arquitetura.
- **Notas individuais longas são tão perigosas quanto quantidade** — nota de auditoria ou handoff pode ter 2000+ chars. Truncar a 500 é suficiente para contexto sem explodir o token budget.
- **Regra permanente:** toda chamada que injeta lista no contexto Claude (notas, mensagens, histórico) DEVE ter limite explícito + truncagem de texto. Nunca confiar no default.

### 0. (21/07/2026) Bug C-64 — Loop circular: fallbacks C-31/C-54 contêm frases stall que C-60 deveria bloquear

**Origem:** lead 24330790 Lauanne recebeu às 19:03 BRT a frase "Deixa eu reconferir os horários com o calendário aqui. Qual dia da semana..." — um stall clássico do C-60.

**Causa raiz — 2 problemas simultâneos:**

1. **`_DIA_SEMANA_FALLBACK`, `_DIA_NAO_ATENDIDO_FALLBACK`, `_DIA_SEM_DATA_FALLBACK`** em `responder.py` começavam com "Deixa eu reconferir/conferir..." — as próprias frases que C-60 deveria bloquear. Quando filtro C-31/C-54 acionava → gerava stall → C-60 deveria pegar mas não pegava → paciente recebia loop.

2. **Regex C-60 com `.{0,25}` era estreito demais.** A frase "reconferir os horários com o calendário aqui. Qual dia da semana" tem gap de ~40 chars entre "reconferir" e "dia da semana" — regex `.{0,25}` não casava.

**Fix (commit e2885d0, 21/07/2026):**

1. **`_DIA_SEMANA_FALLBACK`** → `"Qual dia da semana e turno funcionam melhor pra você? Assim confirmo a data e o horário exatos na unidade certa."`
2. **`_DIA_NAO_ATENDIDO_FALLBACK`** → `"Qual turno funciona melhor pra você — manhã ou tarde? Com isso confirmo o horário disponível."`
3. **`_DIA_SEM_DATA_FALLBACK`** → `"A Dra. Karla Delalíbera atende seg/qua/sex em Asa Norte e ter/qui em Águas Claras. Qual dia funciona melhor pra você?"`
4. **Regex C-60 expandido de `.{0,25}` para `.{0,60}`** — cobre gaps maiores.
5. **Padrão novo:** `re.compile(r"(?:reconferir).{0,30}(?:horários|calendário|agenda).{0,30}(?:aqui|correto)", ...)`

**Pytest:** `test_bug_c64_circular_fallback.py` — 12/12 verde. Valida que nenhum fallback contém stall phrase E que C-60 pega frases com gap >25 chars.

**Lição arquitetural CRÍTICA:**
- **Fallbacks de filtros de defesa NÃO podem conter as frases que esses filtros bloqueiam.** Loop circular é inevitável se o "texto de substituição seguro" contém o padrão que desencadeou a substituição.
- **Antes de escrever qualquer fallback/substituto, validar manualmente que NÃO aciona nenhum outro filtro.** Simples checklist: rodar `_has_stall(fallback_text)` antes de commitar.
- **Regex com `{0,N}` curto (N<30) falha em frases com subordinadas.** Sempre usar N≥60 pra capturar frases com cláusulas intermediárias.

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

- **Asa Norte**: `28.655.944/0001-16` (CNPJ)
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
