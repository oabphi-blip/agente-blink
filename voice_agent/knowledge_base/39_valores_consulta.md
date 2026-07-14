# Artigo 39 — Valores oficiais de consultas Blink

**Origem:** Fábio 02/06/2026 — bug recorrente: paciente pergunta valor,
Lia faz 4 perguntas antes de responder. Solução: tabela oficial como
conhecimento de primeira ordem.

**Revisão 13/07/2026 (Fábio print Kommo campo R$ KARLA DELALÍB id 1259108):**
Valores atualizados conforme fonte oficial no Kommo — corrige bug C-55
(Lia dizia "Sem Convênio é coberto, coparticipação" pra particular).

Regra fixa: **NUNCA explicar cobertura do convênio do paciente**. Isso
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

### 2. Consulta SÁBADO / ENCAIXE — Dra. Karla Delalíbera

Consulta em horário especial de sábado ou encaixe fora da grade regular
(agenda estendida, valor incentivado).

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

Fonte oficial: Kommo field **R$ FABRICIO** (id 1260631). Revisão 13/07/2026.

| Forma de pagamento | Valor |
|---|---|
| 📲 **1ª opção — Pix (à vista)** | **R$ 445,00** |
| 💳 **2ª opção — Cartão 1x** | **R$ 470,00** |
| 💳 **3ª opção — Cartão 2x sem juros** | **R$ 470,00** (2x R$ 235,00) |

Pós-operatório até 30 dias segue mesmo valor.

**Ganho no Pix:** R$ 25 de desconto vs. cartão. Sempre apresentar as 3 opções na ordem acima pra o paciente escolher.

---

## Como a Lia deve responder

### Caso 1 — Paciente pergunta valor SEM convênio (particular / "Sem Convênio" / "Não se aplica")

Lia responde DIRETO com as 3 opções + exames inclusos. Zero fala sobre
cobertura de plano.

Script canônico:

> "A consulta com a Dra. Karla Delalíbera tem 3 opções:
>
> 📲 **1ª opção — Pix (à vista):** R$ 611
> 💳 **2ª opção — Cartão 1x:** R$ 670
> 💳 **3ª opção — Cartão 2x sem juros:** R$ 670 (2x R$ 335)
>
> A consulta já inclui tonometria, motilidade e mapeamento de retina.
>
> Qual forma de pagamento fica melhor pra você?"

Para APV (R$ 800/870), sábado/encaixe (R$ 511/570), Fabrício catarata
(R$ 297) — usar a linha correspondente da tabela.

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
> • Consulta especial de sábado (Dra. Karla): R$ 511 Pix ou R$ 570 em 2x
> • Avaliação do Processamento Visual (aprendizagem): R$ 800
> • Avaliação de catarata (Dr. Fabrício Freitas): R$ 445 Pix ou R$ 470 no cartão (1x ou 2x R$ 235)
>
> Qual desses interessa pra você?"

### Caso 5 — Paciente pergunta sobre sábado / encaixe

Sábado é valor incentivado (mais barato que dia útil regular):

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

---

## Regra negativa — o que a Lia NÃO pode fazer

❌ **NUNCA falar em "cobertura", "coparticipação", "reembolso", "não
paga direto à clínica", "depende do plano"** quando o paciente tem
convênio. Regra Fábio 13/07/2026 (bug C-55, leads 24292474 Dani e
24295374 Emilly).

❌ **NUNCA tratar "Sem Convênio" ou "Não se aplica" como convênio.** São
sinônimos de PARTICULAR — aplicar Caso 1 (3 opções Pix/Cartão 1x/Cartão 2x).

❌ **NUNCA misturar valor de dia útil (R$ 611) com sábado (R$ 511).**
Se paciente quer sábado, aplicar tabela sábado. Se quer dia útil, aplicar
tabela dia útil. Não somar, não confundir.

❌ Perguntar "com ou sem convênio?" quando `ctx.known.convenio` já tem
qualquer valor (incluindo "Não se aplica", "Particular", "Não aceita").

❌ Pedir nome + nasc + CPF + motivo + convênio em sequência ANTES de
revelar pelo menos uma faixa de valor.

❌ Dizer "preciso de mais informações pra te passar o valor" sem dar
pelo menos a tabela do Caso 4.

❌ Inventar valores fora desta tabela. Se Fábio mudar valor, este
artigo é a única fonte de verdade. Lia deve ler aqui.

❌ Falar em "sinal 50%" logo no valor. Sinal só entra na etapa E9
(pós-agendamento), não no Caso 1 (apresentação de valor).

---

## Fonte oficial

**Campo Kommo `R$ KARLA DELALÍB`** (field_id 1259108, seleção múltipla).
Enum values transcritos do print Fábio 13/07/2026:

```
Individual até 2 pacientes
  ├── Primeira Opção. R$611,00 Pix
  ├── Segunda Opção. R$670,00 (1x Cartão)
  └── Terceira Opção. R$670,00 (2x Cartão)

Sábado, Encaixe
  ├── Primeira Opção. R$511,00 Pix
  ├── Segunda Opção. R$570,00 (1x Cartão)
  └── Terceira Opção. R$570,00 (2x Cartão)

Avaliação do Processamento Visual
  ├── Primeira Opção. R$800,00 Pix
  ├── Segunda Opção. R$870,00 (1x Cartão)
  └── Terceira Opção. R$870,00 (2x Cartão)
```

**Campo Kommo `R$ FABRICIO`** (field_id 1260631, seleção múltipla).
Enum values transcritos do print Fábio 13/07/2026:

```
R$ FABRICIO (catarata + pós-op)
  ├── Primeira Opção: R$445,00 Pix
  ├── Segunda Opção: R$470,00 Cartão (1x)
  └── Terceira Opção: R$235,00 2X (= R$470 total, 2x R$235)
```

**Correção 13/07/2026 (Fábio):** o enum do Kommo estava com "R$230,00 2X"
(erro de cadastro). Valor real é **2x R$235,00 = R$470,00 total**, igual
ao cartão 1x. Verificar/corrigir também no Kommo se o campo ainda estiver
com R$230.
