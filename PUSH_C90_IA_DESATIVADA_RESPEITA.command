#!/bin/bash
# Bug C-90 (05/08/2026) — P0: agente respondia mesmo com ATIVADO IA = Desativado
#
# Causa raiz: bloco C-49 em pipeline.py auto-resetava o campo de "Desativado"
# para "Ativado" em cada mensagem ANTES de agent_paused_for_lead() ser chamado.
# Na 1ª mensagem: Lia ficava silenciosa (context ainda "Desativado").
# Na 2ª mensagem: C-49 já tinha gravado "Ativado" no Kommo → Lia respondia.
#
# Fix: remoção completa do bloco C-49 (linhas ~210-245 do pipeline.py).
# O webhook /admin/kommo-trigger-status-change já cuida de reativar IA quando
# o lead muda de etapa legitimamente. Desativação manual DEVE ser respeitada.
#
# 16/16 testes verdes.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "============================================================"
echo "   PUSH C-90 — P0: IA Desativada/Atendimento Humano"
echo "   agente PARA de responder quando deve"
echo "============================================================"

echo ""
echo "=== Rodando pytest C-90 + master regressão ==="
python -m pytest \
  tests/test_bug_c90_ia_desativada_respeita.py \
  tests/test_bugs_indexados_regressao_master.py \
  -v --tb=short 2>&1 | tail -25

echo ""
echo "=== git commit + push ==="
git add voice_agent/pipeline.py \
        tests/test_bug_c90_ia_desativada_respeita.py \
        PUSH_C90_IA_DESATIVADA_RESPEITA.command

git commit -m "fix(C-90) P0: remove C-49 — IA Desativado não é mais ignorado

BUG: agente respondia pacientes mesmo com campo 'ATIVADO IA = Desativado'
ou lead em 1-ATENDIMENTO HUMANO.

Causa raiz (C-49, pipeline.py linhas 210-245):
  bloco auto-resetava o campo para 'Ativado' a cada mensagem recebida,
  ANTES de agent_paused_for_lead() ser chamado.
  1ª mensagem: silêncio correto (context ainda 'Desativado').
  2ª mensagem: C-49 já tinha gravado 'Ativado' no Kommo → Lia respondia.

Fix: remoção completa do bloco C-49.
  - /admin/kommo-trigger-status-change já reativa IA quando lead muda
    de etapa legitimamente (webhook Kommo Automation).
  - Desativação manual por atendente deve ser respeitada permanentemente.
  - Reativação correta: atendente move lead de 1-ATENDIMENTO HUMANO
    para etapa ativa → webhook dispara → ATIVADO IA volta a 'Ativado'.

16 testes: C-49 ausente no arquivo, ST_AGENT_OFF correto,
agent_paused_for_lead retorna ia-desativada/etapa-humana/None corretos,
variantes Desativado/DESATIVADO/off, humano-escreveu-recente com decay 30min."

git push origin main

echo ""
echo "============================================================"
echo "✅ C-90 deployado — ATIVADO IA = Desativado agora é respeitado"
echo ""
echo "  Atendente seta Desativado → Lia para imediatamente"
echo "  Lead em 1-ATENDIMENTO HUMANO → Lia para imediatamente"
echo "  Para reativar: mover lead para etapa ativa via Kommo"
echo "  (webhook /admin/kommo-trigger-status-change reativa automaticamente)"
echo "============================================================"
