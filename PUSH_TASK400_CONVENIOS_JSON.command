#!/bin/bash
# PUSH_TASK400_CONVENIOS_JSON.command
#
# Task #400 parte 1 (20/07/2026) — Migrar convênios NÃO aceitos pra JSON externo.
#
# CONTEXTO (Fábio 11/07 P0 arquitetural, Bug C-53):
#   "continuar disfuncional porque não grava esta tabela no database, para
#   não ocorrer retrocessos. Já tivemos este mesmo tipo de erro 1000 vezes."
#
# ANTES:
#   voice_agent/responder.py::_CONVENIOS_NAO_ACEITOS_KB18 = frozenset({...})
#   Editar convênio novo NÃO aceito exigia: código Python → commit → push →
#   auto-deploy (~5min).
#
# DEPOIS:
#   voice_agent/convenios_nao_aceitos.json = fonte de verdade (43 convênios)
#   voice_agent/convenios_nao_aceitos_loader.py = cache TTL 60s + fallback
#   responder.py importa via loader (semântica idêntica, zero breaking change)
#
# EDITAR CONVÊNIO EM PROD (após deploy):
#   1. Editar voice_agent/convenios_nao_aceitos.json (adicionar/remover string)
#   2. Commit + push
#   3. Auto-deploy Easypanel pega em 2-5min
#   4. Loader recarrega no próximo turn (cache TTL 60s)
#
# BUGS QUE ESSA MIGRAÇÃO BLINDA:
#   - C-22 Sandra 24130752 — GDF token isolado adicionado sem redeploy
#   - C-43 Mariana — convênio novo aparece rápido
#   - Padrão arquitetural C-31 / C-38 / C-53 (hard-coded regras clínicas)
#
# PYTEST:
#   test_convenios_nao_aceitos_loader.py — 10 cenários (JSON default,
#   env override, fallback, cache, normalização, bug C-22 GDF)

set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "PUSH: Task #400 parte 1 — Convênios JSON"
echo "=========================================="

echo ""
echo "-> Sintaxe..."
python3 -c "
import ast, json
ast.parse(open('voice_agent/convenios_nao_aceitos_loader.py').read())
ast.parse(open('voice_agent/responder.py').read())
json.loads(open('voice_agent/convenios_nao_aceitos.json').read())
print('OK sintaxe (Python + JSON)')
" || { echo "!! Syntax error"; exit 1; }

echo ""
echo "-> Pytest (28/28 esperado)..."
python3 -m pytest \
    tests/test_convenios_nao_aceitos_loader.py \
    tests/test_bug_c59_dedup_slot.py \
    tests/test_task420_agenda_sql.py \
    -q 2>&1 | tail -5 || { echo "!! Pytest reprovou"; exit 1; }

echo ""
echo "-> git status..."
git status --short \
    voice_agent/convenios_nao_aceitos.json \
    voice_agent/convenios_nao_aceitos_loader.py \
    voice_agent/responder.py \
    tests/test_convenios_nao_aceitos_loader.py

echo ""
echo "-> git add..."
git add \
    voice_agent/convenios_nao_aceitos.json \
    voice_agent/convenios_nao_aceitos_loader.py \
    voice_agent/responder.py \
    tests/test_convenios_nao_aceitos_loader.py \
    PUSH_TASK400_CONVENIOS_JSON.command

echo ""
echo "-> Commit..."
git commit -m "feat(convenios): Task #400 pt1 — migrar convênios NÃO aceitos KB18 pra JSON externo

Continuação do padrão arquitetural iniciado em C-53 (calendar_atendimento.json)
e C-43 (planos_medware.json). Fábio 11/07 P0:
'continuar disfuncional porque não grava esta tabela no database, para não
ocorrer retrocessos. Já tivemos este mesmo tipo de erro 1000 vezes.'

Arquivos novos:
- voice_agent/convenios_nao_aceitos.json (43 convênios canônicos KB18)
- voice_agent/convenios_nao_aceitos_loader.py (cache TTL 60s + fallback)
- tests/test_convenios_nao_aceitos_loader.py (10 cenários)

Refactor:
- voice_agent/responder.py::_CONVENIOS_NAO_ACEITOS_KB18 vira alias lazy
  do loader. Semântica idêntica (frozenset[str], substring match).
- Fallback hard-coded EM TRÊS camadas (loader→fallback→responder try/except)
  garante zero downtime se JSON desaparecer/quebrar.

Editar convênio novo em prod:
1. Editar voice_agent/convenios_nao_aceitos.json
2. Commit + push
3. Auto-deploy 2-5min
4. Loader recarrega em 60s (TTL)

Zero breaking change: mesmo tipo, mesma API, mesma semântica.

Pytest 28/28 verde:
- test_convenios_nao_aceitos_loader.py (10 cenários novos)
- test_bug_c59_dedup_slot.py (9 regressão)
- test_task420_agenda_sql.py (9 regressão)

Bugs blindados (histórico):
- C-22 (Sandra 24130752 10/06): 'gdf' isolado adicionar sem redeploy
- C-43 pattern (Mariana Lopes): convênio novo Kommo → JSON → prod rápido" || {
    echo "!! Commit falhou"; exit 1;
}

echo ""
echo "-> git push..."
git push origin main

echo ""
echo "=========================================="
echo "OK — Easypanel auto-deploy 2-5min"
echo "=========================================="
read -p "ENTER pra fechar."
