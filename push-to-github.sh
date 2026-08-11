#!/bin/bash
# Push simples para o GitHub — NÃO destrói o .git existente.
set -e

cd "$HOME/Documents/Claude/Projects/AGENTE IA BLINK"

# Se não tem repo, inicializa uma vez só
if [ ! -d ".git" ]; then
  git init -b main
  git config user.email "oabphi@gmail.com"
  git config user.name "Fábio"
  git remote add origin https://github.com/oabphi-blip/agente-blink.git
fi

git push --force origin main

echo ""
echo "✅ Push concluído. Easypanel fará o deploy automático em 2-5 min."
