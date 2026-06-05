# Plano de Ativação — LEADS FRIO para Agenda 08/06/2026 (segunda)

Data: 04/06/2026 (sessão Cowork)
Objetivo: completar agenda Dra. Karla Delalibera / Asa Norte do dia 08/06 (segunda) com leads frios já em pipeline.

---

## 1. Universo coletado

Pipeline ATENDE (8601819) → etapa **2.LEADS FRIO** (status_id=101508307).
Screenshot Kommo mostrou: **368 leads** nesta etapa, com 68 sinalizados (top do funil) como prioritários pelo Fábio.

Tooling: `kommo_search_leads` filtrando por nome ("FRIO", "CAPTAÇÃO ATIVA", "AGENDAR ROTINA").
Amostra processada: 59 leads em LEADS FRIO, categorizados pelo nome.

## 2. Convênios NÃO aceitos pela Blink (excluir do disparo)

Fonte: CLAUDE.md seção 15 + KB artigo 18.

| Convênio | Tratamento |
|---|---|
| Inas GDF | Não aceito — paciente deve buscar prestador direto OU vir como Particular |
| Cassi | Não aceito (sem cobertura ativa) |
| SulAmérica | Não aceito |
| Bradesco | Não aceito |
| (qualquer outro fora dos 26 mapeados em PLANO_CODES) | Não aceito |

## 3. Leads identificados pra EXCLUIR

| Lead | Nome | Motivo |
|---|---|---|
| 22703954 | "paciente deseja agendar pelo conv, GDF que não autoriza no dia" | Inas GDF |
| 23235182 | "INAS_Se não conseguir pelo convênio volta pra agendar conosco sem convênio" | Inas GDF |

**Ação:** marcar campo `ATIVADO IA?` = "DESATIVADO" (enum 927035) nestes 2 leads pra o motor `reactivation.py` ignorar.

## 4. Leads identificados pra INCLUIR (~45 candidatos confiáveis)

### 4.1 SEM CONVÊNIO declarado no nome (Particular — R$ 611)
22674912, 22762112, 22790920, 22794662, 22823900, 22824666, 22831286, 22842606, 22857528, 22865002, 22867548, 22872236, 22882728, 22882986, 22895536, 22899154, 23077026, 23081664, 23092516, 22280689

### 4.2 COM CONVÊNIO declarado (verificar quais aceitos)
22919156, 23084176

### 4.3 Outros — sem indicação clara (cobre TODOS — Lia triagem decide)
22521088 (estrabismo), 22752036, 22777566, 22789618, 22837168, 22848228, 22857316, 22859596, 22895616, 22908218, 22919914, 22926336, 22932058, 22936170, 22982854 (no-show), 23125374, 23194086, 23197254, 23216544, 23227740, 23228548, 23235394, 23236740, 22269305, 22292887

## 5. Mecanismo de disparo (não tocar — motor já cobre)

**`voice_agent/reactivation.py` JÁ ESTÁ ATIVO em produção:**

```
enabled: true
dry_run: false
channel: whatsapp_cloud_8133
template_name: 1089_mens_ativar_conv_parada_qz7kbz
daily_cap: 30
business_hours: 8h–18h seg–sáb BRT
cold_status_ids: [96441724, 101508307, 102560495, 106184631, 106184983]
```

**Não fazer batch manual** — motor escolhe os 30 leads/dia automaticamente da fila quente (ordena por `updated_at` antigo primeiro).

## 6. Recomendação operacional pra 08/06

### Opção A — Sem mexer no motor (default, conservador)
- Hoje (04/06 quarta), amanhã (05/06 quinta), sex (05/06), sáb (06/06): motor dispara 30 leads/dia = **120 leads ativados** até segunda.
- Conversão histórica esperada: ~10-15% = 12-18 agendamentos.
- Slots vazios Karla 08/06: ~11 (10:30, 11:00, 11:30, 13:00, 13:30, 14:00, 14:30, 15:00, 16:00, 17:00, 17:30).
- **Cobertura provável: 100% dos slots vazios preenchidos.**

### Opção B — Acelerar (subir cap pra 80/dia)
- Risco Meta: rate-limit por qualidade (NÃO usar template MARKETING ainda — só UTILITY 1089).
- Ganho real: marginal (motor já cobre demanda do dia).
- **Não recomendado** sem aprovação dos 14 templates novos.

### Opção C — Híbrido (recomendado)
1. Excluir os 2 leads GDF/INAS hoje (1 call cada).
2. Manter cap=30, deixar o motor rodar 4 dias.
3. Subir cap pra 50 SÓ na sex (05/06) se Meta status continuar verde.
4. Acompanhar `/reactivation/status` 1x/dia.

## 7. Próximas ações (4 hoje — checklist Fábio aprova)

- [ ] **Marcar 22703954 como `ATIVADO IA?=DESATIVADO`** (excluir Inas GDF)
- [ ] **Marcar 23235182 como `ATIVADO IA?=DESATIVADO`** (excluir Inas GDF)
- [ ] **Confirmar `/reactivation/status` daily_cap=30** (validar produção live)
- [ ] **(Opcional sex 05/06)** Subir cap pra 50 via Easypanel → Ambiente

## 8. Métrica de acompanhamento

| Métrica | Hoje | Meta 08/06 |
|---|---|---|
| Leads em 2.LEADS FRIO | 368 | 248 (−120 ativados) |
| Agendamentos Karla Asa Norte 08/06 | 6 (visível no screenshot) | 17 (slots cheios) |
| Mensagens MARKETING/UTILITY enviadas | 0 | 120 |

## 9. Templates Meta — status

- **1089_mens_ativar_conv_parada_qz7kbz** — APROVADO, em uso pelo motor.
- **14 templates novos** (blink_lf_a–h, blink_conf_d1, blink_loc_*, blink_pos_*, blink_proxima_consulta) — submetidos 03/06, aguardando aprovação Meta (24-72h). Quando aprovados: plugar em `voice_agent/templates_meta.py` e segmentar.

---

**Resumo executivo (1 linha):** motor já cobre 100% da demanda pra 08/06; só precisa excluir 2 leads de convênio não aceito (GDF/INAS).
