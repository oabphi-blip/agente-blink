# Arquitetura reversa — 40 agendamentos/dia

Meta: **40 agendamentos confirmados por dia útil** (240/semana × 4 semanas = ~960/mês).

## Cálculo reverso (taxa de conversão observada)

Dados reais Blink (últimos 30 dias, amostra Top 30 captação):
- **Captação → Agendado**: 80% (24 de 30 leads já viraram consulta marcada ou realizada)
- **Reativação fria → Resposta**: 17–25% (dado nacional para reativação WhatsApp template)
- **Resposta → Agendamento**: 35–50% (paciente que responde já tá quente)

Então pra agendar **40/dia**, precisa receber **40 pacientes engajados/dia** no topo do funil:

| Estágio | Taxa observada | Volume necessário |
|---|---|---|
| Agendamento confirmado | 100% | **40** |
| Resposta engajada (paciente quer marcar) | 50% → agendamento | **80** |
| Mensagem disparada (reativação ou contato novo) | 25% → resposta | **320** |
| Lead na fila ativável | 100% → mensagem | 320 |

**Conclusão**: pra atingir 40 agendamentos/dia, motor precisa disparar **320 mensagens/dia** (com taxa 25% resposta + 50% conversão).

## Gap atual vs meta

| Métrica | Hoje (28/05) | Meta | Gap |
|---|---|---|---|
| daily_cap motor | 200 | 320 | +120 |
| min_interval_min | 4 | 3 | -1 min |
| Horário ativo | 8h-18h (10h) | mesmo | OK |
| Taxa resposta | ? | 25% | ligar Slack log pra medir |
| Taxa resposta→agendamento | ? | 50% | medir via Kommo (lead saiu de 2-AGENDAR pra 4-AGENDADO em X dias) |

**3 ações pra fechar o gap:**

1. **Subir daily_cap 200 → 320** (5 min — mesma rota Easypanel)
2. **Ligar Slack log + medir conversão real** (10 min — webhook URL)
3. **Reduzir min_interval 4 → 3 min** (5 min — Easypanel ENV)

Com isso e tier Meta WhatsApp suficiente (250+/dia), o motor cobre 320 disparos em 10h úteis. Margem de segurança: 320 disparos / (600 min / 3 min) = 200 slots de execução = OK.

## Pré-requisitos críticos não-codáveis

1. **Tier Meta WhatsApp Business**: contas novas têm limite de 250 conversas iniciadas/24h. Pra 320 precisa subir tier (formulário Meta Business Suite → "Aumentar limite"). Aprovação em 1-3 dias.

2. **Crédito Anthropic suficiente**: 320 disparos + ~80 respostas × ~5 turnos cada × ~3000 tokens médio = ~1.2M tokens/dia. Custo Sonnet 4.5: ~US$3-5/dia. **Manter auto-recharge ligado** com mínimo US$50.

3. **Slots reais disponíveis no Medware**: 40 agendamentos/dia × 30 min cada = 20h de atendimento/dia entre Karla + Fabrício. Karla 8h + Fabrício 8h = 16h. **Gap de 4h/dia** — precisa contratar 3º médico ou estender horário.

## Camadas em construção pra otimizar

| Camada | Status | Impacto |
|---|---|---|
| Reativação 24h | LIVE (cap 200) | Base operacional |
| Nota auto + ATIVADO IA? | LIVE (commit 1e3bf01) | Linha contínua Kommo |
| Dedup fallback instabilidade | DEPLOY pendente (commit 1143504) | Não repetir erros |
| Slack log disparos | aguarda webhook URL | Visibilidade |
| Painel "gap amanhã" | a fazer | Reativação focada em slots vazios |
| Meta Lead Form direto Kommo | a fazer | Captação automática |
| Pytest cenários | a fazer | Não regredir |

## Decisões pendentes pro Fábio

1. **Subir cap pra 320?** (precisa confirmar tier Meta primeiro)
2. **Criar Slack webhook?** (canal #ativação-de-leads-de-forma-continua)
3. **Quem cobre os 4h/dia de gap médico?** (Karla extra, Fabrício extra ou novo)

Última atualização: 28/05/2026
