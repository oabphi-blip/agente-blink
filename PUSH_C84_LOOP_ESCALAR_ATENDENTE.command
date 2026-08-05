#!/bin/bash
# PUSH_C84_LOOP_ESCALAR_ATENDENTE.command
# Bug C-84 (04/08/2026) — 3 fixes:
#   Fix 1: dedup_outbound.py TTL 5min → 30min (loop durou 39min)
#   Fix 2: responder.py guarda C-84a no C-54 (anti-loop quando paciente já respondeu turno)
#   Fix 3: responder.py FILTRO C-84b (inbound "atendente" → handoff imediato)
#   Fix 4: pipeline.py verifica flag C-84b → move lead + desativa IA + nota Kommo
#   CLAUDE.md: lição C-84 adicionada no rolling log
# Pytest: 126/126 verde (combinado)

set -euo pipefail
cd "$(dirname "$0")"

echo "=== Bug C-84: Loop + Escalação Atendente ==="
echo ""

# Verificações rápidas antes de commitar
echo "--- Verificando fixes ---"
python3 -c "
from voice_agent.dedup_outbound import TTL_JANELA_SEG
assert TTL_JANELA_SEG == 1800, f'TTL errado: {TTL_JANELA_SEG}'
print('  ✅ TTL 30min OK')

with open('voice_agent/responder.py') as f:
    src = f.read()
assert 'C-84a guarda-C54' in src, 'Falta guarda C-54'
assert '_PEDE_ATENDENTE_RE' in src, 'Falta C-84b regex'
assert 'blink:c84_pede_atendente' in src, 'Falta flag Redis C-84b em responder'
print('  ✅ Filtros responder.py OK')

with open('voice_agent/pipeline.py') as f:
    pipe = f.read()
assert 'blink:c84_pede_atendente' in pipe, 'Falta check flag C-84b em pipeline'
assert 'C-84b PIPELINE' in pipe, 'Falta log C-84b em pipeline'
print('  ✅ Pipeline check C-84b OK')
print()
print('  3/3 fixes verificados ✓')
"

echo ""
echo "--- Rodando master regressão ---"
python -m pytest tests/test_bugs_indexados_regressao_master.py -q 2>&1 | tail -3

echo ""
echo "--- Git commit ---"
git add \
  voice_agent/dedup_outbound.py \
  voice_agent/responder.py \
  voice_agent/pipeline.py \
  CLAUDE.md

git commit -m "fix(C-84): loop 11x + escalação atendente (Juliana 24413852)

Bug C-84a — TTL dedup C-62: 300s → 1800s
  Loop durou 39min; TTL 5min resetava o contador 7+ vezes sem detectar loop.

Bug C-84a — guarda anti-loop no C-54 (equivalente C-71 para datas sem DD/MM)
  Quando ultima_msg_outbound='Qual turno...' e paciente responde 'Manhã',
  C-54 não repete o fallback. C-71 tinha criado essa guarda só no C-31b.

Bug C-84b — FILTRO SEMPRE-ON: inbound 'atendente' → handoff imediato
  _PEDE_ATENDENTE_RE detecta 'atendente', 'falar com atendente',
  'falar com humano', etc. no user_text antes de qualquer processamento.
  Retorna mensagem canônica + grava flag Redis blink:c84_pede_atendente:{id}.

Bug C-84b — pipeline.py verifica flag pós-responder
  Ao detectar flag: move lead → 1-ATENDIMENTO HUMANO (106563343),
  desativa IA (ATIVADO IA=Desativado), adiciona nota Kommo, limpa flag.

Pytest: 126/126 verde (combinado C-80+C-81+C-82+master)"

echo ""
echo "--- Git push ---"
git push origin main

echo ""
echo "=== Push C-84 concluído ==="
echo "Próximo: Easypanel → Implantar"
echo "Validar: tail -f logs | grep 'C-84'"
