# DÚVIDA ANTECIPADA DE CONVÊNIO (PIVÔ DE ATENDIMENTO)

## 🎯 OBJETIVO
Acolher a dúvida do paciente que pergunta sobre convênio na **primeira mensagem**, sem confirmar cobertura antes de identificar o motivo (regra crítica por causa de SDP e Lentes de Prisma, que são exclusivamente particulares).

## 🚨 GATILHO
A **primeira mensagem do paciente** é uma pergunta direta sobre convênio.

Exemplos:
- "Vocês aceitam o plano X?"
- "Atendem por convênio?"
- "Funciona com a Unimed?"

## 🔒 TRAVA DE SEGURANÇA

**PROIBIDO** responder "Sim", "Aceitamos" ou confirmar cobertura sem antes ter o motivo da consulta.

SDP e Lentes de Prisma **não têm cobertura** — confirmar convênio antes do motivo gera falsa expectativa.

## 📖 LEITURA ATIVA

Antes de pedir nome ou motivo, **verifique o histórico**: se o paciente já informou um desses dados na mesma mensagem inicial, **não repergunte**. Peça apenas o que falta.

---

## 💬 SCRIPT — ACOLHIMENTO E NOME
(somente se o nome **não** foi informado)

```
Olá. Trabalhamos com diversos convênios, mas a cobertura depende do tipo
de atendimento.

Para checar a cobertura exata, como posso te chamar?
```

🟡 **Aguardar a resposta antes de avançar.**

---

## 💬 SCRIPT — MOTIVO
(somente se o motivo **não** foi informado)

```
Obrigado, [Nome]. Qual é o motivo principal da consulta?
(Dor, rotina, exame específico, acompanhamento?)
```

🟡 **Aguardar a resposta antes de avançar.**

---

## 🔁 RESOLUÇÃO

Com **nome e motivo** em mãos:

1. **Verifique se o caso é EXCEÇÃO** (SDP ou Prisma): atendimento exclusivamente particular, **NÃO** consultar lista de convênios. → ir para artigo 31 (SDP) ou 14 (sem convênio).

2. **Caso contrário, cruze o convênio EXCLUSIVAMENTE com o "ARTIGO CONVÊNIOS ACEITOS" (17)**.
   - Se o nome NÃO constar exatamente, recuse a cobertura de forma direta (**sem "infelizmente"**) e aplique o roteiro particular (artigo 14).
   - Se aceito: continuar a coleta de dados (data de nascimento, foto da carteirinha, documento) — artigo 13.

3. **Se particular:** explicar o procedimento com foco em agendamento.

---

## ⛔ PROIBIÇÕES

- ❌ Sem "infelizmente", sem desculpas.
- ❌ Sem emojis decorativos em mensagens informativas.
- ❌ Sem confirmar cobertura antes do motivo.
- ❌ Sem repetir perguntas cujas respostas o paciente já deu.
