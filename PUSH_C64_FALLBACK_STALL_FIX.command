#!/bin/bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
echo "=== Push C-64: fix loop circular fallback stall ==="
git push origin main
echo ""
echo "=== Commits no push ==="
git log --oneline origin/main..main 2>/dev/null || git log --oneline -3
echo ""
echo "=== DONE ==="
