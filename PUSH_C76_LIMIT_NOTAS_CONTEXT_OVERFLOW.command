#!/bin/bash
# Push Bug C-76 — limitar notas 15 + truncar 500 chars (evita 400 contexto Claude API)
# Commit: 68a4114
cd "$(dirname "$0")"

echo "=== push ==="
git push origin main

echo ""
echo "=== DONE — deploy automático Easypanel em ~2min ==="
echo "Commit: 68a4114 (C-76 get_lead_notes limit=15 + truncar nota 500 chars)"
