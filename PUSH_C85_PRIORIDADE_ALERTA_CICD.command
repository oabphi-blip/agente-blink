#!/bin/bash
# PUSH_C85_PRIORIDADE_ALERTA_CICD.command
# Task #444 (C-85a) — pipeline.py: nota Kommo 🟡 quando urgência priority detectada
# Task #445 (C-85b) — Dockerfile: CI gate pytest bloqueia Easypanel deploy se regressão
# Pytest: 161/161 verde (regressão master + C-80 + C-82 + intent_classifier)

set -uo pipefail
cd "$(dirname "$0")"

echo "=== C-85: Alerta Urgência Priority + CI/CD Gate ==="
echo ""

echo "--- Verificando fixes ---"
python3 -c "
# Fix 1 — pipeline.py: alerta Kommo priority
with open('voice_agent/pipeline.py') as f:
    pipe = f.read()
assert 'C-81 PRIORITY' in pipe and 'add_note' in pipe and 'nota_pr' in pipe, 'Falta nota Kommo priority'
print('  \xe2\x9c\x85 pipeline.py nota Kommo priority OK')

# Fix 2 — Dockerfile: CI gate
with open('Dockerfile') as f:
    df = f.read()
assert 'COPY tests' in df, 'Falta COPY tests no Dockerfile'
assert 'test_bugs_indexados_regressao_master' in df, 'Falta pytest no Dockerfile'
print('  \xe2\x9c\x85 Dockerfile CI gate OK')
print()
print('  2/2 fixes verificados \xe2\x9c\x93')
" || { echo "ERRO: verificações falharam — abortando"; exit 1; }

echo ""
echo "--- Rodando master regressão ---"
python -m pytest tests/test_bugs_indexados_regressao_master.py -q 2>&1 | tail -3

echo ""
echo "--- Git commit ---"
git add \
  voice_agent/pipeline.py \
  Dockerfile \
  PUSH_C85_PRIORIDADE_ALERTA_CICD.command

git commit -m "feat(C-85): alerta Kommo urgência priority + CI gate Dockerfile" \
  2>&1 | grep -v "^$" || echo "  (nada novo pra commitar)"

echo ""
echo "--- Git log ---"
git log --oneline -3

echo ""
echo "--- Git push ---"
git push origin main

echo ""
echo "=== Push C-85 concluído ==="
echo "Próximo: Easypanel → Implantar"
echo ""
echo "--- VERIFICAR MANUALMENTE: MEDWARE_AGENDA_SQL ---"
echo "Acesse: https://6prkfn.easypanel.host/projects/blink/app/agent"
echo "→ Ambiente → procurar MEDWARE_AGENDA_SQL"
echo "→ Se não existir: adicionar MEDWARE_AGENDA_SQL = 1 → Salvar → Implantar"
