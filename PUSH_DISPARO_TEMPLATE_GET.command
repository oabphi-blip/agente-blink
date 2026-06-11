#!/bin/bash
# Push endpoint GET /admin/disparar-template-get/{lead_id}
# Bypassa dispatcher hardcoded — aceita template + body_params via query.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push endpoint disparar-template-get (Slack #04)"
echo "==============================================="

git add voice_agent/webhook.py PUSH_DISPARO_TEMPLATE_GET.command
git commit -m "feat(webhook): GET /admin/disparar-template-get/{id} bypass dispatcher

Sessão 11/06/2026 — Fábio: 'envio autônomo pacientes 1+ ano'.

Endpoint POST existente exigia JSON body que web_fetch não envia
(só GET). Nova variante GET aceita template + body_params via query
(CSV separado por '|').

Uso:
  GET /admin/disparar-template-get/{lead_id}
    ?template=1089_mens_ativar_conv_parada_qz7kbz
    &body_params=Cecilia
    &secret=\$WS

Resolve Bug C-25 sem precisar trocar env Easypanel — chamador escolhe
o template aprovado real (1089, 1079, blink_lf_*, etc) em vez de
depender do dispatcher hardcoded em 1039_ativar_grau_de_urgencia
(que NÃO existe no Meta — erro 132001)." || echo "  (nada novo)"
git push origin main 2>&1 | tail -5

echo ""
echo "✓ Push completo. Deploy Easypanel ~3 min."
echo "  Após deploy: o Claude (Cowork) detecta endpoint live e dispara"
echo "  os 13 leads do Slack #04 autonomamente via web_fetch."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
