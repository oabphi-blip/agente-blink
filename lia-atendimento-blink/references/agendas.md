# Agendas dos Médicos por Unidade

> Referência rápida pra cruzar "dia da semana" com "médico atende ou não nessa unidade".
> Quando o paciente pede dia que o médico não atende, use a regra de oferecer a outra
> unidade.

---

## Dra. Karla Delalíbera (codMedico = 12080)

### Asa Norte (codUnidade = 5)
- **Segunda-feira**
- **Quarta-feira**
- **Sexta-feira**
- Primeiro horário típico:
  - Segundas: tende a abrir a partir das 10:00 ou 11:00 (não tem matinal cedo).
  - Quartas/sextas: primeiro horário às 08:30 quando há.

### Águas Claras (codUnidade = 3)
- **Terça-feira**
- **Quinta-feira**
- Eventuais **sábados** (Agenda Extra)
- Primeiro horário típico: 08:30 (matinal cedo)

### Regra de transferência de unidade
Quando paciente pede dia que Karla NÃO atende na unidade escolhida, OFERECER a outra
unidade:

> Paciente: "Quero terça em Asa Norte com a Dra. Karla"
> Lia: "Na Asa Norte a Dra. Karla atende seg/qua/sex. Em Águas Claras ela atende terça e
> quinta. Você prefere mudar pra Águas Claras na terça, ou ficar em Asa Norte numa segunda?"

---

## Dr. Fabrício Freitas (codMedico = 12081)

### Águas Claras (codUnidade = 3) — exclusivamente
- **Segunda-feira (tarde)** — avaliação cirúrgica
- **Sexta-feira (manhã)** — avaliação cirúrgica

Atendimento de Fabrício é principalmente catarata e lentes intraoculares. Não tem agenda em
Asa Norte. Se paciente pedir Asa Norte → única opção é Águas Claras.

---

## Dra. Kátia Delalíbera

### Asa Norte (codUnidade = 5)
- Agenda específica (consultar Medware via `horarios_disponiveis` com codMedico da Kátia)
- Foco em pré-operatório de catarata (mapeamento de retina)

### Regra de isenção
Consulta da Kátia é **isenta** se paciente já assinou contrato de cirurgia de catarata com
Fabrício e pagou a primeira parcela. Apresentar como:
> "A consulta com a Dra. Kátia pro mapeamento de retina é R$ 611. Esse valor é isento (ou
> reembolsado) caso você feche a cirurgia com o Dr. Fabrício e pague a primeira parcela —
> na prática, o mapeamento entra como cortesia dentro do pacote cirúrgico."

---

## Tabela rápida (cruzamento)

| Dia | Karla Asa Norte | Karla Águas Claras | Fabrício Águas Claras |
|---|---|---|---|
| Segunda | ✅ | ❌ | ✅ tarde |
| Terça | ❌ | ✅ | ❌ |
| Quarta | ✅ | ❌ | ❌ |
| Quinta | ❌ | ✅ | ❌ |
| Sexta | ✅ | ❌ | ✅ manhã |
| Sábado | raro | Agenda Extra | ❌ |

---

## Janela de oferta dinâmica

O `responder.py` injeta no system prompt o bloco `JANELA DE OFERTA DE AGENDA` com os
próximos 5 dias úteis calculados pelo `_offer_window_block()`. Isso garante que a Lia
**nunca** oferece data fora da janela e nunca inventa dia da semana.

Sábados que caiam no intervalo são listados separadamente como "Agenda Extra de sábado".

### Regras vinculadas

1. Só oferecer datas da lista injetada.
2. NUNCA calcular/deduzir/inventar dia da semana.
3. Citar sempre dia-da-semana + data juntos (ex.: "quarta-feira, 04/06/2026").
4. Cruzar com agenda do médico (tabela acima).
5. Se paciente pedir fora da janela: oferecer as datas da janela e perguntar.
6. Horário exato (HH:MM) vem do Medware (`horarios_disponiveis`), não inventar.

---

## Códigos de procedimento típicos

| codProcedimento | Descrição | Plano |
|---|---|---|
| `303` | Consulta Particular Dra. Karla | Particular Básico |
| `308` | Consulta em consultório (Particular) | Particular Básico |
| `15` | Retorno (gratuito até 15 dias) | Particular Básico |
| `13` | Consulta em consultório (convênio) | Convênio Básico |
| `302` | `<<CONVENIO AGUAS CLARAS>>` | Saúde Caixa Básico |
| `14` | `<<AGRUPADOR>>` | TJDFT Direto Básico |

Use `308` como default pra consulta particular nova quando não tiver procedimento
específico definido.
