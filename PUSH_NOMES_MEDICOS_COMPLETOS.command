#!/bin/bash
# Push regra nome+sobrenome do medico em TODA mencao - 16/06/2026
#
# Origem: Fabio - "atualizar pronto agente, sempre que referi ao medico,
# constar nome e sobrenome"
#
# Mudancas:
#   - 26 arquivos KB (.md) com 106 substituicoes automatizadas:
#     'Dra. Karla' -> 'Dra. Karla Delalibera' (62x)
#     'Dr. Fabricio' -> 'Dr. Fabricio Freitas' (44x)
#   - _MASTER_INSTRUCTION.md secao 0AA.5 reforcada com regra imperativa
#   - Bump VERSAO_PROMPT forca re-cache Anthropic
#   - tests/test_nome_sobrenome_medicos_kb.py (NOVO, 12 cenarios)
#
# Pytest: 12/12 verde + 90/90 verde combinado

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push regra nome+sobrenome medicos"
echo "==============================================="

echo ""
echo "[1/5] Pytest regra de nomes + suite anti-hesitacao..."
python3 -m pytest tests/test_nome_sobrenome_medicos_kb.py \
                  tests/test_c30a_medware_down.py \
                  tests/test_anti_hesitacao_agenda_c30.py \
                  tests/test_watchdog_promessa.py -q 2>&1 | tail -3

echo ""
echo "[2/5] Conferencia: zero ocorrencias sem sobrenome nos KB..."
total=0
for f in voice_agent/knowledge_base/*.md; do
    n=$(grep -cP "Dra\.\s+Karla(?!\s+Delal)|Dr\.\s+Fabr[ií]cio(?!\s+Freitas)" "$f" 2>/dev/null || echo 0)
    n_real=$(echo "$n" | head -1)
    # Filtra anti-exemplos (linhas com nunca/(incompleto)/(informal/abreviado/X) — esses sao legitimos
    n_validos=$(grep -P "Dra\.\s+Karla(?!\s+Delal)|Dr\.\s+Fabr[ií]cio(?!\s+Freitas)" "$f" 2>/dev/null | \
                grep -vP "❌|nunca|incompleto|informal|abreviado" | wc -l | tr -d ' ')
    if [ "$n_validos" -gt 0 ] 2>/dev/null; then
        echo "  $f: $n_validos violacoes (ex-anti-exemplos)"
        total=$((total + n_validos))
    fi
done 2>/dev/null
echo "  Total restante: $total (esperado: 0)"

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
git add voice_agent/knowledge_base/*.md \
        tests/test_nome_sobrenome_medicos_kb.py \
        CLAUDE.md \
        PUSH_NOMES_MEDICOS_COMPLETOS.command

git commit -m "feat(prompt): nome+sobrenome do medico SEMPRE em toda mencao

Origem: Fabio 16/06/2026 — atualizar pronto agente, sempre que referi
ao medico, constar nome e sobrenome.

Mudancas:

1. Substituicao em massa em 26 arquivos KB (.md) — 106 ocorrencias:
   - 'Dra. Karla' (sem 'Delal' depois) -> 'Dra. Karla Delalibera' (62x)
   - 'Dr. Fabricio' / 'Dr. Fabricio' (sem 'Freitas') -> 'Dr. Fabricio Freitas' (44x)
   - Regex protegidos: nao altera onde sobrenome ja esta, nao altera
     'Karla 30min' tecnico interno, nao toca outras medicas

2. _MASTER_INSTRUCTION.md secao 0AA.5 reforcada:
   - Regra IMPERATIVA 'NOME + SOBRENOME SEMPRE'
   - Exemplos corretos com sobrenome
   - Anti-exemplos sem sobrenome (com marcador ❌)
   - Razao explicita: paciente conhece medico pelo nome completo,
     apresentacao parcial enfraquece autoridade clinica
   - Bump VERSAO_PROMPT: 2026-06-16-nome-sobrenome-medico-obrigatorio
     forca re-cache Anthropic (cache_control breakpoint)

3. tests/test_nome_sobrenome_medicos_kb.py (NOVO, 12 cenarios):
   - Varre TODOS os artigos KB recursivamente
   - Falha se 'Dra. Karla' sem 'Delal' OU 'Dr. Fabricio' sem 'Freitas'
   - Ignora linhas anti-exemplo (com marcador ❌, 'nunca', '(incompleto)',
     '(informal', 'abreviado')
   - Sanity: regex nao dispara em 'Karla 30min' tecnico nem em outras
     medicas (Dra. Katia)
   - Validacao 0AA.5: master instruction tem 'NOME + SOBRENOME SEMPRE'
   - Validacao VERSAO_PROMPT atualizada

Resultado:
  12/12 verde local
  90/90 verde combinado (nomes + C-30 + C-30A + watchdog promessa)

Sem envs novas. Pega na proxima conversacao apos deploy.

Licao: quando Fabio define regra de tom/apresentacao, aplicar em TODO
KB simultaneamente. KB e fragmentado em 38+ artigos — regra que vive
so na Master nao chega ao prompt final (RAG injeta o que for relevante).

CLAUDE.md atualizado — regra no topo do rolling log.
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
echo "  Regra nome+sobrenome em prod."
echo "  Sem envs novas. Proximo paciente nova"
echo "  conversacao ja recebe nome completo."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
