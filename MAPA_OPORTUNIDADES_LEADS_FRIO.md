---
title: "Mapa de Oportunidades — Leads Frios"
tags: [mapa, campanha, operacao, leads-frio]
data_criacao: 2026-06-04
data_revisao: 2026-06-04
proxima_revisao: 2026-06-11
status: ativo
responsavel: Fábio
categorias: [R, E, V, C, A, X]
---

# Mapa de Oportunidades — Leads Frios Blink

> Documento vivo. Atualizar a cada ciclo de campanha (semanal recomendado).
> Última atualização: **04/06/2026** — preparação agenda 08/06 (segunda).
> Navegação: [[00-INDEX]] · [[PLANO_ATIVACAO_LEADS_FRIO_08_06_2026]] · [[CLAUDE]]

---

## 1. Resumo executivo

| Categoria | Vol. amostra | Temp. | Resposta esp. | Agendamento esp. | Template recomendado |
|---|---:|:---:|---:|---:|---|
| **R — Reagendar/Encaixe** | 9 | 🔥🔥 | 40-55% | 25-35% | `blink_lf_e_pausa_paciente_v1` (após Meta) |
| **E — Com convênio declarado** | 2 | 🔥🔥 | 35-45% | 25-30% | `blink_lf_a_convenio_aceito_v1` (após Meta) |
| **V — Sem resposta após valor** | 15 | 🟠 | 15-22% | 8-12% | `blink_lf_b_particular_v1` (após Meta) |
| **C — Sem convênio genérico** | 15 | 🟡 | 10-15% | 5-7% | `blink_lf_b_particular_v1` (após Meta) |
| **A — Agendar sem contexto** | 8 | ❄ | 5-10% | 2-4% | `1089_mens_ativar_conv_parada_qz7kbz` (atual aprovado) |
| **X — Excluir (convênio não aceito)** | 2 | — | — | — | NÃO disparar (motor IA desativada) |

**Total amostra processada:** 51 leads (de 368 em 2.LEADS FRIO + alguns em 0-ETAPA ENTRADA).

---

## 2. Detalhamento por categoria

### R — Reagendar / Encaixe (🔥🔥 prioridade máxima)

**Definição:** Pacientes que JÁ tentaram agendar, faltaram (no-show), desmarcaram OU pediram remarcação. Demonstram intenção explícita de retornar.

**Sinais no nome do lead:** `REAGENDAR`, `REMARCAÇÃO`, `PÓS DESMARCAÇÃO`, `Faltou consulta`, `aguardo documento`, `desmarcou`.

**Por que é a mais quente:** já validaram interesse no serviço. Só falta horário compatível.

**Template ideal (após aprovação Meta):** `blink_lf_e_pausa_paciente_v1` — reativa lembrando do contexto anterior.
**Fallback HOJE:** `1089_mens_ativar_conv_parada_qz7kbz`.

**Leads identificados na amostra:**

| Lead | Etapa | Sinal específico | URL |
|---|---|---|---|
| 22789618 | 2.LEADS FRIO | "REAGENDAR aguardo documento" | https://univeja.kommo.com/leads/detail/22789618 |
| 22982854 | 2.LEADS FRIO | "Faltou consulta!" | https://univeja.kommo.com/leads/detail/22982854 |
| 21710873 | 0-ETAPA ENTRADA | "REMARCAÇÃO recebido justificação dezembro" | https://univeja.kommo.com/leads/detail/21710873 |
| 22580154 | Closed-won | "REMARCAÇÃO verificar nova disponibilidade" | https://univeja.kommo.com/leads/detail/22580154 |
| 22225601 | 0-ETAPA ENTRADA | "AVALIAÇÃO CIRURGIA paciente desmarcou" | https://univeja.kommo.com/leads/detail/22225601 |
| 12751536 | 0-ETAPA ENTRADA | "REAGENDAR ativação 16/12" | https://univeja.kommo.com/leads/detail/12751536 |
| 22181129 | 0-ETAPA ENTRADA | "AGENDAR PÓS DESMARCAÇÃO" | https://univeja.kommo.com/leads/detail/22181129 |
| 10916579 | 0-ETAPA ENTRADA | "REMARCAÇÃO somente 100% antecipado" | https://univeja.kommo.com/leads/detail/10916579 |
| 13347530 | 0-ETAPA ENTRADA | "REMARCAÇÃO CONVÊNIO 2 ESTRELAS" | https://univeja.kommo.com/leads/detail/13347530 |

**Ação 08/06:** disparar HOJE em horário comercial (motor automático ou manual nos 4 mais quentes). Conversão esperada: 2-3 agendamentos pra segunda.

---

### E — Com convênio declarado (🔥🔥 alta conversão)

**Definição:** Lead sinalizou convênio no próprio nome → atendente já filtrou. Convênio aceito = consulta "gratuita" → alto incentivo a fechar.

**Sinais no nome do lead:** `COM CONVÊNIO`, nome do convênio explícito (ex: "Saúde Caixa", "Amil").

**Atenção:** validar antes de disparar se o convênio é aceito (cruzar com PLANO_CODES — 26 aceitos, 1 não: Inas GDF).

**Template ideal:** `blink_lf_a_convenio_aceito_v1`.

**Leads identificados:**

| Lead | Etapa | Sinal | URL |
|---|---|---|---|
| 22919156 | 2.LEADS FRIO | "AGENDAR_ COM CONVÊNIO" | https://univeja.kommo.com/leads/detail/22919156 |
| 23084176 | 2.LEADS FRIO | "AGENDAR COM CONVÊNIO_sem resposta" | https://univeja.kommo.com/leads/detail/23084176 |

**Ação 08/06:** ler campo CONVÊNIO antes de disparar. Se aceito → fila prioritária. Se Inas GDF → marcar `ATIVADO IA?=Desativado` (igual aos 2 já tratados).

---

### V — Sem resposta após apresentado valor (🟠 morno)

**Definição:** Atendente apresentou valor R$ 305/R$ 611 e paciente sumiu. Indicador de fricção em PREÇO ou tempo de decisão.

**Sinais no nome do lead:** `apresentado valor`, `não respondeu após valor`, `aguardando retorno sobre valor`, `verificar com marido`, `aguardando concordância`.

**Por que é morno e não frio:** o paciente CHEGOU até o valor — não desistiu antes. Pode estar comparando.

**Template ideal:** `blink_lf_b_particular_v1` (com lembrete de opção parcelada/Pix se aplicável).

**Leads identificados (parcial):**

| Lead | Sinal | URL |
|---|---|---|
| 22674912 | "não respondeu mais após valor" | https://univeja.kommo.com/leads/detail/22674912 |
| 22762112 | "demonstrou interesse e não respondeu mais" | https://univeja.kommo.com/leads/detail/22762112 |
| 22794662 | "não teve interesse após valores" | https://univeja.kommo.com/leads/detail/22794662 |
| 22823900 | "aguardando retorno paciente sobre valor" | https://univeja.kommo.com/leads/detail/22823900 |
| 22831286 | "saber valor segunda opinião" | https://univeja.kommo.com/leads/detail/22831286 |
| 22882728 | "AGUARDANDO CONCORDANCIA COM VALOR" | https://univeja.kommo.com/leads/detail/22882728 |
| 23092516 | "apresentado valor consulta aguardando resposta" | https://univeja.kommo.com/leads/detail/23092516 |
| 23235394 | "parou de responder após envio valor" | https://univeja.kommo.com/leads/detail/23235394 |
| 23236740 | "entrará em contato após verificar com marido" | https://univeja.kommo.com/leads/detail/23236740 |
| 22292887 | "verificar valor com marido" | https://univeja.kommo.com/leads/detail/22292887 |
| 22790920 | "filho de 3 anos aguardando" | https://univeja.kommo.com/leads/detail/22790920 |
| 22521088 | "estrabismo cirurgia interesse não respondeu" | https://univeja.kommo.com/leads/detail/22521088 |
| 22859596 | "estrabismo cirurgia interesse" | https://univeja.kommo.com/leads/detail/22859596 |
| 22857316 | "aguardando retorno paciente" | https://univeja.kommo.com/leads/detail/22857316 |
| 22865002 | "aguardando retorno paciente" | https://univeja.kommo.com/leads/detail/22865002 |

**Ação 08/06:** disparar via motor com cap 30/dia. Lia oferece slot direto (sem repergunta de convênio se já está no ctx).

---

### C — Sem convênio genérico / Particular (🟡 médio)

**Definição:** Atendente registrou "SEM CONVÊNIO" no nome mas sem outro sinal. Paciente provavelmente comparou e vai por Particular.

**Sinais no nome do lead:** `SEM CONVÊNIO`, `SEM CONVENIO`, `Particular`.

**Template ideal:** `blink_lf_b_particular_v1`.

**Leads identificados:**

22842606, 22857528, 22867548, 22872236, 22882986, 22895536, 22899154, 23077026, 23081664, 22280689, 22283589, 22287763, 22336002, 22363106, 22377310.

(URLs no padrão `https://univeja.kommo.com/leads/detail/{id}`.)

**Ação 08/06:** mesma fila do V, prioridade menor.

---

### A — Agendar sem contexto (❄ frio)

**Definição:** Atendente só registrou "AGENDAR_" sem qualquer outra informação. Pode ser lead que abandonou no 1º contato OU registro incompleto.

**Sinais no nome do lead:** apenas `AGENDAR_`, `AGENDAR`, `AGENDA`.

**Por que é frio:** sem qualificação, taxa de erro alta (paciente pode ter desistido completo).

**Template ideal:** `1089_mens_ativar_conv_parada_qz7kbz` (genérico, baixo custo).
**Após aprovação Meta:** `blink_lf_h_sem_nome_v1`.

**Leads identificados:** 22752036, 22777566, 22837168, 22848228, 22908218, 22932058, 22936170, 23216544, 23227740, 23228548.

**Ação 08/06:** deixar pro motor processar com cap 30/dia (sem priorização). Esperar baixa resposta.

---

### X — Excluir (convênio não aceito) ⛔

**Definição:** Convênio fora da lista Blink (Inas GDF principalmente).

**Sinais no nome do lead:** `INAS`, `GDF`, nomes de convênios não-aceitos (Cassi, SulAmérica, Bradesco).

**Ação:** marcar `ATIVADO IA?=Desativado` no Kommo + nota explicando.

**Leads já tratados (04/06/2026):**

| Lead | Sinal | Status |
|---|---|---|
| 22703954 | "GDF que não autoriza no dia" | ✅ Desativado |
| 23235182 | "INAS_volta pra agendar sem convênio" | ✅ Desativado |

---

## 3. Fluxo operacional de campanha (template reutilizável)

**Antes de cada campanha:**

1. Re-scan `kommo_search_leads` com filtros por palavra-chave de cada categoria.
2. Atualizar esta tabela com IDs novos.
3. Marcar `ATIVADO IA?=Desativado` em qualquer lead com sinal de convênio não aceito.
4. Confirmar `/reactivation/status` → `enabled:true`, `cap` no nível desejado.

**Durante a campanha:**

5. Motor `reactivation.py` dispara cap/dia em horário comercial seg-sáb 8-18h.
6. Lia conversa → consulta agenda Medware → oferece 2 slots → grava no Medware (autônomo desde commit 28de20d / 04/06/2026).
7. Stephany/Ariany supervisionam casos escalados (circuit breaker Medware ou checklist incompleto).

**Após cada campanha (semana fechada):**

8. Rodar `/admin/healthz` e verificar volume disparado vs. agendamentos confirmados.
9. Atualizar coluna "Resposta esp." × real desta tabela com taxas observadas.
10. Mover leads engajados (responderam) pro pipeline normal; reclassificar quem virou "morno".

---

## 4. Métricas-alvo por semana

| KPI | Meta semanal | Como medir |
|---|---|---|
| Leads ativados | 150-200 | Motor cap × dias úteis |
| Taxa resposta | ≥ 15% | Inbound novo / disparos |
| Conversão agendamento | ≥ 8% | Agendamentos confirmados / disparos |
| Slots vazios preenchidos | ≥ 70% | Slots ocupados / slots livres pré-campanha |
| Reativações de IA pós-handoff | 100% dos respondidos | Field `ATIVADO IA?=Ativado` após mensagem |

---

## 5. Backlog de melhorias do mapa

- [ ] Re-scan completo das 368 LEADS FRIO (amostra atual = 51, 14%).
- [ ] Cruzar cada ID com campo CONVÊNIO real (não só nome do lead) — alguns marcados "SEM CONVÊNIO" no nome têm convênio no field.
- [ ] Auto-pulsar este mapa após cada campanha via endpoint `/admin/audit/lead-frio-categorias`.
- [ ] Plugar dashboard semanal de KPIs (Slack ou artifact Cowork).
- [ ] Aprovação Meta dos 14 templates novos (`blink_lf_a` a `blink_pos_*`) — depois disso plugar mapping `categoria → template_slug`.

---

## 6. Decisões consolidadas (não regredir)

- **Cap 30/dia hoje** — não subir pra 200 até Meta aprovar os templates novos (risco strike spam).
- **Templates atuais aprovados:** `1089_mens_ativar_conv_parada_qz7kbz` (genérico), `1039 ATIVAR GRAU DE URGÊNCIA`.
- **Convênios não aceitos:** Inas GDF (KB art. 18). Demais aceitos via PLANO_CODES (26 mapeados).
- **Médicos atendentes em 04/06:** Karla Delalibera (12080, Asa Norte 5), Fabrício Freitas (12081). Kátia em pausa.
- **Slots vazios Karla 08/06 (segunda):** 10:30, 11:00, 11:30, 13:00, 13:30, 14:00, 14:30, 15:00, 16:00, 17:00, 17:30 (11 slots).
- **Lia grava agendamento autônomo** desde 04/06 (commit 28de20d).

---

**Próxima revisão:** 11/06/2026 (segunda da próxima semana, pós-campanha 08-11/06).
