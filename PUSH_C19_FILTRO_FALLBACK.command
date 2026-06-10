#!/bin/bash
# Push fix Bug C-19 — filtro SEMPRE-ON contra "equipe entra em contato"
# Duplo-clique pra rodar.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push C-19 — filtro fallback equipe contata"
echo "==============================================="

git add voice_agent/responder.py tests/test_bug_c19_fallback_equipe_contata.py PUSH_C19_FILTRO_FALLBACK.command
git commit -m "fix(c-19): filtro SEMPRE-ON contra fallback 'equipe entra em contato'

Bug C-19 — Medware HTTP 503 desde 16h BRT 10/06/2026 deixou Lia em
loop 'vou consultar' que terminava em fallback Juliene 'nossa equipe
entra em contato'.

Casos reais hoje:
  - 24129390 Julia/Lucas (5m): 'vou anotar 11h, equipe entra em contato'
  - 24129498 Sarah Cordeiro: 'agenda não retorna, equipe entrará'

Fix:
- _viola_fallback_equipe_contata() em responder.py — 7 patterns regex
  cobrindo 'equipe entra/retorna/consulta', 'anotar preferência + equipe',
  'vou passar pra equipe/atendente humano', 'retorno em horário comercial'
- Plugado em _scrub_prohibited como invariante SEMPRE-ON (não depende de
  FILTROS_LEGACY que está =0 em prod)
- _gerar_resposta_honesta_medware_down() substitui pela frase:
  '[Nome], deixa eu reconsultar a agenda real aqui pra você — volto em
   1 minuto com os horários certos.'

Pytest novo: tests/test_bug_c19_fallback_equipe_contata.py — 23 cenários
verde (casos reais Julia + Sarah, variações, falsos positivos, scrub)." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo. Easypanel deploy em ~3 min."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
