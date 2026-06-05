#!/usr/bin/env bash
# Blink Bridge MCP — instalador automático
# Uso: bash install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "  Blink Bridge MCP — instalador"
echo "═══════════════════════════════════════════════════════════"
echo ""

# 1. Procura Python 3.10+ (MCP SDK exige isso)
PYTHON=""
for v in 3.13 3.12 3.11 3.10; do
  if command -v "python$v" &> /dev/null; then
    PYTHON="python$v"
    break
  fi
done

# Fallback: testa python3 default
if [ -z "$PYTHON" ] && command -v python3 &> /dev/null; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PYTHON="python3"
  fi
fi

if [ -z "$PYTHON" ]; then
  echo "✗ Python 3.10+ NÃO encontrado."
  echo ""
  echo "Você tem Python 3.9 ou mais antigo. O MCP SDK precisa 3.10+."
  echo ""
  echo "Instale Python 3.11 via Homebrew (5 min):"
  echo ""
  echo "  brew install python@3.11"
  echo ""
  echo "Depois roda este script de novo:"
  echo ""
  echo "  bash install.sh"
  echo ""
  exit 1
fi

PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
echo "✓ $PYTHON ($PY_VERSION) encontrado"

# 2. Cria venv isolado (remove anterior se existir e for de versão errada)
if [ -d "venv" ]; then
  EXISTING_VER=$(./venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
  EXISTING_MAJOR_MINOR=$(echo "$EXISTING_VER" | awk -F. '{print $1*10+$2}')
  if [ "$EXISTING_MAJOR_MINOR" -lt 310 ]; then
    echo "→ venv anterior tem Python $EXISTING_VER — removendo e recriando..."
    rm -rf venv
  fi
fi

if [ ! -d "venv" ]; then
  echo "→ Criando venv com $PYTHON..."
  $PYTHON -m venv venv
fi

# 3. Ativa venv e instala dependências
echo "→ Instalando dependências (mcp, httpx, python-dotenv)..."
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# 4. Cria .env.mcp se não existir
if [ ! -f ".env.mcp" ]; then
  cp .env.mcp.example .env.mcp
  echo ""
  echo "⚠  .env.mcp criado a partir do template."
  echo "   AGORA: edita .env.mcp e cola o WEBHOOK_SECRET real."
  echo "   Pega do Easypanel → app agent → Ambiente → WEBHOOK_SECRET"
  echo ""
fi

# 5. Valida import
echo "→ Validando import do módulo..."
python -c "from mcp.server.fastmcp import FastMCP; print('  ✓ MCP SDK carregado')"
python -c "import httpx; print('  ✓ httpx carregado')"
python -c "from dotenv import load_dotenv; print('  ✓ python-dotenv carregado')"

# 6. Caminho absoluto do Python venv pra config Claude Desktop
PYTHON_PATH="$SCRIPT_DIR/venv/bin/python"
SCRIPT_PATH="$SCRIPT_DIR/blink_bridge_mcp.py"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Instalação OK"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Próximos passos:"
echo ""
echo "1. Edita .env.mcp e cola o WEBHOOK_SECRET real:"
echo "   nano $SCRIPT_DIR/.env.mcp"
echo ""
echo "2. Adiciona ao Claude Desktop config:"
echo "   ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "   Adicione dentro de \"mcpServers\":"
echo ""
cat <<EOF
   "blink-bridge": {
     "command": "$PYTHON_PATH",
     "args": ["$SCRIPT_PATH"]
   }
EOF
echo ""
echo "3. Reinicia Claude Desktop (Cmd+Q + reabrir)"
echo ""
echo "4. Confirma que o MCP carregou: nova sessão, peça 'list mcps'"
echo ""
