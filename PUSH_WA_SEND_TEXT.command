#!/bin/bash
# Push endpoint /admin/wa-send-text/{lead_id} — resgate de mensagens com erro Kommo
# Fabio 12/06/2026 caso Carmen 24142996

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push endpoint /admin/wa-send-text"
echo "==============================================="

git add voice_agent/webhook.py PUSH_WA_SEND_TEXT.command

git commit -m "feat(admin): /admin/wa-send-text/{lead_id} - texto livre WA Cloud 8133

Fabio 12/06/2026 caso Carmen 24142996.

Endpoint POST/GET que envia TEXTO LIVRE via WhatsApp Cloud 8133 pra
um lead Kommo, usando a sessao de 24h ativa (paciente respondeu nas
ultimas 24h). Sem template Meta.

Use casos:
  - Resgate de mensagens humanas com status=erro no Kommo
  - Atendente humana sem acesso ao Meta Business escreve no Kommo,
    da erro de envio. Endpoint reenviar o texto direto via Meta Graph.

Fluxo:
  1. Pega telefone do lead via kommo.get_lead_main_contact
  2. Envia texto via wa_cloud.send_text(phone, text)
  3. Grava nota Kommo com timestamp + texto + wamid

Body JSON ou query params:
  - text (obrigatorio) - texto livre
  - secret (obrigatorio)
  - kommo_note (default true)

Pyloeam:
  curl 'https://blink-agent.6prkfn.easypanel.host/admin/wa-send-text/24142996?\\
text=Ola+Carmen!&secret=...'
" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "Aguardando deploy Easypanel (~3 min)..."
for i in $(seq 1 12); do
    sleep 20
    body=$(curl -s --max-time 15 "https://blink-agent.6prkfn.easypanel.host/admin/wa-send-text/24142996?secret=blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a" 2>/dev/null || echo "")
    if echo "$body" | grep -q "obrigatorio\|400"; then
        echo "  LIVE [${i}x20s = $((i*20))s]"
        echo "  $body"
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "Endpoint pronto. Disparo Carmen 24142996 sera"
echo "feito via JS console (texto Conclusao Agenda)."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
