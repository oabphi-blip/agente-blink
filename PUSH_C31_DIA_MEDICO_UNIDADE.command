#!/bin/bash
# Push Bug C-31 — Karla por unidade + dia-da-semana SEMPRE-ON
# 16/06/2026
#
# Origem: Fabio 16/06/2026 lead 24113652 (Fabio Philipe Martins).
# Lia ofereceu:
#   "1 quarta-feira, 18/06 as 08:30"  — 18/06/2026 e quinta
#   "2 sexta-feira, 20/06 as 08:00"   — 20/06/2026 e sabado
# Karla Asa Norte so atende seg/qua/sex e nunca fim-de-semana.
#
# Fix arquitetural:
#   1. Novo mapping _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE por (medico, unidade)
#      - karla + asa norte = {0,2,4} (seg/qua/sex)
#      - karla + aguas claras = {1,3} (ter/qui)
#      - fabricio = {1,3}
#   2. _viola_oferta_em_dia_nao_atendido le unidade do ctx.known
#   3. _viola_dia_semana e _viola_oferta_em_dia_nao_atendido SEMPRE-ON
#      (saem do gate FILTROS_LEGACY=0 — invariantes duros)
#
# Pytest local: 17/17 verde + 107/107 verde combinado

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-31 — Dia/Medico/Unidade"
echo "==============================================="

echo ""
echo "[1/5] Pytest C-31 + suite anti-hesitacao..."
python3 -m pytest tests/test_bug_c31_dia_medico_unidade.py \
                  tests/test_nome_sobrenome_medicos_kb.py \
                  tests/test_c30a_medware_down.py \
                  tests/test_anti_hesitacao_agenda_c30.py \
                  tests/test_watchdog_promessa.py -q 2>&1 | tail -3

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
echo "  OK"

echo ""
echo "[4/5] Commit + push..."
git add voice_agent/responder.py \
        tests/test_bug_c31_dia_medico_unidade.py \
        CLAUDE.md \
        PUSH_C31_DIA_MEDICO_UNIDADE.command

git commit -m "fix(C-31): Karla por unidade + dia-da-semana SEMPRE-ON

Origem: Fabio 16/06/2026, lead 24113652 Fabio Philipe Martins.
Lia ofereceu 'quarta 18/06' (era quinta) E 'sexta 20/06' (era sabado,
Karla nao atende fim-de-semana). Duas violacoes simultaneas.

Causa raiz dupla:

1. Mapping incompleto
   _DIAS_ATENDIMENTO_POR_MEDICO = {'karla': {0,1,2,3,4}} (seg-sex)
   inclui QUINTA, mas Karla Asa Norte so atende seg/qua/sex. Faltava
   dimensao UNIDADE.

2. Filtros atras de FILTROS_LEGACY=0
   _viola_dia_semana e _viola_oferta_em_dia_nao_atendido estavam atras
   do gate desligado em prod. Mesmo bug arquitetural do C-30 — gate
   unico derrubou 2 filtros legitimos de calendario.

Fix arquitetural (voice_agent/responder.py):

1. Novo mapping _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE com chave (medico, unidade):
   - ('karla', 'asa norte') -> {0, 2, 4}  (seg, qua, sex)
   - ('karla', 'aguas claras') -> {1, 3}  (ter, qui)
   - ('fabricio', '*') -> {1, 3}
   - Fallback _DIAS_ATENDIMENTO_POR_MEDICO mantido (uniao) pra ctx
     sem unidade definida

2. _viola_oferta_em_dia_nao_atendido le unidade do ctx.known:
   - Se unidade conhecida: usa mapping especifico
   - Se unidade ausente: fallback pro mapping antigo (uniao seg-sex)

3. _viola_dia_semana e _viola_oferta_em_dia_nao_atendido SEMPRE-ON:
   - Saem do gate _FILTROS_LEGACY_ATIVOS
   - Renomeados nos logs como [FILTRO C-31a] e [FILTRO C-31b]
   - Sao invariantes duros (fatos calculaveis, nao regras subjetivas)

Fonte canonica dos dias (voice_agent/knowledge_base/22_agenda_dra_karla.md):
  Karla Asa Norte:    segunda, quarta, sexta
  Karla Aguas Claras: terca, quinta
  Karla sab/dom:      NUNCA
  Fabricio:           terca, quinta

Pytest novo: tests/test_bug_c31_dia_medico_unidade.py — 17 cenarios:
  - TestMappingMedicoUnidade (5): sanity check do mapping
  - TestViolaOfertaEmDiaNaoAtendido (7): cobre Karla quinta na Asa Norte
    (violacao) vs Aguas Claras (OK), sabado violacao, caso real Fabio
  - TestViolaDiaSemana (3): divergencia dia-da-semana vs data real
  - TestIntegracaoScrubProhibited (2): texto literal Fabio substituido

17/17 verde local + 107/107 verde combinado (C-31 + nomes + C-30 +
C-30A + watchdog promessa).

Sem envs novas. Filtros sempre-ON entram em vigor no proximo turno
apos deploy.

Licao arquitetural:
- Fato objetivo (calendario, medico atende ou nao) != regra subjetiva.
  Invariantes duros sempre-ON, sem toggle.
- Gate unico FILTROS_LEGACY=0 ja foi causa raiz do C-30 e agora C-31.
  Mover pra sempre-ON e o fix em ambos os casos.
- KB tem fonte canonica em 22_agenda_dra_karla.md. Codigo tinha
  mapping incompleto ha semanas. Disciplina: regras estruturais no KB
  tem que casar com o codigo.

CLAUDE.md atualizado — C-31 no topo do rolling log.
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
echo "  Bug C-31 em prod. Sem envs novas."
echo "  Proxima oferta com data invalida sera"
echo "  substituida pelo fallback (Lia reconfere)."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
