#!/bin/bash
# SETUP_TEMPLATES_META_KOMMO.command
# Cria 5 custom fields no Kommo + sincroniza enums com templates Meta aprovados.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Setup Templates Meta -> Kommo"
echo "==============================================="

# Pega KOMMO_TOKEN e WHATSAPP_CLOUD_TOKEN do .env.local
ENV_FILE="lia_engineer/.env.local"
if [ ! -f "$ENV_FILE" ]; then
    echo "ERRO: $ENV_FILE nao encontrado."
    read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
    exit 1
fi

KOMMO_TOKEN=$(grep -E "^KOMMO_TOKEN=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
META_TOKEN=$(grep -E "^WHATSAPP_CLOUD_TOKEN=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
WABA_ID=$(grep -E "^WHATSAPP_CLOUD_WABA_ID=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)

if [ -z "$KOMMO_TOKEN" ]; then
    echo "KOMMO_TOKEN nao encontrado em $ENV_FILE. Cole (oculto) e Enter:"
    read -s KOMMO_TOKEN
    echo ""
fi
if [ -z "$META_TOKEN" ]; then
    echo "WHATSAPP_CLOUD_TOKEN nao encontrado. Cole (oculto) e Enter:"
    read -s META_TOKEN
    echo ""
fi

export KOMMO_TOKEN
export KOMMO_SUBDOMAIN="${KOMMO_SUBDOMAIN:-univeja}"
export WHATSAPP_CLOUD_TOKEN="$META_TOKEN"
export WHATSAPP_CLOUD_WABA_ID="${WABA_ID:-1990931811727552}"

echo ""
echo "[1/2] Criando custom fields no Kommo (idempotente)..."
echo "--------------------------------------------"
python3 voice_agent/scripts/criar_campos_kommo_templates_meta.py
if [ $? -ne 0 ]; then
    echo ""
    echo "Algum campo falhou. Verifica /tmp/blink_campos_kommo_templates.json"
    read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
    exit 1
fi

echo ""
echo "[2/2] Sincronizando enums Meta -> Kommo..."
echo "--------------------------------------------"
python3 voice_agent/scripts/sync_meta_to_kommo.py

echo ""
echo "==============================================="
echo "  Setup concluido."
echo ""
echo "  Proximos passos manuais no Kommo:"
echo "  1. Abre univeja.kommo.com -> Configuracoes ->"
echo "     Setor 'Leads' -> Custom Fields"
echo "  2. Cria um Grupo (Tab) chamado 'Templates Meta'"
echo "  3. Move pra dentro dele os 5 campos criados:"
echo "     - ULTIMO TEMPLATE META"
echo "     - TEMPLATES JA RECEBIDOS"
echo "     - CATEGORIA TEMPLATE"
echo "     - DATA ULTIMO DISPARO META"
echo "     - STATUS ULTIMO DISPARO"
echo "  4. Salva."
echo ""
echo "  Output detalhado:"
echo "    /tmp/blink_campos_kommo_templates.json"
echo "    /tmp/blink_sync_meta_kommo.json"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
