# Intent Inventory — Blink Oftalmologia
**Data:** 05/08/2026 | **Fonte:** Amostra real Kommo (leads 24413976, 24413852, 24381272 + 60 dias histórico bugs)  
**Método:** Utterance Collection + Deterministic Response Mapping  
**Cobertura estimada:** 125 variações, 20 intents

---

## DIAGNÓSTICO EXECUTIVO

### Por que os fixes individuais são tampões?

| Abordagem | Cobertura | Velocidade | Custo p/ novo padrão |
|---|---|---|---|
| **Fix individual (C-86, C-84…)** | 60-70% | Rápido | 1 sessão + pytest |
| **Intent Inventory (este doc)** | 90-95% | Mais lento p/ implementar | Zero — padrão novo = 1 linha de regex |

**Causa raiz arquitetural:** o LLM recebe 120K tokens de contexto e toma decisões livres. Para 80% dos turnos, a resposta correta é determinística — uma das 20 intents abaixo tem uma resposta única e correta que nunca muda. O LLM não precisa "pensar" nisso.

### Precedente estabelecido
O procedimento se chama **Utterance Collection + Deterministic Response Mapping** (ou "Intent-Based Hardcoding"). É a mesma abordagem usada em IVRs (URA), chatbots de atendimento e regras de triagem clínica. Os filtros C-30, C-31, C-78, C-84 e C-86 já são a execução fragmentada desse processo. Este documento centraliza e completa.

---

## MAPA COMPLETO DE INTENTS

### 🟢 JÁ TEM BYPASS DETERMINÍSTICO

| ID | Intent | Variações observadas | Bypass ativo |
|---|---|---|---|
| 10_VALOR | Perguntar valor/preço | "Valores", "quanto custa?", "preços", "pix", "custo", "cartão?" | C-86b (FAQ) + C-86c (pré-slot) |
| 16_URGENCIA | Urgência clínica | "olho inchado", "dor", "perdeu visão", "bateu" | C-81 (intent_classifier) |
| 14_ATENDENTE | Pedir atendente humano | "Falar com atendente", "quero falar com pessoa" | C-84b |
| 13_DISPONIBILIDADE | Disponibilidade hoje/sábado | "sábado vcs atendem?", "está atendendo hj?" | C-78 |
| 02_CONVENIO_QUERY | Convênio não aceito | "aceitam Bradesco?", "atendem GDF?" | C-22, C-16 |
| 17_CANCELAR | Cancelar/remarcar | "preciso cancelar", "quero remarcar" | C-66/C-68 |

---

### 🔴 CRÍTICO — SEM BYPASS, CAUSA BUGS CONFIRMADOS EM PROD

#### 11_ENDERECO — Endereço / localização

**Variações reais:**
- "Vcs ficam no felicita?" → Loop C-54 ignorou, Lia continuou pedindo turno
- "qual o endereço?"
- "onde fica a clínica?"
- "tem estacionamento?"

**Resposta canônica Águas Claras:**
> "Sim! Águas Claras fica no Felicittá Shopping — R. 36 Norte, 05 - Bloco 11, Loja 48, 1º Andar 📍 https://maps.app.goo.gl/FRbkUtg4U4xG55q18"

**Resposta canônica Asa Norte:**
> "Asa Norte fica na SHIN QI 5 Bloco J Loja 22, Lago Norte, próximo à Asa Norte 📍 https://maps.app.goo.gl/jPfjSsXA1bHhsyw56"

**Resposta canônica sem unidade definida:**
> "Temos 2 unidades:\n🏥 Asa Norte — SHIN QI 5 Bloco J Loja 22\n🏥 Águas Claras — Felicittá Shopping\nQual fica mais perto de você?"

**Impacto:** Lead 24413852 (Juliana) — "Vcs ficam no felicita?" foi RESPONDIDA CORRETAMENTE por coincidência, mas como texto livre do LLM. Se o LLM não soubesse, entraria em loop. Bypass garante resposta instantânea, constrói confiança, reduz fricção.

**Implementar em:** `blindagens_deterministicas.py::tentar_bypass_deterministico()` ANTES do FAQ valor

---

#### 18_ACEITA_SLOT — Seleção de slot ofertado

**Variações reais:**
- "1" → quando Lia ofertou "1️⃣ quarta 05/08 às 11:30 / 2️⃣ sexta 07/08 às 11:00"
- "2"
- "O primeiro"
- "o de quarta"
- "Quero o 1"
- "esse horário"

**Bug CONFIRMADO em prod:** Lead 24413976 — Lia ofertou 2 slots às 20:57. Paciente respondeu "Valores" → Lia ignorou VALOR e respondeu perguntando turno. Na 3ª mensagem "Quero saber valores", C-56 disparou. Se tivesse selecionado "1" ou "2", provavelmente o LLM teria entrado em FSM de confirmação normalmente.

**O risco real:** paciente responde "2" e o LLM não reconhece como seleção de slot — trata como input de convênio, nome ou qualquer outra coisa no contexto.

**Regra determinística:**
```
SE (última msg Lia continha "1️⃣" e "2️⃣") E (inbound é "1", "2", "1️⃣", "2️⃣", "O primeiro", "O segundo", "quero o 1")
→ mapear p/ slot 1 ou slot 2 → avançar para confirmação
```

**Implementar em:** `pipeline.py` logo após receber inbound, antes de qualquer processamento LLM

---

#### 06_CONFIRMACAO_VAGA — Confirmações ambíguas

**Variações reais (confirmadas em 2 leads):**
- "Isso" → Juliana respondeu "Isso" quando Lia perguntou se era com convênio — causou loop
- "Sim" → confirmação de data de nascimento
- "Ok" → múltiplos contextos
- "Pode ser"

**O problema:** "Isso" e "Sim" são respostas válidas para QUALQUER pergunta de sim/não. O LLM precisa inferir o contexto, mas com 120K tokens o contexto se perde.

**Regra determinística simples:**
```
SE (última pergunta Lia era SIM/NÃO) E (inbound ∈ {"isso", "sim", "ok", "pode ser", "tá bom", "correto", "exato"})
→ interpretar como confirmação positiva da última pergunta
```

**Implementar em:** `responder.py` novo helper `_eh_confirmacao_positiva(text, ultima_pergunta)`

---

### 🟡 IMPORTANTE — SEM BYPASS, AFETA CONVERSÃO

#### 12_HORARIO — Preferência de horário / turno

**Variações reais (confirmadas em bugs C-84, C-64):**
- "Manhã" → Loop C-54 ignorou 11 vezes (Bug C-84)
- "Segunda ou quarta de manhã / Manhã" → Lia perguntou de novo
- "O ideal seria segunda de manhã ou quinta à tarde" → Lia deu slots de terça (dia errado)
- "Não tenho definido o turno / Depende do dia" → Lia ficou em loop

**Bug CONFIRMADO:** Lead 24413852 (Juliana) — paciente disse "Segunda ou quarta de manhã" → Lia respondeu "Qual turno funciona melhor pra você — manhã ou tarde?" (pergunta JÁ RESPONDIDA). Loop 11 vezes.

**Regra determinística:**
```
SE (ctx.fsm == AGENDA) E (inbound extrai turno=manhã ou tarde E dia=X)
→ chamar tool oferecer_slot(turno=X, dia=Y) DIRETAMENTE
→ NÃO reperguntar turno que já foi respondido
```

**Implementar em:** `responder.py` na função que monta o context block antes do LLM — injetar turno e dia extraídos como `known.turno` e `known.dia_pref` para impedir nova pergunta

---

#### 04_PARA_TERCEIRO — Agendamento para outra pessoa

**Variações reais:**
- "Outra pessoa" → Lia tratou corretamente nesse caso
- "É meu filho / Gabriel Almrifa Sousa" → Lia captou nome do filho mas escreveu "Gabriel Almeida" (errou sobrenome!)
- "É minha filha"

**O problema:** quando paciente manda nome junto com "é meu filho", LLM transcreve errado o nome (bug visto: "Gabriel Almrifa" → "Gabriel Almeida"). Determinístico extrai a substring após "/" como nome bruto, NÃO alucinado.

---

#### 19_DUVIDA_CLINICA — Dúvidas clínicas frequentes

**Variações previstas (padrão dos bugs históricos):**
- "o exame dilata a pupila?" → FAQ frequente que LLM tende a inventar resposta técnica
- "quanto tempo dura a consulta?" → Lia inventava "60-90 minutos" (real: 30min Karla, 40min Fabrício — Bug C-28)
- "pode levar o bebê?"
- "precisa de encaminhamento?"

**Respostas canônicas (definidas no KB):**
- Duração: Karla 30 min | Fabrício 40 min
- Dilatação: "Sim, o exame pode dilatar a pupila. A visão fica embaçada por algumas horas — traga um acompanhante se possível."
- Bebê: "Claro! Atendemos crianças de todas as idades, inclusive recém-nascidos."

---

### ⚪ MANTER LLM — MUITO CONTEXTUAL

| ID | Intent | Por quê LLM |
|---|---|---|
| 05_NOME | Nome do paciente | Extração NER — LLM é melhor |
| 07_DATA_NASC | Data de nascimento | Parsing de formato variado — usar regex + LLM fallback |
| 08_MOTIVO | Motivo da consulta | Classificação clínica — LLM c/ regex regex de urgência como guard |
| 09_UNIDADE | Unidade de preferência | Simples mas contextual (pode ser implícito no endereço) |
| 20_INFO_EXTRA | Informações espontâneas | Muito variado |

---

## PLANO DE IMPLEMENTAÇÃO — PRIORIDADE

### P0 — Resolve bugs ativos (esta semana)

| # | Bypass | Arquivo | Tempo est. |
|---|---|---|---|
| 1 | **11_ENDERECO** — endereço/localização determinístico | `blindagens_deterministicas.py` | 2h |
| 2 | **Turno já respondido** — guard anti-loop FSM | `responder.py` (injetar no context block) | 1h |
| 3 | **06_CONFIRMACAO** — mapear "Isso"/"Sim" à última pergunta | `responder.py` novo helper | 2h |

### P1 — Alta conversão (próxima sessão)

| # | Bypass | Arquivo | Tempo est. |
|---|---|---|---|
| 4 | **18_ACEITA_SLOT** — "1"/"2" após oferta de slot | `pipeline.py` pre-LLM | 3h |
| 5 | **19_DUVIDA_CLINICA** — FAQ clínica (duração, dilatação, bebê) | `blindagens_deterministicas.py` | 2h |

### P2 — Qualidade (futura)

| # | Bypass |
|---|---|
| 6 | Extração regex de nome quando paciente manda "É meu filho / [NOME]" |
| 7 | Extração regex de data de nascimento de qualquer formato |

---

## EXEMPLO CONCRETO: O QUE MUDA PARA A JULIANA (24413852)

**Conversa real — com LLM hoje (39 min de loop):**
```
Lia: "Qual turno funciona melhor pra você — manhã ou tarde?"
Juliana: "Segunda ou quarta de manhã"
Lia: "Qual turno funciona melhor pra você — manhã ou tarde?"  ← LOOP
Juliana: "Manhã"
Lia: "Qual turno funciona melhor pra você — manhã ou tarde?"  ← LOOP
...11 vezes...
Juliana: "Desisto"
```

**Conversa com Intent Inventory (turno já respondido — guard):**
```
Lia: "Qual turno funciona melhor pra você — manhã ou tarde?"
Juliana: "Segunda ou quarta de manhã"
[GUARD: turno=manhã extraído, dia=segunda/quarta — injeta no ctx]
Lia: "Tenho estes horários de manhã com a Dra. Karla em Águas Claras:
  1️⃣ Segunda-feira 10/08 às 09:30
  2️⃣ Quarta-feira 12/08 às 09:00
  Qual funciona?"
Juliana: "O 1"
[GUARD: 18_ACEITA_SLOT — confirma slot 1]
Lia: "Ótimo! Segunda 10/08 às 09:30 com a Dra. Karla..."
```

**Resultado esperado:** conversa de 3 turnos em vez de 39 minutos. Agendamento concluído.

---

## ARQUITETURA FINAL (quando todos implementados)

```
INBOUND PACIENTE
     │
     ▼
[C-81 URGÊNCIA critical] ──→ Resposta PS + escalação humana
     │
     ▼
[C-81 URGÊNCIA priority] ──→ Encaixe imediato + skip convênio  
     │
     ▼
[C-84b ATENDENTE] ──────────→ Handoff + ATENDIMENTO HUMANO
     │
     ▼
[11 ENDEREÇO] ──────────────→ Endereço canônico (NOVO P0)
     │
     ▼
[10 VALOR] ─────────────────→ Tabela preço canônica (C-86b)
     │
     ▼
[13 DISPONIBILIDADE] ───────→ Calendário determinístico (C-78)
     │
     ▼
[18 ACEITA SLOT] ───────────→ Confirmar slot selecionado (NOVO P1)
     │
     ▼
[06 CONFIRMAÇÃO VAGA] ──────→ Resolver contra última pergunta (NOVO P0)
     │
     ▼
[GUARD: turno já respondido]→ Injetar turno no ctx, não reperguntar (NOVO P0)
     │
     ▼
[C-22 CONVÊNIO N.ACEITO] ───→ Script não credenciado canônico
     │
     ▼
[C-66/C-68 CANCELAR] ───────→ Fluxo reagendamento
     │
     ▼
[19 FAQ CLÍNICA] ───────────→ Resposta canônica (NOVO P1)
     │
     ▼
[LLM Claude Sonnet/Opus] ───→ Contexto complexo, coleta dados, FSM
     │
     ▼
[C-86c SLOT SEM VALOR] ─────→ Injetar preço antes de slot (C-86c)
     │
     ▼
[C-30/C-31 GUARDS] ─────────→ Stall, dia errado, hesitação
     │
     ▼
ENVIO WHATSAPP
```

**Com esta arquitetura: ~90% dos turnos têm resposta determinística ou guardada por bypass. O LLM age apenas em contextos complexos onde realmente agrega valor.**

---

## NÚMEROS ESPERADOS (estimativa conservadora)

| Métrica | Hoje | Com Intent Inventory |
|---|---|---|
| Turnos com resposta determinística | 30-40% | 85-90% |
| Taxa de loop detectado | ~15% dos leads | <2% |
| Leads que desistem por loop | 5-8/semana | 0-1/semana |
| Tempo médio até oferta de slot | 8-12 turnos | 3-5 turnos |
| Conversão estimada | baseline | +20-30% |
