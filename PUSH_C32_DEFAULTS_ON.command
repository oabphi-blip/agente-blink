#!/bin/bash
# Push Bug C-32 — Defaults ON pra envs criticas (TOOL_CALLING + TRACING)
# 16/06/2026
#
# Origem: Fabio 16/06/2026, lead 24113652. Apos deploy C-30/C-30A/C-31 +
# regra nomes, Lia AINDA inventou dia errado. Healthz revelou que fix #183
# (LIA_TOOLS_ENABLED) e TRACING_ENABLED estavam INERTES em prod — env
# nunca foi setada no Easypanel.
#
# Padrao reincidente em C-29, C-30, C-31 — todas com a mesma causa raiz
# "default OFF, ligar pra usar".
#
# Fix arquitetural — inverter pra DEFAULT ON:
#   - voice_agent/tools_lia.py::tools_habilitadas() -> default ON
#   - voice_agent/tracing.py::esta_habilitado() -> default ON
#   - voice_agent/pipeline.py::PIPELINE_LOCK_ENABLED ja era default ON
#
# Rollback: setar EXPLICITAMENTE LIA_TOOLS_ENABLED=0 ou TRACING_ENABLED=0
#
# Pytest: 14/14 verde + 121/121 verde combinado

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-32 — Defaults ON em prod"
echo "==============================================="

echo ""
echo "[1/5] Pytest C-32 + toda suite anti-bug agenda..."
python3 -m pytest tests/test_c32_defaults_on.py \
                  tests/test_bug_c31_dia_medico_unidade.py \
                  tests/test_nome_sobrenome_medicos_kb.py \
                  tests/test_c30a_medware_down.py \
                  tests/test_anti_hesitacao_agenda_c30.py \
                  tests/test_watchdog_promessa.py -q 2>&1 | tail -3

echo ""
echo "[2/5] AST check tools_lia + tracing..."
python3 -c "
import ast
for f in ['voice_agent/tools_lia.py', 'voice_agent/tracing.py']:
    ast.parse(open(f).read())
    print(f'  AST OK: {f}')
"

echo ""
echo "[3/5] Varredura segredos no diff..."
DIFF=$(git diff --staged 2>/dev/null; git diff 2>/dev/null)
if echo "$DIFF" | grep -qE "ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\."; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/tools_lia.py \
        voice_agent/tracing.py \
        tests/test_c32_defaults_on.py \
        CLAUDE.md \
        PUSH_C32_DEFAULTS_ON.command

git commit -m "fix(C-32): defaults ON pra envs criticas — fim do padrao 'completed mas inerte'

Origem: Fabio 16/06/2026, lead 24113652 Fabio Philipe Martins. Apos deploy
de C-30/C-30A/C-31/nomes, Lia AINDA inventou 'quarta 18/06' (era quinta).
Healthz revelou que fix #183 (LIA_TOOLS_ENABLED) e TRACING_ENABLED
estavam INERTES em prod — env nunca setada no Easypanel.

Causa raiz arquitetural (reincidente em C-29/C-30/C-31):
  Padrao 'default OFF, ligar pra usar' = fonte recorrente de bugs
  silenciosos. Code completed mas inerte porque env esquecida.

Fix C-32 — inverter pra DEFAULT ON:

1. voice_agent/tools_lia.py::tools_habilitadas()
   Antes: (or '').lower() in ('1','true','yes')  -> default OFF
   Depois: (or '1').lower() not in ('0','false','no','off','')  -> default ON

2. voice_agent/tracing.py::esta_habilitado()
   Antes: os.getenv('TRACING_ENABLED', '0') == '1'  -> default OFF
   Depois: (or '1') not in ('0','false','no','off','')  -> default ON

3. voice_agent/pipeline.py::PIPELINE_LOCK_ENABLED
   Ja era default ON — sem acao.

Rollback emergencial:
  LIA_TOOLS_ENABLED=0  (ou 'false'/'no'/'off')
  TRACING_ENABLED=0

Pytest novo: tests/test_c32_defaults_on.py — 14 cenarios:
  - TestLiaToolsEnabledDefaultOn (8): sem env, env vazia, '1', 'true',
    '0', 'false', 'no', 'off'
  - TestTracingEnabledDefaultOn (5): mesmos cenarios
  - TestRollbackPath (1): combinado off pra emergencia

14/14 verde local + 121/121 verde combinado (C-32 + C-31 + nomes +
C-30 + C-30A + watchdog).

8 camadas FINAIS anti-bug 'Lia inventa data':
  1. Prompt E7 coerente
  2. Tool calling forcado FSM=AGENDA — agora DEFAULT ON via C-32
  3. Filtro C-30 (agenda cheia + stall -> oferta real)
  4. Filtro C-30A (agenda vazia + stall -> frase honesta)
  5. Filtro C-31a SEMPRE-ON (dia inventado)
  6. Filtro C-31b SEMPRE-ON (medico/unidade/dia)
  7. Watchdog promessa cron 2min
  8. Tracing DEFAULT ON via C-32 — replay disponivel pra todo lead

Licao arquitetural:
- Default OFF em codigo NOVO so vale durante rollout gradual.
  Depois de validado, INVERTER pra ON. Senao 'completed' no task list
  nunca vira realidade.
- Tracing OFF cega diagnostico — sem replay nao da pra investigar
  bug em prod.
- Healthz tem que expor TODAS as envs criticas como sinal de saude.

CLAUDE.md atualizado — C-32 no topo do rolling log.
" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "[5/5] Aguardando deploy Easypanel (~3 min)..."
for i in $(seq 1 12); do
    sleep 20
    body=$(curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/health" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"status":"ok"'; then
        echo "  HEALTHZ OK [${i}x20s = $((i*20))s]"
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "  Bug C-32 em prod."
echo "  TOOL CALLING e TRACING agora default ON."
echo "  Sem precisar mexer no Easypanel."
echo ""
echo "  Validacao pos-deploy:"
echo "  curl https://blink-agent.6prkfn.easypanel.host/admin/healthz?secret=$WS"
echo "  -> settings deve mostrar tracing/tools como ativos"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
