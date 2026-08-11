#!/bin/bash
# Wrapper do Lia Engineer pra rodar via launchd (cron macOS)
# Source as envs locais e executa 1 tick.

set -e

REPO_ROOT="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
LOG_DIR="$REPO_ROOT/bin/logs"
mkdir -p "$LOG_DIR"

# Carregar envs locais
set -a
source "$REPO_ROOT/lia_engineer/.env.local"
set +a

# Carregar Python 3.11+ — ajustar PATH pra incluir python3 do user
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

# Mudar pra diretório do repo
cd "$REPO_ROOT"

# Rodar tick com log timestamped
TS=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/tick_$TS.log"

{
  echo "=== Lia Engineer tick — $TS ==="
  echo "Cwd: $(pwd)"
  echo "Python: $(which python3)"
  echo "Engineer ENABLED: $LIA_ENGINEER_ENABLED"
  echo ""
  python3 -m lia_engineer.cli tick
  echo ""
  echo "=== Fim do tick ==="
} >> "$LOG_FILE" 2>&1

# Manter só os últimos 100 logs (housekeeping)
cd "$LOG_DIR"
ls -t tick_*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null || true
