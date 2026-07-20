#!/bin/bash
# PUSH_FIX_C59_COUNT_DISTINCT_PACIENTE.command
#
# Bug C-59 revisão (20/07/2026) — Task #422.
#
# CAUSA RAIZ CORRIGIDA (minha má interpretação anterior):
#   Achei que 1.299 registros AGENDAMENTO eram "duplicatas C-59" e
#   propus limpar 91 slots. FALSO. Estrutura Medware é 1 consulta =
#   1 PARENT + N children (um child por procedimento/exame). Não é
#   duplicata — é o agrupador de procedimentos.
#
# Prova: 54101 (Ísis) e 54111 (Ísis) mesmo slot têm CODPROCEDIMENTO
# diferentes (311 vs 5). Procedimentos DIFERENTES. Não duplicata.
#
# CORREÇÃO NO CÓDIGO:
#   voice_agent/medware_sql.py:
#     - contar_slots_ocupados_hora (novo nome; alias
#       contar_duplicatas_slot mantido pra compat): usa
#       COUNT(DISTINCT CODPACIENTE). Retorna PACIENTES no slot, não
#       registros AGENDAMENTO.
#     - listar_slots_livres: query ocupados usa
#       DISTINCT DATAHORAAGENDADA, CODPACIENTE. Um slot é ocupado
#       se pelo menos 1 paciente marcado.
#     - existe_agendamento + listar_slots_ocupados_dia: REMOVI o
#       filtro CODAGENDAMENTOPAI IS NULL que estava vazando falsos
#       negativos (11 registros da Eloah tinham TODOS PAI preenchido).
#
# VALIDAÇÃO CONTRA PROD (Karla Asa Norte):
#   Slot        | Antes (bug)     | Depois (fix)    | Realidade
#   20/07 11:30 | 56 "duplicatas" | 3 pacientes     | 3 ✓
#   22/07 13:30 | livre (bug)     | OCUPADO (2 pac) | Lia ofertou errado
#   24/07 16:30 | livre (bug)     | OCUPADO (1 pac) | Lia ofertou errado
#   31/07 13:30 | livre           | LIVRE           | Livre ✓
#
# Agenda Karla Asa Norte 30d = 68 slots livres em 8 dias.
# Agenda Karla Águas Claras 30d = 105 slots livres em 12 dias.
# Sem duplicatas pra limpar. Bug era conceitual (código), não dados.
#
# PYTEST:
#   test_task420_agenda_sql.py: 9/9
#   test_bug_c59_dedup_slot.py: 9/9 (asserção COUNT(*) → COUNT DISTINCT)
#   test_bugs_indexados_regressao_master.py: 35/35
#   TOTAL 53/53 verde local.
#
# ROLLOUT:
#   MEDWARE_AGENDA_SQL=1 já ligado em prod desde Task #420.
#   Este push AJUSTA a lógica sem tocar em envs.
#   Após deploy (2-5min auto), próximo lead que triggerar oferta
#   vai receber slots realmente livres. Bug do Fábio Philipe
#   (24259380: ofertou 22/07 e 24/07 ocupados) desaparece.

set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "PUSH: Fix C-59 revisão — COUNT DISTINCT PACIENTE"
echo "Task #422"
echo "=========================================="

echo ""
echo "-> Sintaxe..."
python3 -c "
import ast
for p in ['voice_agent/medware_sql.py','voice_agent/medware.py']:
    ast.parse(open(p).read())
print('OK sintaxe')
" || { echo "!! Syntax error"; exit 1; }

echo ""
echo "-> Pytest (53/53 esperado)..."
python3 -m pytest \
    tests/test_task420_agenda_sql.py \
    tests/test_bug_c59_dedup_slot.py \
    tests/test_bugs_indexados_regressao_master.py \
    -q 2>&1 | tail -5 || {
    echo "!! Pytest reprovou"; exit 1;
}

echo ""
echo "-> git status..."
git status --short \
    voice_agent/medware_sql.py \
    voice_agent/medware.py \
    tests/test_bug_c59_dedup_slot.py \
    CLAUDE.md

echo ""
echo "-> git add..."
git add \
    voice_agent/medware_sql.py \
    voice_agent/medware.py \
    tests/test_bug_c59_dedup_slot.py \
    CLAUDE.md \
    PUSH_FIX_C59_COUNT_DISTINCT_PACIENTE.command

echo ""
echo "-> Commit..."
git commit -m "fix(medware_sql): C-59 revisão — COUNT DISTINCT CODPACIENTE (Task #422)

Correção da causa raiz do Bug C-59. A interpretação anterior
('1.299 duplicatas') era falsa: estrutura Medware é 1 consulta =
1 PARENT AGENDAMENTO + N filhos, um por procedimento do agrupador.
Registros com CODPROCEDIMENTO diferentes (ex 311 vs 5) NÃO são
duplicatas — são exames diferentes da mesma consulta.

Consequência do bug antigo (Task #420 com filtro errado):
Lia ofertou slots OCUPADOS ao Fábio Philipe lead 24259380
(22/07 13:30 e 24/07 16:30 — ambos com paciente marcado).

Fix em 3 pontos de medware_sql.py:

1. contar_slots_ocupados_hora (novo nome; contar_duplicatas_slot
   virou alias DEPRECATED pra compat):
   COUNT(DISTINCT CODPACIENTE) AS QTD

2. listar_slots_livres query ocupados:
   SELECT DISTINCT DATAHORAAGENDADA, CODPACIENTE
   (um slot é ocupado se >=1 paciente distinto)

3. existe_agendamento + listar_slots_ocupados_dia:
   removido filtro CODAGENDAMENTOPAI IS NULL — provou vazar
   falsos negativos (Eloah 23955974 tinha 11 registros TODOS
   com PAI preenchido, retornava 0). Nova query pega qualquer
   registro do slot.

Validação prod (Karla Asa Norte):
- 20/07 11:30 → 3 pacientes ✓ (Fabiana + Isis + Rosemeire)
- 22/07 13:30 → 2 pacientes ✓ (Lia ofertou errado antes)
- 24/07 16:30 → 1 paciente ✓ (Lia ofertou errado antes)
- 31/07 13:30 → 0 pacientes ✓ (LIVRE)

Agenda 30d: 68 livres/8 dias Asa Norte, 105 livres/12 dias
Águas Claras. Sem duplicatas pra limpar — bug era conceitual.

Pytest 53/53 verde:
- test_task420_agenda_sql.py 9/9
- test_bug_c59_dedup_slot.py 9/9 (asserção COUNT DISTINCT)
- test_bugs_indexados_regressao_master.py 35/35

MEDWARE_AGENDA_SQL=1 já ligado em prod desde Task #420. Este
commit ajusta apenas a semântica das queries." || {
    echo "!! Commit falhou"; exit 1;
}

echo ""
echo "-> git push..."
git push origin main

echo ""
echo "=========================================="
echo "OK — Easypanel auto-deploy 2-5min"
echo "=========================================="
echo ""
echo "SMOKE PÓS-DEPLOY:"
echo "  Novo lead → Lia oferta slots. Verificar:"
echo "  - Se paciente escolher slot X, checar Medware SQL:"
echo "    (data hora tem paciente antes?) = LIVRE (livre)"
echo "    Se pipeline retornar OCUPADO, bug volta — abrir issue."
echo ""
read -p "ENTER pra fechar."
