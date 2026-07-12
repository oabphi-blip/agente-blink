#!/bin/bash
# INSTALAR_BLINK_ATENDIMENTO_MCP.command
# Camada 1 da MEMORIA ATIVA CLAUDE.
#
# Instala o servidor MCP `blink-atendimento` no Claude Desktop/Cowork.
# Após rodar + reiniciar Claude, quando URL de lead do Kommo aparecer,
# EU (Claude) tenho tool `ler_chat_completo_lead(lead_id)` obrigatoria
# antes de responder. Impede repetir bug Theo/Tiago (perguntar A/B/C
# sem ter lido chat).
#
# Duplo clique = tudo feito.

set -e

PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
MCP_DIR="$PROJETO/mcp_servers"
CFG_DIR="$HOME/Library/Application Support/Claude"
CFG_FILE="$CFG_DIR/claude_desktop_config.json"

echo "==============================================================="
echo "  INSTALAR blink-atendimento MCP — Camada 1 Memoria Ativa"
echo "==============================================================="

# ---------------------------------------------------------------------------
# [1/6] Extrair credenciais dos .env locais
# ---------------------------------------------------------------------------
echo ""
echo "[1/6] Lendo credenciais dos .env locais..."
KOMMO_TOKEN=""
WA_TOKEN=""
WA_PHONE_ID=""
MED_USER=""
MED_PASS=""

for env_file in \
    "$PROJETO/lia_engineer/.env.local" \
    "$PROJETO/.env" \
    "$PROJETO/.env.local" \
    "$PROJETO/voice_agent/.env"; do
    if [ -f "$env_file" ]; then
        [ -z "$KOMMO_TOKEN" ] && KOMMO_TOKEN=$(grep -E "^KOMMO_TOKEN=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        [ -z "$WA_TOKEN" ] && WA_TOKEN=$(grep -E "^WHATSAPP_CLOUD_TOKEN=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        [ -z "$WA_PHONE_ID" ] && WA_PHONE_ID=$(grep -E "^WHATSAPP_CLOUD_PHONE_NUMBER_ID=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        [ -z "$MED_USER" ] && MED_USER=$(grep -E "^MEDWARE_USER=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        [ -z "$MED_PASS" ] && MED_PASS=$(grep -E "^MEDWARE_PASSWORD=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
    fi
done

echo "  KOMMO_TOKEN: $([ -n "$KOMMO_TOKEN" ] && echo "OK (${#KOMMO_TOKEN} chars)" || echo "AUSENTE — obrigatório")"
echo "  WHATSAPP_CLOUD_TOKEN: $([ -n "$WA_TOKEN" ] && echo "OK" || echo "ausente (opcional)")"
echo "  MEDWARE_USER: $([ -n "$MED_USER" ] && echo "OK" || echo "ausente (opcional)")"

if [ -z "$KOMMO_TOKEN" ]; then
    echo ""
    echo "  ERRO: KOMMO_TOKEN é obrigatório e não foi encontrado nos .env."
    echo "  Adicione KOMMO_TOKEN=... em um dos arquivos:"
    echo "    $PROJETO/.env.local"
    echo "    $PROJETO/voice_agent/.env"
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi

# ---------------------------------------------------------------------------
# [2/6] Instalar/verificar uv
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] Verificando uv..."
if ! command -v uv &> /dev/null; then
    echo "  uv não instalado. Instalando (10s)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
UV_BIN="$(which uv)"
echo "  uv: $UV_BIN"

# ---------------------------------------------------------------------------
# [3/6] Sync deps Python
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] Sincronizando deps Python (mcp, httpx, pydantic)..."
cd "$MCP_DIR"
"$UV_BIN" sync --all-extras 2>&1 | tail -3

# ---------------------------------------------------------------------------
# [4/6] Testar import do blink_atendimento.server
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] Testando import do server..."
"$UV_BIN" run python -c "
from blink_atendimento import server
print('  OK — server carrega')
print(f'  MCP name: {server.mcp.name}')
" 2>&1 | tail -3

# ---------------------------------------------------------------------------
# [5/6] Rodar pytest (8 casos)
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] Rodando pytest do blink_atendimento (8 casos)..."
"$UV_BIN" run python -m pytest blink_atendimento/test_server.py -q --tb=line 2>&1 | tail -5

# ---------------------------------------------------------------------------
# [6/6] Registrar no claude_desktop_config.json (merge seguro)
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Atualizando claude_desktop_config.json..."

mkdir -p "$CFG_DIR"

if [ ! -f "$CFG_FILE" ]; then
    echo "  Arquivo não existia — criando..."
    echo '{"mcpServers": {}}' > "$CFG_FILE"
fi

# Exporta credenciais pra ambient — Python usa via os.environ
export KOMMO_TOKEN
export WA_TOKEN
export WA_PHONE_ID
export MED_USER
export MED_PASS
export UV_BIN
export MCP_DIR
export CFG_FILE

"$UV_BIN" run python <<'PY'
import json, os

cfg_path = os.environ["CFG_FILE"]
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

cfg.setdefault("mcpServers", {})
cfg["mcpServers"]["blink-atendimento"] = {
    "command": os.environ["UV_BIN"],
    "args": ["run", "python", "-m", "blink_atendimento.server"],
    "cwd": os.environ["MCP_DIR"],
    "env": {
        "KOMMO_TOKEN": os.environ.get("KOMMO_TOKEN", ""),
        "KOMMO_BASE_URL": "https://univeja.kommo.com/api/v4",
        "WHATSAPP_CLOUD_TOKEN": os.environ.get("WA_TOKEN", ""),
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID": os.environ.get("WA_PHONE_ID", ""),
        "MEDWARE_USER": os.environ.get("MED_USER", ""),
        "MEDWARE_PASSWORD": os.environ.get("MED_PASS", ""),
        "MEDWARE_BASE_URL": "https://medware.blinkoftalmologia.com.br/api",
    },
}

with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)

print(f"  ✓ blink-atendimento registrado em {cfg_path}")
print(f"  Servidores MCP configurados agora: {list(cfg['mcpServers'].keys())}")
PY

echo ""
echo "==============================================================="
echo "  ✓ INSTALAÇÃO CONCLUÍDA"
echo ""
echo "  PRÓXIMO PASSO OBRIGATÓRIO:"
echo "  1. Cmd+Q em Claude Desktop / Cowork"
echo "  2. Abre de novo"
echo "  3. Numa conversa comigo, cola URL de lead — ex:"
echo "     https://univeja.kommo.com/leads/detail/21759911"
echo ""
echo "  Eu vou chamar automaticamente:"
echo "     ler_chat_completo_lead(21759911)"
echo ""
echo "  e responder com base no chat REAL, não em suposição."
echo "==============================================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
