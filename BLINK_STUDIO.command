#!/bin/bash
# BLINK_STUDIO.command
# Abre um "estudio" com 4 paineis pra vc acompanhar tudo em 1 tela.
# Detecta se voce tem iTerm2 (melhor) ou usa Terminal.app padrao.

PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
APP_URL="https://blink-agent.6prkfn.easypanel.host"
ALIASES_FILE="$HOME/.blink_aliases.sh"

# ---------------------------------------------------------------------------
# 1) Cria arquivo de aliases uteis (sobrescreve toda vez, garante atualidade)
# ---------------------------------------------------------------------------
cat > "$ALIASES_FILE" <<'ALIASES'
# Blink aliases — carregado no shell dos paineis do estudio.

BLINK_PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
BLINK_APP="https://blink-agent.6prkfn.easypanel.host"

# Extrai WEBHOOK_SECRET do .env.local do projeto.
_ws() {
    grep -E "^WEBHOOK_SECRET=" "$BLINK_PROJETO/lia_engineer/.env.local" 2>/dev/null \
        | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs
}

# Navegacao rapida
alias bd='cd "$BLINK_PROJETO"'
alias bc='cd "$BLINK_PROJETO" && claude --dangerously-skip-permissions'

# Prod status
alias bhz='curl -s "$BLINK_APP/health" | python3 -m json.tool 2>/dev/null || curl -s "$BLINK_APP/health"'
alias bslo='WS=$(_ws); open "$BLINK_APP/admin/slo?secret=$WS"'
alias bslojson='WS=$(_ws); curl -s "$BLINK_APP/admin/slo.json?secret=$WS" | python3 -m json.tool'

# Janela 24h
alias bjanela_diag='WS=$(_ws); curl -s "$BLINK_APP/admin/janela24h-diagnostico?secret=$WS" | python3 -m json.tool'
alias bjanela_flush='WS=$(_ws); curl -s -X POST "$BLINK_APP/admin/janela24h-cache-flush?secret=$WS" | python3 -m json.tool'

# Reativacao / broadcast / campanhas
alias breact='WS=$(_ws); curl -s "$BLINK_APP/reactivation/status?secret=$WS" | python3 -m json.tool'
alias bbroad='WS=$(_ws); curl -s "$BLINK_APP/broadcast/status?secret=$WS" | python3 -m json.tool'

# Templates Meta
alias btpls_sync='WS=$(_ws); curl -s -X POST "$BLINK_APP/admin/sync-meta-templates-to-kommo?secret=$WS" | python3 -m json.tool'

# Kommo lead — passa lead_id como argumento: bkl 24232988
bkl() {
    if [ -z "$1" ]; then
        echo "uso: bkl <lead_id>"
        return 1
    fi
    open "https://univeja.kommo.com/leads/detail/$1"
}

# Replay tracing de 1 lead
bkr() {
    if [ -z "$1" ]; then
        echo "uso: bkr <lead_id>"
        return 1
    fi
    WS=$(_ws)
    curl -s "$BLINK_APP/admin/replay/$1?secret=$WS" | python3 -m json.tool | head -80
}

# Git — atalhos frequentes
alias bg='cd "$BLINK_PROJETO" && git status --short'
alias bgl='cd "$BLINK_PROJETO" && git log --oneline -10'

# Push wrapper
bpush() {
    cd "$BLINK_PROJETO" || return 1
    if [ -z "$1" ]; then
        echo "uso: bpush 'mensagem do commit'"
        return 1
    fi
    git add -A && git commit -m "$1" && git push origin main
}

# Pytest — passa arquivo opcional: bt tests/test_bug_c38...
bt() {
    cd "$BLINK_PROJETO" || return 1
    if [ -z "$1" ]; then
        python3 -m pytest -q --tb=line 2>&1 | tail -20
    else
        python3 -m pytest "$@" -q --tb=line 2>&1 | tail -20
    fi
}

# Listar leads quentes de hoje (via reactivation status)
alias bquentes='breact | grep -A 2 daily_count'

# Painel resumo — 1 comando mostra tudo
bstatus() {
    echo "==================== BLINK STATUS ===================="
    date "+%d/%m %H:%M"
    echo ""
    echo "-- HEALTHZ --"
    bhz
    echo ""
    echo "-- REACTIVATION --"
    breact 2>/dev/null | grep -E "enabled|daily_count|dry_run" | head -5
    echo ""
    echo "-- JANELA 24H --"
    bjanela_diag 2>/dev/null | grep -E "toggle|redis_ultima|redis_rotulo|kommo_field" | head -6
    echo "======================================================"
}

echo "[blink] aliases carregados. use bstatus, bhz, bslo, bjanela_diag, bkl, bpush, bt..."
ALIASES

chmod +x "$ALIASES_FILE"

# ---------------------------------------------------------------------------
# 2) Detecta terminal preferido
# ---------------------------------------------------------------------------
have_iterm=0
if [ -d "/Applications/iTerm.app" ] || [ -d "$HOME/Applications/iTerm.app" ]; then
    have_iterm=1
fi

# ---------------------------------------------------------------------------
# 3) Abre o layout
# ---------------------------------------------------------------------------
if [ $have_iterm -eq 1 ]; then
    # iTerm2 — layout 2x2 splits com cada painel executando algo especifico.
    osascript <<'APPLESCRIPT'
tell application "iTerm"
    activate
    set newWindow to (create window with default profile)
    tell current session of newWindow
        write text "source ~/.blink_aliases.sh && bd && clear && echo '=== PAINEL 1: CLAUDE CODE ===' && echo 'Digite: bc  (pra iniciar Claude Code)'"
    end tell
    tell current session of newWindow
        set painel2 to (split horizontally with default profile)
    end tell
    tell painel2
        write text "source ~/.blink_aliases.sh && clear && echo '=== PAINEL 2: STATUS PROD (a cada 30s) ===' && while true; do clear; bstatus; sleep 30; done"
    end tell
    tell current session of newWindow
        set painel3 to (split vertically with default profile)
    end tell
    tell painel3
        write text "source ~/.blink_aliases.sh && bd && clear && echo '=== PAINEL 3: TERMINAL LIVRE ===' && echo 'Aliases prontos. Digite bstatus, bkl 24170466, bslo, etc.'"
    end tell
    tell painel2
        set painel4 to (split vertically with default profile)
    end tell
    tell painel4
        write text "source ~/.blink_aliases.sh && bd && clear && echo '=== PAINEL 4: LOGS + GIT ===' && watch -n 5 'git log --oneline -5; echo; ls -la outputs/*.csv 2>/dev/null | tail -3'"
    end tell
end tell
APPLESCRIPT

else
    # Terminal.app — abre 4 abas ao inves de splits (Terminal nao suporta splits via osascript).
    osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    set newWindow to do script "source ~/.blink_aliases.sh && cd \"$PROJETO\" && clear && echo '=== ABA 1 (Cmd+1): CLAUDE CODE ===' && echo 'Digite bc pra iniciar Claude Code'"
    tell application "System Events" to keystroke "t" using command down
    delay 0.4
    do script "source ~/.blink_aliases.sh && clear && echo '=== ABA 2 (Cmd+2): STATUS PROD (a cada 30s) ===' && while true; do clear; bstatus; sleep 30; done" in front window
    tell application "System Events" to keystroke "t" using command down
    delay 0.4
    do script "source ~/.blink_aliases.sh && cd \"$PROJETO\" && clear && echo '=== ABA 3 (Cmd+3): TERMINAL LIVRE ===' && echo 'Aliases carregados. Ex: bstatus, bkl 24170466, bslo, bpush mensagem'" in front window
    tell application "System Events" to keystroke "t" using command down
    delay 0.4
    do script "source ~/.blink_aliases.sh && cd \"$PROJETO\" && clear && echo '=== ABA 4 (Cmd+4): GIT + LOGS ===' && watch -n 5 'git log --oneline -5; echo; ls -la outputs/*.csv 2>/dev/null | tail -3'" in front window
end tell
APPLESCRIPT
fi

echo ""
echo "==============================================="
echo "  Blink Studio aberto."
echo ""
echo "  Aliases carregados em: $ALIASES_FILE"
echo ""
echo "  ATALHOS PRA VOCE DECORAR:"
echo "    bstatus         — painel resumo (healthz + reactivation + janela)"
echo "    bhz             — /health"
echo "    bslo            — abre dashboard SLO no browser"
echo "    bkl <lead_id>   — abre lead no Kommo"
echo "    bkr <lead_id>   — replay do lead (traces)"
echo "    bjanela_diag    — diagnostico da JANELA 24H"
echo "    bjanela_flush   — flush do cache travado"
echo "    breact          — status reactivation"
echo "    bc              — entra no projeto + roda Claude Code"
echo "    bpush 'msg'     — git add + commit + push"
echo "    bt              — pytest curto"
echo "    bg / bgl        — git status / log"
echo ""
echo "  Pra USAR OS ALIASES em qualquer terminal novo, adiciona no seu"
echo "  ~/.zshrc essa linha (1x, permanente):"
echo "    source ~/.blink_aliases.sh"
echo "==============================================="
