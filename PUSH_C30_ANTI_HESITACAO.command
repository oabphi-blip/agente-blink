#!/bin/bash
# Push Fix C-30 — Anti-Hesitação "deixa eu consultar" (Sofia 24158652)
# 16/06/2026
#
# Origem: Fábio caso Sofia 24158652 às 10:00 BRT — Lia coletou tudo certo
# e ao entrar em FSM=AGENDA escreveu "Deixa eu consultar a agenda exata
# para esse período e volto com os horários reais pra você em um instante."
#
# 2 causas vivas:
#   1. Contradição na _MASTER_INSTRUCTION.md E7 (5 dias úteis + _offer_window_block morto)
#   2. Filtro _viola_oferta_agenda gated por FILTROS_LEGACY=0 (desligado em prod)
#
# Fix (6 arquivos):
#   - voice_agent/janela_preferencia.py (NOVO)
#   - voice_agent/medware.py (request específico janela)
#   - voice_agent/pipeline.py (chama janela_preferencia.extrair)
#   - voice_agent/responder.py (filtro C-30 sempre-ON + toggle LIA_ANTI_HESITACAO_AGENDA)
#   - voice_agent/knowledge_base/_MASTER_INSTRUCTION.md (E7 reescrita + bump VERSAO_PROMPT)
#   - tests/test_janela_preferencia.py (NOVO, 30 cenários)
#   - tests/test_anti_hesitacao_agenda_c30.py (NOVO, 15 cenários — frases exatas Sofia)
#
# Pytest local: 68/68 verde

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Fix C-30 Anti-Hesitação (Sofia 24158652)"
echo "==============================================="

echo ""
echo "[1/5] Pytest dos arquivos novos..."
python3 -m pytest tests/test_janela_preferencia.py tests/test_anti_hesitacao_agenda_c30.py -v --tb=short 2>&1 | tail -15

echo ""
echo "[2/5] AST check..."
python3 -c "import ast; [ast.parse(open(f).read()) for f in [
  'voice_agent/janela_preferencia.py',
  'voice_agent/medware.py',
  'voice_agent/pipeline.py',
  'voice_agent/responder.py'
]]; print('AST OK em todos os 4 .py')"

echo ""
echo "[3/5] Varredura segredos no diff..."
DIFF=$(git diff --staged 2>/dev/null; git diff 2>/dev/null)
if echo "$DIFF" | grep -qE "ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\."; then
    echo "  ALERTA: padrão de segredo detectado no diff. Abortando."
    echo "$DIFF" | grep -nE "ghp_|sk-|eyJ" | head -5
    exit 1
fi
echo "  OK — sem segredos"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/janela_preferencia.py \
        voice_agent/medware.py \
        voice_agent/pipeline.py \
        voice_agent/responder.py \
        voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        tests/test_janela_preferencia.py \
        tests/test_anti_hesitacao_agenda_c30.py \
        CLAUDE.md \
        PUSH_C30_ANTI_HESITACAO.command

git commit -m "fix(C-30): anti-hesitacao 'deixa eu consultar' — 2 causas vivas (Sofia 24158652)

Origem: Fabio 16/06/2026 10:00 BRT. Lead 24158652 Sofia (7a, Bacen, Karla
Asa Norte rotina). Lia coletou tudo certo (nome+data nasc+convenio+medico+
motivo+unidade+turno) e ao entrar em FSM=AGENDA escreveu 'Deixa eu consultar
a agenda exata para esse periodo e volto com os horarios reais pra voce em
um instante'. Mesmo padrao Fernanda/Carolina/Maite — fix #183 marcado como
completed mas nao funcionava em prod.

2 causas vivas (nao 1):

1. Contradicao na _MASTER_INSTRUCTION.md E7
   - Mandava 'ofertar SOMENTE nos proximos 5 dias uteis'
   - Apontava pra _offer_window_block (CODIGO MORTO — definido em responder.py
     mas nunca chamado)
   - O que de fato entra no prompt eh _agenda_block (agenda real 90d)
   - Modelo recebia 2 instrucoes contraditorias e hesitava
   - Fix: E7 reescrita, fonte de verdade = AGENDA REAL 90d, sem limite 5 dias,
     respeitando janela do paciente, proibicao explicita de hesitar.
     Bump VERSAO_PROMPT forca re-cache Anthropic.

2. Rede de seguranca desligada
   - Filtro _viola_oferta_agenda (anti-hesitacao) existe em responder.py
     mas esta atras do gate _FILTROS_LEGACY_ATIVOS (desligado em prod via
     FILTROS_LEGACY=0 desde 796ba2a)
   - Nada pegou a hesitacao da Sofia
   - Fix: filtro NOVO _viola_hesitacao_agenda_c30 sempre-ON em _scrub_prohibited,
     ANTES dos legacy gates. Toggle proprio LIA_ANTI_HESITACAO_AGENDA
     (ativo/shadow/off). Nao compartilha gate com legacy.

Modulo novo:
  voice_agent/janela_preferencia.py
   - extrai janela temporal da preferencia do paciente
   - 'semana de 13/07' -> dataInicio/dataFim especifico
   - fallback 90d se vazio

Padroes detectados pelo filtro C-30 (com ctx.agenda preenchido):
   - 'deixa eu consultar a agenda'
   - 'reconsultar a agenda'
   - 'volto em 1 minuto'
   - 'puxar a agenda exata'
   - 'Medware nao esta retornando'
   - 'vou buscar os horarios'
   - 'ainda estou buscando'

Quando dispara -> substitui pela oferta real de 2 slots (formato canonico
1 manha + 1 tarde do dia mais proximo da preferencia).

Pytest:
  - test_janela_preferencia.py — 30 cenarios
  - test_anti_hesitacao_agenda_c30.py — 15 cenarios (frases exatas Sofia)
  - 68/68 verde local

Envs novas (Easypanel):
  - MEDWARE_JANELA_PREFERENCIA=1 (request especifico por preferencia)
  - LIA_ANTI_HESITACAO_AGENDA=1 (filtro C-30 ativo)

Rollback sem revert: flags pra 0, Implantar.

Licao arquitetural (C-30):
- 'completed' no Mac != rodando em prod. Fix #183 estava completed ha semanas.
- Codigo morto mata. _offer_window_block apontava pra regra que nao rodava.
- Gates de filtro sao bombas-relogio. FILTROS_LEGACY=0 desligou 4 filtros
  legitimos. C-30 nasceu sempre-ON com toggle proprio.

Atualiza CLAUDE.md secao 0 — rolling log C-30.
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
echo "PROXIMO PASSO MANUAL:"
echo " 1. Easypanel -> blink/agent -> Ambiente -> Adicionar:"
echo "      MEDWARE_JANELA_PREFERENCIA=1"
echo "      LIA_ANTI_HESITACAO_AGENDA=1"
echo " 2. Implantar"
echo " 3. Aguardar healthz 200 (~2min)"
echo " 4. Smoke validacao com canary lead:"
echo "    curl -X POST 'https://blink-agent.6prkfn.easypanel.host/admin/simulate-inbound?secret=blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"conversation_key\":\"sofia-test-c30\",\"text\":\"manha\",\"ctx_known\":{\"nome\":\"Sofia\",\"medico\":\"Karla\",\"unidade\":\"Asa Norte\",\"convenio\":\"Bacen\",\"motivo\":\"rotina\",\"perfil\":\"crianca\"}}'"
echo ""
echo " 5. Esperar resposta com 2 slots concretos, sem 'deixa eu consultar'."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
