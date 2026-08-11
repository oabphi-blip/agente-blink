# Respostas Canônicas da Lia — Documento para Revisão
**Data:** 05/08/2026 | **Status:** Aguardando aprovação do Fábio antes de implementar  
**Objetivo:** Eliminar texto livre do LLM para as situações mais comuns. Cada texto abaixo será hard-coded — a Lia envia EXATAMENTE isso, sem variação.

---

## Como usar este documento

- Fábio lê cada situação
- Ajusta o texto se necessário (edita aqui mesmo)
- Sinaliza ✅ OK ou ❌ Alterar
- Claude implementa em lote depois da aprovação

---

## SITUAÇÕES JÁ IMPLEMENTADAS — Confirmar se textos estão corretos

---

### ✅ S01 — Paciente pergunta o VALOR da consulta

**Quando dispara:** paciente manda qualquer coisa como:
"Valores", "Preço", "Quanto custa?", "Qual o valor?", "tem desconto?", "pago com cartão?", "aceita PIX?"

**Texto que a Lia envia (quando não sabe o médico/convênio):**

> Nossa Avaliação do Processamento Visual com a Dra. Karla Delalíbera inclui:
> 
> 👁️ Refração (grau dos óculos)
> 👁️ Biomicroscopia
> 👁️ Mapeamento de retina
> 👁️ Tonometria (pressão)
> 👩‍⚕️ Avaliação com especialistas do corpo clínico (Catarata, Refrativa, Plástica Ocular, Retina e Vítreo).
> 
> 💳 O valor da Avaliação do Processamento Visual com a Dra. Karla Delalíbera tem as seguintes opções: Primeira Opção: R$ 611 Pix, Segunda Opção: R$ 670 (1x Cartão), Terceira Opção: R$ 670 (2x Cartão), para o primeiro paciente.
> 
> Qual a sua escolha?

**Chaves Pix a usar:**
- Asa Norte: `karladelaliberaoftalmo@gmail.com`
- Águas Claras: `52.303.729/0001-30`

**Status:** ✅ Implementado (C-86b) — confirmar se os valores e texto estão corretos

---

### ✅ S02 — Urgência clínica (olho vermelho, dor, perda de visão)

**Quando dispara:** "olho inchado", "dor no olho", "perdeu a visão", "bateu no olho", "olho vermelho", "remelando", "ardendo"

**Urgência CRÍTICA (dispara filtro imediato, sem LLM):**

> ⚠️ Isso parece uma emergência ocular. Por segurança, recomendo ir IMEDIATAMENTE a um pronto-socorro (PS) ou ligar 192 (SAMU).
> 
> Vou acionar nossa equipe agora para te ajudar.

**Urgência PRIORITÁRIA (encaixe rápido, pula triagem de convênio):**

> Entendo! Vamos providenciar um encaixe com urgência. Qual unidade fica mais perto de vocês — Asa Norte ou Águas Claras?

**Status:** ✅ Implementado (C-81 intent_classifier) — confirmar textos

---

### ✅ S03 — Paciente pede atendente humano

**Quando dispara:** "Falar com atendente", "quero falar com pessoa", "atendente", "me transfere", "humano", "falar com alguém"

**Texto que a Lia envia:**

> Tudo bem! Vou transferir você para nossa equipe agora mesmo. Um momento! 🙏

*(Lead é movido para 1-ATENDIMENTO HUMANO automaticamente)*

**Status:** ✅ Implementado (C-84b) — confirmar texto

---

### ✅ S04 — Disponibilidade (atende hoje? atende sábado?)

**Quando dispara:** "está atendendo hoje?", "tem horário hoje?", "atende sábado?", "atende domingo?"

**Texto quando NÃO atende hoje (ex: sábado):**

> Hoje é sábado — não temos atendimento. A próxima data disponível com a Dra. Karla Delalíbera é segunda-feira (XX/XX) em Asa Norte ou terça-feira (XX/XX) em Águas Claras. Posso agendar?

**Texto quando atende hoje:**

> Sim! Hoje [dia] a Dra. Karla Delalíbera tem atendimento em [unidade]. Quer que eu verifique os horários disponíveis?

**Status:** ✅ Implementado (C-78) — confirmar textos

---

### ✅ S05 — Convênio não aceito

**Quando dispara:** "atendem Bradesco?", "aceitam GDF?", "tem INAS?", "SulAmérica?"

**Texto que a Lia envia:**

> O [CONVÊNIO] não está credenciado na nossa rede. Mas atendemos particular com condições especiais:
> 
> **Com a Dra. Karla Delalíbera:**
> R$ 611 (PIX) | R$ 670 (cartão 1x ou 2x)
> 
> Como prefere seguir?
> 1️⃣ Agendar sem convênio
> 2️⃣ Encerro por aqui (somente com convênio)

**Status:** ✅ Implementado (C-22) — confirmar texto

---

### ✅ S06 — Endereço / onde fica

**Quando dispara:** "onde fica?", "endereço", "como chegar", "fica no felicittá?", "shin qi", "lago norte", "estacionamento"

**Texto — unidade Asa Norte:**

> Nossa unidade Asa Norte fica na SHIN QI 5 Bloco J Loja 22, Lago Norte 📍
> https://maps.app.goo.gl/jPfjSsXA1bHhsyw56

**Texto — unidade Águas Claras:**

> Nossa unidade Águas Claras fica no Felicittá Shopping — R. 36 Norte, 05 - Bloco 11, Loja 48, 1º Andar 📍
> https://maps.app.goo.gl/FRbkUtg4U4xG55q18

**Texto — sem unidade definida (paciente não disse qual):**

> Temos 2 unidades:
> 
> 🏥 **Asa Norte** — SHIN QI 5 Bloco J Loja 22, Lago Norte
> 📍 https://maps.app.goo.gl/jPfjSsXA1bHhsyw56
> 
> 🏥 **Águas Claras** — Felicittá Shopping, R. 36 Norte 05, Bloco 11 Loja 48
> 📍 https://maps.app.goo.gl/FRbkUtg4U4xG55q18
> 
> Qual fica mais perto de você?

**Status:** ✅ Implementado (C-87) — confirmar textos e links

---

## SITUAÇÕES SEM BYPASS — Precisa implementar

---

### 🔴 S07 — Paciente seleciona slot ofertado ("1", "2", "o primeiro")

**Quando dispara:** Lia acabou de oferecer dois horários (com "1️⃣" e "2️⃣") E paciente responde:
"1", "2", "1️⃣", "2️⃣", "o primeiro", "o segundo", "quero o 1", "esse horário", "o de quarta", "o de manhã"

**O que a Lia faz HOJE:** LLM tenta interpretar "1" como qualquer coisa (nome? convênio? CPF?) — **causa bug real confirmado**

**O que queremos:**

> ✅ Perfeito! Horário [SLOT ESCOLHIDO] confirmado. Para finalizar, preciso de:
> 
> 📋 Nome completo do paciente
> 🎂 Data de nascimento
> 📱 CPF (apenas se for convênio)

*(se dados já foram coletados anteriormente:)*

> ✅ Ótimo! Então ficamos com [DIA] às [HORA] com a Dra. Karla Delalíbera em [UNIDADE]. Confirma?

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🔴 S08 — Confirmação ambígua ("Isso", "Ok", "Sim", "Correto", "Pode ser")

**Quando dispara:** Lia fez uma pergunta de sim/não e paciente responde com confirmação curta

**Exemplos reais:**
- Lia: "A consulta será por convênio ou particular?" → Paciente: "Isso" → Lia entrou em loop
- Lia: "Confirma data de nascimento 15/03/2010?" → Paciente: "Sim" → Lia perguntou de novo

**O que queremos:** mapear resposta ao contexto da última pergunta da Lia

**Texto quando confirmou convênio:**

> Anotado! Convênio [X]. Me passa o nome completo do paciente e a data de nascimento para verificar cobertura.

**Texto quando confirmou slot:**

> Ótimo! Slot confirmado. [Avança para coleta de dados ou gravação]

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🔴 S09 — Turno já informado (anti-loop)

**Quando dispara:** Lia perguntou turno, paciente respondeu "manhã" ou "tarde", e a Lia REPERGUNTA o mesmo turno

**Bug real:** Lead 24413852 (Juliana) — "Segunda ou quarta de manhã" → Lia respondeu "Qual turno funciona melhor pra você — manhã ou tarde?" 11 vezes seguidas

**O que queremos:** quando detectar que turno já foi informado no turno anterior, NUNCA reperguntar. Buscar slots do turno já informado diretamente.

**Não é uma resposta nova** — é um guard interno que bloqueia a pergunta redundante. O comportamento correto é a Lia apresentar slots do turno que o paciente já disse.

**Precisa implementar?** ⬜ Sim ⬜ Não

---

### 🟡 S10 — Duração da consulta

**Quando dispara:** "quanto tempo dura?", "demora muito?", "a consulta é demorada?", "leva quanto tempo?"

**Texto — Dra. Karla:**

> A consulta com a Dra. Karla Delalíbera dura em média 30 minutos.

**Texto — Dr. Fabrício:**

> A consulta com o Dr. Fabrício Freitas dura em média 40 minutos.

**Texto — médico não definido:**

> As consultas duram em média 30 a 40 minutos dependendo do atendimento.

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S11 — Dilatação da pupila

**Quando dispara:** "dilata a pupila?", "vai dilatar?", "minha visão vai ficar embaçada?", "precisa de colírio?"

**Texto que a Lia envia:**

> Sim, dependendo do exame pode ser necessário dilatar a pupila com colírio. A visão fica embaçada por algumas horas depois — se possível, traga um acompanhante para dirigir.

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S12 — Pode levar bebê / criança pequena?

**Quando dispara:** "atende bebê?", "pode levar recém-nascido?", "tem limite de idade?", "atende crianças?"

**Texto que a Lia envia:**

> Sim! Atendemos crianças de todas as idades, incluindo recém-nascidos. A Dra. Karla Delalíbera é especialista em oftalmopediatria. 👶

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S13 — Precisa de encaminhamento?

**Quando dispara:** "precisa de encaminhamento?", "precisa de pedido médico?", "posso marcar direto?", "precisa de guia?"

**Texto — particular:**

> Não, pode marcar direto! Sem necessidade de encaminhamento para consulta particular.

**Texto — convênio:**

> Depende do seu convênio. Alguns exigem pedido médico, outros não. Qual é o seu plano?

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S14 — Paciente questiona espera / demora na resposta

**Quando dispara:** "oi", "estão aí?", "alguém me atende?", "tô esperando", "cadê o atendimento?", "oi oi"

**Texto que a Lia envia (saudação inicial):**

> Olá! 😊 Sou a Lia, assistente da Blink Oftalmologia. Fico feliz em te atender!
> 
> Como posso ajudar você hoje?

**Texto quando paciente volta após silêncio:**

> Olá! 😊 Tudo bem por aí? Posso continuar te ajudando com o agendamento?

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S15 — Horário específico pedido pelo paciente

**Quando dispara:** "tem horário às 10h?", "quero de manhã cedo", "só posso no fim do dia", "tem horário no almoço?"

**Texto quando TEM horário próximo do pedido:**

> Tenho disponível às [HORA] — fica bom?

**Texto quando NÃO tem no horário exato:**

> Não tenho às [HORA_PEDIDA], mas o horário mais próximo que tenho é às [HORA_DISPONIVEL] na [unidade]. Funciona?

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S16 — Paciente manda foto de carteirinha ou documento

**Quando dispara:** paciente envia imagem (carteirinha de convênio, comprovante, RG)

**Texto que a Lia envia:**

> Recebi! Vou registrar aqui. Um momento enquanto verifico... 📋

*(Internamente: extrair nome do convênio e validar se aceito)*

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S17 — Paciente diz que já tem consulta marcada

**Quando dispara:** "já tenho consulta marcada", "minha consulta é dia X", "já agendei"

**Texto que a Lia envia:**

> Que ótimo! Sua consulta está confirmada. Se precisar de qualquer informação adicional — como endereço, preparativos ou reagendamento — é só me falar! 😊

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S18 — Paciente manda áudio

**Quando dispara:** paciente envia mensagem de áudio (não texto)

**Texto que a Lia envia:**

> Recebi seu áudio! Por enquanto consigo atender melhor por texto. Pode me escrever o que precisa? 😊

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

### 🟡 S19 — Cancelamento / não pode mais comparecer

**Quando dispara:** "preciso cancelar", "não vou poder ir", "quero remarcar", "desmarcou", "preciso desmarcar"

**Texto que a Lia envia:**

> Entendido! Vou registrar o cancelamento.
> 
> Quer remarcar para outra data? Posso verificar a agenda agora mesmo. 📅

**Precisa implementar?** ⬜ Parcialmente implementado — confirmar

---

### 🟡 S20 — Referência a consulta anterior / retorno

**Quando dispara:** "quero marcar retorno", "já fui aí antes", "minha filha fez consulta", "é retorno"

**Texto que a Lia envia:**

> Claro! Para retorno com a Dra. Karla Delalíbera, sigo o mesmo processo de agendamento. Qual unidade você prefere — Asa Norte ou Águas Claras?

**Precisa implementar?** ⬜ Sim ⬜ Não ⬜ Ajustar texto

---

## REGRAS FIXAS (não são textos, são comportamentos)

Estas regras **nunca mudam** independente do que o paciente manda:

| # | Regra | Status |
|---|---|---|
| R01 | Karla atende: seg/qua/sex em Asa Norte; ter/qui em Águas Claras | ✅ Implementado |
| R02 | Fabrício atende: ter/qui em Águas Claras | ✅ Implementado |
| R03 | NUNCA dizer "SDP" ou "Síndrome da Deficiência Postural" | ✅ Implementado |
| R04 | Chave Pix Asa Norte: `karladelaliberaoftalmo@gmail.com` | ✅ Implementado |
| R05 | Chave Pix Águas Claras: `52.303.729/0001-30` | ✅ Implementado |
| R06 | Valor Karla: R$611 PIX / R$670 cartão | ✅ Implementado |
| R07 | Valor Fabrício catarata: R$445 PIX / R$470 cartão | ✅ Implementado |
| R08 | NUNCA dizer "coberto pelo convênio" sem validar | ✅ Implementado |
| R09 | Lead com ATIVADO IA = Desativado → silêncio absoluto | ✅ Implementado (C-90) |
| R10 | Lead em 1-ATENDIMENTO HUMANO → silêncio absoluto | ✅ Implementado |
| R11 | Consulta dura 30min (Karla) / 40min (Fabrício) — nunca inventar outro número | ✅ Prompt |
| R12 | NUNCA oferecer slot já ocupado (validar antes de oferecer) | ✅ Implementado (C-80) |
| R13 | NUNCA re-ofertar mesmo slot para o mesmo paciente | ✅ Implementado (C-80b) |

---

## PRIORIDADE DE IMPLEMENTAÇÃO

**Após aprovação do Fábio neste documento:**

| Prioridade | Situação | Impacto esperado |
|---|---|---|
| 🔴 P0 | S09 — Anti-loop turno | Elimina bug C-84 (loop 11x) |
| 🔴 P0 | S07 — Seleção de slot ("1"/"2") | Elimina conversão perdida quando paciente escolhe |
| 🔴 P0 | S08 — "Isso"/"Sim" contextualizados | Elimina loops de confirmação |
| 🟡 P1 | S10 — Duração consulta | Elimina invenção de "60-90 min" |
| 🟡 P1 | S11 — Dilatação | Resposta correta sem improvisação |
| 🟡 P1 | S12 — Bebê/criança | Converte mais pais |
| 🟡 P1 | S13 — Encaminhamento | Reduz atrito |
| ⚪ P2 | S14 até S20 | Qualidade geral |

---

*Documento gerado em 05/08/2026. Implementação ocorre SOMENTE após aprovação explícita do Fábio.*
