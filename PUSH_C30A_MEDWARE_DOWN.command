#!/bin/bash
# Push Fix C-30A — Anti-hesitacao SEM agenda (Medware down)
# 16/06/2026
#
# Origem: Sofia 24158652 13:07-13:40 BRT — depois do C-30 deployado,
# ainda restava o cenario "Medware intermitente". ctx.agenda=[] e Lia
# entrou em loop "deixa eu reconsultar a agenda real aqui pra voce —
# volto em 1 minuto" 4x. Filtro C-30 NAO age sem has_agenda.
#
# Fix C-30A complementa o C-30:
#   - 3 funcoes novas em responder.py
#   - 1 branch em _scrub_prohibited (apos C-30, antes do C-19)
#   - Reaproveita _gerar_resposta_honesta_medware_down (existente)
#   - Reusa toggle LIA_ANTI_HESITACAO_AGENDA (mesma flag do C-30)
#   - Frase substituida ("volto em 1 minuto") integra com watchdog
#     promessa automatico — sem mexer no watchdog
#
# Arquivos:
#   - voice_agent/responder.py (3 helpers + 1 branch)
#   - tests/test_c30a_medware_down.py (NOVO, 22 cenarios)
#   - CLAUDE.md (rolling log C-30A no topo)
#
# Pytest local: 22/22 verde + 78/78 verde combinado (C-30 + C-30A + watchdog)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Fix C-30A Anti-Hesitacao Medware Down"
echo "==============================================="

echo ""
echo "[1/5] Pytest C-30A + C-30 + watchdog..."
python3 -m pytest tests/test_c30a_medware_down.py \
                  tests/test_anti_hesitacao_agenda_c30.py \
                  tests/test_watchdog_promessa.py -q 2>&1 | tail -5

echo ""
echo "[2/5] AST check responder.py..."
python3 -c "import ast; ast.parse(open('voice_agent/responder.py').read()); print('AST OK')"

echo ""
echo "[3/5] Varredura segredos no diff..."
DIFF=$(git diff --staged 2>/dev/null; git diff 2>/dev/null)
if echo "$DIFF" | grep -qE "ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\."; then
    echo "  ALERTA: padrao de segredo detectado. Abortando."
    exit 1
fi
echo "  OK — sem segredos"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/responder.py \
        tests/test_c30a_medware_down.py \
        CLAUDE.md \
        PUSH_C30A_MEDWARE_DOWN.command

git commit -m "fix(C-30A): anti-hesitacao SEM agenda (Medware down) — variante do C-30

Origem: Sofia 24158652 13:07-13:40 BRT, 16/06/2026. Depois do fix C-30
deployado, restava cenario 'Medware intermitente': ctx.agenda=[] mas Lia
em loop 'deixa eu reconsultar a agenda real aqui pra voce — volto em 1
minuto' 4x consecutivas. Filtro C-30 NAO age sem has_agenda.

Fix C-30A — 3 funcoes novas em responder.py + 1 branch em _scrub_prohibited:

1. _texto_contem_hesitacao_stall(text)
   - Detecta padroes de stall SEM o gate has_agenda
   - Reusa _FAKE_AGENDA_LOOKUP existente

2. _lia_em_estado_agenda_provavel(ctx)
   - Heuristica: medico+unidade OU medico+motivo OU fsm in {AGENDA,
     CONFIRMACAO}
   - Evita falso positivo em fase inicial (so nome / so convenio)

3. _sinalizar_escalation_medware_down(ctx)
   - Grava blink:c30a_medware_down:{lead_id} TTL 30min
   - Best-effort: nao quebra resposta se Redis cair

Branch em _scrub_prohibited (apos C-30, antes do C-19):
- not has_agenda AND _texto_contem_hesitacao_stall(text) AND
  _lia_em_estado_agenda_provavel(ctx)
  -> substitui pela frase honesta (_gerar_resposta_honesta_medware_down)
  -> sinaliza Redis pra escalation

Integracao natural com watchdog promessa:
- Frase substituida ('deixa eu reconsultar... volto em 1 minuto') ja eh
  padrao de promessa que o watchdog detecta
- Em 3min watchdog move lead pra 1-ATENDIMENTO HUMANO automaticamente
- Sem necessidade de modificar watchdog_promessa.py

Toggle compartilhado: LIA_ANTI_HESITACAO_AGENDA (1/shadow/0) — mesma
flag do C-30. Ja setada=1 em prod no deploy do C-30.

5 camadas finais de defesa anti-hesitacao:
1. Prompt coerente (E7 reescrita)
2. Tool calling forcado FSM=AGENDA (#183)
3. Filtro C-30 (agenda cheia + stall -> oferta real)
4. Filtro C-30A (agenda vazia + stall + estado AGENDA -> frase honesta)
5. Watchdog promessa cron 2min (move pra atendimento humano em 3min)

Pytest:
- tests/test_c30a_medware_down.py — 22 cenarios novos
- TestTextoContemHesitacaoStall (6)
- TestLiaEmEstadoAgendaProvavel (8)
- TestScrubProhibitedC30A (5 — frase exata Sofia incluida)
- TestSinalizacaoRedis (1)
- TestTextoContemHesitacaoStall.test_puxar_agenda_exata_dispara (1)
- TestTextoContemHesitacaoStall.test_vou_consultar_agenda_dispara (1)

78/78 verde combinado (C-30A + C-30 + watchdog promessa).

CLAUDE.md atualizado — C-30A entry no topo do rolling log.

Rollback: LIA_ANTI_HESITACAO_AGENDA=0 desliga AMBOS C-30 e C-30A
simultaneamente (mesmo toggle). Implantar.
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
echo "  C-30A em prod. Sem envs novas — reusa"
echo "  LIA_ANTI_HESITACAO_AGENDA=1 que ja esta setada."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
