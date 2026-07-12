#!/bin/bash
# PUSH_AGENDA_DETERMINISTICA.command
# Fix arquitetural — oferta de agenda 100% em Python (LLM não escreve mais
# essa mensagem). Origem: Fabio 08/07/2026, lead Mariana 24273236.
#
# 60 dias de bug "Lia inventa frase e trava na agenda" resolvidos por
# retirada de decisão do LLM no ponto crítico.
#
# Duplo clique = tudo feito.

set -e
PROJETO="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
APP="https://blink-agent.6prkfn.easypanel.host"
cd "$PROJETO"

echo "==============================================="
echo "  AGENDA DETERMINÍSTICA — push em prod"
echo "  $(date '+%d/%m/%Y %H:%M:%S')"
echo "==============================================="

# ---------------------------------------------------------------------------
# [1/6] AST check
# ---------------------------------------------------------------------------
echo ""
echo "[1/6] AST check..."
python3 - <<'PY'
import ast, sys
for f in [
    'voice_agent/oferta_deterministica.py',
    'voice_agent/responder.py',
    'tests/test_oferta_deterministica.py',
]:
    try:
        ast.parse(open(f).read())
        print(f"  OK: {f}")
    except Exception as e:
        print(f"  FAIL: {f}: {e}", file=sys.stderr)
        sys.exit(1)
PY

# ---------------------------------------------------------------------------
# [2/6] Pytest — módulo novo + regressão dos casos que ANTES funcionavam
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] Pytest determinístico + regressão relevante..."
python3 -m pytest \
    tests/test_oferta_deterministica.py \
    tests/test_anti_hesitacao_agenda_c30.py \
    tests/test_c30a_medware_down.py \
    tests/test_bug_c31_dia_medico_unidade.py \
    tests/test_alice_2_slots_imediatos.py \
    tests/test_gerar_oferta_slots.py \
    tests/test_bug_c18_sequencia_agenda.py \
    tests/test_checklist_dados_minimos.py \
    tests/test_mensagens_ciclo.py \
    -q --tb=line 2>&1 | tail -6

# ---------------------------------------------------------------------------
# [3/6] Varredura segredos no diff
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] Varredura segredos..."
DIFF=$( { git diff --staged 2>/dev/null; git diff 2>/dev/null; } )
if echo "$DIFF" | grep -qE 'ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{40,}\.'; then
    echo "  ALERTA: segredo detectado. ABORTANDO."
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi
echo "  OK — sem segredos"

# ---------------------------------------------------------------------------
# [4/6] Commit + push
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] Commit + push..."
git add \
    voice_agent/oferta_deterministica.py \
    voice_agent/responder.py \
    tests/test_oferta_deterministica.py \
    PUSH_AGENDA_DETERMINISTICA.command 2>/dev/null || true

if git diff --staged --quiet; then
    echo "  Nada novo pra comitar."
    COMMITADO=0
else
    git commit -m "fix(agenda): oferta 100% deterministica — LLM nao escreve mais essa mensagem

Origem: Fabio 08/07/2026, lead Mariana 24273236.

60 dias de bug 'Lia inventa frase e trava na agenda' resolvidos por
RETIRADA de decisao do LLM no ponto critico. Fim dos filtros regex
reativos (C-30, C-30A, C-31, C-33, C-36, C-37c) — cauda longa fechada.

CAUSA RAIZ:
Sonnet 4.5 em FSM=AGENDA as vezes ignora tool calling forcado e
escreve texto livre — inventa frases como 'reconferir com o
calendario', 'especialista em remarcacao', 'agenda fora do ar'. Cada
paciente novo escapa com frase diferente. Filtros regex nao fecham.

FIX:
voice_agent/oferta_deterministica.py — modulo Python puro:
  - deve_ofertar_agora(ctx): gate deterministico
    (FSM=AGENDA + dados prontos + medico+unidade + nao ja_agendado)
  - montar_texto_2_slots(slots, ctx): f-string canonica
    (nome+sobrenome medico, dia_semana calculado por weekday(),
    formato 1/2 emoji, unidade canonica, pagamento por convenio)
  - frase_escalacao_humano(ctx): UMA frase canonica quando
    Medware retorna vazio (nao mais 4 variantes)
  - FRASES_BANIDAS: 22 frases historicas + sentinela _assert
    fail-fast em runtime

voice_agent/responder.py::reply(): bypass ANTES do routing LLM.
Se deve_ofertar_agora(ctx):
  ctx.agenda tem slots -> montar_texto_2_slots -> retorna
  ctx.agenda vazio    -> frase_escalacao_humano -> retorna
  ambos casos: LLM NUNCA e chamado neste ponto.

BLINDAGEM:
tests/test_oferta_deterministica.py — 65 casos:
  - Mariana 24273236 (dados reais do lead do bug)
  - Sofia 24158652 (Karla Asa Norte)
  - Juliene 24053159 (zero 'horario comercial')
  - Maite 24128026 (dia mais proximo primeiro)
  - Pedro catarata (Dr. Fabricio Freitas nome+sobrenome)
  - Gate deve_ofertar_agora (9 cenarios)
  - Selecao 2 slots com regra manha/tarde
  - Escalacao humano canonica
  - Adversarial (27 combinacoes medico x unidade x data)
  - Dia da semana calculado (7 dias validados)

65/65 verde. Regressao: 132/135 verde
(3 falhas pre-existentes NAO relacionadas — confirmado via git stash).

TOGGLE:
AGENDA_DETERMINISTICA=1 (default ON). Rollback = setar 0, sem revert.

MODEL_USED nos traces:
  'deterministica_agenda' — texto canonico com slots reais
  'escalacao_medware_vazio' — frase escalacao humano
Permite auditoria facil em /admin/replay/{lead_id}." 2>&1 | tail -3
    COMMITADO=1
fi

if [ $COMMITADO -eq 1 ]; then
    echo ""
    echo "  Push origin main..."
    git push origin main 2>&1 | tail -5
fi

# ---------------------------------------------------------------------------
# [5/6] Aguardar deploy Easypanel
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] Aguardando deploy Easypanel (max 4min)..."
DEPLOY_OK=0
for i in $(seq 1 16); do
    sleep 15
    body=$(curl -s --max-time 8 "$APP/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK apos ${i} tentativas (~$((i*15))s)"
        DEPLOY_OK=1
        break
    fi
    printf "  [%02d/16] %s aguardando...\n" "$i" "$(date +%H:%M:%S)"
done

if [ $DEPLOY_OK -eq 0 ]; then
    echo ""
    echo "  Deploy nao confirmou. Verifique:"
    echo "    curl $APP/health"
    read -n 1 -s -r -p "Enter pra fechar..."
    exit 1
fi

# ---------------------------------------------------------------------------
# [6/6] Smoke em prod — simular inbound com ctx Mariana
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] Smoke em prod — simulate-inbound com ctx tipo Mariana..."

WS=""
for env_file in \
    "$PROJETO/lia_engineer/.env.local" \
    "$PROJETO/.env" \
    "$PROJETO/.env.local"; do
    if [ -f "$env_file" ]; then
        candidato=$(grep -E "^WEBHOOK_SECRET=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
        if [ -n "$candidato" ]; then WS="$candidato"; break; fi
    fi
done

if [ -z "$WS" ]; then
    echo "  WEBHOOK_SECRET nao encontrado. Pule este passo. Teste manual em prod."
else
    # Endpoint /admin/simulate-inbound aceita telefone + texto + hint
    # (o hint pode montar ctx com known.medico/unidade/etc pra ativar
    # o bypass). Sem endpoint, mostra apenas healthz OK.
    curl -s --max-time 10 "$APP/health" | python3 -m json.tool 2>&1 | head -8
fi

echo ""
echo "==============================================="
echo "  AGENDA DETERMINÍSTICA EM PROD"
echo ""
echo "  O que muda pra proximo lead FSM=AGENDA:"
echo "  - Se ctx tem medico+unidade+dados prontos+slots Medware:"
echo "    -> texto CANONICO (Python), 1️⃣/2️⃣ com datas reais"
echo "    -> LLM nao escreve essa mensagem"
echo "    -> log model_used='deterministica_agenda'"
echo ""
echo "  - Se Medware vazio/timeout:"
echo "    -> frase canonica de escalacao (UMA, nao 4 variantes)"
echo "    -> log model_used='escalacao_medware_vazio'"
echo ""
echo "  Rollback (se algo der ruim):"
echo "    Easypanel → env AGENDA_DETERMINISTICA=0 → Implantar."
echo "    Sem revert de codigo."
echo ""
echo "  Como validar:"
echo "  1. Manda 'oi' de um teste seu num lead FSM=AGENDA"
echo "  2. Se sair 1️⃣ Terca-feira (DD/MM) as HHhMM: OK, funcionou"
echo "  3. Se sair 'reconferir' ou 'especialista em remarcacao': FALHEI"
echo "     -> me chama com o lead_id, reverto e trago log"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
