#!/bin/bash
set -e

cd "$HOME/Documents/Claude/Projects/AGENTE IA BLINK"

# 1. Limpa qualquer git anterior
rm -rf .git

# 2. Garante .gitignore com segredos protegidos
cat > .gitignore << 'EOF'
# Secrets — NEVER commit
.env
.env.local
*.env
!.env.example
config.json

# Build artifacts
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/

# Local-only build files
.deploy_dockerfile_v2.txt
.deploy_dockerfile_v3.txt
blink-agent.tar.xz
blink-agent.zip
EOF

# 3. Inicia repo, adiciona e commita
git init -b main
git config user.email "oabphi@gmail.com"
git config user.name "Fábio"
git add -A
git commit -m "Initial commit: voice agent with STJ/Tribunal fix"

# 4. Conecta ao GitHub e empurra
git remote add origin https://github.com/oabphi-blip/agente-blink.git
git push -u origin main

echo ""
echo "✅ Push concluído. Agora volte para a janela do Easypanel e diga 'pronto' que eu finalizo o deploy."
