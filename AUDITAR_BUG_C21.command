#!/bin/bash
# Auditoria Bug C-21 — quantos dos 81 disparos do batch ferias julho atropelaram protocolo médico
# Duplo-clique pra rodar.

set -e

REPO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
cd "$REPO"

echo "==============================================="
echo "  Auditoria Bug C-21 — protocolo médico"
echo "==============================================="
echo ""
echo "Lê os 81 lead_ids disparados no batch julho e cruza com:"
echo "  • Campo 1.MÊS PRÓX CONSULTA (1260588)"
echo "  • Campo 1.DIA CONSULTA <6 meses (1255723)"
echo ""

python3 -m pip install --user --quiet --break-system-packages requests 2>/dev/null \
  || python3 -m pip install --user --quiet requests

python3 scripts/auditar_batch_julho_protocolo.py

echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
