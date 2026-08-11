# Modelos pré-férias escolares julho 2026 — Princípio da Escassez

Origem: pedido Fábio 25/06/2026 (reformulação 25/06).
Objetivo: ativar leads aproveitando o gatilho real de **férias escolares (DF: 04/07 a 27/07)** + escassez de horários, garantindo que o paciente programe e tenha CHOICE em vez de aceitar o que sobrar.

**Princípio da escassez ético embutido:**
- Verdade sobre demanda alta no período (não inventa pressão)
- "Quem agenda primeiro escolhe; quem espera fica com o que sobra"
- Mostrar contagem real de slots quando possível
- Frase canônica de 10 min de reserva (regra E6-B)

**Regras embutidas:**
- Dra. Karla Delalíbera (sempre com sobrenome)
- Dr. Fabrício Freitas (sempre com sobrenome)
- Sem "horário comercial 8h-18h"
- Oferta de 2 slots concretos
- Apresentação clara: convênio OU particular (regra C-41)

---

## Por que esse gatilho funciona em julho

| Quem | Por que agenda agora |
|---|---|
| **Pais (Crianças 3-12)** | Férias escolares = filhos disponíveis pra consulta sem faltar aula |
| **Mães (Bebês 0-2)** | Rotina mais flexível, dá pra levar bebê sem corrida |
| **Adultos que viajam** | Querem fechar check-up ANTES de viajar |
| **Pacientes pós-op catarata (Fabrício)** | Retorno marcado pra avaliar antes da rotina normal voltar |
| **Profissionais com filhos** | Conseguem horários junto com os filhos no mesmo dia |

---

## 1️⃣ Template Meta WhatsApp (estrutura pra submeter aprovação)

**Nome sugerido:** `1032_ferias_escolares_garanta_horario_v1`

**Categoria Meta:** UTILITY

**Body APROVADO Fábio 25/06/2026** (versão final, removida a frase de "10 minutos de reserva" — Lia menciona no follow-up):

```
{{1}}, as férias escolares estão chegando (de {{2}} a {{3}}) e a agenda da Dra. Karla Delalíbera costuma encher rápido nesse período — famílias inteiras aproveitam o recesso pra agendar a consulta dos filhos e dos pais no mesmo dia.

Pra você garantir o melhor horário pra família, separei dois ainda livres na nossa unidade {{4}}:

1️⃣ {{5}}
2️⃣ {{6}}

Aproveita: dá pra trazer crianças e adultos no mesmo período — sem precisar voltar outra vez.

Qual dos dois prefere?
```

**Status:** ✅ aprovado pelo Fábio em 25/06/2026.
**Próximo passo:** submeter ao Meta Business pra aprovação técnica (24-72h).

**Mapping de variáveis (6 vars, dentro do limite Meta de 10):**

| Var | Valor exemplo | Origem do dado |
|---|---|---|
| `{{1}}` | Nome do contato | `1.NOME PACIENTE` ou contato principal |
| `{{2}}` | "04/07" | calendário escolar DF 2026 (confirmar com secretaria) |
| `{{3}}` | "27/07" | calendário escolar DF 2026 |
| `{{4}}` | "Asa Norte" ou "Águas Claras" | campo `UNIDADE` (1245125) do lead |
| `{{5}}` | "Quarta 02/07 às 10:30" | Medware horários reais |
| `{{6}}` | "Sexta 04/07 às 09:00" | Medware horários reais |

**Atenção sobre nome do médico:**
- Dra. Karla Delalíbera fica **FIXA no body** (não é variável).
- Esse template é EXCLUSIVO Karla. Se quiser disparar pro Dr. Fabrício Freitas, usar variante 5 deste mesmo doc.
- Templates separados por médico aprovam mais rápido no Meta (categoria UTILITY clara).

**Botões (3 quick replies):**
- `QUERO O 1`
- `QUERO O 2`
- `OUTRO DIA`

**Variante adulto solo (caso lead claramente sem filhos):** se preferir 2 templates (família vs solo), submete também `1033_ferias_escolares_garanta_horario_solo_v1` com o mesmo body sem a frase "trazer crianças e adultos no mesmo período". Roteamento usa `1.PERFIL` pra decidir qual disparar.

---

## 2️⃣ Texto livre — janela 24h aberta (Lia em conversa)

Pra leads que JÁ respondem nas últimas 24h. Mais natural.

```
{{Nome}}, as férias escolares de julho já estão batendo na porta (começam dia 04/07) e a agenda da Dra. Karla Delalíbera enche bem rápido nesse período — pais inteiros aproveitam pra colocar a consulta dos filhos em dia.

Pra você não ficar dependendo do que sobrar, separei dois horários que ainda dá pra fechar:

1️⃣ Quarta 02/07 às 10:30 — Águas Claras
2️⃣ Sexta 04/07 às 09:00 — Asa Norte

Os dois ficam reservados pra você por 10 minutos. Quer um deles ou prefere outro dia? Quanto antes a gente fecha, mais opção você tem.
```

---

## 3️⃣ Variante CONVÊNIO ACEITO — escassez + plano facilita

Pra leads com `CONVENIO` definido E aceito (não Inas, GDF, Bradesco, SulAmerica).

```
{{Nome}}, vi aqui que você atende pelo {{Convênio}} — esse plano tem cobertura integral com a Dra. Karla Delalíbera.

Estamos chegando nas férias escolares (04/07 a 27/07), e julho é o mês que mais lota nossa agenda — famílias inteiras marcam consulta nesse período.

Pra garantir o melhor horário pra sua rotina, dois ainda livres:

1️⃣ Quarta 02/07 às 10:30 — Águas Claras
2️⃣ Quinta 03/07 às 14:00 — Asa Norte

Pra firmar a reserva, me manda a foto da carteirinha + RG (ou certidão se for menor que 16) — eu já autorizo antes do dia.

Qual dos dois?
```

---

## 4️⃣ Variante PARTICULAR (regra C-41 + escassez)

Pra leads sem convênio aceito. Apresenta as 2 trilhas mostrando que quem decide primeiro escolhe.

```
{{Nome}}, julho é nosso mês mais cheio — férias escolares + recesso de meio de ano fazem a agenda fechar antes do esperado.

Pra você ainda ter opção de escolha, dois horários particulares com a Dra. Karla Delalíbera:

1️⃣ Quarta 02/07 às 10:30 — Águas Claras
2️⃣ Sexta 04/07 às 09:00 — Asa Norte

Consulta = R$ 670. Pra firmar a reserva você tem duas trilhas:

🔒 *Reserva imediata* — adiantamento de 50% via Pix (R$ 335). Garante seu horário, sem disputa. Chave: karladelaliberaoftalmo@gmail.com

📋 *Fila de encaixe* — sem adiantamento. Você fica na lista, mas vai pegando a vaga que sobrar (se sobrar).

Qual horário e qual modalidade?
```

---

## 5️⃣ Variante FABRÍCIO catarata 50+ (escassez + saúde)

Adultos 50+ — argumento de prevenção + agenda apertada.

```
{{Nome}}, a partir dos 50 a oftalmologia preventiva fica essencial — catarata começa nessa faixa e quanto antes diagnostica, melhor o resultado.

Estamos entrando no período de férias escolares (04/07 a 27/07), e o Dr. Fabrício Freitas costuma ter agenda apertada no julho porque muitos pacientes adiantam check-up antes das viagens.

Dois horários ainda disponíveis:

1️⃣ Terça 01/07 às 09:40 — Águas Claras
2️⃣ Quinta 03/07 às 10:20 — Asa Norte

Consulta R$ 297. Pagamento no dia ou Pix antecipado (50% de sinal se preferir reservar com 100% de garantia).

Qual prefere?
```

---

## 6️⃣ Variante PEDIÁTRICA (pais — argumento de escassez familiar)

Pra leads pediátricos (Bebê 0-2 ou Criança 3-12) — gatilho família + rotina escolar.

```
{{Nome}}, as férias escolares começam 04/07 e a nossa agenda pediátrica fecha primeiro nesse período — pais aproveitam que filhos não têm aula pra colocar a consulta em dia.

Pra você não correr atrás de horário em cima da hora, dois ainda disponíveis com a Dra. Karla Delalíbera:

1️⃣ Quarta 02/07 às 10:30 — Águas Claras
2️⃣ Quinta 03/07 às 14:00 — Asa Norte

Se preferir manhã ou tarde específico, me passa que ajusto. Os horários ficam reservados por 10 minutos depois que você escolher.

Qual dos dois?
```

---

## Padrões de escassez usados (todas as variantes)

Cada mensagem usa pelo menos 2 destes 5 mecanismos:

1. **Tempo de janela explícito** — "férias escolares 04/07 a 27/07"
2. **Razão social plausível** — "pais aproveitam o recesso", "famílias inteiras marcam"
3. **Comparação implícita** — "quem agenda primeiro escolhe, quem espera pega o que sobra"
4. **Limite de tempo** — "10 minutos de reserva" (E6-B)
5. **Identificação de identidade** — "pra sua rotina", "rotina escolar", "pais ocupados"

Tudo VERDADE — não inventa pressão. Princípio da escassez ético.

---

## Critérios de envio (Lia em prod ou batch manual)

### Quem RECEBE:

```sql
WHERE
  ATIVADO_IA = 'Ativado'
  AND status_id IN (101508307, 106184631)  -- 2.LEADS FRIO ou 4.REAGENDAR
  AND (1.MÊS_PRÓX_CONSULTA IS NULL OR 1.MÊS_PRÓX_CONSULTA <= 'Julho 2026')
  AND (1.DIA_CONSULTA IS NULL OR 1.DIA_CONSULTA < NOW())
  AND CONVÊNIO NOT IN ('Inas GDF', 'SulAmerica', 'Bradesco', 'Cassi')
  AND ULTIMA_MENS_LIA < NOW() - INTERVAL '24 hours'
```

### Roteamento por perfil:

| Perfil paciente | Variante |
|---|---|
| `1.PERFIL = 'Bebê 0-2'` ou `'Criança 3-12'` | 6 (Pediátrica) |
| `1.PERFIL = 'Adulto 19-49'` + convênio aceito | 3 (Convênio) |
| `1.PERFIL = 'Adulto 19-49'` + sem convênio | 4 (Particular) |
| `1.PERFIL = 'Adulto 50+'` ou motivo catarata | 5 (Fabrício 50+) |

---

## Cronograma sugerido (26/06 a 04/07)

| Data | Ação | Cap |
|---|---|---|
| Qui 26/06 | Submeter template `1032_ferias_escolares_garanta_horario_v1` ao Meta | — |
| 27-28/06 | Aprovação Meta (24-72h) | — |
| Dom 29/06 | Validar datas escolares com a secretaria (DF férias 04/07?) | — |
| Seg 30/06 | Batch 1 — Pediátrico convênio (variante 6) | 80 |
| Ter 01/07 | Batch 2 — Adulto convênio (variante 3) | 80 |
| Qua 02/07 | Batch 3 — Adulto particular (variante 4) | 80 |
| Qui 03/07 | Batch 4 — Fabrício 50+ (variante 5) | 80 |
| Sex 04/07 | Batch 5 — 4.REAGENDAR | 80 |

**Total estimado:** 400 leads ativados.

---

## Métricas a monitorar

- Taxa de resposta em 24h (alvo: **≥35%** — gatilho de escassez sobe vs 30% padrão)
- Conversão "responde → fecha slot" (alvo: ≥45%)
- Slots fechados até 11/07 (semana 1 de férias)
- Reservas particulares: % com sinal Pix vs Fila de Encaixe (alvo: 65% Pix — escassez aumenta sinal)
- Bounce Meta (alvo: ≤1%)

---

## Pendências antes do disparo

1. ✅ Confirmar **calendário escolar DF 2026** (04/07 a 27/07 — provável, mas valida com secretaria)
2. **Submeter template ao Meta** — variante 1 (24-72h pra aprovação)
3. **Renovar KOMMO_TOKEN** (item 0017 do `#bugs-agent`) pra notas Kommo gravarem
4. **Confirmar férias dos médicos** — pode haver overlap (Karla em férias parcial, Fabrício escala diferente)
5. **Aprovação Karla** — texto sai em nome dela, ela precisa ler antes (cosmoética)
6. **Pré-filtrar leads elegíveis** via SQL ou export Kommo
