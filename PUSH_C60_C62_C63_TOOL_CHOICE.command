#!/bin/bash
# PUSH_C60_C62_C63_TOOL_CHOICE.command
#
# 3 fixes num push:
#
# C-60 (Caroline 22949500, 21/07): frase "conferir os dias antes de gravar"
#   repetida 4x. Regex expandida em _FAKE_AGENDA_LOOKUP.
#
# C-62 (Lead 24325532, 20/07): mesma pergunta 7x em 5 min.
#   dedup_outbound.py — estava local mas nunca commitado.
#
# C-63 (21/07, causa raiz): tool_choice forçado em estados DADOS/CONVENIO.
#   Antes: {"type":"any"} quando só tinha agenda. Modelo podia escolher tool
#   errada OU escrever texto livre após tool falhar na 2ª iteração.
#   Depois: DADOS→confirmar_dados_paciente, CONVENIO→confirmar_dados_paciente,
#   agenda presente (qualquer estado)→oferecer_slot especificamente.
#   Isso FECHA o caminho do texto livre fora de TRIAGEM.
#
# PYTEST: 38/38 verde:
#   - test_bug_c60_caroline_loop_conferir.py (6 cenários)
#   - test_bug_c62_dedup_outbound.py (22 cenários)
#   - test_convenios_nao_aceitos_loader.py (10 regressão)

set -e
cd "$(dirname "$0")"

echo "============================================"
echo "PUSH: C-60 + C-62 + C-63 (tool_choice fix)"
echo "============================================"

echo ""
echo "-> Sintaxe Python..."
python3 -c "
import ast
for p in ('voice_agent/responder.py',
          'voice_agent/dedup_outbound.py',
          'voice_agent/handoff_humano.py'):
    ast.parse(open(p).read())
print('OK sintaxe')
" || { echo "!! Syntax error"; exit 1; }

echo ""
echo "-> Pytest..."
python3 -m pytest \
    tests/test_bug_c60_caroline_loop_conferir.py \
    tests/test_bug_c62_dedup_outbound.py \
    tests/test_convenios_nao_aceitos_loader.py \
    -q 2>&1 | tail -5 || { echo "!! Pytest reprovou"; exit 1; }

echo ""
echo "-> Removendo lock se existir..."
rm -f .git/index.lock

echo ""
echo "-> git add..."
git add \
    voice_agent/responder.py \
    voice_agent/dedup_outbound.py \
    voice_agent/handoff_humano.py \
    tests/test_bug_c60_caroline_loop_conferir.py \
    tests/test_bug_c62_dedup_outbound.py \
    tests/test_bug_c61_cobertura_e_handoff.py \
    PUSH_C60_C62_C63_TOOL_CHOICE.command

echo ""
echo "-> Commit..."
git commit -m "fix(tool-choice): C-60+C-62+C-63 — elimina texto livre fora de TRIAGEM

BUG C-63 (causa raiz das stall phrases, 60+ dias):
- _TOOL_POR_ESTADO expandido: DADOS→confirmar_dados_paciente,
  CONVENIO→confirmar_dados_paciente
- elif _agenda_ctx: trocado de {\"type\":\"any\"} pra
  {\"type\":\"tool\",\"name\":\"oferecer_slot\"} (específico)
- Modelo NÃO PODE mais escrever texto livre em DADOS, CONVENIO, AGENDA,
  CONFIRMACAO ou GRAVACAO. Só TRIAGEM (saudação inicial) é texto livre.

BUG C-62 (20/07): dedup_outbound.py (hash SHA256, TTL 180s, loop→humano)
estava LOCAL desde 20/07 mas nunca commitado → não estava em prod.

BUG C-60 (Caroline 22949500, 21/07): 3 novos padrões regex em
_FAKE_AGENDA_LOOKUP cobrindo 'conferir os dias', 'antes de gravar',
'seg/qua/sex...ter/qui' como stall.

Pytest 38/38 verde." || {
    echo "!! Commit falhou"; exit 1;
}

echo ""
echo "-> git push..."
git push origin main

echo ""
echo "============================================"
echo "OK — Easypanel auto-deploy 2-5min"
echo "============================================"
echo ""
echo "Após deploy: modelo não pode mais escrever texto livre"
echo "em estados DADOS/CONVENIO/AGENDA/CONFIRMACAO/GRAVACAO."
echo "Só TRIAGEM é texto livre (saudação inicial)."
echo ""
read -p "ENTER pra fechar."
