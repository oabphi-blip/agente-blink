---
title: "Batch REAGENDAR — Asa Norte segunda 08/06/2026"
tags: [campanha, reagendar, asa-norte]
data: 2026-06-04
status: ativo
---

# 📣 Batch REAGENDAR — segunda 08/06 Asa Norte

**Para:** Stephany / Ariany
**De:** Lia (preparação automática)
**Data preparo:** 04/06/2026 18h
**Agenda confirmada (Karla Asa Norte 08/06):** **11:00** · 11:30 · 13:30 · 14:00 · 16:00 (5 slots)

> ⚠️ API Medware retornou apenas: 11:30, 13:30, 14:00, 16:00.
> 11:00 confirmado pelo Fábio (operação real). Abrir slot no Medware antes da gravação.

---

## ✅ Pacientes preparados (2 confirmados)

### 1. Noah Pereira Vieira — Lead 22982854

- **Histórico:** Faltou consulta!
- **Convênio:** Particular (R$ 611)
- **Unidade:** Asa Norte
- **Status Kommo:** 2.LEADS FRIO
- **ATIVADO IA?:** ✅ Ativado (Lia processa resposta)
- **URL:** https://univeja.kommo.com/leads/detail/22982854

**Mensagem pronta pra copiar/colar no WhatsApp:**

```
Oi! Tudo bem? Aqui é da Blink Oftalmologia.

Vi que o Noah não conseguiu vir na consulta com a Dra. Karla Delalibera e queria reagendar pra você.

Tenho 2 horários abertos na segunda-feira (08/06) na Asa Norte:

1️⃣ 11:00 (manhã)
2️⃣ 14:00 (tarde)

Qual fica melhor? Se preferir outro dia/horário, me avisa que confiro a agenda. ✨
```

---

### 2. Flávia Tavares Correia — Lead 21710873

- **Histórico:** REMARCAÇÃO — recebido justificação para liberar novo horário
- **Convênio:** PróSaúde Câmara dos Deputados (aceito, codPlano 39)
- **Unidade:** Asa Norte
- **Status Kommo:** 0-ETAPA ENTRADA
- **ATIVADO IA?:** ✅ Ativado (Lia processa resposta)
- **URL:** https://univeja.kommo.com/leads/detail/21710873

**Mensagem pronta:**

```
Oi Flávia! Tudo bem? Aqui é da Blink Oftalmologia.

Estamos remarcando consultas com a Dra. Karla Delalibera e abriram 2 horários na segunda (08/06) na Asa Norte:

1️⃣ 11:00 (manhã)
2️⃣ 14:00 (tarde)

Sua consulta é coberta pelo seu plano PróSaúde (Câmara dos Deputados). Qual horário fica melhor? Se preferir outro dia, me avisa que verifico a agenda. ✨
```

---

## ⚠️ Pulados (com motivo)

### Liz Lopes Rodrigues — Lead 22789618
- **Motivo:** Unidade preferencial = Águas Claras (não Asa Norte). Se quiserem ofertar Asa Norte como alternativa, abro nota separada.
- URL: https://univeja.kommo.com/leads/detail/22789618

### Bento + Tito Bilésimo Hahn — Lead 22580154
- **Motivo:** Status Closed-won → já tem agendamento fechado. Não abordar.
- URL: https://univeja.kommo.com/leads/detail/22580154

---

## 🤖 Após o paciente responder

1. **Paciente aceita 1 dos 2 horários** → Lia entra automaticamente (ATIVADO IA? = Ativado), valida dados (nome, data nasc, CPF se Particular), e **grava no Medware sozinha** (fix #208 — commit 28de20d).
2. **Paciente pede outro dia/horário** → Lia consulta agenda Medware e oferece alternativas.
3. **Paciente não responde em 24h** → Lia dispara renovação via template (mecanismo automático já em produção).

---

## 📊 Métricas esperadas

- **Resposta esperada (REAGENDAR alta intenção):** 40-55% → ~1 resposta provável
- **Conversão em agendamento:** 25-35% → 1 agendamento provável segunda 08/06
- **Slots Asa Norte 08/06:** 4 livres (11:30, 13:30, 14:00, 16:00). Restantes ficam disponíveis pro motor de reativação geral processar o resto da semana.

---

## ➕ Próximos lotes (quando quiser ampliar)

Outros 5 REAGENDAR identificados na amostra que ainda não foram processados:

| Lead | Status pipeline | Sinal |
|---|---|---|
| 22225601 | 0-ETAPA ENTRADA | AVALIAÇÃO CIRURGIA paciente desmarcou |
| 12751536 | 0-ETAPA ENTRADA | REAGENDAR ativação 16/12 |
| 22181129 | 0-ETAPA ENTRADA | AGENDAR PÓS DESMARCAÇÃO |
| 10916579 | 0-ETAPA ENTRADA | REMARCAÇÃO somente 100% antecipado |
| 13347530 | 0-ETAPA ENTRADA | REMARCAÇÃO CONVÊNIO 2 ESTRELAS |

**Quando quiser disparar esses 5:** me avise — eu valido convênio/unidade/médico de cada um e preparo as mensagens pro mesmo padrão.
