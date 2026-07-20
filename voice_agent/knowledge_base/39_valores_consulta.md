# Artigo 39 — Valores oficiais de consultas Blink

**Origem:** Fábio 02/06/2026 — bug recorrente: paciente pergunta valor,
Lia faz 4 perguntas antes de responder. Solução: tabela oficial como
conhecimento de primeira ordem.

**Revisão 15/07/2026 — Bug C-59 (Fábio consolidou print field 1259108):**
Categorias simplificadas: **"Encaixe / Sábado / Mais de 2 pacientes"**
viraram UMA categoria única (mesmo valor R$ 511/570/570). Antes da C-59
tínhamos 4 categorias distintas — agora são 3.

**Regra fixa:** NUNCA explicar cobertura do convênio do paciente. Isso
é decisão do paciente com o plano dele. Nós apresentamos SEMPRE o valor
particular (Pix, cartão 1x, cartão 2x) e paciente decide.

---

## Tabela oficial — Dra. Karla Delalíbera (fonte: Kommo field 1259108)

### 1. Consulta INDIVIDUAL até 2 pacientes (rotina, oftalmopediatria, estrabismo)

| Forma de pagamento | Valor |
|---|---|
| 📲 **1ª opção — Pix (à vista)** | **R$ 611,00** |
| 💳 **2ª opção — Cartão 1x** | **R$ 670,00** |
| 💳 **3ª opção — Cartão 2x sem juros** | **R$ 670,00** (2x R$ 335,00) |

**Exames inclusos na consulta:** tonometria, motilidade, mapeamento de retina.

---

### 2. Consulta ENCAIXE / SÁBADO / MAIS DE 2 PACIENTES — Dra. Karla Delalíbera

Categoria consolidada (15/07/2026 — Fábio). Cobre 3 situações:
- **Encaixe** — slot extra em dia útil (2ª a 6ª) fora da grade regular
- **Sábado** — agenda especial de sábado
- **Mais de 2 pacientes** — família com 3+ pessoas na mesma consulta

Todas essas 3 situações têm o MESMO valor.

| Forma de pagamento | Valor |
|---|---|
| 📲 **1ª opção — Pix (à vista)** | **R$ 511,00** |
| 💳 **2ª opção — Cartão 1x** | **R$ 570,00** |
| 💳 **3ª opção — Cartão 2x sem juros** | **R$ 570,00** (2x R$ 285,00) |

**Exames inclusos:** tonometria, motilidade, mapeamento de retina.

**Sábados atendidos:**
- **Asa Norte** — penúltimo sábado do mês
- **Águas Claras** — último sábado do mês

---

### 3. Avaliação do Processamento Visual (APV) — Dra. Karla Delalíbera

Consulta específica de APV (Suporte ao Desenvolvimento e Aprendizagem).

| Forma de pagamento | Valor |
|---|---|
| 📲 **1ª opção — Pix (à vista)** | **R$ 800,00** |
| 💳 **2ª opção — Cartão 1x** | **R$ 870,00** |
| 💳 **3ª opção — Cartão 2x sem juros** | **R$ 870,00** (2x R$ 435,00) |

---

### 4. Avaliação para cirurgia de catarata + pós-op — Dr. Fabrício Freitas

Fonte oficial: Kommo field **R$ FABRICIO** (id 1260631).

| Forma de pagamento | Valor |
|---|---|
| 📲 **1ª opção — Pix (à vista)** | **R$ 445,00** |
| 💳 **2ª opção — Cartão 1x** | **R$ 470,00** |
| 💳 **3ª opção — Cartão 2x sem juros** | **R$ 470,00** (2x R$ 235,00) |

Pós-operatório até 30 dias segue mesmo valor.

**Ganho no Pix:** R$ 25 de desconto vs. cartão.

---

## Como a Lia deve responder

Existem 2 formatos autorizados. A Lia usa o **Formato Padrão** por default;
o **Formato Humano (Pix sinal 50%)** só é liberado quando o atendente humano
já enviou mensagem nesse formato no chat (Lia replica o modelo humano) OU
quando o paciente pergunta explicitamente sobre parcelamento/sinal.

### Formato PADRÃO — 3 opções à vista, sinal só depois da aceitação

Script canônico (Caso 1 — particular / "Sem Convênio" / "Não se aplica"):

> "A consulta com a Dra. Karla Delalíbera tem 3 opções:
>
> 📲 **1ª opção — Pix (à vista):** R$ 611
> 💳 **2ª opção — Cartão 1x:** R$ 670
> 💳 **3ª opção — Cartão 2x sem juros:** R$ 670 (2x R$ 335)
>
> A consulta já inclui tonometria, motilidade e mapeamento de retina.
>
> Qual forma de pagamento fica melhor pra você?"

Depois que paciente aceitar o slot, aí sim entra o sinal 50% na etapa E9
(agendamento). No PADRÃO, apresentação inicial NÃO menciona sinal.

Para APV (R$ 800/870), encaixe/sábado/mais de 2 (R$ 511/570), Fabrício
catarata (R$ 445) — usar a linha correspondente da tabela.

### Formato HUMANO — Pix 50% sinal + Cartão integral no ato

Autorização: quando atendente humano enviou mensagem nesse formato antes
da Lia (Lia replica o padrão do chat) OU quando paciente pergunta sobre
sinal/parcelamento/reserva.

Script canônico (Caso 1 humano — particular):

> "Olá, [Nome],
>
> Em continuidade ao atendimento sem convênio, apresentamos o valor da consulta.
>
> 🎯 Sua consulta oftalmológica já inclui exames importantes como:
> 👁️ Tonometria
> 👀 Exame de Motilidade
> 🌀 Mapeamento de Retina
>
> 💳 Valor total: R$ 611,00 — 2 formas de pagar:
>
> 1️⃣ **Pix** — sinal de 50% (R$ 305,50) no ato do agendamento e os R$ 305,50 restantes no dia da consulta.
>
> 2️⃣ **Cartão de crédito** — valor integral de R$ 670,00 no ato do agendamento.
>
> Chave Pix ([Unidade]): [chave conforme unidade]
>
> Qual a sua escolha?"

Chaves Pix (allowlist estrita — filtro `_scrub_prohibited` bloqueia qualquer outra):
- **Asa Norte:** `karladelaliberaoftalmo@gmail.com` (e-mail)
- **Águas Claras:** CNPJ `52.303.729/0001-30`

Cálculo do sinal 50% por categoria (formato humano):

| Categoria | Valor total | Sinal 50% Pix | Cartão integral |
|---|---|---|---|
| Individual até 2 | R$ 611 | R$ 305,50 | R$ 670 |
| Encaixe/Sábado/Mais de 2 | R$ 511 | R$ 255,50 | R$ 570 |
| APV | R$ 800 | R$ 400,00 | R$ 870 |
| Fabrício catarata | R$ 445 | R$ 222,50 | R$ 470 |

### Caso 2 — Paciente pergunta valor COM convênio aceito

Lia NÃO fala em "cobertura", "coparticipação", "reembolso". Só confirma
que atendemos e avança pra unidade/horário.

Script canônico:

> "Sim, atendemos o [convênio]! 👍 Qual unidade fica melhor para você —
> Asa Norte ou Águas Claras?"

**PROIBIDO:** dizer "é coberto", "você não paga direto à clínica",
"pode ter coparticipação", "depende do plano". Nunca. Cobertura é
problema do paciente com o plano dele.

### Caso 3 — Convênio NÃO aceito

Lia nega direto, oferece particular:

> "Esse convênio a clínica não atende. Mas posso te oferecer o
> particular com a Dra. Karla Delalíbera:
>
> 📲 **Pix:** R$ 611
> 💳 **Cartão 1x:** R$ 670
> 💳 **Cartão 2x sem juros:** R$ 670 (2x R$ 335)
>
> A consulta já inclui tonometria, motilidade e mapeamento de retina.
> Quer seguir?"

### Caso 4 — Paciente pergunta valor sem contexto

Lia pergunta 1 coisa só (motivo/especialidade) e antecipa faixa:

> "Depende do tipo de consulta:
> • Consulta com a Dra. Karla (rotina, pediátrica, estrabismo): R$ 611 Pix ou R$ 670 em 2x
> • Encaixe / Sábado / Família 3+ pacientes: R$ 511 Pix ou R$ 570 em 2x
> • Avaliação do Processamento Visual (aprendizagem): R$ 800
> • Avaliação de catarata (Dr. Fabrício Freitas): R$ 445 Pix ou R$ 470 no cartão (1x ou 2x R$ 235)
>
> Qual desses interessa pra você?"

### Caso 5 — Paciente pergunta sobre sábado

Sábado tem o mesmo valor de encaixe e família 3+ pacientes:

> "Nossa agenda especial de sábado com a Dra. Karla Delalíbera é uma
> oportunidade de cuidar da visão sem correria de escola ou trabalho:
>
> 📲 **1ª opção — Pix:** R$ 511
> 💳 **2ª opção — Cartão 1x:** R$ 570
> 💳 **3ª opção — Cartão 2x sem juros:** R$ 570 (2x R$ 285)
>
> A consulta já inclui os exames. Sábados atendidos:
> • Asa Norte — penúltimo sábado do mês
> • Águas Claras — último sábado do mês
>
> Qual unidade fica melhor?"

### Caso 6 — Paciente pergunta sobre encaixe

Encaixe = slot extra em dia útil fora da grade regular. Mesmo valor de
sábado e família 3+ pacientes.

> "Nossa agenda de encaixe (2ª a 6ª) com a Dra. Karla Delalíbera é uma
> oportunidade quando abre slot extra fora da grade regular:
>
> 📲 **1ª opção — Pix:** R$ 511
> 💳 **2ª opção — Cartão 1x:** R$ 570
> 💳 **3ª opção — Cartão 2x sem juros:** R$ 570 (2x R$ 285)
>
> Encaixes dependem de disponibilidade — me diz qual unidade prefere
> (Asa Norte ou Águas Claras) e eu verifico o próximo slot livre."

### Caso 7 — Família com 3+ pacientes (mesma consulta) — NOVO 15/07/2026

Família com 3 ou mais pacientes tem o mesmo valor especial de
encaixe/sábado (mais barato que individual até 2).

> "Para família com 3 ou mais pacientes, temos um valor especial:
>
> 📲 **1ª opção — Pix:** R$ 511
> 💳 **2ª opção — Cartão 1x:** R$ 570
> 💳 **3ª opção — Cartão 2x sem juros:** R$ 570 (2x R$ 285)
>
> A consulta já inclui os exames. Quer confirmar quantos pacientes exatamente?"

---

## Regra negativa — o que a Lia NÃO pode fazer

❌ **NUNCA falar em "cobertura", "coparticipação", "reembolso", "não
paga direto à clínica", "depende do plano"** quando o paciente tem
convênio.

❌ **NUNCA tratar "Sem Convênio" ou "Não se aplica" como convênio.** São
sinônimos de PARTICULAR — aplicar Caso 1 (3 opções Pix/Cartão 1x/Cartão 2x).

❌ **NUNCA misturar valor de encaixe/sábado/família 3+ (R$ 511) com
individual até 2 (R$ 611).** Se paciente pediu encaixe, sábado ou
família 3+, aplicar tabela consolidada R$ 511/570/570.

❌ Perguntar "com ou sem convênio?" quando `ctx.known.convenio` já tem
qualquer valor (incluindo "Não se aplica", "Particular", "Não aceita").

❌ Pedir nome + nasc + CPF + motivo + convênio em sequência ANTES de
revelar pelo menos uma faixa de valor.

❌ Dizer "preciso de mais informações pra te passar o valor" sem dar
pelo menos a tabela do Caso 4.

❌ Inventar valores fora desta tabela. Se Fábio mudar valor, este
artigo é a única fonte de verdade. Lia deve ler aqui.

❌ **Falar em "sinal 50%" no Formato PADRÃO.** Sinal só entra na etapa
E9 (pós-agendamento) OU quando o atendente humano já usou o Formato
HUMANO no chat (Lia replica o padrão) OU quando paciente pergunta
explicitamente sobre parcelamento/sinal.

---

## Fonte oficial

**Campo Kommo `R$ KARLA DELALÍB`** (field_id 1259108, seleção múltipla).
Enum values transcritos do print Fábio 15/07/2026 (versão consolidada):

```
Individual até 2 pacientes
  ├── Primeira Opção. R$611,00 Pix
  ├── Segunda Opção. R$670,00 (1x Cartão)
  └── Terceira Opção. R$670,00 (2x Cartão)

Encaixe / Sábado / Mais de 2 pacientes (CONSOLIDADO 15/07/2026)
  ├── Primeira Opção. R$511,00 Pix
  ├── Segunda Opção. R$570,00 (1x Cartão)
  └── Terceira Opção. R$570,00 (2x Cartão)

Avaliação do Processamento Visual
  ├── Primeira Opção. R$800,00 Pix
  ├── Segunda Opção. R$870,00 (1x Cartão)
  └── Terceira Opção. R$870,00 (2x Cartão)
```

**Campo Kommo `R$ FABRICIO`** (field_id 1260631, seleção múltipla).

```
R$ FABRICIO (catarata + pós-op)
  ├── Primeira Opção: R$445,00 Pix
  ├── Segunda Opção: R$470,00 Cartão (1x)
  └── Terceira Opção: R$235,00 2X (= R$470 total, 2x R$235)
```
