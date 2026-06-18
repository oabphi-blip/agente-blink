#!/bin/bash
# PUSH_FIX_ENDPOINTS_SRE.command
# Fix: webhook.py nao foi commitado no sprint SRE. Reaplica os 10 endpoints.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Re-aplicar endpoints sprint SRE no webhook.py"
echo "==============================================="

echo ""
echo "[1/4] AST + endpoints check..."
python3 -c "import ast; ast.parse(open('voice_agent/webhook.py').read()); print('  AST OK')"
N=$(grep -c "/admin/slo\|/admin/auditoria-diaria\|/admin/synthetic-tick\|/admin/prompt-versions\|/admin/prompt-diff\|/admin/chaos" voice_agent/webhook.py)
echo "  Endpoints SRE em webhook.py: $N (deve ser >= 10)"

echo ""
echo "[2/4] Commit + push..."
git add voice_agent/webhook.py PUSH_FIX_ENDPOINTS_SRE.command

git commit -m "fix(sprint-sre): reaplica 10 endpoints admin em webhook.py

O commit 44f125c (sprint SRE) trouxe os modulos slo.py, auditoria_diaria.py,
synthetic_users.py, error_budget.py, prompt_versioning.py, chaos.py — mas
o webhook.py NAO foi commitado, entao /admin/slo retornava 404 em prod.

Reaplicado:
  - /admin/slo (HTML) + /admin/slo.json
  - /admin/auditoria-diaria
  - /admin/synthetic-tick
  - /admin/prompt-versions + /admin/prompt-diff
  - /admin/chaos-tick + /admin/chaos-stop + /admin/chaos-status + /admin/chaos-suite

Todos autenticam via settings.webhook_secret (mesmo padrao do /admin/replay).
" || echo "  (nada a commitar)"

git push origin main 2>&1 | tail -5

echo ""
echo "[3/4] Aguardando deploy Easypanel (~3min)..."
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
echo "[4/4] Validando /admin/slo em prod..."
WEBHOOK_SECRET="blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a"
SLO_RESP=$(curl -s --max-time 15 "https://blink-agent.6prkfn.easypanel.host/admin/slo.json?secret=${WEBHOOK_SECRET}")
echo "$SLO_RESP" | head -c 800
echo ""

if echo "$SLO_RESP" | grep -q "Not Found"; then
    echo ""
    echo "  AINDA 404 -- esperar mais 1min e tentar de novo"
    sleep 60
    curl -s --max-time 15 "https://blink-agent.6prkfn.easypanel.host/admin/slo.json?secret=${WEBHOOK_SECRET}" | head -c 800
elif echo "$SLO_RESP" | grep -q "slo_24h\|error_budget"; then
    echo ""
    echo "  SLO endpoint funcionando!"
fi

echo ""
echo "==============================================="
echo "  Done. Visite /admin/slo no browser pra ver dashboard."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
