#!/bin/bash
# INSTALADOR Lia Engineer FORA do TCC (~/Documents/Claude/ é bloqueada pelo launchd).
# Reinstala completamente. Roda 1 tick imediato pra validar.
# Duplo-clique pra rodar.

set -e

SRC_REPO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
DEST_DIR="$HOME/.lia-engineer"
PLIST_DEST="$HOME/Library/LaunchAgents/com.blink.lia-engineer.plist"

echo "==============================================="
echo "  Lia Engineer — Instalação fora do TCC"
echo "==============================================="
echo ""

# 1. Limpar plist e launchd antigos
echo "▶ 1/7 Limpando instalação anterior..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true
rm -f "$PLIST_DEST"
echo "  ✓ Limpo"

# 2. Criar pasta destino fora de Documents/Claude
echo ""
echo "▶ 2/7 Criando $DEST_DIR..."
mkdir -p "$DEST_DIR/lia_engineer"
mkdir -p "$DEST_DIR/voice_agent"
mkdir -p "$DEST_DIR/logs"
echo "  ✓ Estrutura criada"

# 3. Copiar lia_engineer + .env.local + voice_agent (deps Python)
echo ""
echo "▶ 3/7 Copiando lia_engineer + .env.local + voice_agent..."
# IMPORTANTE: usar /. no source pra copiar dotfiles (.env.local)
cp -R "${SRC_REPO}/lia_engineer/." "$DEST_DIR/lia_engineer/"
cp -R "${SRC_REPO}/voice_agent/"*.py "$DEST_DIR/voice_agent/" 2>/dev/null || true
touch "$DEST_DIR/voice_agent/__init__.py"
echo "  ✓ Arquivos copiados"

# 4. Validar envs essenciais com aspas no path
echo ""
echo "▶ 4/7 Validando envs..."
ENV_FILE="$DEST_DIR/lia_engineer/.env.local"
REQUIRED_ENVS=(LIA_ENGINEER_GH_TOKEN SLACK_WEBHOOK_LIA_ENGINEER_URL ANTHROPIC_API_KEY KOMMO_TOKEN WEBHOOK_SECRET)
MISSING=()
for env_name in "${REQUIRED_ENVS[@]}"; do
  if ! grep -qE "^${env_name}=.+" "${ENV_FILE}"; then
    MISSING+=("$env_name")
  fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
  echo "  ❌ FALTAM envs:"
  for m in "${MISSING[@]}"; do
    echo "     • $m"
  done
  exit 1
fi
echo "  ✓ Todas envs preenchidas"

# 5. Garantir python3 + deps
echo ""
echo "▶ 5/7 Python + deps..."
if ! command -v python3 &> /dev/null; then
  echo "  ❌ python3 não encontrado"
  exit 1
fi
echo "  Python: $(python3 --version)"
python3 -m pip install --user --quiet --break-system-packages anthropic requests python-dotenv 2>/dev/null \
  || python3 -m pip install --user --quiet anthropic requests python-dotenv
echo "  ✓ deps instaladas"

# 6. Criar wrapper novo no destino + plist
echo ""
echo "▶ 6/7 Criando wrapper + plist..."
cat > "$DEST_DIR/wrapper.sh" << 'WRAPEOF'
#!/bin/bash
set -e
DIR="$HOME/.lia-engineer"
mkdir -p "$DIR/logs"
set -a; source "$DIR/lia_engineer/.env.local"; set +a
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
export PYTHONPATH="$DIR:$PYTHONPATH"
cd "$DIR"
TS=$(date +"%Y-%m-%d_%H-%M-%S")
LOG="$DIR/logs/tick_$TS.log"
{
  echo "=== Tick $TS ==="
  echo "Cwd: $(pwd)"
  echo "Python: $(which python3)"
  echo "ENGINEER_ENABLED: $LIA_ENGINEER_ENABLED"
  python3 -m lia_engineer.cli tick 2>&1
  echo "=== Fim ==="
} >> "$LOG" 2>&1
ls -t "$DIR/logs/tick_"*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null || true
WRAPEOF
chmod +x "$DEST_DIR/wrapper.sh"

cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.blink.lia-engineer</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$DEST_DIR/wrapper.sh</string>
  </array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DEST_DIR/logs/launchd-stdout.log</string>
  <key>StandardErrorPath</key><string>$DEST_DIR/logs/launchd-stderr.log</string>
  <key>WorkingDirectory</key><string>$DEST_DIR</string>
</dict>
</plist>
EOF
echo "  ✓ wrapper + plist instalados em ${DEST_DIR}"

# 7. Carregar via launchctl + tick imediato
echo ""
echo "▶ 7/7 Carregando launchd + tick imediato..."
launchctl load -w "$PLIST_DEST"
sleep 3

if launchctl list | grep -q "com.blink.lia-engineer"; then
  echo "  ✓ launchd ATIVO"
else
  echo "  ⚠️  launchctl list não mostrou — investigar"
fi

# Rodar 1 tick imediato pra validar
echo ""
echo "  Rodando tick imediato pra validar..."
bash "$DEST_DIR/wrapper.sh"
sleep 2

LAST_LOG=$(ls -t "$DEST_DIR/logs/tick_"*.log 2>/dev/null | head -1)
if [ -n "$LAST_LOG" ]; then
  echo ""
  echo "=== Saída do tick (últimas 30 linhas) ==="
  tail -30 "$LAST_LOG"
fi

echo ""
echo "==============================================="
echo "  ✓ INSTALAÇÃO COMPLETA"
echo "==============================================="
echo ""
echo "  • Ver status:  launchctl list | grep lia-engineer"
echo "  • Último log:  ls -t $DEST_DIR/logs/tick_*.log | head -1 | xargs cat"
echo "  • Parar:       launchctl unload -w $PLIST_DEST"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
