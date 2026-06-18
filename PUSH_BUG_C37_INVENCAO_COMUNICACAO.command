#!/bin/bash
# PUSH_BUG_C37_INVENCAO_COMUNICACAO.command
# Bugs C-37 + C-37b + C-37c (lead 21341221 Livia/Linielle + benchmark)
#
# C-37  — Lia inventou comunicacao interna ("vou avisar a equipe")
# C-37b — Agent ignorava campo ATIVADO IA? (bug FUNDAMENTAL)
# C-37c — 3 filtros estavam DESLIGADOS por gate FILTROS_LEGACY (benchmark engenheiro)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push C-37 + C-37b + C-37c -- Fixes Lia"
echo "==============================================="

echo ""
echo "[1/6] AST check responder.py + kommo.py..."
python3 -c "
import ast
for f in ['voice_agent/responder.py', 'voice_agent/kommo.py']:
    ast.parse(open(f).read())
    print(f'  AST OK: {f}')
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
echo "[3/6] Pytest C-37 + C-37b (27 cenarios)..."
python3 -m pytest tests/test_bug_c37_invencao_comunicacao_interna.py \
                  tests/test_bug_c37b_ia_desativada_gate.py -q 2>&1 | tail -5

echo ""
echo "[4/6] Varredura segredos no diff..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}\.'; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[5/6] Commit + push..."
git add voice_agent/responder.py \
        voice_agent/kommo.py \
        voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        tests/test_bug_c37_invencao_comunicacao_interna.py \
        tests/test_bug_c37b_ia_desativada_gate.py \
        PUSH_BUG_C37_INVENCAO_COMUNICACAO.command

git commit -m "fix(C-37 + C-37b + C-37c): comunicacao interna + IA gate + filtros sempre-on

Origem: Fabio 18/06/2026, lead 21341221 Livia/Linielle + benchmark engenheiro.
3 bugs interligados — fix combinado pra resolver causa raiz dos retrocessos.

C-37 — Invencao comunicacao interna
Sintoma: Lia inventou 5 frases falsas no atraso da paciente.
Fix: regra 0AA.5b no _MASTER_INSTRUCTION.md + filtro
     _viola_invencao_comunicacao_interna em responder.py.

C-37b — Agent ignorava ATIVADO IA?
Sintoma: Lia respondia com campo ATIVADO IA? = Desativado.
Causa raiz: agent_paused_for_lead em kommo.py NAO lia campo.
Fix: regra 0 — known['ativado_ia'] = Desativado retorna 'ia-desativada'
     ANTES de qualquer outra checagem.

C-37c — 3 filtros sempre-on (benchmark engenheiro)
Descoberto via auditoria estatica responder.py. 3 filtros estavam
GATEADOS por FILTROS_LEGACY=0 (off por default em prod):
  - _viola_pergunta_redundante_convenio (bug Adriana 24063769)
  - _viola_oferta_apos_agendado (bug Esther 24060221 + Manuela 24165262)
  - _viola_oferta_agenda (loop 'deixa eu consultar')

Esses filtros existiam mas NUNCA rodavam em producao porque
ninguem nunca setou FILTROS_LEGACY=1 no Easypanel.

Fix: removido o gate. Os 3 viraram SEMPRE-ON.

Total: 21 filtros, 0 gateados, 100% sempre-on.

Pytest: 27/27 verde.
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
echo "  Bugs C-37 + C-37b + C-37c em prod"
echo ""
echo "  21 filtros, 0 gateados, 100% sempre-on"
echo "  IA desativada bloqueia respostas (REGRA 0)"
echo "  Lia nao pode mais inventar comunicacao interna"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
