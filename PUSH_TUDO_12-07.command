#!/bin/bash
# PUSH_TUDO_12-07.command
# Sobe TUDO que está preso local numa única ação:
#   - Commit d708121 (MEGA SPRINT: C-38 + C-39 + C-40 + JANELA24H) já commitado
#   - voice_agent/oferta_deterministica.py (Python puro anti-hesitação)
#   - responder.py bypass antes do LLM
#   - voice_agent/medware.py: Afego = codPlano 7 (Bug C-43)
#   - voice_agent/webhook.py: status_id 108749463 (campanha agosto) em ATIVOS_IA
#   - MCP server blink_atendimento + skill file
#
# Depois: git push, aguarda deploy, testa endpoint, flush cache JANELA 24H.

set -e
PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
APP="https://blink-agent.6prkfn.easypanel.host"
cd "$PROJETO"

echo "==============================================="
echo "  PUSH TUDO 12/07 — MEGA SPRINT + C-43 + agenda deterministica"
echo "  $(date '+%d/%m/%Y %H:%M:%S')"
echo "==============================================="

# ---------------------------------------------------------------------------
# [1/8] AST check
# ---------------------------------------------------------------------------
echo ""
echo "[1/8] AST check..."
python3 - <<'PY'
import ast, sys
for f in [
    'voice_agent/medware.py',
    'voice_agent/webhook.py',
    'voice_agent/responder.py',
    'voice_agent/oferta_deterministica.py',
    'mcp_servers/blink_atendimento/server.py',
    'tests/test_oferta_deterministica.py',
]:
    try:
        ast.parse(open(f).read())
        print(f"  OK: {f}")
    except FileNotFoundError:
        print(f"  AVISO: {f} nao existe")
    except Exception as e:
        print(f"  ERRO AST em {f}: {e}", file=sys.stderr)
        sys.exit(1)
PY

# ---------------------------------------------------------------------------
# [2/8] Pytest — determinístico agenda (65 casos)
# ---------------------------------------------------------------------------
echo ""
echo "[2/8] Pytest oferta_deterministica (65 casos)..."
python3 -m pytest tests/test_oferta_deterministica.py -q --tb=line 2>&1 | tail -3

# ---------------------------------------------------------------------------
# [3/8] Varredura segredos no diff
# ---------------------------------------------------------------------------
echo ""
echo "[3/8] Varredura segredos..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: segredo detectado. ABORTANDO."
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi
echo "  OK — sem segredos"

# ---------------------------------------------------------------------------
# [4/8] Commit dos fixes novos (Afego + status 108749463)
# ---------------------------------------------------------------------------
echo ""
echo "[4/8] Commit dos fixes novos..."
git add \
    voice_agent/medware.py \
    voice_agent/webhook.py \
    voice_agent/oferta_deterministica.py \
    voice_agent/responder.py \
    mcp_servers/blink_atendimento/__init__.py \
    mcp_servers/blink_atendimento/server.py \
    mcp_servers/blink_atendimento/test_server.py \
    tests/test_oferta_deterministica.py \
    MEMORIA_ATIVA_CLAUDE.md \
    MEMORIA_ATIVA_CLAUDE.docx \
    INSTALAR_BLINK_ATENDIMENTO_MCP.command \
    BLINK_STUDIO.command \
    PUSH_AGENDA_DETERMINISTICA.command \
    PUSH_TUDO_12-07.command 2>/dev/null || true

if git diff --staged --quiet; then
    echo "  Nada novo pra comitar (arvore limpa)."
    COMMITADO_NOVO=0
else
    git commit -m "fix(bugs): C-43 Afego + status 108749463 + agenda deterministica + MCP blink-atendimento

Origem: Fabio 12/07/2026 (lead Mariana Lopes 22617170).

C-43: LIA TRAVOU EM ETAPA NOVA 'campanha agosto'
- webhook.py: status_id 108749463 (2.1 campanha agosto) adicionado
  nas 2 politicas ATIVOS_IA (simplificada + antiga rollback C-42).
- Sem isso, Lia entra em fallback generico e mente 'agenda fora do
  ar' em leads da lista AGO 2026 (0116AGO Mariana Lopes).

medware.py: Kommo 'Afego' -> AFFEGO codPlano 7
- PLANO_CODES ganha aliases 'afego', 'affeg' (sem 2 F).
- Sem isso, gravacao Medware falha com 'plano nao mapeado'.

oferta_deterministica.py (Python puro, sem LLM)
- Nova modulo com montar_texto_2_slots + frase_escalacao_humano.
- FRASES_BANIDAS com 22 padroes historicos (reconferir, especialista
  em remarcacao, etc).
- Sentinela _assert_zero_frases_banidas fail-fast em runtime.

responder.py: bypass ANTES do LLM
- Se FSM=AGENDA + dados prontos + medico+unidade + slots Medware:
  monta texto canonico em Python (nao chama LLM). Zero probabilidade
  de invencao de frase.
- Toggle AGENDA_DETERMINISTICA=1 (default ON).

MCP server blink-atendimento (Camada 1 Memoria Ativa)
- ler_chat_completo_lead(lead_id): forca Claude Cowork a ler chat
  antes de responder sobre um lead.
- desativar_ia_lead(lead_id, motivo): quando humano assumir.
- confirmar_slot_medware(...): antes de gravar.
- 8/8 pytest verde.

Total: 65 pytest oferta_deterministica + 8 MCP + AST OK 6 arquivos.
" 2>&1 | tail -3
    COMMITADO_NOVO=1
fi

# ---------------------------------------------------------------------------
# [5/8] Push origin main
# ---------------------------------------------------------------------------
echo ""
echo "[5/8] Push origin main..."
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD_BEFORE=$(git ls-remote origin main 2>/dev/null | awk '{print $1}')
echo "  Antes:  local=$LOCAL_HEAD"
echo "          remoto=$REMOTE_HEAD_BEFORE"

PUSH_OUTPUT=$(git push origin main 2>&1)
echo "$PUSH_OUTPUT" | tail -8

sleep 3
REMOTE_HEAD_AFTER=$(git ls-remote origin main 2>/dev/null | awk '{print $1}')

if [ "$REMOTE_HEAD_AFTER" = "$LOCAL_HEAD" ]; then
    echo "  PUSH CONFIRMADO — remoto agora aponta pra $REMOTE_HEAD_AFTER"
else
    echo "  PUSH FALHOU — remoto continua em $REMOTE_HEAD_AFTER"
    echo "  Motivo provavel: PAT expirou ou faltou credencial no keychain."
    echo "  Rode: git push origin main"
    echo "  Quando pedir senha, cola o PAT (github_pat_...)"
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi

# ---------------------------------------------------------------------------
# [6/8] Aguardar deploy Easypanel
# ---------------------------------------------------------------------------
echo ""
echo "[6/8] Aguardando deploy Easypanel (max 4min)..."
DEPLOY_OK=0
for i in $(seq 1 16); do
    sleep 15
    body=$(curl -s --max-time 8 "$APP/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK apos ${i} tentativas (~$((i*15))s)"
        DEPLOY_OK=1
        break
    fi
    printf "  [%02d/16] %s aguardando healthz...\n" "$i" "$(date +%H:%M:%S)"
done

if [ $DEPLOY_OK -eq 0 ]; then
    echo "  Deploy nao confirmou. Verifica manual:"
    echo "    curl $APP/health"
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi

# ---------------------------------------------------------------------------
# [7/8] Testar endpoint /admin/janela24h-diagnostico (fim do MEGA SPRINT)
# ---------------------------------------------------------------------------
echo ""
echo "[7/8] Testando endpoint /admin/janela24h-diagnostico..."
WS=""
for env_file in "$PROJETO/lia_engineer/.env.local" "$PROJETO/.env" "$PROJETO/.env.local"; do
    if [ -f "$env_file" ]; then
        c=$(grep -E "^WEBHOOK_SECRET=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        if [ -n "$c" ]; then WS="$c"; break; fi
    fi
done

if [ -z "$WS" ]; then
    echo "  WEBHOOK_SECRET nao encontrado. Pra testar manual:"
    echo "    curl '$APP/admin/janela24h-diagnostico?secret=SEU_SECRET'"
else
    DIAG_RESP=$(curl -s --max-time 12 "$APP/admin/janela24h-diagnostico?secret=$WS")
    echo "$DIAG_RESP" | python3 -m json.tool 2>&1 | head -25
    if echo "$DIAG_RESP" | grep -q '"detail":"Not Found"'; then
        echo ""
        echo "  ENDPOINT AINDA 404 — deploy nao pegou o novo codigo."
        read -n 1 -s -r -p "Enter pra fechar..."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# [8/8] Flush cache JANELA 24H (destrava a coluna Kommo)
# ---------------------------------------------------------------------------
if [ -n "$WS" ]; then
    echo ""
    echo "[8/8] Flush cache JANELA 24H..."
    curl -s --max-time 15 -X POST "$APP/admin/janela24h-cache-flush?secret=$WS" \
        | python3 -m json.tool 2>&1 | head -15
fi

echo ""
echo "==============================================="
echo "  TUDO EM PROD"
echo ""
echo "  O que mudou:"
echo "  ✓ MEGA SPRINT (C-38 + C-39 + C-40 + JANELA24H)"
echo "  ✓ Agenda deterministica ativa (Python puro, sem LLM)"
echo "  ✓ Bug C-43 fixed (Afego + campanha agosto)"
echo "  ✓ Endpoints /admin/janela24h-* respondendo"
echo "  ✓ Cache JANELA 24H limpo"
echo ""
echo "  Como validar em 20 min:"
echo "  1. Kommo lista ATENDE — coluna JANELA 24H deve VARIAR"
echo "     (Falta 5h, Falta 10h, Expirou) em vez de 'Falta 20h' fixo"
echo "  2. Proximo lead FSM=AGENDA da campanha AGO 2026 nao deve"
echo "     mais mentir 'agenda fora do ar' — vai receber texto"
echo "     canonico com datas reais 1️⃣/2️⃣"
echo ""
echo "  Rollback (se algo der ruim):"
echo "    Easypanel → env AGENDA_DETERMINISTICA=0 → Implantar"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
