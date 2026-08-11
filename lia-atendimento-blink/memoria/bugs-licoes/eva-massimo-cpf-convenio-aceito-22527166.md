---
tags: [bug, cpf, convenio-aceito, gap-agenda]
lead: 22527166
paciente: Eva Massimo Agrelis (4 anos)
contato: Massimo Guida
convenio: Plan Assiste - MPF (MPU)
data_bug: 2026-06-02
data_diagnostico: 2026-06-04
status: corrigido-em-189
---

# Lead Eva Massimo 22527166 — Lia pediu CPF com convênio aceito

## Cenário

**Lead:** Massimo Guida (contato) buscando agendamento pra filha **Eva Massimo Agrelis (4 anos)** com **Dra. Karla Delalibera** no convênio **Plan Assiste - MPF (MPU)** — convênio ACEITO pela Blink (codPlano 4).

## Sequência da Lia (02/06/2026)

| Hora | Mensagem Lia |
|---|---|
| 19:40 | "É pra você ou outra pessoa? Rotina/sintoma?" |
| 19:42 | "Qual a idade da sua filha? Sintomas?" |
| 19:43 | "Vamos agendar. Antes de oferecer horários, preciso: nome completo, data nasc" |
| 19:46 | **"Confirma CPF da Eva para eu registrar"** ← bug |
| — | Paciente parou de responder |

## O Bug

Lia pediu **CPF da Eva** (paciente menor) MESMO com **Plan Assiste MPF** (convênio aceito).

Regra correta da Blink (já documentada na KB 38 + checklist):

- CPF é **obrigatório APENAS pra Particular** (paciente sem cobertura)
- Pra convênios aceitos: CPF é dispensável (operadora identifica via carteirinha + nome + data nasc)

A pergunta de CPF desnecessária:
1. Cria fricção no atendimento (paciente cria objeção)
2. Levanta suspeita LGPD ("por que precisa do CPF de uma criança?")
3. Pode bloquear o agendamento se paciente não tiver CPF da menor à mão

## Causa raiz

A conversa de 02/06 aconteceu ANTES do deploy da task **#189** (CPF dispensável p/ convênio aceito).

Fix #189 implementou:
- `voice_agent/checklist_dados_minimos.py`: `cpf_exigido = (convenio == "Particular")`
- `voice_agent/responder.py`: filtro `_viola_pergunta_redundante_cpf` substitui se Lia perguntar CPF com convênio aceito
- `voice_agent/knowledge_base/_MASTER_INSTRUCTION.md` E2: regra escrita
- Pytest `tests/test_cpf_opcional_convenio.py`: 11 cenários verdes

## Gap secundário detectado

Lead foi **agendado manualmente no Medware** depois (17/12/2026 09:30) — campo `1.DIA CONSULTA` preenchido com timestamp = 17/12/2026 12:30 UTC.

Mas o **status_id atual = 106157327** não é nenhuma das etapas mapeadas no CLAUDE.md seção 4. Provavelmente etapa nova ("realizado consulta" ou "próxima consulta" no funil pós-consulta).

Camada 2 do `ja_agendado` (CLAUDE.md seção 11-D) deveria pegar isso via `1.DIA CONSULTA` futuro — confirmar se Lia respeita esse sinal.

## Ações tomadas

- ✅ **Fix principal coberto pela task #189** — já em produção
- ✅ **Lição registrada aqui** pra próxima sessão saber
- ⏭ Verificar se `ja_agendado` (camada 2) está respeitando o `1.DIA CONSULTA` preenchido nesse lead
- ⏭ Documentar status_id `106157327` no CLAUDE.md seção 4 (provavelmente "10-PRÓXIMA CONSULTA" ou similar)

## Como Lia DEVE comportar-se agora (pós-fix #189)

Pra lead idêntico (paciente menor + convênio aceito):

```
Lia: "Vamos agendar a consulta da Eva (4 anos) com a Dra. Karla na Asa Norte
     pelo Plan Assiste MPF. Tenho 2 horários abertos:

     1️⃣ Quinta (10/06) às 09:00
     2️⃣ Quinta (10/06) às 14:00

     Qual fica melhor? Se preferir outro dia, me avisa."
```

CPF NÃO é pedido. Convênio cobre. Pronto.
