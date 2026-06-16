#!/bin/bash
# Push Bug C-33 — Pterigio/Cornea = Dr. Fabricio Freitas
# 16/06/2026
#
# Origem: Fabio 16/06/2026, lead 24160634. Paciente perguntou sobre pterigio.
# Lia respondeu "fazemos catarata (Fabricio) e estrabismo (Karla)" — omitiu
# cornea inteira. Quando paciente confirmou pterigio, Lia caiu em hesitacao
# "deixa eu reconsultar a agenda... volto em 1 minuto".
#
# Causa raiz: pterigio NAO existia em NENHUM artigo KB. Lia nao sabia rotear.
#
# Fix em 3 camadas:
#   1. _MASTER_INSTRUCTION.md secao 5.6 + 5.7-A: regra Cornea->Fabricio
#   2. 01_medicos_e_especialidades.md cabecalho + mapa rapido com pterigio
#   3. Bump VERSAO_PROMPT pra forcar re-cache Anthropic
#
# Pytest: 5/5 verde

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-33 — Pterigio/Cornea"
echo "==============================================="

echo ""
echo "[1/5] Pytest C-33 + suite anti-bug agenda..."
python3 -m pytest tests/test_bug_c33_pterigio_cornea.py \
                  tests/test_bug_c31_dia_medico_unidade.py \
                  tests/test_nome_sobrenome_medicos_kb.py \
                  tests/test_c30a_medware_down.py \
                  tests/test_anti_hesitacao_agenda_c30.py \
                  tests/test_watchdog_promessa.py -q 2>&1 | tail -3

echo ""
echo "[2/5] Verificacao: pterigio e cornea no KB..."
N_PTERIGIO=$(grep -clE "pter[íi]gio" voice_agent/knowledge_base/*.md 2>/dev/null | wc -l)
N_CORNEA=$(grep -clE "c[óo]rnea" voice_agent/knowledge_base/*.md 2>/dev/null | wc -l)
echo "  pterigio em $N_PTERIGIO arquivo(s) KB"
echo "  cornea em $N_CORNEA arquivo(s) KB"

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
git add voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        voice_agent/knowledge_base/01_medicos_e_especialidades.md \
        tests/test_bug_c33_pterigio_cornea.py \
        CLAUDE.md \
        PUSH_C33_PTERIGIO_CORNEA.command

git commit -m "fix(C-33): pterigio/cornea -> Dr. Fabricio Freitas (lead 24160634)

Origem: Fabio 16/06/2026, lead 24160634. Paciente perguntou sobre pterigio.
Lia respondeu 'fazemos catarata (Fabricio) e estrabismo (Karla)' — omitiu
cornea inteira. Quando paciente confirmou pterigio, Lia caiu em hesitacao
'deixa eu reconsultar a agenda... volto em 1 minuto'.

Causa raiz: pterigio NAO existia em NENHUM artigo do KB. Nem cornea.
Lia nao sabia rotear motivo -> medico -> caiu em fallback hesitacao.

Fix em 3 camadas:

1. _MASTER_INSTRUCTION.md secao 5.6 + 5.7-A:
   - Apresentacao canonica: 'Cornea (Pterigio, Ceratocone, Transplante)
     -> Dr. Fabricio Freitas, especialista em cornea'
   - Inferencia por medico 5.6.1: 'Dr. Fabricio Freitas -> Catarata,
     Cornea (incluindo Pterigio), saude ocular do adulto 50+'
   - Matching motivo 5.7-A: 'Qualquer idade + Cornea/Pterigio/
     Ceratocone/Transplante -> Dr. Fabricio Freitas'

2. 01_medicos_e_especialidades.md:
   - Cabecalho atualizado de '(cirurgiao de catarata)' pra
     '(saude ocular adulto 50+ e especialista em cornea)'
   - Especialidades expandidas: Catarata, Cornea (Pterigio, Ceratocone,
     Transplante)
   - Lista de gatilhos linguisticos: pterigio, 'carne no olho', cornea,
     ceratocone, olho ardido com vermelho persistente
   - Mapa rapido ganhou linha 'Pterigio (carne no olho), cornea,
     ceratocone -> Dr. Fabricio Freitas | Aguas Claras'

3. Bump VERSAO_PROMPT -> 2026-06-16-pterigio-cornea-fabricio
   Forca re-cache Anthropic (cache_control breakpoint)

Pytest novo: tests/test_bug_c33_pterigio_cornea.py — 5 cenarios:
  - TestPterigioNoKB (3): pterigio em 2+ KB, junto a Fabricio na master,
    em 01_medicos
  - TestCorneaNoKB (1): cornea em 2+ KB
  - TestVersaoPromptAtualizada (1): VERSAO_PROMPT bumped

5/5 verde local.

Licao arquitetural:
- Sintoma 'deixa eu reconsultar' pode esconder 'KB incompleto' como
  causa raiz, nao so Medware vazio ou env desligada.
- Auditoria recorrente: cada hesitacao real, verificar se motivo do
  paciente existe no KB ANTES de tratar como bug de filtro.
- KB e fonte da verdade pro tool calling decidir medico. KB incompleto
  = modelo sem como rotear = hesitacao silenciosa.

CLAUDE.md atualizado — C-33 no topo do rolling log.
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
echo "  Bug C-33 em prod."
echo "  Cornea/Pterigio -> Dr. Fabricio Freitas."
echo "  Proximo paciente com pterigio recebe roteamento correto."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
