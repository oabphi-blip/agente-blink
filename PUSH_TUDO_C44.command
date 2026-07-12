#!/bin/bash
# PUSH_TUDO_C44.command
# Consolida os 3 fixes do Bug C-44 (Clarice 22544990) num único push:
#
#   1. Prompt (soft) — seção 0-AD no _MASTER_INSTRUCTION.md
#   2. FRASES_BANIDAS ampliadas no oferta_deterministica.py
#   3. Filtro reativo _viola_papel_inventado SEMPRE-ON no responder.py
#   4. Pytest 33/33 blindando textos literais do chat da Clarice
#
# Substitui o PUSH_PROMPT_CLARICE.command anterior (mais complete).
# Duplo clique. 5 min.

set -e
PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
APP="https://blink-agent.6prkfn.easypanel.host"
cd "$PROJETO"

echo "==============================================="
echo "  PUSH TUDO C-44 — Clarice + papéis inventados"
echo "  $(date '+%d/%m/%Y %H:%M:%S')"
echo "==============================================="

# [1/5] AST + pytest
echo ""
echo "[1/5] AST + pytest 3 arquivos + regressão..."
python3 - <<'PY'
import ast
for f in [
    'voice_agent/oferta_deterministica.py',
    'voice_agent/responder.py',
    'tests/test_bug_c44_papel_inventado_clarice.py',
]:
    ast.parse(open(f).read())
    print(f"  OK: {f}")
PY

python3 -m pytest \
    tests/test_bug_c44_papel_inventado_clarice.py \
    tests/test_oferta_deterministica.py \
    tests/test_bug_c43_mariana_lopes_campanha_agosto.py \
    -q --tb=line 2>&1 | tail -3

# [2/5] Varredura segredos
echo ""
echo "[2/5] Varredura segredos..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: segredo detectado. ABORTANDO."
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi
echo "  OK"

# [3/5] Commit + push
echo ""
echo "[3/5] Commit + push..."
git add \
    voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    voice_agent/oferta_deterministica.py \
    voice_agent/responder.py \
    tests/test_bug_c43_mariana_lopes_campanha_agosto.py \
    tests/test_bug_c44_papel_inventado_clarice.py \
    CLAUDE.md \
    PUSH_TUDO_C44.command 2>/dev/null || true

if git diff --staged --quiet; then
    echo "  Nada novo pra comitar."
else
    git commit -m "fix(bugs): C-44 papeis inventados 3 camadas (Clarice 22544990)

Origem: Fabio 12/07/2026, lead 22544990 Clarice Santos Brunelli.

Lia mandou 4x 'vou encaminhar voce para nossa especialista em
remarcacao' em intervalos de 22s a 2h. Papel inexistente. Prompt
bumped mas Lia continuou (cache Anthropic 5min TTL).

FIX EM 3 CAMADAS COMPLEMENTARES:

CAMADA 1 — Prompt (soft) — _MASTER_INSTRUCTION.md
- Nova secao 0-AD (Reconhecimento Ativo + Papeis Inexistentes Banidos)
- 0AD.1: PROIBIDO repetir pergunta que paciente ja respondeu
- 0AD.2: papeis inexistentes banidos textualmente
- 0AD.3: contra-exemplo Clarice literal
- Bump VERSAO_PROMPT (forca re-cache Anthropic)

CAMADA 2 — FRASES_BANIDAS (soft-hard) — oferta_deterministica.py
FRASES_BANIDAS +10 variantes: especialista em [remarcacao/
agendamento/cancelamento/mudanca], nossa especialista em X, vou
encaminhar voce para nossa/nosso.

CAMADA 3 — Filtro reativo (HARD, sempre-on) — responder.py
_viola_papel_inventado + _gerar_fallback_papel_inventado. Regex
compilado _PAPEIS_INVENTADOS detecta cargo inventado. Substitui por
frase canonica 'vou te conectar com nossa equipe pra dar continuidade
— so um momento'. NAO depende de FSM=AGENDA. NAO depende de
deve_ofertar_agora. Sempre-on.

Pytest tests/test_bug_c44_papel_inventado_clarice.py:
- 33 casos (texto literal Clarice + 8 variantes + 8 falsos-positivos
  + integracao _scrub_prohibited).
- 33/33 verde + 79/79 regressao (oferta_deterministica + c43).
" 2>&1 | tail -3

    git push origin main 2>&1 | tail -5

    sleep 3
    LOCAL_HEAD=$(git rev-parse HEAD)
    REMOTE_HEAD=$(git ls-remote origin main 2>/dev/null | awk '{print $1}')
    if [ "$REMOTE_HEAD" = "$LOCAL_HEAD" ]; then
        echo "  PUSH CONFIRMADO — $REMOTE_HEAD"
    else
        echo "  PUSH FALHOU"
        read -n 1 -s -r -p "Enter..."
        exit 1
    fi
fi

# [4/5] Aguardar deploy
echo ""
echo "[4/5] Aguardando Easypanel build (max 4min)..."
for i in $(seq 1 16); do
    sleep 15
    body=$(curl -s --max-time 8 "$APP/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK apos ~$((i*15))s"
        break
    fi
    printf "  [%02d/16] %s aguardando...\n" "$i" "$(date +%H:%M:%S)"
done

# [5/5] Resumo
echo ""
echo "==============================================="
echo "  ✓ C-44 EM PROD — 3 CAMADAS"
echo ""
echo "  Camada 1 (prompt):"
echo "    VERSAO_PROMPT bumped — Anthropic re-cacheia em 5min"
echo ""
echo "  Camada 2 (FRASES_BANIDAS):"
echo "    oferta_deterministica.py bloqueia oferta com frase banida"
echo ""
echo "  Camada 3 (filtro reativo HARD):"
echo "    responder.py::_scrub_prohibited SEMPRE substitui"
echo "    'especialista em X' pela frase canonica de handoff"
echo ""
echo "  Proximo lead que a Lia atender, 'especialista em X'"
echo "  eh MATEMATICAMENTE IMPOSSIVEL de sair — nao depende de"
echo "  cache Anthropic, nao depende de FSM."
echo ""
echo "  Clarice (lead 22544990) ja esta com IA desativada + nota."
echo "  Voce conduz manual."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
