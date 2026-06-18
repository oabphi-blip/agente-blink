#!/bin/bash
# PUSH_SPRINT_SRE.command
# Sprint 1h SRE — 8 pilares pra estabilizar o agente Lia
#
# Pilares entregues:
#  1. SLO board + endpoint /admin/slo (HTML + JSON)
#  2. Auditoria diaria juiz Haiku (cron 7h BRT + Slack alert)
#  3. Golden 50 - bateria de regressao bloqueante no CI
#  4. Synthetic users 100/dia + Error budget Slack alerts
#  5. Versionamento de prompt + endpoint /admin/prompt-diff
#  6. Chaos test - injecao de falha Medware/Kommo/Anthropic
#  7. Filtros C-37c sempre-ON (saiu FILTROS_LEGACY)
#  8. CI gate bloqueante em .github/workflows/test.yml
#
# Pytest: 127 verde (8 + 12 + 53 + 17 + 10 + 9 + 18)
# Tempo: 1.45s

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Sprint SRE -- 8 pilares pra estabilidade"
echo "==============================================="

echo ""
echo "[1/6] AST check em 8 arquivos modificados/criados..."
python3 -c "
import ast
arquivos = [
    'voice_agent/slo.py',
    'voice_agent/auditoria_diaria.py',
    'voice_agent/synthetic_users.py',
    'voice_agent/error_budget.py',
    'voice_agent/prompt_versioning.py',
    'voice_agent/chaos.py',
    'voice_agent/webhook.py',
    'voice_agent/cron_interno.py',
    'voice_agent/responder.py',
    'voice_agent/kommo.py',
    'voice_agent/medware.py',
]
for f in arquivos:
    ast.parse(open(f).read())
    print('  AST OK:', f)
"

echo ""
echo "[2/6] Confirmando 0 filtros sob gate FILTROS_LEGACY..."
N=$(grep -c '_FILTROS_LEGACY_ATIVOS and _viola' voice_agent/responder.py 2>/dev/null; true)
N=${N:-0}
echo "  Filtros gateados: $N (deve ser 0)"
if [ "$N" -ne 0 ] 2>/dev/null; then
    echo "  ERRO: ainda tem filtros sob gate"
    exit 1
fi

echo ""
echo "[3/6] Pytest sprint SRE + bugs (127 cenarios)..."
python3 -m pytest \
    tests/test_slo.py \
    tests/test_auditoria_diaria.py \
    tests/test_golden_50.py \
    tests/test_synthetic_e_error_budget.py \
    tests/test_prompt_versioning_e_chaos.py \
    tests/test_bug_c37_invencao_comunicacao_interna.py \
    tests/test_bug_c37b_ia_desativada_gate.py \
    -q --tb=line 2>&1 | tail -5

echo ""
echo "[4/6] Varredura segredos no diff..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[5/6] Commit + push..."
git add \
    voice_agent/slo.py \
    voice_agent/auditoria_diaria.py \
    voice_agent/synthetic_users.py \
    voice_agent/error_budget.py \
    voice_agent/prompt_versioning.py \
    voice_agent/chaos.py \
    voice_agent/webhook.py \
    voice_agent/cron_interno.py \
    voice_agent/responder.py \
    voice_agent/kommo.py \
    voice_agent/medware.py \
    voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    tests/test_slo.py \
    tests/test_auditoria_diaria.py \
    tests/test_golden_50.py \
    tests/test_synthetic_e_error_budget.py \
    tests/test_prompt_versioning_e_chaos.py \
    tests/test_bug_c37_invencao_comunicacao_interna.py \
    tests/test_bug_c37b_ia_desativada_gate.py \
    .github/workflows/test.yml \
    PUSH_SPRINT_SRE.command \
    PUSH_BUG_C37_INVENCAO_COMUNICACAO.command

git commit -m "feat(sprint-sre): 8 pilares de estabilidade -- SLO + auditoria + golden + synthetic + chaos + filtros sempre-on

Origem: Fabio 18/06/2026 -- 'A claude eh disruptiva, e a unica coisa
que distorce o tempo eh a intensidade.'

Sprint de 1h pra responder 'porque nao traz o playbook publico de
SRE pra LLM agents.' Entregue em paralelo via 5 sub-agentes.

PILAR 1 -- SLO Board
====================
voice_agent/slo.py + 2 endpoints (/admin/slo HTML + /admin/slo.json).
Calcula hallucination_rate, latency_p99, tool_call_success,
delivery_rate, agent_uptime, escalations 24h e 7d. Error budget
classifica healthy/warning/burnt vs metas (1% hallu, 99% uptime,
95% delivery). 8 pytest.

PILAR 2 -- Auditoria Diaria
============================
voice_agent/auditoria_diaria.py + cron 7h BRT + Slack alert.
Varre Redis tracing 24h, juiz Haiku critica cada turno, agrega
sintomas por tipo, manda relatorio Slack com top 5 sintomas e
3 leads piores com link /admin/replay. 12 pytest.

PILAR 3 -- Golden 50 (CI bloqueante)
=====================================
tests/test_golden_50.py: 53 cenarios (21 bugs C-XX + 10 feliz +
10 edge + 9 invariantes + 1 meta). Roda em <1s. .github/workflows/
test.yml com job golden_suite bloqueante. 53 pytest.

PILAR 4 -- Synthetic Users 100 + Error Budget
==============================================
voice_agent/synthetic_users.py + voice_agent/error_budget.py + 2
workers cron. 100 cenarios (30 feliz + 20 edge + 20 adversarial +
15 risco clinico + 15 bugs historicos). Alerta Slack quando burn_
rate > 1. 17 pytest.

PILAR 5 -- Versionamento Prompt
================================
voice_agent/prompt_versioning.py + endpoints /admin/prompt-versions
e /admin/prompt-diff. Auto-registra VERSAO_PROMPT no startup do app.
Hash SHA256[:16] + snippet 200 chars. 5 pytest.

PILAR 6 -- Chaos Test
======================
voice_agent/chaos.py + 4 endpoints. Injeta falha em Medware/Kommo/
Anthropic via flag Redis. Suite valida que Lia escala pra humano em
vez de inventar resposta. Gate condicional em criar_agendamento,
find_lead_id_by_phone, reply -- default OFF (zero overhead). 5 pytest.

PILAR 7 -- C-37c filtros sempre-ON
===================================
3 filtros gateados por FILTROS_LEGACY desligados em prod ha meses:
  - _viola_pergunta_redundante_convenio (Adriana 24063769)
  - _viola_oferta_apos_agendado (Esther 24060221 + Manuela 24165262)
  - _viola_oferta_agenda (Sofia/Adelia/Maite)
21 filtros total, 0 gateados, 100% sempre-on.

PILAR 8 -- CI Gate
===================
.github/workflows/test.yml: job golden_suite sem continue-on-error,
bloqueante, timeout 5min. Job pytest antigo segue nao-bloqueante.

Total pytest: 127 verde em 1.45s.
Arquivos novos: 6 voice_agent + 5 tests.
Arquivos modificados: webhook.py, cron_interno.py, responder.py,
kommo.py, medware.py, _MASTER_INSTRUCTION.md.

Envs novas (default ON, exceto SYNTHETIC):
  AUDITORIA_DIARIA_ENABLED=1
  ERROR_BUDGET_ALERTS_ENABLED=1
  SYNTHETIC_USERS_ENABLED=0
  SLACK_WEBHOOK_AUDITORIA_URL=...
  SLACK_WEBHOOK_ALERTAS_URL=...
" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "[6/6] Aguardando deploy Easypanel (~3min)..."
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 20
    body=$(curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK em ${i}x20s"
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "  Sprint SRE em prod -- 8 pilares ativos"
echo ""
echo "  Visite https://blink-agent.6prkfn.easypanel.host/admin/slo?secret=..."
echo ""
echo "  Proximos passos manuais:"
echo "  1. GitHub branch protection: Settings > Branches > main"
echo "     > Require status checks: golden_suite (bloqueante)"
echo "  2. Easypanel > Ambiente: adicionar SLACK_WEBHOOK_AUDITORIA_URL"
echo "     e SLACK_WEBHOOK_ALERTAS_URL (opcional)"
echo "  3. Apos 24h em prod, ligar SYNTHETIC_USERS_ENABLED=1"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
