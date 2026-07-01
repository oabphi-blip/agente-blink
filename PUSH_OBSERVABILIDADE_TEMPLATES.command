#!/bin/bash
# PUSH_OBSERVABILIDADE_TEMPLATES.command
# Parte 2 — Observabilidade Templates Meta no Kommo:
#  * Endpoint /admin/sync-meta-templates-to-kommo + worker cron 1h
#  * gravar_template_disparado em renovacao_dispatcher.py e broadcast.py
#  * Webhook Meta /whatsapp atualiza STATUS ULTIMO DISPARO via wamid
#  * Pytest 15 cenarios

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Observabilidade Templates Meta -> Kommo"
echo "==============================================="

echo ""
echo "[1/5] AST check (9 arquivos)..."
python3 -c "
import ast
arquivos = [
    'voice_agent/templates_observabilidade.py',
    'voice_agent/scripts/sync_meta_to_kommo.py',
    'voice_agent/cron_interno.py',
    'voice_agent/webhook.py',
    'voice_agent/whatsapp_cloud.py',
    'voice_agent/renovacao_dispatcher.py',
    'voice_agent/broadcast.py',
    'voice_agent/kommo.py',
    'tests/test_templates_observabilidade.py',
]
for f in arquivos:
    ast.parse(open(f).read())
    print('  AST OK:', f)
"

echo ""
echo "[2/5] Pytest observabilidade (15 cenarios)..."
python3 -m pytest tests/test_templates_observabilidade.py -q --tb=line 2>&1 | tail -3

echo ""
echo "[3/5] Pytest combinado (templates + observabilidade)..."
python3 -m pytest tests/test_templates_observabilidade.py tests/test_templates_meta.py -q --tb=line 2>&1 | tail -3

echo ""
echo "[4/5] Varredura segredos no diff..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[5/5] Commit + push..."
git add \
    voice_agent/templates_observabilidade.py \
    voice_agent/scripts/sync_meta_to_kommo.py \
    voice_agent/scripts/criar_campos_kommo_templates_meta.py \
    voice_agent/cron_interno.py \
    voice_agent/webhook.py \
    voice_agent/whatsapp_cloud.py \
    voice_agent/renovacao_dispatcher.py \
    voice_agent/broadcast.py \
    voice_agent/kommo.py \
    tests/test_templates_observabilidade.py \
    SETUP_TEMPLATES_META_KOMMO.command \
    PUSH_OBSERVABILIDADE_TEMPLATES.command

git commit -m "feat(observabilidade-meta): sync templates Meta + Kommo + dispatch tracking

Implementa observabilidade categorizada de templates Meta no Kommo.

5 custom fields no Kommo (criados via SETUP_TEMPLATES_META_KOMMO.command):
  - ULTIMO TEMPLATE META (select)
  - TEMPLATES JA RECEBIDOS (multiselect)
  - CATEGORIA TEMPLATE (select 9 categorias)
  - DATA ULTIMO DISPARO META (date_time)
  - STATUS ULTIMO DISPARO (select sent/delivered/read/failed)

Sincronizacao Meta -> Kommo:
  - voice_agent/scripts/sync_meta_to_kommo.py com funcao publica sincronizar()
  - Endpoint /admin/sync-meta-templates-to-kommo (manual)
  - Worker cron 1h (_worker_sync_templates_meta_loop, default ON)
  - Categorizacao por prefixo + LEGACY_ALLOWLIST pra templates antigos

Dispatch tracking:
  - voice_agent/templates_observabilidade.py com
    gravar_template_disparado() + lookup_lead_por_wamid() +
    atualizar_status_ultimo_disparo() + descobrir_field_ids() (cache modulo)
  - renovacao_dispatcher.py e broadcast.py chamam gravar_template_disparado
    apos cada envio bem-sucedido (captura wamid, grava nos 5 campos +
    Redis blink:wamid_lead:{wamid} TTL 7d).

Webhook status:
  - whatsapp_cloud.py::parse_status_callbacks() extrai wamid+status do payload
  - webhook /whatsapp em webhook.py: pra cada status, faz lookup
    Redis wamid -> lead_id e atualiza STATUS ULTIMO DISPARO

Pytest: 15/15 verde. Combinado 38/38 em 0.07s.

Decisoes:
  - TEMPLATES JA RECEBIDOS grava o template do disparo atual (acumular
    historico exigiria GET previo em todo disparo)
  - free_form_renovacao_24h tambem registrado, categoria Operacional
  - Worker default ON seguindo regra C-32 do CLAUDE.md
  - Best-effort: falhas em gravar_template_disparado nao derrubam disparo

Origem: Fabio 28/06/2026 — observabilidade categorizada dos templates
disparados, fonte da verdade = Meta API, espelho Kommo via custom fields.
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
echo "  Observabilidade Templates em prod."
echo ""
echo "  PROXIMOS PASSOS:"
echo "  1. Roda 1x SETUP_TEMPLATES_META_KOMMO.command pra criar os"
echo "     5 custom fields no Kommo (se ainda nao rodou)."
echo "  2. No Kommo: cria grupo 'Templates Meta' e arrasta os 5 campos."
echo "  3. Worker cron sincronizara enums a cada 1h automaticamente."
echo "  4. A partir do proximo disparo, todo template gravara nos 5"
echo "     campos do lead. Sem mais nota livre — agora eh estruturado."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
