# Template Meta WhatsApp Business — Retorno Anual Férias Julho

**Slug proposto:** `1033_retorno_anual_ferias_julho_v1`
**Categoria:** `UTILITY` (não-marketing — é lembrete de protocolo médico)
**Linguagem:** `pt_BR`
**Origem:** Sessão 28/06/2026, requisito Fábio:
> "Nome do contato + nome do paciente + data de nascimento. Acima de 2 anos.
> Consulta anual. Para nova consulta em determinada unidade. E uma pergunta
> gatilho ao final, para reservar agora o seu horário neste período de férias.
> Princípio da escassez."

---

## Versão A — Recomendada (Princípio da escassez baseado em FATO)

### Variáveis

| Var | Conteúdo | Exemplo |
|---|---|---|
| {{1}} | Nome do contato/responsável | Lydia |
| {{2}} | Nome do paciente | Davi |
| {{3}} | Idade (calculada da data nasc) | 9 anos |
| {{4}} | Unidade | Asa Norte |

### Body (em até 1024 chars)

```
Oi, {{1}}! 😊

Aqui é a Ariany, da Blink Oftalmologia. Estou organizando a agenda da
Dra. Karla Delalíbera de julho/2026 e vi aqui que o {{2}} ({{3}}) chegou
a hora da próxima consulta.

Estamos em pleno período de férias escolares e nossa agenda na unidade
{{4}} fecha rápido — famílias aproveitam o recesso pra evitar falta na
escola. Restam poucos horários neste mês.

Quer que eu reserve um horário pro {{2}} agora antes de fechar a agenda
de julho?
```

### Buttons (Quick Reply)

1. `Sim, reservar agora` (payload: `RESERVAR_JULHO`)
2. `Ver outras datas` (payload: `VER_OUTRAS`)

### Footer

```
Blink Oftalmologia · Asa Norte e Águas Claras
```

---

## Versão B — Mais curta (caso UTILITY exigir conciso)

```
{{1}}, oi! 😊

Aqui é a Ariany, da Blink Oftalmologia. A consulta anual do {{2}} ({{3}})
está no ponto de retorno — a Dra. Karla Delalíbera acompanha o
desenvolvimento visual nessa idade.

Férias escolares (julho/2026) é nosso período mais procurado em {{4}} —
agenda fecha rápido. Posso reservar um horário pro {{2}} agora?
```

### Buttons

1. `Sim, reservar julho`
2. `Falar com atendente`

---

## Versão C — Tom mais técnico (princípio da autoridade reforçado)

```
{{1}}, boa tarde 🌿

Aqui é a Ariany, da equipe da Dra. Karla Delalíbera (Blink Oftalmologia).
O {{2}}, hoje com {{3}}, já está no período recomendado pela
oftalmopediatria pra consulta anual — janela importante pra detectar
ametropias ainda em fase de adaptação.

Como julho/2026 concentra a maior demanda do ano (férias escolares), os
horários da unidade {{4}} se esgotam nas primeiras semanas.

Posso garantir agora um horário pro {{2}} antes que a agenda de julho
feche?
```

### Buttons

1. `Reservar horário julho`
2. `Quero ver alternativas`

---

## Princípios psicológicos aplicados (Cialdini)

| Princípio | Aplicação |
|---|---|
| **Escassez genuína** | Férias escolares = pico de demanda real (não é gatilho fake) |
| **Autoridade** | Menciona Dra. Karla Delalíbera + protocolo oftalmopediátrico |
| **Personalização** | Nome contato + nome paciente + idade calculada + unidade específica |
| **Urgência temporal** | "Agenda fecha rápido", "antes que a agenda de julho feche" |
| **Compromisso/coerência** | Lembra que paciente já é cliente da Blink (retorno) |
| **Reciprocidade implícita** | "Posso reservar AGORA pra você" — Blink se compromete primeiro |

---

## Regras Meta a respeitar

- ✅ Não usa emojis em excesso (máx 1-2 por mensagem)
- ✅ Não promete agendamento sem coleta de dados (só "posso reservar?")
- ✅ Variáveis numeradas {{1}} a {{4}}, sequenciais
- ✅ Não menciona promoção/preço/desconto
- ✅ CTAs claros via Quick Reply Buttons (não link externo)
- ✅ Categoria UTILITY (lembrete sobre paciente existente, não captação fria)
- ✅ Body < 1024 caracteres
- ✅ Footer < 60 caracteres

---

## JSON pronto pra submissão (Meta WhatsApp Business API)

### Versão A — JSON completo

```json
{
  "name": "1033_retorno_anual_ferias_julho_v1",
  "language": "pt_BR",
  "category": "UTILITY",
  "components": [
    {
      "type": "BODY",
      "text": "Oi, {{1}}! 😊\n\nAqui é a Ariany, da Blink Oftalmologia. Estou organizando a agenda da Dra. Karla Delalíbera de julho/2026 e vi aqui que o {{2}} ({{3}}) chegou a hora da próxima consulta.\n\nEstamos em pleno período de férias escolares e nossa agenda na unidade {{4}} fecha rápido — famílias aproveitam o recesso pra evitar falta na escola. Restam poucos horários neste mês.\n\nQuer que eu reserve um horário pro {{2}} agora antes de fechar a agenda de julho?",
      "example": {
        "body_text": [
          ["Lydia", "Davi", "9 anos", "Asa Norte"]
        ]
      }
    },
    {
      "type": "FOOTER",
      "text": "Blink Oftalmologia · Asa Norte e Águas Claras"
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Sim, reservar agora"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Ver outras datas"
        }
      ]
    }
  ]
}
```

---

## Filtros de elegibilidade pro disparo

Pra evitar disparar pra paciente errado:

| Filtro | Valor | Por quê |
|---|---|---|
| Status pipeline | `0-ETAPA ENTRADA (96441724)` | Lead na entrada, sem agendamento ativo |
| Campanha | `Julho/2026 (cf 1260440 enum 927043)` | Marcado pela equipe pra essa campanha |
| 1.DATA NASCIMENTO | preenchida E idade ≥ 2 anos | Acima de 2 anos = anual (regra Dra. Karla) |
| 1.PRÓX CONSULTA | `Julho 2026` OU vazio | Protocolo médico já apontou Julho |
| Última consulta Medware | > 10 meses atrás | Janela retorno anual + tolerância |
| ATIVADO IA? | `Ativado` ou `Solicitado` | Não disparar se humano desativou |

---

## Cálculo automático da idade (var {{3}})

Script `SYNC_KOMMO_MEDWARE_JUL2026.py` já tem 1.DATA NASCIMENTO em ISO.
Converter pra texto humano:

```python
from datetime import datetime, timezone, timedelta
BRT = timezone(timedelta(hours=-3))

def idade_texto(iso_nasc: str) -> str:
    nasc = datetime.fromisoformat(iso_nasc).replace(tzinfo=BRT)
    hoje = datetime.now(BRT)
    anos = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
    if anos < 1:
        meses = (hoje.year - nasc.year) * 12 + (hoje.month - nasc.month)
        return f"{meses} meses"
    if anos == 1:
        return "1 ano"
    return f"{anos} anos"
```

---

## Próximos passos (operacional)

1. **Aprovação Fábio** da versão A/B/C escolhida.
2. **Submissão Meta** via Business Manager (WABA ID Blink). Cat UTILITY costuma aprovar em 1-24h.
3. **Slug do template aprovado** → plugar em `voice_agent/templates_meta.py` (campo `TEMPLATE_RETORNO_ANUAL_FERIAS_JULHO`).
4. **Disparo via endpoint** `/admin/disparar-batch` filtrando os 51 leads JUL2026 já sincados.
5. **Aguardar resposta** dos pacientes — Lia entra em conversa com ctx já preenchido (dia consulta anterior, médico, unidade, convênio) → ofereta 2 slots imediatos do Medware → grava agendamento autônomo (fix #208).
