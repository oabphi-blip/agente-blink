#!/bin/bash
# Push: Trigger automático Avaliação Google
# Quando lead vai pra 8-REALIZADO CONSULTA + médico = Dra. Karla
# Origem: Fábio 15/06/2026

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH TRIGGER GOOGLE REVIEW KARLA"
echo "==============================================================="
echo ""

# Sanity check
test -f voice_agent/webhook.py || { echo "ERRO: webhook.py não existe"; exit 1; }
test -f tests/test_trigger_google_review_karla.py || { echo "ERRO: pytest não existe"; exit 1; }

grep -q "kommo-trigger-google-review" voice_agent/webhook.py \
    || { echo "ERRO: endpoint kommo-trigger-google-review não está no webhook.py"; exit 1; }
grep -q "blink_pos_avaliacao_asa_norte_v1" voice_agent/webhook.py \
    || { echo "ERRO: template Asa Norte não está mapeado"; exit 1; }

python3 -c "import ast; ast.parse(open('voice_agent/webhook.py').read())" \
    || { echo "ERRO: webhook.py tem syntax error"; exit 1; }

echo "✓ Sanity check OK"
echo ""

git add voice_agent/webhook.py \
        tests/test_trigger_google_review_karla.py \
        PUSH_TRIGGER_GOOGLE_REVIEW_KARLA.command

git commit -m "feat(trigger): /admin/kommo-trigger-google-review — disparo template Google quando 8-REALIZADO + Karla

Origem: Fábio 15/06/2026. Quando atendimento humano move lead pra
8-REALIZADO CONSULTA (91486864) E médico = Dra. Karla Delalíbera, o
endpoint dispara automaticamente o template Meta:
- blink_pos_avaliacao_asa_norte_v1 (se unidade = Asa Norte)
- blink_pos_avaliacao_aguas_claras_v1 (se unidade = Águas Claras)

Filtros aplicados:
- status_id == 91486864 (8-REALIZADO)
- MEDICOS contém 'karla' (case-insensitive)
- UNIDADE in {Asa Norte, Águas Claras}
- Dedup Redis 90 dias por lead_id

Aceita JSON {lead_id, status_id} OU form-urlencoded nativo do
Kommo Automation. Query params: forcar=1 ignora dedup, dry_run=1
retorna decisão sem disparar.

Pós-disparo: grava nota Kommo + setex dedup Redis.

Pytest: 20 cenários cobrindo médico Karla/Fabrício/Kátia, unidades
Asa Norte/Águas Claras/Taguatinga, status correto/errado.

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
echo "PRÓXIMO PASSO: configurar Automação Kommo"
echo ""
echo "  1. Kommo → Configurações → Automações → Add"
echo "  2. Quando: lead muda pra 8-REALIZADO CONSULTA (91486864)"
echo "  3. Ação: HTTP Request (Webhook)"
echo "     URL: https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-google-review?secret=\$WEBHOOK_SECRET"
echo "     Method: POST"
echo "     Body: leads[status][0][id]={{lead.id}}&leads[status][0][status_id]={{lead.status_id}}"
echo "  4. Salvar"
echo ""
echo "TESTE MANUAL:"
echo ""
echo "  Trocar LEAD_ID por um lead real movido pra 8-REALIZADO + Karla:"
echo ""
echo "  curl -X POST \"https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-google-review?secret=\$WEBHOOK_SECRET&dry_run=1\" \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"lead_id\": LEAD_ID, \"status_id\": 91486864}'"
echo ""
echo "  Resposta esperada (dry_run):"
echo "  {ok:true, acao:'dry_run', template:'blink_pos_avaliacao_<unidade>_v1', body_params:[...]}"
echo ""
echo "  Remover dry_run=1 pra disparar de verdade."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
