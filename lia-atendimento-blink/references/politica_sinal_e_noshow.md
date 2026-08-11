# Política de Sinal 50%, Remarcação e No-Show

> Espelho do artigo 38 do KB (`voice_agent/knowledge_base/38_politica_sinal_remarcacao_noshow.md`),
> compactado pra consulta rápida. Quando precisar de detalhe completo (frases prontas,
> exemplos, scripts), leia o artigo 38 do KB direto.

---

## 1. Quando cobrar sinal

### 1.1 Sinal OPCIONAL (paciente escolhe entre Reserva Imediata ou Fila de Encaixe)

- **Dra. Karla — Sem convênio** (rotina, pediatria, SDP)
- **Dr. Fabrício — Avaliação Catarata** (R$ 297)

### 1.2 Sinal NÃO COBRADO

- Consulta com convênio aceito
- Retorno dentro de 15 dias úteis
- Mapeamento Kátia pré-cirurgia (se contrato Fabrício assinado)

### 1.3 Sinal OBRIGATÓRIO (sem opção de Fila de Encaixe)

- Paciente com **2+ no-shows** → exigir Reserva Imediata 50%
- Paciente com **3+ no-shows** → exigir pagamento INTEGRAL antecipado + escalar humano
- SDP (R$ 800) → opcional, mas recomendar Reserva Imediata

---

## 2. Valores de sinal (50%)

| Modalidade | Valor cheio | Sinal 50% |
|---|---|---|
| Karla Oftalmologia/Pediatria/Rotina | R$ 611,00 | **R$ 305,50** |
| Karla SDP | R$ 800,00 | **R$ 400,00** |
| Fabrício Avaliação Catarata | R$ 297,00 | **R$ 148,50** |

Sempre `valor_cheio / 2` arredondado a 2 casas. Nunca improvisar.

---

## 3. Chaves Pix oficiais

### Asa Norte
- Chave: `karladelaliberaoftalmo@gmail.com`
- Tipo: e-mail

### Águas Claras
- Chave: `52.303.729/0001-30`
- Tipo: CNPJ

**Qualquer outra chave Pix = alucinação.** O filtro pós-geração em `responder.py` bloqueia
e substitui por fallback seguro.

---

## 4. Fluxo de cobrança

```
Paciente escolhe Reserva Imediata
   ↓
Lia envia: chave Pix + valor exato + prazo 30 min
   ↓
Paciente envia comprovante
   ↓
Equipe HUMANA valida o comprovante (Lia não)
   ↓
Kommo: SINAL STATUS = "Pago" + SINAL DATA PIX preenchido
   ↓
Lia confirma vaga garantida
```

### Prazo de validade do pedido de sinal
- 30 minutos após Lia enviar a chave.
- Sem comprovante em 30 min → vaga volta pra agenda. Lia avisa: "Prazo expirou, quer pagar
  agora ou prefere Fila de Encaixe?"

---

## 5. Remarcação

| Janela | Sinal pago? | Regra |
|---|---|---|
| **>48h antes** | Sim | Remarca sem custo. Sinal migra pra nova data. |
| **>48h antes** | Não | Remarca sem custo (estava em Fila de Encaixe). |
| **24-48h antes** | Sim | Remarca **com cobrança de NOVO sinal** (anterior retido). |
| **24-48h antes** | Não | Remarca sem custo. |
| **<24h ou no-show** | Sim | **Sinal NÃO devolvido.** Paga sinal cheio na nova vaga. |
| **<24h ou no-show** | Não | Paciente perde posição na Fila. Reentra no fim. |

### Comunicação ANTES do paciente pagar
A Lia explica em UMA frase no momento do "Combinado":
> "Antes de te passar a chave, deixa eu te explicar a regra: o sinal é não-reembolsável se
> você cancelar com menos de 24h. Quer prosseguir?"

Aguardar "sim" antes de mandar a chave.

---

## 6. No-show

### Definição
- **No-show**: não compareceu + não avisou.
- **Cancelamento tardio**: avisou com <24h.
- Ambos contam pro `NO-SHOW COUNT`.

### Sanções progressivas

| Contagem | Sanção |
|---|---|
| 1º | Aviso amigável no próximo contato. Sem sanção. |
| 2º | Próximo agendamento exige Reserva Imediata (sem Fila de Encaixe). |
| 3º | Próximo exige pagamento INTEGRAL antecipado + escalonamento humano. |
| 4º | Bloqueio do agendamento online. Só com aprovação direta do médico. |

### Comunicação ao paciente recorrente

Se `NO-SHOW COUNT >= 2`:
> "[Nome], como já tivemos uns ajustes de agenda antes, hoje a reserva é só com adiantamento
> mesmo. Posso te passar a chave do Pix?"

Tom firme mas acolhedor. Não acusar. Não envergonhar.

---

## 7. Campos Kommo (em criação)

A criar manualmente no Kommo UI (task #49):

| Campo | Tipo | Valores |
|---|---|---|
| `SINAL STATUS` | radiobutton | Aguardando solicitação · Solicitado · Pago · Não pago · Devolvido |
| `SINAL VALOR R$` | textarea | Ex: `305,50` |
| `SINAL DATA PIX` | date_time | Timestamp do Pix |
| `SINAL COMPROVANTE` | URL/file | Link do comprovante |
| `NO-SHOW COUNT` | numeric | Incrementa por no-show |
| `MODALIDADE AGENDA` | select | Reserva Imediata · Fila de Encaixe |

Enquanto não existirem, a Lia age conservadoramente: oferece as duas opções, deixa equipe
humana atualizar manualmente.

---

## 8. Lembretes automáticos (Salesbot — separado da Lia)

Configurados no Salesbot Kommo, não na Lia:
- **D-1 às 14h**: lembrete amigável + pedido de confirmação ativa
- **D-0 às 8h**: lembrete final
- **D-0 +30 min após horário marcado**: marca no-show automaticamente

Lia sabe que existem (pra não duplicar) mas não os controla.

---

## 9. Frases de ouro (testadas)

Para apresentar a política:
- "A reserva imediata garante seu horário, e o adiantamento é só metade do valor — o
  restante você paga no dia."
- "Se preferir não adiantar, fica na Fila de Encaixe — assim que abrir vaga compatível,
  te avisamos."
- "O adiantamento não é devolvido se cancelar com menos de 24h — é uma forma de respeitar
  a agenda da Dra. Karla e dos outros pacientes."

Para paciente recorrente:
- "Como já tivemos uns ajustes antes, hoje a reserva é só com adiantamento."

---

## 10. Proibições importantes

- ❌ Lia **não** oferece Reserva Imediata sem mencionar Fila de Encaixe (filtro bloqueia)
- ❌ Lia **não** inventa outras formas de pagamento antecipado (boleto, cartão antecipado)
- ❌ Lia **não** promete reembolso automático em cancelamento tardio
- ❌ Lia **não** ignora `NO-SHOW COUNT` — se ≥2, sem Fila de Encaixe
