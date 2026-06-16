# Artigo 39 — Valores oficiais de consultas Blink

**Origem:** Fábio 02/06/2026. Bug recorrente: paciente pergunta valor,
Lia faz 4 perguntas antes de responder algum número. Solução: tabela
oficial registrada como conhecimento de primeira ordem.

---

## Tabela oficial (junho 2026)

| Tipo de consulta | Médico | Valor cheio | Sinal 50% |
|---|---|---|---|
| Consulta completa, rotina, check-up | Dra. Karla Delalibera | **R$ 611,00** | R$ 305,50 |
| Oftalmopediatria | Dra. Karla Delalibera | **R$ 611,00** | R$ 305,50 |
| Avaliação de estrabismo | Dra. Karla Delalibera | **R$ 611,00** | R$ 305,50 |
| Avaliação para cirurgia de catarata | Dr. Fabrício Freitas | **R$ 297,00** | R$ 148,50 |
| Pós-operatório catarata (até 30 dias) | Dr. Fabrício Freitas | **R$ 297,00** | R$ 148,50 |
| Avaliação do Processamento Visual (Suporte ao Desenvolvimento e Aprendizagem) | Dra. Karla Delalibera | **R$ 800,00** | R$ 400,00 |

---

## Como a Lia deve responder

### Caso 1 — Paciente pergunta valor e ctx tem dados parciais

Lia consulta o `ctx.known`:

- Se `convenio` está preenchido (qualquer valor, incluindo "Não se aplica"),
  **NÃO pergunte de novo "com ou sem convênio"**. Use o que já tem.
- Se `medico` + `especialidade` + `motivo` preenchidos → responda DIRETO
  com R$ da tabela acima.
- Se falta só 1 ou 2 dos campos → faça 1 só pergunta cobrindo os campos
  que faltam, e logo abaixo já antecipe os valores possíveis.

### Caso 2 — Paciente pergunta valor sem ctx

Lia responde com a TABELA INTEIRA + pergunta qual atendimento:

> "Os valores são:
> • Consulta completa, oftalmopediatria ou estrabismo (Dra. Karla Delalíbera): **R$ 611**
> • Avaliação ou pós-op de catarata (Dr. Fabrício Freitas): **R$ 297**
> • Avaliação do Processamento Visual (Aprendizagem, Dra. Karla Delalíbera): **R$ 800**
>
> Qual desses interessa pra você? Aí já vamos pra agenda."

### Caso 3 — Convênio aceito

Se `convenio` está em `CONVENIOS_ACEITOS` (artigo 15 — STJ, TJDFT,
Plan Assiste, etc), Lia diz:

> "Pelo seu convênio (XYZ) a consulta é coberta — você não paga direto à
> clínica. Pode ter co-participação dependendo do seu plano. Quer
> seguir pro agendamento?"

### Caso 4 — Convênio NÃO aceito (Inas GDF — artigo 18)

> "Esse convênio a clínica não atende. Mas posso te oferecer o
> particular: consulta completa R$ 611 com Dra. Karla Delalíbera. Quer seguir?"

---

## Regra negativa — o que a Lia NÃO pode fazer

❌ Perguntar "com ou sem convênio?" quando `ctx.known.convenio` já tem
qualquer valor (incluindo "Não se aplica", "Particular", "Não aceita").

❌ Pedir nome + nasc + CPF + motivo + convênio em sequência ANTES de
revelar pelo menos uma faixa de valor. Pergunta de valor é fluxo
informativo, não checklist de agendamento.

❌ Dizer "preciso de mais informações pra te passar o valor" sem dar
pelo menos a tabela 3 categorias.

❌ Inventar valores fora desta tabela. Se Fábio mudar valor, este
artigo é a única fonte de verdade. Lia deve ler aqui.
