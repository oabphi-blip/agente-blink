# POLÍTICA DE SINAL, REMARCAÇÃO E NO-SHOW

> Complementa os artigos **15** (pagamento pós-consulta) e **36** (reserva imediata 50% / fila de encaixe — Karla sem convênio). Aplica-se a **Dra. Karla Delalíbera** (atendimento sem convênio) e — quando o paciente optar por sinal — também a **Dr. Fabrício Freitas** (avaliação cirúrgica de catarata, R$ 297). NÃO se aplica a consultas com convênio (artigo 13) nem retornos no prazo (artigo 09).

## 1. QUANDO COBRAR SINAL

### 1.1. Casos com sinal opcional (paciente escolhe)
- **Dra. Karla Delalíbera — Sem convênio (rotina/pediatria/Avaliação do Processamento Visual)** — Paciente escolhe entre:
  - **Reserva Imediata 50%** → adianta metade via Pix, garante o slot exato.
  - **Fila de Encaixe** → sem adiantamento, paga no dia, agenda fica em standby.
- **Dr. Fabrício Freitas — Avaliação Catarata (R$ 297)** — mesmo critério: Reserva Imediata (50% = R$ 148,50) ou Fila de Encaixe.

### 1.2. Casos SEM sinal (obrigatoriamente)
- Consulta com convênio aceito (artigo 17) — não há cobrança nenhuma antecipada.
- Retorno dentro de 15 dias úteis (artigo 09) — cortesia.
- Mapeamento de retina da Dra. Kátia pré-cirurgia de catarata, se contrato com Fabrício foi assinado (artigo 19 §C).

### 1.3. Casos com sinal OBRIGATÓRIO (sem opção de fila)
- Paciente com **2+ no-shows registrados** no Kommo → exigir Reserva Imediata 50% (não oferecer Fila de Encaixe).
- Paciente com **3+ no-shows** → exigir **pagamento INTEGRAL antecipado** e escalar para a equipe humana antes de confirmar.
- Avaliação do Processamento Visual (R$ 800 Karla) — pode ter sinal opcional, mas dado o valor alto, sempre apresentar Reserva Imediata como recomendada.

## 2. VALORES DE SINAL (50% da consulta)

| Modalidade | Valor cheio | Sinal 50% |
|---|---|---|
| Karla — Oftalmologia/Pediatria/Rotina | R$ 611,00 | **R$ 305,50** |
| Karla — Avaliação do Processamento Visual | R$ 800,00 | **R$ 400,00** |
| Fabrício — Avaliação Catarata | R$ 297,00 | **R$ 148,50** |

⚠️ O valor exato é sempre `valor_cheio / 2` arredondado a 2 casas. Nunca improvisar outro valor.

## 3. DADOS DE COBRANÇA (FONTES OFICIAIS)

### 3.1. Asa Norte (Dra. Karla Delalíbera / Dr. Fabrício Freitas)
- **Chave Pix:** `karladelaliberaoftalmo@gmail.com`
- Tipo: e-mail (chave pessoal — verificada e ativa)

### 3.2. Águas Claras (Dra. Karla Delalíbera / Dr. Fabrício Freitas)
- **Chave Pix:** `52.303.729/0001-30`
- Tipo: CNPJ da clínica

❌ **PROIBIDO inventar qualquer outra chave Pix.** Se a unidade do paciente não couber em 3.1 ou 3.2, escalar para humano.

## 4. FLUXO DE CONFIRMAÇÃO DO SINAL

```
[paciente escolhe Reserva Imediata]
      ↓
1. Lia envia: chave Pix + valor exato + prazo de 30 min para o comprovante
      ↓
2. Paciente envia comprovante via WhatsApp
      ↓
3. Equipe humana valida o comprovante (não é a Lia — bate olho humano)
      ↓
4. Kommo: campo SINAL STATUS = "Pago" + SINAL DATA PIX preenchido
      ↓
5. Lia confirma: "Recebido! Sua vaga está garantida em [dia/hora]."
```

### 4.1. Prazo de validade da solicitação de sinal
- Após Lia enviar a chave, paciente tem **30 minutos** para enviar o comprovante.
- Se passou 30 min sem comprovante → vaga **volta para a agenda** e Lia avisa: "O prazo de 30 min expirou. Quer pagar agora ou prefere a Fila de Encaixe?".

### 4.2. Caso o paciente envie o comprovante depois do prazo
- Se a vaga ainda estiver disponível → aceitar.
- Se a vaga já tiver sido remanejada → oferecer próximas vagas.

## 5. POLÍTICA DE REMARCAÇÃO

| Janela | Sinal pago anteriormente | Regra |
|---|---|---|
| **>48h antes** da consulta | Sim | Remarca sem custo. Sinal migra automaticamente para a nova data. |
| **>48h antes** | Não | Remarca sem custo (estava em Fila de Encaixe). |
| **24–48h antes** | Sim | Remarca com **cobrança de NOVO sinal** (sinal anterior fica retido — paciente paga 50% de novo). |
| **24–48h antes** | Não | Remarca sem custo. |
| **<24h antes** ou **no-show** | Sim | **Sinal NÃO é devolvido.** Para reagendar, paga sinal cheio na nova vaga. |
| **<24h antes** ou **no-show** | Não | Paciente perde a posição na Fila de Encaixe. Pode reentrar mas no fim da fila. |

### 5.1. Como comunicar a política ANTES do paciente pagar
A Lia deve apresentar esta política em UMA frase curta no momento do "Combinado", ANTES de pedir o Pix:

> "Antes de te passar a chave, deixa eu te explicar a regra: o sinal é não-reembolsável se você cancelar com menos de 24h. Quer prosseguir?"

Aguardar resposta. Só prosseguir se for "sim".

## 6. POLÍTICA DE NO-SHOW

### 6.1. Definição
- **No-show**: paciente não comparece e não avisa.
- **Cancelamento tardio**: paciente avisa com menos de 24h.
- Os dois são contados juntos no campo `NO-SHOW COUNT`.

### 6.2. Sanções progressivas
- **1º no-show**: aviso amigável no próximo contato. Sem sanção.
- **2º no-show**: exigência de Reserva Imediata (sem opção de Fila de Encaixe) no próximo agendamento.
- **3º no-show**: pagamento INTEGRAL antecipado obrigatório. Escalar para equipe humana antes de confirmar.
- **4º no-show**: bloqueio do agendamento online. Só atendimento via aprovação direta do médico.

### 6.3. Como a Lia comunica em caso de paciente recorrente
Quando o lead Kommo tiver `NO-SHOW COUNT` ≥ 2, a Lia deve mencionar de forma natural (sem tom de cobrança):

> "[Nome], como já tivemos uns ajustes de agenda antes, hoje a reserva é só com adiantamento mesmo. Posso te passar a chave do Pix?"

## 7. CAMPOS DO KOMMO RELACIONADOS

| Campo | Tipo | Valores |
|---|---|---|
| `SINAL STATUS` | radiobutton | 🟡 Aguardando solicitação · 🟠 Solicitado · 🟢 Pago · 🔴 Não pago · ⚫ Devolvido |
| `SINAL VALOR R$` | text | Ex.: `305,50` |
| `SINAL DATA PIX` | date_time | Quando o Pix foi confirmado |
| `SINAL COMPROVANTE` | URL/file | Link/anexo do comprovante |
| `NO-SHOW COUNT` | numeric | Contador automático |
| `MODALIDADE AGENDA` | select | Reserva Imediata · Fila de Encaixe |

(Esses campos estão em criação — consultar a estrutura no Kommo antes de assumir valores. Se um campo ainda não existir, Lia age conservadoramente: oferece as opções do artigo 36 e deixa a equipe humana atualizar manualmente.)

## 8. LEMBRETES AUTOMÁTICOS (SALESBOT KOMMO)

Configurados separadamente no Salesbot — não são responsabilidade da Lia, mas a Lia deve saber que existem para não duplicar:

- **D-1 às 14h**: lembrete amigável + pedido de confirmação ativa.
- **D-0 às 8h**: lembrete final.
- **D-0 +30 min do horário**: marca no-show automaticamente.

## 9. PROIBIÇÕES IMPORTANTES

- ❌ Lia **NÃO oferece** Reserva Imediata 50% **sem mencionar** a Fila de Encaixe como alternativa (regra do artigo 36).
- ❌ Lia **NÃO inventa** outras formas de pagamento antecipado (boleto, cartão antecipado, transferência) — só Pix nas chaves de 3.1 e 3.2.
- ❌ Lia **NÃO promete reembolso** automático em caso de cancelamento tardio — a regra é não-reembolsável <24h.
- ❌ Lia **NÃO ignora** o `NO-SHOW COUNT` do lead — se ≥2, NÃO oferece Fila de Encaixe.

## 10. ÂNCORA DE COMUNICAÇÃO (FRASES DE OURO)

Use estas frases (ou variações próximas) — testadas para soar firmes mas acolhedoras:

- "A reserva imediata garante seu horário, e o adiantamento é só metade do valor — o restante você pode pagar no dia."
- "Se preferir não adiantar, fica na Fila de Encaixe — assim que abrir vaga, te avisamos."
- "O adiantamento não é devolvido se você cancelar com menos de 24h — é uma forma de respeitar a agenda da Dra. Karla Delalíbera e dos outros pacientes."
- "Como já tivemos uns ajustes antes, hoje a reserva é só com adiantamento."

---

**Resumo de uma linha:** Sinal de 50% é opcional (Reserva Imediata vs Fila de Encaixe), não-reembolsável <24h, chaves Pix oficiais por unidade, sanções progressivas por no-show. Lia sempre apresenta AS DUAS opções antes de pedir Pix.
