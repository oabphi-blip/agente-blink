# Checklist Produção — Estado 28/06/2026 22:30 BRT

Lista clara do que falta produção AGORA, em ordem de prioridade.
Foco: **converter** (não só rodar tasks).

---

## 🔴 P0 — Travando conversão HOJE

### 1. Lead 24219750 caiu no fallback "instabilidade rápida"
- **Sintoma:** paciente entrou em 28/06 18:39, Lia respondeu fallback `[VA-FB-2025]` ao invés de conversar normal
- **Hipótese:** Anthropic API timeout OU Medware timeout OU Redis lento
- **Próxima ação:** rodar `curl /admin/replay/24219750` e ler logs Easypanel últimos 15min
- **Tempo estimado:** 15 min pra diagnosticar
- **Quem:** Claude (eu) via MCP

### 2. SYNC JUL2026 batch — terminar os 51 leads
- **Estado:** 1/51 manual (Lydia) + script v3 calibrado OK no canary
- **Bloqueio:** filtro 2624 leads em série travou (rate-limit Kommo)
- **Próxima ação:** Ctrl+C no terminal + rodar de novo passando lista direta dos 21 IDs visíveis
- **Tempo estimado:** 5 min execução
- **Quem:** Fábio (duplo-clique v3) + Claude (passa IDs)

### 3. Template Meta 1033 — aprovação
- **Estado:** versão A confirmada, `SUBMETER_TEMPLATE_1033_META.md` pronto
- **Próxima ação:** Fábio submete via Business Manager UI
- **Tempo estimado:** 3 min preencher + 1-24h aprovação Meta
- **Quem:** Fábio

---

## 🟡 P1 — Pra disparar batch nos 51 leads JUL2026

Depende da P0.1 e P0.2 e P0.3 acima.

### 4. Plugar slug aprovado em templates_meta.py
- **Estado:** aguardando aprovação Meta do 1033
- **Tempo estimado:** 5 min após aprovação
- **Quem:** Claude (após Fábio mandar slug)

### 5. Criar endpoint /admin/disparar-batch-retorno-julho
- **Estado:** pendente
- **Detalhe:** filtra os 51 leads sincados + dispara 1033 com 4 vars (contato/paciente/idade/unidade)
- **Tempo estimado:** 15 min implementar + 5 min push deploy
- **Quem:** Claude

### 6. Smoke test 1 lead piloto (canary disparo real)
- **Estado:** pendente
- **Detalhe:** dispara pra 1 lead (Lydia 21431041 — eu mesmo testo no número da clínica)
- **Tempo estimado:** 5 min
- **Quem:** Claude + Fábio (acompanha)

### 7. Disparar batch 50 leads restantes
- **Estado:** pendente, depende #6 verde
- **Tempo estimado:** 30 min (rate-limit Meta = 80 msg/seg)
- **Quem:** Claude

---

## 🟠 P2 — Pendências arquiteturais ativas

### 8. Renovar KOMMO_TOKEN do agent em prod (task #242)
- **Estado:** PENDENTE há 19 dias
- **Sintoma:** HTTP 403 quando agente tenta gravar notas → notas não aparecem em chat
- **Próxima ação:** gerar novo JWT 3011 chars no Kommo + atualizar Easypanel
- **Tempo estimado:** 5 min se executado via RENOVAR_KOMMO_TOKEN.command
- **Quem:** Fábio (duplo-clique)

### 9. Push fixes #183 + #260 + #208 + #209 ao GitHub (tasks #209, #257, #261)
- **Estado:** commits travados local há dias
- **Detalhe:** pipeline lock + tool_choice FSM + gravação Medware autônoma + métricas live
- **Tempo estimado:** 10 min push manual + 3 min auto-deploy Easypanel
- **Quem:** Fábio (terminal Mac)

### 10. Bug C-16 — Lia disse "Atendemos INAS GDF" (task #274)
- **Estado:** in_progress, sem fix arquitetural
- **Detalhe:** regra E4-NA do `_MASTER_INSTRUCTION.md` precisa bloquear INAS explicitamente
- **Tempo estimado:** 30 min (regra + pytest + bump versão prompt)
- **Quem:** Claude

### 11. Canal 8133 não disponível no Kommo Business Cloud (task #321/#322/#323)
- **Estado:** in_progress, gera mensagens "Erro" no Kommo
- **Detalhe:** reconectar canal via Business Cloud + auto-recovery
- **Tempo estimado:** 15 min reconexão manual
- **Quem:** Fábio (admin Kommo)

### 12. Regra E6-B Redis (reserva 10min + não-repetir slot) (task #325)
- **Estado:** pending — risco moderado de Lia repetir slot já ofertado a outro
- **Tempo estimado:** 45 min
- **Quem:** Claude

---

## 🟢 P3 — Lovable Fase 2 (memória + dashboard)

### 13. Postgres MCP no Cowork apontando Supabase Lovable (task #363)
- **Estado:** PLUGAR_POSTGRES_MCP_LOVABLE_FASE2.command criado, não executado
- **Tempo estimado:** 5 min duplo-clique
- **Quem:** Fábio

### 14. Webhook secret no Easypanel pra Lovable receber eventos
- **Estado:** secret gerado: `b035819d617d536a42251767cb5ea52c7fdf9c33b072d322f34ad30e23b7bdf2`
- **Tempo estimado:** 3 min setar env Easypanel + redeploy
- **Quem:** Fábio

### 15. Integração privada Kommo "lovable-fase2-dashboard" JWT (task #362)
- **Estado:** in_progress
- **Tempo estimado:** 5 min Fábio configurar
- **Quem:** Fábio (UI Kommo)

---

## 🔵 Produção JÁ funcionando (não mexer)

- ✅ Lia respondendo WhatsApp via webhook Meta
- ✅ ATIVADO IA? gate visual por lead
- ✅ Watchdog promessa cron 2min
- ✅ Cron interno semanal CAMPANHA_SEMANAL_ENABLED=1
- ✅ Filtros C-30/C-30A/C-31/C-32 default ON em prod
- ✅ Auto-desativar IA em 1-ATENDIMENTO HUMANO + 5-AGENDADO + 6-CONFIRMAR + 7.CONFIRMADO
- ✅ Webhook redirect 0710 → 8133
- ✅ Trigger Avaliação Google em 8-REALIZADO + Karla
- ✅ SYNC Medware→Kommo canary v3 validado

---

## Próxima ação ÚNICA (priorize você)

1. **Fábio:** Ctrl+C no terminal travado + duplo-clique v3 + cola 21 IDs (P0.2 — 5 min)
2. **Fábio:** submete template 1033 no Business Manager (P0.3 — 3 min)
3. **Claude:** diagnostica lead 24219750 via replay (P0.1 — 15 min, em paralelo)

Quando 1+2+3 terminarem, próximo bloco P1 (#4-#7) leva ~50 min e a campanha JUL2026 está LIVE.
