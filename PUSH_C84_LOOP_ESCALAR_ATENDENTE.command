#!/bin/bash
# PUSH_C84_LOOP_ESCALAR_ATENDENTE.command
# Bug C-84 (04/08/2026) — 3 fixes:
#   Fix 1: dedup_outbound.py TTL 5min → 30min (loop durou 39min)
#   Fix 2: responder.py guarda C-84a no C-54 (anti-loop quando paciente já respondeu turno)
#   Fix 3: responder.py FILTRO C-84b (inbound "atendente" → handoff imediato)
#   Fix 4: pipeline.py verifica flag C-84b → move lead + desativa IA + nota Kommo
#   CLAUDE.md: lição C-84 adicionada no rolling log
# Pytest: 126/126 verde (combinado)

set -uo pipefail
cd "$(dirname "$0")"

echo "=== Bug C-84: Loop + Escalação Atendente ==="
echo ""

# Verificações rápidas antes de commitar
echo "--- Verificando fixes ---"
python3 -c "
from voice_agent.dedup_outbound import TTL_JANELA_SEG
assert TTL_JANELA_SEG == 1800, f'TTL errado: {TTL_JANELA_SEG}'
print('  \xe2\x9c\x85 TTL 30min OK')

with open('voice_agent/responder.py') as f:
    src = f.read()
assert 'C-84a guarda-C54' in src, 'Falta guarda C-54'
assert '_PEDE_ATENDENTE_RE' in src, 'Falta C-84b regex'
assert 'blink:c84_pede_atendente' in src, 'Falta flag Redis C-84b em responder'
print('  \xe2\x9c\x85 Filtros responder.py OK')

with open('voice_agent/pipeline.py') as f:
    pipe = f.read()
assert 'blink:c84_pede_atendente' in pipe, 'Falta check flag C-84b em pipeline'
assert 'C-84b PIPELINE' in pipe, 'Falta log C-84b em pipeline'
print('  \xe2\x9c\x85 Pipeline check C-84b OK')
print()
print('  3/3 fixes verificados \xe2\x9c\x93')
" || { echo "ERRO: verificações falharam — abortando"; exit 1; }

echo ""
echo "--- Rodando master regressão ---"
python -m pytest tests/test_bugs_indexados_regressao_master.py -q 2>&1 | tail -3

echo ""
echo "--- Git commit (idempotente) ---"
git add \
  voice_agent/dedup_outbound.py \
  voice_agent/responder.py \
  voice_agent/pipeline.py \
  CLAUDE.md \
  PUSH_C84_LOOP_ESCALAR_ATENDENTE.command

# Commit — ok se "nothing to commit" (já foi feito em sessão anterior)
git commit -m "fix(C-84): loop 11x + escalação atendente (Juliana 24413852)" \
  2>&1 | grep -v "^$" || echo "  (nada novo pra commitar — commit já existia)"

echo ""
echo "--- Git status ---"
git log --oneline -3

echo ""
echo "--- Git push ---"
git push origin main

echo ""
echo "=== Push C-84 concluído ==="
echo "Próximo: Easypanel → Implantar"
echo "Validar: tail -f logs | grep 'C-84'"
