# Solicitação técnica — Campo "Data da Próxima Consulta" no prontuário

**De:** Fábio Philipe Martins — Diretoria Blink Oftalmologia
**Para:** Equipe técnica Medware
**Data:** 01/06/2026
**Prioridade:** Alta — bloqueio operacional do motor de lembretes da clínica
**Referência:** *Solicitação Blink — Próxima Consulta v1*

---

## 1. Contexto

A Blink Oftalmologia opera um motor automatizado de lembretes pré-consulta (D-3, D-1, D-0 e check de no-show) integrado ao WhatsApp e ao prontuário Medware. Hoje conseguimos disparar lembretes para a **consulta atual** porque essa data está no agendamento. Mas não temos como disparar lembrete para a **próxima consulta sugerida pela médica** no fim do atendimento — esse dado não está estruturado no prontuário e fica registrado apenas em texto livre na anamnese, inacessível para extração automatizada.

O impacto operacional é direto: pacientes que precisariam ter sido lembrados em 6 meses, 1 ano ou intervalo definido pela médica acabam não retornando, ou retornam tardiamente. Estimamos perda significativa de continuidade de tratamento — especialmente em retinopatia, glaucoma, oftalmopediatria com acompanhamento programado e pós-operatório de catarata.

A solicitação abaixo cria o dado estruturado que destrava o fluxo.

---

## 2. Objeto do pedido

Criação de **um campo dedicado no prontuário/avaliação** chamado **"Data da Próxima Consulta"**, preenchido pela médica responsável no momento do fechamento do atendimento, persistido no banco da Medware e exposto via API REST para consumo pela automação da Blink.

---

## 3. Especificação técnica sugerida

### 3.1 Modelo de dados

| Atributo | Especificação |
|---|---|
| Nome lógico | Data da Próxima Consulta |
| Nome técnico sugerido | `dataProximaConsulta` (alinhar com convenção camelCase já usada em `dataConsulta`, `codAgenda`, etc.) |
| Tipo | `datetime` (ISO 8601 com timezone) |
| Obrigatoriedade | Opcional. Quando vazio = "sem retorno programado" |
| Vínculo | Por `codAgendamento` (1 valor por agendamento concluído) |
| Faixa válida | Entre `dataConsulta` (data da consulta atual) + 1 dia e `dataConsulta` + 5 anos |
| Auditoria | Registrar `codMedico` que preencheu + timestamp |

### 3.2 Comportamento na UI do prontuário

- Campo deve aparecer na tela de finalização do atendimento (mesmo passo onde médica registra procedimentos realizados e conduta).
- Componente recomendado: date picker com sugestões rápidas — "+30 dias", "+90 dias", "+6 meses", "+12 meses" — opcional a critério da Medware.
- Validação client-side: data não pode ser anterior à data da consulta atual.
- Campo é **editável** até o momento da assinatura final do prontuário pela médica; após assinatura, vira read-only.
- Quando vazio na assinatura, registrar explicitamente como "sem retorno programado" (evita ambiguidade vs "esquecimento de preenchimento").

### 3.3 Endpoints REST necessários

Solicitamos **três operações** sobre o novo campo:

**3.3.1** `GET /Medware/Agendamento/Listar` — adicionar `dataProximaConsulta` ao payload de resposta de cada agendamento finalizado, junto dos demais campos já retornados.

**3.3.2** `POST /Medware/Agendamento/AtualizarProximaConsulta` (endpoint novo) — atualizar apenas esse campo sem mexer no restante do agendamento:
```
POST /Medware/Agendamento/AtualizarProximaConsulta
Body:
{
  "codAgendamento": <int>,
  "dataProximaConsulta": "<ISO 8601>" | null,
  "codMedico": <int>
}
Response:
{
  "ok": true,
  "codAgendamento": <int>,
  "dataProximaConsulta": "<ISO 8601>" | null
}
```

**3.3.3** `GET /Medware/ProximasConsultas/Listar` (endpoint novo) — extração programada para o motor de lembretes:
```
GET /Medware/ProximasConsultas/Listar
Query params:
  dataInicio=<DD/MM/YYYY>
  dataFim=<DD/MM/YYYY>
  codMedico=<int> (opcional)
  codUnidade=<int> (opcional)
Response:
{
  "ok": true,
  "registros": [
    {
      "codAgendamento": <int>,
      "codPaciente": <int>,
      "nomePaciente": "<str>",
      "telefone": "<str>",
      "codMedico": <int>,
      "nomeMedico": "<str>",
      "codUnidade": <int>,
      "dataConsultaOriginal": "<ISO 8601>",
      "dataProximaConsulta": "<ISO 8601>"
    },
    ...
  ]
}
```

Esse endpoint é o que efetivamente destrava nosso motor de lembretes — permite varredura diária para identificar quem precisa ser comunicado nos próximos D-30, D-15, D-3, D-1.

### 3.4 Compatibilidade com o que já existe

Pedimos que o novo campo **não altere** o contrato atual dos endpoints `Listar`, `Salvar` ou `Horarios/Listar`. Acréscimo de campo opcional não quebra nossos clients existentes (Blink + qualquer terceiro). Manter convenções já usadas: mesmas regras de autenticação (Bearer JWT via `/Acesso/login`), mesmo padrão de erro, mesmo formato datetime.

---

## 4. Casos de uso reais (motivação)

| Cenário | Fluxo desejado |
|---|---|
| Paciente diabético tipo 2 — Dra. Karla recomenda retorno em 6 meses | Médica preenche `dataProximaConsulta = hoje + 180d`. Motor da Blink dispara WhatsApp em D-30 com convite para reagendar. |
| Pós-operatório catarata Dr. Fabrício — retorno 30 dias | Médica preenche `+30d`. Motor dispara D-3 lembrete da consulta de revisão pré-agendada. |
| Oftalmopediatria — acompanhamento anual | Médica preenche `+12m`. Motor da Blink dispara reativação em D-30 com a mãe. |
| Glaucoma — controle a cada 4 meses | Médica preenche `+120d`. Recurrência indefinida (cada consulta gera próxima). |
| Consulta sem necessidade de retorno | Médica deixa vazio. Motor não dispara nada. Sem ruído. |

---

## 5. Critérios de aceitação

Implementação está aprovada quando:

1. Médica preenche o campo na UI → valor persiste no banco e aparece em `GET /Agendamento/Listar?codAgendamento=N` na resposta subsequente.
2. Chamada `POST /AtualizarProximaConsulta` com payload válido retorna `200 OK` e o valor é refletido em consulta subsequente.
3. Chamada `POST /AtualizarProximaConsulta` com data anterior à `dataConsulta` retorna `400` com mensagem clara.
4. `GET /ProximasConsultas/Listar?dataInicio=01/07/2026&dataFim=31/07/2026` retorna todos os agendamentos com `dataProximaConsulta` dentro da janela.
5. Campo é read-only após assinatura final do prontuário (não pode ser alterado por endpoint nem UI).
6. Performance: `GET /ProximasConsultas/Listar` responde em < 2s para janela de 60 dias com ≤ 5000 registros.

---

## 6. Prazo ágil proposto

Considerando que se trata de **acréscimo de uma coluna em tabela existente + um endpoint de atualização + um endpoint de listagem**, propomos o cronograma abaixo:

| Marco | Entrega | Data limite |
|---|---|---|
| **M1 — Kick-off técnico** | Reunião de 30 min para alinhar nome do campo, tipo, validações e tabela alvo | **02/06/2026 (seg)** |
| **M2 — Schema + persistência** | Coluna criada no banco + UI do prontuário expondo o campo (mesmo que ainda sem endpoint público) | **05/06/2026 (qui)** |
| **M3 — Endpoints REST** | `Listar` retornando o campo + `AtualizarProximaConsulta` + `ProximasConsultas/Listar` documentados em Swagger/Postman | **10/06/2026 (ter)** |
| **M4 — Homologação Blink** | Equipe Blink valida em ambiente de teste com casos reais (5 agendamentos finalizados) | **13/06/2026 (sex)** |
| **M5 — Go-live produção** | Deploy em produção + smoke test conjunto Blink ↔ Medware | **16/06/2026 (seg)** |

**Total: 15 dias úteis.** Se algum marco encontrar restrição arquitetural não prevista, pedimos sinalização em até 24h após identificação, para realinharmos o cronograma sem surpresas.

---

## 7. Próximos passos imediatos

1. **Confirmação de recebimento** desta solicitação em até 24h.
2. **Resposta técnica** com aceite, contraproposta de cronograma ou pedidos de esclarecimento até **04/06/2026 (qua) 12h**.
3. **Estimativa de horas** e proposta comercial até **04/06/2026 (qua) 18h**, para liberação do orçamento.
4. **Agendamento do kick-off M1** preferencialmente na **segunda 02/06 às 10h ou 16h** (disponibilidade confirmar).

---

## 8. Observações

- As demandas adicionais — **Receita Médica** e **endpoints API complementares para extração de prontuário** — serão formalizadas em documentos separados nos próximos dias, para não atrasar esta primeira entrega que tem impacto operacional imediato.
- A Blink coloca à disposição um engenheiro técnico para acompanhar a integração e responder dúvidas durante o desenvolvimento.
- Ficamos no aguardo do retorno e à disposição para qualquer ajuste de escopo.

Atenciosamente,

**Fábio Philipe Martins**
Diretoria — Blink Oftalmologia
