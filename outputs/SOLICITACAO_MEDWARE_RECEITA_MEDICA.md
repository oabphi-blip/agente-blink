# Solicitação técnica — Receita Médica estruturada no prontuário

**De:** Fábio Philipe Martins — Diretoria Blink Oftalmologia
**Para:** Equipe técnica Medware
**Data:** 01/06/2026
**Prioridade:** Alta — bloqueio na rastreabilidade de prescrições
**Referência:** *Solicitação Blink — Receita Médica v1*

---

## 1. Resumo executivo

Precisamos transformar o módulo de Receita Médica do prontuário Medware em **dado estruturado e auditável**, com:

1. Estrutura no banco que permita armazenar prescrições item-por-item (não em texto livre).
2. UI no prontuário que facilite a médica prescrever com rapidez (autocomplete de medicamentos, posologia em campos separados).
3. Endpoints REST que devolvam as prescrições por paciente, por período e por médico.
4. Geração de PDF assinado (mantendo o atual) + extração via API para integração com WhatsApp e farmácias parceiras.

Hoje a receita é PDF gerado mas o conteúdo não é estruturado — o que impede automações de adesão, reposição e integração.

---

## 2. Decisão de modelo — estruturado vs texto livre

### 2.1 Por que estruturar

Texto livre tem 4 problemas operacionais que medimos na clínica:

| Problema | Custo |
|---|---|
| Não consigo enviar lembrete "está perto de acabar seu colírio" | Perdemos rebuy + paciente sem medicamento |
| Não consigo medir adesão terapêutica em retornos | Médica fica cega ao decidir conduta |
| Receita igual entre médicas escrita de forma diferente | Auditoria interna impossível |
| Erro de transcrição vira problema clínico | Risco assistencial real |

Estruturar resolve os 4 e permite uma série de integrações com pouca fricção adicional.

### 2.2 Modelo de dados proposto

**Receita** (cabeçalho):
| Campo | Tipo | Notas |
|---|---|---|
| codReceita | int | PK |
| codAgendamento | int | FK |
| codPaciente | int | FK |
| codMedico | int | FK |
| dataEmissao | datetime | preenchido na emissão |
| validadeDias | int | default 30 (configurável) |
| tipoReceita | enum | "comum" / "especial_b" / "antimicrobiano" |
| observacoes | text | livre, opcional |
| status | enum | "rascunho" / "emitida" / "cancelada" |
| urlPdfAssinado | string | gerado na emissão |
| hashAssinatura | string | integridade do PDF |

**ItemReceita** (1 receita → N itens):
| Campo | Tipo | Notas |
|---|---|---|
| codItemReceita | int | PK |
| codReceita | int | FK |
| nomeMedicamento | string | autocomplete a partir de tabela |
| dose | string | "1 gota" / "20mg" / "1 comprimido" |
| via | enum | "oftálmica OD" / "oftálmica OE" / "oftálmica AO" / "oral" / "tópica" |
| frequencia | string | "a cada 6h" / "1x ao dia" |
| duracaoDias | int | nullable ("uso contínuo" = null) |
| usoContinuo | bool | true bloqueia duracaoDias |
| observacaoItem | string | opcional, livre |

### 2.3 Tabela de medicamentos (autocomplete)

Solicitamos uma tabela auxiliar **Medicamento** com dados mínimos pra autocomplete:
- nomeComercial (Maxitrol, Tobradex, ...)
- principioAtivo (Dexametasona + Neomicina + Polimixina, ...)
- categoria (corticoide / antibiótico / lubrificante / midriático / hipotensor / ...)
- apresentacaoPadrao (colírio 5ml / suspensão 5ml / comprimido 0,3mg)
- principiosControlados (boolean, marca se exige receita especial)

A tabela pode ser pré-populada com os 50 medicamentos oftalmológicos mais frequentes na clínica — nós entregamos a lista junto com o aceite técnico.

---

## 3. UX no prontuário — fluxo proposto

### 3.1 Tela "Adicionar Receita"

```
+ Nova Receita
─────────────────────────────────────────
Tipo:   ( ) Comum   ( ) Esp. B   ( ) Antimicrobiano
Validade: [30 dias]
─────────────────────────────────────────
Medicamento:  [autocompleta...           ]   + Adicionar
                 ↓
   [Maxitrol] [Tobradex] [Predfort 1%]
─────────────────────────────────────────
Adicionados:
┌────────────────────────────────────────┐
│ 1. Maxitrol — 1 gt OD 6/6h por 7 dias │
│ 2. Polysoph — 1 gt AO 4x/dia contínuo │
└────────────────────────────────────────┘

Observações: [campo livre opcional]
─────────────────────────────────────────
            [Cancelar]  [Salvar Rascunho]  [Emitir Receita]
```

### 3.2 Comportamento

- Autocomplete busca por nome OU princípio ativo
- Ao clicar num medicamento, abre subform: dose · via · frequência · duração · uso contínuo
- "Uso contínuo" disable duração e força no PDF "uso contínuo"
- Adicionar quantos itens quiser na mesma receita
- "Salvar Rascunho" persiste mas não gera PDF nem expõe via API
- "Emitir Receita" gera PDF assinado + define status="emitida" + dispara webhook (item 4 abaixo)

### 3.3 Validações

- Tipo "Especial B" obriga campos extras (paciente CPF + endereço)
- Tipo "Antimicrobiano" obriga "duração" preenchida
- Receita sem nenhum item bloqueia emissão
- Não permite editar receita já "emitida" — apenas "cancelar" + emitir nova

---

## 4. Endpoints REST

### 4.1 `POST /Medware/Receita/Criar` — emitir receita

```json
Body:
{
  "codAgendamento": <int>,
  "tipoReceita": "comum",
  "validadeDias": 30,
  "observacoes": "...",
  "itens": [
    {
      "nomeMedicamento": "Maxitrol",
      "dose": "1 gota",
      "via": "OD",
      "frequencia": "a cada 6 horas",
      "duracaoDias": 7,
      "usoContinuo": false
    },
    {
      "nomeMedicamento": "Polysoph",
      "dose": "1 gota",
      "via": "AO",
      "frequencia": "4 vezes ao dia",
      "usoContinuo": true
    }
  ]
}

Response 200 OK:
{
  "ok": true,
  "codReceita": 12345,
  "urlPdfAssinado": "https://medware.../receita/12345.pdf",
  "hashAssinatura": "<sha256>",
  "dataEmissao": "2026-06-01T10:30:00"
}
```

### 4.2 `GET /Medware/Receita/Listar` — buscar receitas

```
Query params:
  codPaciente=<int>   (opcional)
  codAgendamento=<int> (opcional)
  codMedico=<int>      (opcional)
  dataInicio=<DD/MM/YYYY> (opcional)
  dataFim=<DD/MM/YYYY> (opcional)
  status=<emitida|rascunho|cancelada> (opcional)

Response 200 OK:
{
  "ok": true,
  "total": <int>,
  "receitas": [
    {
      "codReceita": 12345,
      "codAgendamento": 67890,
      "codPaciente": 1111,
      "nomePaciente": "Maria Silva",
      "codMedico": 12080,
      "nomeMedico": "Dra. Karla Delalíbera",
      "dataEmissao": "...",
      "validadeDias": 30,
      "tipoReceita": "comum",
      "status": "emitida",
      "urlPdfAssinado": "...",
      "itens": [ ... mesmo formato do POST ... ]
    }
  ]
}
```

### 4.3 `POST /Medware/Receita/Cancelar`

```json
Body:
{
  "codReceita": 12345,
  "codMedico": 12080,
  "motivoCancelamento": "..."
}
```

### 4.4 Webhook outbound (opcional, fase 2)

Quando uma receita é emitida, dispara HTTP POST para URL configurada pela Blink:

```
POST https://blink-agent.6prkfn.easypanel.host/medware-webhook/receita-emitida

{
  "evento": "receita_emitida",
  "codReceita": 12345,
  "codPaciente": 1111,
  "codAgendamento": 67890,
  "dataEmissao": "...",
  "urlPdfAssinado": "..."
}
```

Isso permite que a Lia (nossa IA) envie o PDF pelo WhatsApp em segundos da emissão, sem ter que poll endpoint.

---

## 5. Casos de uso reais

| Cenário | Como o sistema resolve |
|---|---|
| Médica precisa receitar 2 colírios + 1 oral | Cria 1 receita comum com 3 itens, salva, emite PDF assinado em < 30s |
| Paciente vai à farmácia que tem integração | Farmácia bate `GET /Receita/Listar?codPaciente=N` e valida estoque |
| Lia precisa lembrar paciente que está acabando o colírio | Motor calcula `dataEmissao + duracaoDias - 5d` e dispara WhatsApp |
| Auditoria interna quer medir adesão | Cross check `Receita.Listar` vs farmácia parceira |
| Receita emitida por engano | Médica abre receita → "Cancelar" → emite a correta |
| Médica quer ver histórico do paciente antes de prescrever | Tela já mostra receitas anteriores expandíveis na lateral |

---

## 6. Critérios de aceitação

1. Médica cria receita com 1+ itens, "Emitir" gera PDF assinado em < 30s.
2. PDF assinado tem hash SHA-256 igual ao retornado no response do POST.
3. `GET /Receita/Listar?codPaciente=N` retorna histórico ordenado por `dataEmissao DESC`.
4. Cancelar receita não apaga: `status` vira `cancelada` mas dados persistem (auditoria).
5. Autocomplete responde com ≤ 5 sugestões em < 500ms para query de 3+ caracteres.
6. Receita "Antimicrobiano" sem `duracaoDias` retorna 400 com mensagem clara.
7. Webhook outbound entrega em < 5s da emissão (retry 3x com backoff em falha).

---

## 7. Cronograma proposto — 25 dias úteis

Esta solicitação é maior em escopo que a de "Próxima Consulta" (envolve PDF assinado + tabela auxiliar + UI complexa). Propomos 5 fases:

| Marco | Entrega | Data limite |
|---|---|---|
| M1 — Kick-off técnico (1h) | Confirmar modelo de dados + lista de 50 medicamentos | **04/06/2026 (qua)** |
| M2 — Schema + tabela Medicamento populada | Banco + autocomplete funcionando isolado | **11/06/2026 (qua)** |
| M3 — UI prontuário | Tela "Adicionar Receita" + emissão de PDF assinado | **20/06/2026 (sex)** |
| M4 — Endpoints REST | Criar, Listar, Cancelar funcionando + Swagger | **27/06/2026 (sex)** |
| M5 — Webhook + homologação Blink | Webhook + go-live em produção | **04/07/2026 (sex)** |

---

## 8. Próximos passos imediatos

1. **Confirmação de recebimento** em 24h.
2. **Resposta técnica + aceite/contraproposta** até **06/06/2026 (sex) 12h**.
3. **Proposta comercial** até **06/06/2026 (sex) 18h**.
4. **Reunião M1 kick-off** sugerida pra **04/06/2026 (qua)** 10h ou 16h (1h de duração).
5. A Blink entrega no kick-off:
   - Lista dos 50 medicamentos oftalmológicos mais frequentes pra popular tabela Medicamento.
   - Templates de PDF assinado que esperamos manter (visual atual + campos novos).
   - URL do webhook receptor da Blink.

---

## 9. Observações

- A demanda **"API geral para extração de prontuário"** será formalizada em documento separado nos próximos dias.
- Disponíveis para ajustar qualquer ponto técnico que a Medware tenha convenção interna diferente.
- A Blink coloca um engenheiro técnico à disposição durante toda a integração.

Atenciosamente,

**Fábio Philipe Martins**
Diretoria — Blink Oftalmologia
