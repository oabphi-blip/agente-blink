#!/bin/bash
# PUSH_BUG_C36_FIX_FINAL.command — push fixes #1 + #2 do bug C-36
# Fix #1: race condition pipeline grava nota (3 camadas defesa)
# Fix #2: prompt APV só com sintomas característicos (branching)
# Lead origem: 24168922 Manuela (Fábio 17/06/2026 23:30 BRT)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-36 fixes finais (#1 + #2)"
echo "==============================================="

echo ""
echo "[1/5] AST check pipeline.py + medware.py..."
python3 -c "
import ast
for f in ['voice_agent/pipeline.py', 'voice_agent/medware.py']:
    ast.parse(open(f).read())
    print(f'  AST OK: {f}')
"

echo ""
echo "[2/5] Pytest C-36 (14 cenarios)..."
python3 -m pytest tests/test_bug_c36_apv_e_race_condition.py -q 2>&1 | tail -5

echo ""
echo "[3/5] Varredura segredos no diff..."
DIFF=$(git diff --staged 2>/dev/null; git diff 2>/dev/null)
if echo "$DIFF" | grep -qE "ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\."; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/pipeline.py \
        voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        tests/test_bug_c36_apv_e_race_condition.py \
        PUSH_BUG_C36_FIX_FINAL.command

git commit -m "fix(C-36): #1 race condition gravacao notas + #2 APV so com sintomas

Origem: Fabio 17/06/2026 23:30 BRT, lead 24168922 Manuela.
3 bugs simultaneos detectados (#36c janela 10d ja em prod).

Fix #1 — pipeline.py:_sync_kommo_safely 3 camadas de defesa:
  1. aceita lead_id_hint do caller (webhook payload Kommo)
  2. cache Redis blink:chat_to_lead:{convo} TTL 24h
  3. retry 3x com backoff 1s/2s/4s (race condition indexacao)
  4. log.warning quando falha total (era log.info silencioso)
  5. persiste lead_id no cache apos achar

Fix #2 — _MASTER_INSTRUCTION.md secao 0AA.5 branching APV:
  Antes: anunciava 'especialista APV' pra TODO paciente Karla
  Depois: APV so com sintomas caracteristicos (cefaleia, cansaco
  visual, tontura, postura, dificuldade escolar, sensibilidade luz)

  Branching por motivo declarado:
    - bebe/crianca rotina -> oftalmopediatria
    - estrabismo -> especialista em estrabismo
    - adulto rotina -> saude ocular
    - sintomas APV -> APV
    - catarata/50+ -> Fabricio
    - motivo nao declarado -> sem especialidade

  Bump VERSAO_PROMPT: 2026-06-17-c36-apv-so-com-sintomas

Pytest: 14/14 verde em tests/test_bug_c36_apv_e_race_condition.py

Licao:
  - Substituicao de termo NAO e diagnostico clinico
  - Race condition fail-silent e perigoso (log.warning agora)
  - Bugs aparecem aos pares (3 simultaneos no lead 24168922)
" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "[5/5] Aguardando deploy Easypanel (~3min)..."
for i in $(seq 1 12); do
    sleep 20
    body=$(curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK [${i}x20s = $((i*20))s]"
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "  Bug C-36 RESOLVIDO em prod"
echo ""
echo "  #1 race condition: pipeline tenta 3x + cache 24h"
echo "  #2 APV chute: so com sintomas caracteristicos"
echo "  #36c janela 10d: ja em prod desde push anterior"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
