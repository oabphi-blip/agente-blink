#!/bin/bash
# C-126 — Fix loop convênio não aceito + C-84 cego no bypass (11/08/2026)
# Caso real: lead 24442314 Rafael — GDF recusado → loop + "Robô?" ignorado 3x
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-126 + C-125 + C-123 + C-120/C-119/C-118 + C-124 ==="
python3 -m pytest \
  tests/test_bug_c126_convenio_loop_e_atendente.py \
  tests/test_bug_c125_prova_escuta_uma_pergunta.py \
  tests/test_bug_c118_c119_c120_aceite_e_dados.py \
  tests/test_bug_c123_convenio_recusado.py \
  tests/test_bug_c124_stall_vou_verificar.py \
  -v --tb=short

echo ""
echo "=== Commit C-126 ==="
git add \
  voice_agent/blindagens_deterministicas.py \
  tests/test_bug_c126_convenio_loop_e_atendente.py \
  CLAUDE.md
git add -f PUSH_C126_CONVENIO_LOOP_ATENDENTE.command

git commit -m "fix(C-126): loop convênio não aceito + C-84 cego no bypass

Caso real: lead 24442314 Rafael
  - Paciente informou GDF Saúde (não aceito)
  - C-123 apresentou 1️⃣/2️⃣ corretamente
  - C-120 continuou perguntando convênio (sem gate para convenio_nao_aceito_nome)
  - Paciente perguntou 'Robô?' 3x → ignorado porque C-84 só existe em _scrub_prohibited
    (que NÃO roda quando bypass determina a resposta)

Fix 1 — deve_perguntar_dados_pendentes():
  - Gate: se convenio_nao_aceito_nome e paciente não escolheu ainda → return None
  - Auto-escalação: Redis counter blink:c126_convenio_loop:{lead_id} (TTL 1h)
    Após >= 2 turnos sem escolha → seta blink:c84_pede_atendente + retorna msg handoff

Fix 2 — tentar_bypass_deterministico():
  - C-84 (atendente/robô) ANTES de qualquer outro bypass (incluindo C-120)
  - Regex: atendente, robô, falar com humano, falar com pessoa, me passa pra pessoa
  - Grava blink:c84_pede_atendente:{lead_id} (TTL 86400) → pipeline move lead

Pytest: 53/53 C-126 + 246/246 combinado verde

Rollback: BLINDAGEM_DADOS_PENDENTES_ATIVADO=0 em Easypanel → Implantar"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-126 em produção."
echo ""
echo "IMPORTANTE: Se ainda não deployou C-125, o comando PUSH_C125_PROVA_ESCUTA.command"
echo "já inclui os mesmos arquivos de blindagens_deterministicas.py — use APENAS este"
echo "script (C-126 inclui tudo de C-125 também)."
echo ""
echo "Rollback: BLINDAGEM_DADOS_PENDENTES_ATIVADO=0 no Easypanel → Implantar"
