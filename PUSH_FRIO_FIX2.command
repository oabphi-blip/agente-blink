#!/bin/bash
# Fix 2: helper detecta 1020 e expande 3 body_params automaticamente
# Remove pré-lookup duplicado que estava estourando timeout

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

WEBHOOK_SECRET=$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
AGENT="https://blink-agent.6prkfn.easypanel.host"

echo "==============================================="
echo "  Fix 2: 1020 auto-detect 3 params no helper"
echo "==============================================="

git add voice_agent/webhook.py PUSH_FRIO_FIX2.command
git commit -m "fix(webhook): helper detecta template 1020 e expande 3 params

Endpoint /admin/disparar-leads-frio-direto estava timeout porque o
loop fazia lookup duplicado: get_lead_main_contact UMA vez no endpoint
+ outra dentro do helper. Pra max=3 = 6 chamadas Kommo (15-25s).

Fix: helper _disparar_template_aprovado_para_lead detecta 'if 1020 in
template_name' e expande body_params=[primeiro, primeiro, 'consulta
anterior'] sozinho. Endpoint volta a fazer 1 lookup por lead (via
helper) em vez de 2." || echo "  (nada)"
git push origin main 2>&1 | tail -5

echo ""
echo "▶ Aguardando deploy (~3 min, testa a cada 20s)..."
for i in $(seq 1 12); do
    sleep 20
    body=$(curl -s --max-time 25 "${AGENT}/admin/disparar-leads-frio-direto?dry_run=true&max=2&secret=${WEBHOOK_SECRET}" 2>/dev/null || echo "")
    if [ -n "$body" ] && echo "$body" | grep -q '"ok"'; then
        echo "  ✓ LIVE [${i}x20s = $((i*20))s]"
        echo ""
        echo "▶ Dry-run 5 leads:"
        curl -s --max-time 60 "${AGENT}/admin/disparar-leads-frio-direto?dry_run=true&max=5&secret=${WEBHOOK_SECRET}" | python3 -m json.tool 2>/dev/null | head -80
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "  PRODUÇÃO REAL (cap 30 leads):"
echo ""
echo "  curl '${AGENT}/admin/disparar-leads-frio-direto?max=30&secret=\$WEBHOOK_SECRET' | jq"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
