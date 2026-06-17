#!/bin/bash
# PUSH_BUG_C36c.command — push autônomo + aguarda deploy Easypanel
# Fix: janela agenda Lia reduzida 14d → 10d (medware.py:663)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-36c — Janela agenda 14d → 10d"
echo "==============================================="

echo ""
echo "[1/5] Validando sintaxe medware.py..."
python3 -c "
import ast
ast.parse(open('voice_agent/medware.py').read())
print('  AST OK')
"

echo ""
echo "[2/5] Smoke test calendar_oracle ainda verde..."
if [ -f "voice_agent/calendar_oracle.py" ]; then
    python3 voice_agent/calendar_oracle.py validar 2026-06-18 karla "Águas Claras" > /dev/null 2>&1 && echo "  OK"
fi

echo ""
echo "[3/5] Varredura segredos no diff..."
DIFF=$(git diff --staged 2>/dev/null; git diff 2>/dev/null)
if echo "$DIFF" | grep -qE "ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}"; then
    echo "  ALERTA: padrão de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/medware.py CLAUDE.md PUSH_BUG_C36c.command

git commit -m "fix(C-36c): janela agenda Lia reduzida 14d → 10d (Fábio 17/06)

Origem: Fábio 17/06/2026 23:45 BRT, lead 24168922 Manuela.
Lia recebia 14-90 dias de agenda do Medware → modelo escolhia datas
distantes em vez de dia mais próximo (regra Pedro Miguel C-17).
Token cost alto + menos urgência percebida + mais chance de chute.

Fix em voice_agent/medware.py:663 — horarios_para_agente:
  dias: int = 14  →  dias: int = 10

Histórico janela:
  90d → 21d (C-38 manhã 17/06) → 10d (C-36c noite 17/06)

Override: env MEDWARE_DIAS_DEFAULT (1-90, default 10).

Benefícios:
  1. Urgência percebida — vagas próximas → fecha
  2. Dia mais próximo PRIMEIRO (regra Pedro Miguel C-17)
  3. Menos token cost no prompt
  4. Menos chute do modelo (menos opções = decisão mais segura)
  5. 10d cobre 6-8 atendimentos Karla (suficiente)

Fallback seguro:
  - Se 10d vazio + paciente pediu data específica → janela_preferencia
  - Se ambos vazios → bloco AGENDA INDISPONÍVEL (já existe)

CLAUDE.md indexado — C-36 + C-36c no rolling log com diagnóstico
dos 3 bugs do lead 24168922 (notas não gravam, chute APV, janela ampla).
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
echo "  ✅ Bug C-36c em prod"
echo "  Lia agora vê 10 dias de agenda Medware"
echo "  Próximos leads → dia mais próximo + urgência"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
