#!/bin/bash
# Batch ativação — lista de julho — template blink_proxima_consulta_ferias_v1
# Duplo-clique pra rodar.
#
# Lê WEBHOOK_SECRET + KOMMO_TOKEN do .env local + dispara 184 leads via endpoint
# /admin/disparar-template/{lead_id}. Cada disparo grava nota Kommo automática.

set -e

REPO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
cd "$REPO"

echo "==============================================="
echo "  Batch ativação — julho — template férias"
echo "  Lista: 184 entradas do canal Slack"
echo "==============================================="
echo ""

# Garantir Python + requests
if ! command -v python3 &> /dev/null; then
  echo "❌ python3 não encontrado"
  exit 1
fi
python3 -m pip install --user --quiet --break-system-packages requests 2>/dev/null \
  || python3 -m pip install --user --quiet requests

echo "▶ Rodando batch_ferias_julho.py..."
echo ""
python3 scripts/batch_ferias_julho.py

echo ""
echo "==============================================="
echo "  ✓ BATCH COMPLETO"
echo "==============================================="
echo ""
echo "  Logs em: scripts/log_batch_ferias_julho_*.txt"
echo "  Notas Kommo gravadas automaticamente em cada lead disparado."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
