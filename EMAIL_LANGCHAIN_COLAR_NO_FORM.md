# Texto pronto pra colar no form de contact-sales da LangChain

> URL: https://www.langchain.com/contact-sales
> Preencher os campos abaixo. Forma rápida: copia e cola.

---

## Campo: First name
```
Fabio
```

## Campo: Last name
```
Martins
```

## Campo: Work email
```
diretoria@blinkoftalmologia.com.br
```

## Campo: Message (cola tudo abaixo)

```
Hi LangChain Solutions team,

I run Blink Oftalmologia — an ophthalmology clinic in Brasília, Brazil. We
operate a production WhatsApp scheduling agent ("Lia") built on Anthropic
Claude Sonnet 4.5 + Haiku 4.5, integrating Kommo CRM, Medware (legacy clinic
software), and WhatsApp Cloud API. ~600 active patient conversations/month,
~150 new scheduled appointments/month via the agent.

We've reached a ceiling using raw Anthropic SDK + custom Python FSM. Specific
pain points where I need architectural guidance:

1. Tool-choice enforcement per FSM state — model writes free text instead
   of invoking 'oferecer_slot' when state=AGENDA, even with LIA_TOOLS_ENABLED=1.
2. Reliable production observability — we built 5 custom pillars but a lead
   was abandoned this morning for 90 minutes without any alert firing.
3. Real-transcript evals — we have 700+ pytest with synthetic inputs but
   no eval pipeline against actual production conversations to catch
   regression at scale.

I'd like to evaluate whether migrating to LangGraph + LangSmith Plus (or
Enterprise) is the right next step, or if our current architecture is
sound and just needs polish.

Specific asks:
- 30-45 min call with a Solutions Engineer for architecture sanity-check
- Cost guidance: starting Plus or Enterprise; we're at ~5-10k traces/month
- Pricing for engineering team training (1 dev + 1-2 contractors)
- Whether LangChain Partner Network has consultants experienced with
  healthcare/clinical-scheduling agents in LATAM

I have a 15-page architecture briefing and a 13-page self-audit report ready
to share over NDA. Production health endpoint:
https://blink-agent.6prkfn.easypanel.host/admin/healthz

Best time to talk: weekdays 14:00–18:00 BRT (UTC-3). I prefer English or
Portuguese; happy with either.

Thanks,
Fábio Philipe Martins
Founder / CEO — Blink Oftalmologia
```

## Demais campos do form

| Campo | Resposta |
|---|---|
| Job title | Founder / CEO |
| Company name | Blink Oftalmologia LTDA |
| Company size | 21-100 |
| Company global headquarters | LATAM |

---

# Tabela de custos esperados (Plus vs Enterprise)

| Item | Developer (grátis) | Plus ($39/seat/mês) | Enterprise (custom) |
|---|---|---|---|
| Traces/mês incluídos | 5k | 10k | Customizado |
| Seats | 1 | Ilimitado | Customizado |
| LangSmith Engine (auto-diagnostic) | ❌ | ✅ ($1.50/LCU) | ✅ via créditos |
| Suporte | Comunidade | Email | SLA + Engenheiro dedicado |
| Treinamento da equipe | ❌ | ❌ | ✅ |
| Architectural guidance | ❌ | ❌ | ✅ |
| Hospedagem (Cloud/VPC) | Cloud US/EU | Cloud US/EU | Cloud/Hybrid/Self-hosted |
| SSO custom | ❌ | ❌ | ✅ |
| Faturamento | Self-serve mensal | Self-serve mensal | Invoice anual |

**Estimativa pro seu caso (600 conversas/mês × ~3-5 traces/conversa = 1800-3000 traces/mês):**

- **Plus** já é suficiente em volume de traces, custaria **~$50-80/mês** (1 seat) — bom pra começar
- **Enterprise** só faz sentido se você quiser:
  - Self-hosting (dados não saem do Brasil) → exigência LGPD/CFM
  - SLA de uptime
  - Treinamento estruturado da equipe
  - Architectural guidance dedicado

---

# Caminho alternativo se Enterprise for caro: LangChain Partner Network

URL: https://www.langchain.com/langchain-partner-network

Partners oficiais (vão te recomendar engenheiros que sabem LangGraph + LangSmith):

1. **Fractional CTOs** que fazem implementação LangGraph profissional
2. **Healthcare-specific consultancies** (raros mas existem)
3. **LATAM partners** (poucos mas crescendo)

Você pode pedir indicação no form acima na seção "Message" — adicione: *"If Enterprise isn't a fit, please connect me with a Partner who can do a paid architecture review + LangSmith setup as a one-off engagement."*

---

# Roteiro pra reunião quando agendarem

Caso eles te liguem (deve ser em 1-2 dias úteis após mandar form):

**Primeiros 5 min — você fala:**
"Briefly: ophthalmology clinic in Brazil, WhatsApp agent built on raw Anthropic SDK + custom FSM, 600 conversations/month. Hit ceiling on tool-calling reliability — model writes free text instead of invoking structured tools. Need architectural guidance whether to migrate to LangGraph or polish what we have."

**Próximos 15 min — você pergunta (use as 5 perguntas do briefing):**
1. Tool-choice enforcement por nó do LangGraph
2. Hierarchical agents (router → specialist) — LangGraph ou deepagents?
3. LangSmith Engine sobre traces brutos (sem anotação humana prévia)
4. State persistence across rajada de mensagens (Redis lock atual)
5. Sandboxes pra dry-run agendamento Medware antes de commit

**Últimos 10 min — eles propõem:**
- Plano sugerido (Plus vs Enterprise)
- Próximo passo concreto (demo, POC, signing)
- Quem é o ponto de contato técnico

**Sinais de alerta a observar:**
- Se eles forçarem Enterprise sem você precisar de SLA/self-hosting → pode estar superdimensionado
- Se eles não souberem responder sobre healthcare compliance LGPD/HIPAA → procurar outro consultor
- Se eles oferecerem só LangGraph sem LangSmith eval → falta a metade da entrega
