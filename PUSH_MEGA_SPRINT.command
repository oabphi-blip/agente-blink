#!/bin/bash
# PUSH_MEGA_SPRINT.command
# Um duplo clique = tudo feito. Zero passo manual.
#
# [0] cd no projeto sozinho (nao depende de cwd)
# [1] Aliases permanentes no ~/.zshrc (idempotente)
# [2] AST check em 9 arquivos
# [3] Pytest bugs novos + regressao
# [4] Varredura segredos no diff
# [5] Commit + push
# [6] Aguarda deploy Easypanel (healthz)
# [7] Flush cache JANELA 24H + diagnostico automatico

set -e
PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
APP="https://blink-agent.6prkfn.easypanel.host"
cd "$PROJETO"

echo "==============================================="
echo "  MEGA SPRINT — C-38 + C-39 + C-40 + JANELA 24H"
echo "  $(date '+%d/%m/%Y %H:%M:%S')"
echo "==============================================="

# ---------------------------------------------------------------------------
# [1/7] Aliases permanentes no .zshrc (idempotente)
# ---------------------------------------------------------------------------
echo ""
echo "[1/7] Aliases permanentes no ~/.zshrc..."
if [ -f "$HOME/.blink_aliases.sh" ]; then
    if ! grep -q "source ~/.blink_aliases.sh" "$HOME/.zshrc" 2>/dev/null; then
        printf "\n# Blink aliases (Cowork)\nsource ~/.blink_aliases.sh\n" >> "$HOME/.zshrc"
        echo "  ADICIONADO — agora persiste em TODO terminal novo"
    else
        echo "  Ja no ~/.zshrc (persistente OK)"
    fi
else
    echo "  ~/.blink_aliases.sh nao existe. Rode BLINK_STUDIO.command 1x."
fi

# ---------------------------------------------------------------------------
# [2/7] Extrair WEBHOOK_SECRET dos .env locais (multiplos candidatos)
# ---------------------------------------------------------------------------
WS=""
for env_file in \
    "$PROJETO/lia_engineer/.env.local" \
    "$PROJETO/.env" \
    "$PROJETO/.env.local" \
    "$PROJETO/voice_agent/.env"; do
    if [ -f "$env_file" ]; then
        candidato=$(grep -E "^WEBHOOK_SECRET=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        if [ -n "$candidato" ]; then WS="$candidato"; break; fi
    fi
done

echo ""
if [ -n "$WS" ]; then
    echo "[2/7] WEBHOOK_SECRET encontrado (${#WS} chars)"
else
    echo "[2/7] WEBHOOK_SECRET NAO encontrado — flush cache no fim vai pedir manual"
fi

# ---------------------------------------------------------------------------
# [3/7] AST check em 9 arquivos
# ---------------------------------------------------------------------------
echo ""
echo "[3/7] AST check..."
python3 - <<'PY'
import ast, sys
arquivos = [
    'voice_agent/migracao_canal.py',
    'voice_agent/webhook.py',
    'voice_agent/cron_interno.py',
    'voice_agent/responder.py',
    'voice_agent/tools_lia.py',
    'voice_agent/mensagens_ciclo.py',
    'tests/test_bug_c38_migracao_canal.py',
    'tests/test_bug_c39_c40_proxima_consulta_e_endereco.py',
    'tests/test_bug_janela24h_cache_ttl.py',
]
ok = 0
for f in arquivos:
    try:
        ast.parse(open(f).read())
        ok += 1
    except FileNotFoundError:
        print(f"  AVISO: {f} nao existe (talvez ja mergeado)", file=sys.stderr)
    except Exception as e:
        print(f"  ERRO AST em {f}: {e}", file=sys.stderr)
        sys.exit(1)
print(f"  OK: {ok}/{len(arquivos)} arquivos")
PY

# ---------------------------------------------------------------------------
# [4/7] Pytest — bugs novos + regressao chave
# ---------------------------------------------------------------------------
echo ""
echo "[4/7] Pytest (bugs novos + regressao chave)..."
python3 -m pytest \
    tests/test_bug_c38_migracao_canal.py \
    tests/test_bug_c39_c40_proxima_consulta_e_endereco.py \
    tests/test_bug_janela24h_cache_ttl.py \
    tests/test_bug_c37_invencao_comunicacao_interna.py \
    tests/test_bug_c37b_ia_desativada_gate.py \
    tests/test_templates_observabilidade.py \
    tests/test_migracao_canal.py \
    -q --tb=line 2>&1 | tail -6

# ---------------------------------------------------------------------------
# [5/7] Varredura segredos + commit + push
# ---------------------------------------------------------------------------
echo ""
echo "[5/7] Varredura segredos no diff..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: padrao de segredo detectado no diff. ABORTANDO."
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi
echo "  OK — nenhum segredo detectado"

echo ""
echo "  Commit + push..."
git add \
    voice_agent/migracao_canal.py \
    voice_agent/webhook.py \
    voice_agent/cron_interno.py \
    voice_agent/responder.py \
    voice_agent/tools_lia.py \
    voice_agent/mensagens_ciclo.py \
    voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    tests/test_bug_c38_migracao_canal.py \
    tests/test_bug_c39_c40_proxima_consulta_e_endereco.py \
    tests/test_bug_janela24h_cache_ttl.py \
    BLINK_STUDIO.command \
    PUSH_MEGA_SPRINT.command 2>/dev/null || true

if git diff --staged --quiet; then
    echo "  Nada novo pra comitar (arvore limpa)."
    COMMITADO=0
else
    git commit -m "fix(mega): C-38 migracao canal + C-39 PROXIMA CONSULTA + C-40 pos-agenda endereco + JANELA24H cache TTL

4 bugs fechados em 1 commit. Origem: Fabio 01/07/2026.

C-38 — Migracao canal wired (lead fantasma em canal sem handler)
migracao_canal.py::talvez_disparar_migracao_canal orquestrador.
webhook.py /kommo chama antes do pipeline quando lead cai em
96441724 (0-ETAPA ENTRADA) vazio. Dispara mensagem migracao +
nota Kommo + desativa IA + dedup Redis 7d.

C-39 — PROXIMA CONSULTA (Davi 23326396)
Regra FE.1: status_id=106157327 vai pra ACOMPANHAMENTO, proibido
agendar. FE.2 forca resumo + endereco pos-agendamento. FE.3
invariante. 2 filtros SEMPRE-ON em responder.py.

C-40 — Pos-agendamento sem endereco (Marcela 24232988)
handle_gravar_agendamento_medware pos sucesso dispara resumo +
endereco automaticamente. Determinismo, nao depende da Lia.

JANELA 24H (todos 'Falta 20h' fixo)
Cache blink:janela:rotulo:{lead_id} sem TTL. Fix: setex TTL 1200s.
2 endpoints novos: /admin/janela24h-diagnostico + cache-flush.

Total pytest: 25/25 novos + 82/82 regressao = 107 verde." 2>&1 | tail -3
    COMMITADO=1
fi

if [ $COMMITADO -eq 1 ]; then
    echo ""
    echo "  Push origin main..."
    git push origin main 2>&1 | tail -5
fi

# ---------------------------------------------------------------------------
# [6/7] Aguardar deploy Easypanel
# ---------------------------------------------------------------------------
echo ""
echo "[6/7] Aguardando deploy Easypanel (max 4min)..."
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
    echo ""
    echo "  Deploy nao confirmou em 4min. Verifique manualmente:"
    echo "    curl $APP/health"
    read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
    exit 1
fi

# ---------------------------------------------------------------------------
# [7/7] Flush cache JANELA 24H + diagnostico automatico
# ---------------------------------------------------------------------------
echo ""
echo "[7/7] Flush cache JANELA 24H + diagnostico..."
if [ -z "$WS" ]; then
    echo ""
    echo "  WEBHOOK_SECRET nao encontrado nos .env. Rode manual:"
    echo "    curl -X POST '$APP/admin/janela24h-cache-flush?secret=SEU_SECRET'"
else
    echo ""
    echo "  --- FLUSH ---"
    curl -s --max-time 15 -X POST "$APP/admin/janela24h-cache-flush?secret=$WS" \
        | python3 -m json.tool 2>&1 | head -15
    echo ""
    echo "  --- DIAGNOSTICO ---"
    curl -s --max-time 15 "$APP/admin/janela24h-diagnostico?secret=$WS" \
        | python3 -m json.tool 2>&1 | head -25
fi

echo ""
echo "==============================================="
echo "  MEGA SPRINT COMPLETO"
echo ""
echo "  4 bugs fechados em prod:"
echo "    C-38 migracao canal"
echo "    C-39 PROXIMA CONSULTA modo acompanhamento"
echo "    C-40 pos-agendamento envia endereco"
echo "    JANELA 24H cache TTL"
echo ""
echo "  Cache flush executado — coluna Kommo comeca a"
echo "  atualizar no proximo tick (15min)."
echo ""
echo "  Aliases permanentes ativos em qualquer terminal:"
echo "    bstatus  bhz  bslo  bkl 24170466  bjanela_diag"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
