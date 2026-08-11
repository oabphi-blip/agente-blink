# Solicitação técnica — Próxima Consulta no prontuário (UX + Endpoint)

**De:** Fábio Philipe Martins — Diretoria Blink Oftalmologia
**Para:** Equipe técnica Medware
**Data:** 01/06/2026
**Prioridade:** Alta — destrava motor de lembretes de retorno da clínica

---

## 1. Resumo executivo

Precisamos de **duas coisas** no prontuário Medware:

1. **Uma forma da médica registrar quando o paciente deve voltar** — e esse registro precisa ser **fácil de preencher** (médica gasta < 3 segundos), e **fácil de extrair via API** (motor de lembretes consome diariamente).

2. **Um endpoint REST que devolva esse dado** — hoje a informação fica em texto livre na anamnese e não conseguimos consumir programaticamente.

Abaixo descrevemos a UX que pedimos (item 2), o contrato do endpoint (item 3) e o cronograma (item 4).

---

## 2. Decisão de UX — campo no prontuário

### 2.1 Análise das duas opções óbvias

| Opção | Vantagem | Desvantagem |
|---|---|---|
| **Calendário absoluto** ("voltar em 01/12/2026") | Médica vê a data exata, evita feriado | 3-4 cliques, médica precisa fazer conta mental |
| **Número de dias** ("voltar em 180 dias") | Rápido (1 input), terminologia clínica natural | Pode cair em sábado/feriado |

Cada uma sozinha resolve metade do problema. Por isso recomendamos a **opção híbrida** abaixo, que é o padrão usado por Epic, Cerner e outros prontuários clínicos.

### 2.2 Recomendação — modelo híbrido com 2 campos vinculados

**Campo A — Intervalo de retorno (input principal)**
- Tipo: lista suspensa com opções pré-definidas + opção "Outro" (campo livre numérico)
- Opções pré-definidas: **30 dias · 60 dias · 90 dias · 180 dias · 365 dias · 730 dias · Sem retorno**
- Cobertura clínica: 30d (pós-op imediato), 90d (glaucoma controlado), 180d (rotina geral), 365d (check-up anual), 730d (oftalmopediatria estável)
- Quando a médica clica numa opção → sistema **calcula automaticamente** a data sugerida (campo B)

**Campo B — Data sugerida (input secundário, editável)**
- Tipo: date picker pré-preenchido pelo cálculo do campo A
- Comportamento default: `dataProximaConsultaSugerida = dataConsultaAtual + intervaloRetornoDias`
- Médica pode **editar manualmente** se quiser ajustar (ex.: tirar do sábado, pular feriado, anteceder uma semana)
- Validação: data ≥ data da consulta atual + 7 dias

### 2.3 Por que essa combinação resolve melhor

| Necessidade | Como o modelo híbrido resolve |
|---|---|
| Médica pensa em intervalo clínico ("retorno em 6 meses") | Campo A vira escolha rápida na lista — 1 clique |
| Médica precisa evitar feriado/sábado | Campo B mostra a data calculada e ela edita 1 vez |
| Sistema precisa do dado pra disparar lembrete | Campo B (datetime absoluto) é a "fonte de verdade" pra motor |
| Padronização clínica de protocolos | Campo A (intervalo) facilita auditoria depois ("X% das pós-op têm retorno em 30d?") |
| Médica pode definir intervalo fora do padrão | Opção "Outro" no Campo A aceita qualquer número |
| Médica decidir "sem retorno" | Opção explícita na lista — não fica ambíguo se foi esquecimento |

### 2.4 Comportamento esperado na tela

1. Tela de fechamento do prontuário tem uma seção nova **"Retorno programado"**
2. Médica vê:
   ```
   Retorno programado:
   [▼ Selecione um intervalo ▼]   Data sugerida: [        ]
   ```
3. Médica clica na lista → escolhe "180 dias" → campo data preenche automaticamente "29/11/2026"
4. Se quiser ajustar → clica no calendário → escolhe outra data → sistema atualiza
5. Se quiser "Sem retorno" → escolhe na lista → ambos campos ficam vazios e travados

---

## 3. Endpoint REST — exposição via API

Hoje a informação não está acessível. Precisamos de **três operações**:

### 3.1 Adicionar ao endpoint existente `GET /Medware/Agendamento/Listar`

Acrescentar dois atributos no payload de resposta de cada agendamento concluído:

```json
{
  "codAgendamento": 12345,
  "dataConsulta": "2026-06-01T09:00:00",
  ... (campos atuais mantidos) ...
  "intervaloRetornoDias": 180,
  "dataProximaConsultaSugerida": "2026-11-29T09:00:00"
}
```

Quando "Sem retorno" → ambos `null`.

### 3.2 Endpoint novo — atualização programática

```
POST /Medware/Agendamento/AtualizarRetorno

Body:
{
  "codAgendamento": <int>,
  "intervaloRetornoDias": <int> | null,
  "dataProximaConsultaSugerida": "<ISO 8601>" | null,
  "codMedico": <int>
}

Response 200 OK:
{
  "ok": true,
  "codAgendamento": <int>,
  "intervaloRetornoDias": <int> | null,
  "dataProximaConsultaSugerida": "<ISO 8601>" | null
}

Response 400:
{
  "ok": false,
  "erro": "data anterior à consulta atual" | "intervalo deve ser positivo" | ...
}
```

Útil para correções, integrações futuras e para o nosso sistema gravar quando a médica preenche por dentro do nosso fluxo.

### 3.3 Endpoint novo — listagem programada (o crítico)

Este é o endpoint que **destrava o motor de lembretes da Blink**:

```
GET /Medware/ProximasConsultas/Listar

Query params:
  dataInicio=<DD/MM/YYYY>   (obrigatório)
  dataFim=<DD/MM/YYYY>      (obrigatório)
  codMedico=<int>           (opcional, filtra por médico)
  codUnidade=<int>          (opcional, filtra por unidade)

Response 200 OK:
{
  "ok": true,
  "total": <int>,
  "registros": [
    {
      "codAgendamento": <int>,
      "codPaciente": <int>,
      "nomePaciente": "<str>",
      "telefonePaciente": "<str>",
      "codMedico": <int>,
      "nomeMedico": "<str>",
      "codUnidade": <int>,
      "dataConsultaOriginal": "<ISO 8601>",
      "intervaloRetornoDias": <int>,
      "dataProximaConsultaSugerida": "<ISO 8601>",
      "convenio": "<str>"
    },
    ...
  ]
}
```

**Critério de retorno:** trazer apenas agendamentos com `dataProximaConsultaSugerida` dentro do intervalo `[dataInicio, dataFim]`, ignorando os com retorno = null.

**Performance esperada:** janela de 60 dias com até 5.000 registros respondendo em < 2 segundos.

---

## 4. Como vai funcionar fim-a-fim

```
1. Dra. Karla finaliza prontuário do João (rotina anual)
   → escolhe "365 dias" → sistema sugere 01/06/2027 → ela aceita
   → salva no prontuário

2. Banco Medware persiste:
   intervaloRetornoDias = 365
   dataProximaConsultaSugerida = 2027-06-01T09:00:00

3. Em 01/05/2027 (D-30), motor da Blink roda:
   GET /Medware/ProximasConsultas/Listar
     ?dataInicio=01/05/2027&dataFim=31/05/2027
   → recebe João + telefone + dado de retorno

4. Motor dispara WhatsApp pro João:
   "Olá, João! Faz quase 1 ano da sua consulta com a Dra. Karla.
    Vamos agendar o seu retorno?"

5. João responde → flui o agendamento normal.
```

Sem o endpoint, o passo 3 é impossível e perdemos esses pacientes pra sempre.

---

## 5. Critérios de aceitação

1. Médica preenche os 2 campos na UI → ambos persistem no banco e aparecem em `GET /Agendamento/Listar`.
2. Cálculo automático: ao escolher intervalo na lista, data é preenchida = `dataConsulta + intervalo`.
3. Edição manual da data não altera o intervalo (campos independentes após escolha inicial).
4. `POST /AtualizarRetorno` com `intervaloRetornoDias = null` E `dataProximaConsultaSugerida = null` representa "sem retorno" — gravado explícito.
5. `GET /ProximasConsultas/Listar` para janela 30 dias responde em < 2s com até 5.000 registros.
6. Campos viram read-only após assinatura final do prontuário.

---

## 6. Cronograma proposto — 15 dias úteis

Considerando que se trata de **2 colunas novas + ajuste de UI + 2 endpoints REST novos + 1 alteração em endpoint existente**, propomos:

| Marco | Entrega | Data limite |
|---|---|---|
| M1 — Kick-off técnico (30 min) | Confirmar nomes dos campos, lista de intervalos pré-definidos, tabela alvo | **02/06/2026 (seg)** |
| M2 — Schema + UI | Colunas criadas no banco + tela do prontuário com os 2 campos vinculados | **05/06/2026 (qui)** |
| M3 — Endpoints REST | Listar com campos novos + AtualizarRetorno + ProximasConsultas/Listar | **10/06/2026 (ter)** |
| M4 — Homologação Blink | Equipe Blink valida 5 cenários reais em ambiente de teste | **13/06/2026 (sex)** |
| M5 — Go-live produção | Deploy + smoke conjunto Blink ↔ Medware | **16/06/2026 (seg)** |

---

## 7. Próximos passos imediatos

1. **Confirmação de recebimento** em 24h.
2. **Resposta técnica + aceite/contraproposta** até **04/06/2026 (qua) 12h**.
3. **Proposta comercial** até **04/06/2026 (qua) 18h**.
4. **Reunião M1 kick-off** sugerida pra **02/06/2026 (seg)** 10h ou 16h.

---

## 8. Observações

- Demandas adicionais (**Receita Médica** e **outros endpoints de extração**) serão formalizadas em documentos separados nos próximos dias, para não atrasar esta entrega operacionalmente crítica.
- A Blink coloca um engenheiro à disposição durante todo o desenvolvimento para responder dúvidas sobre o consumo dos endpoints.
- Disponíveis para ajustar nomes de campos, intervalos pré-definidos ou contrato dos endpoints se a Medware tiver convenções internas que façam mais sentido manter.

Atenciosamente,

**Fábio Philipe Martins**
Diretoria — Blink Oftalmologia
