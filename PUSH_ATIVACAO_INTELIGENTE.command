#!/bin/bash
# Push - Ativacao inteligente com prova de escuta + fix search_leads Kommo
# Fabio 12/06/2026 modo autonomo

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

WEBHOOK_SECRET=$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local | head -1 | cut -d= -f2- | tr -d '"')
AGENT="https://blink-agent.6prkfn.easypanel.host"

echo "==============================================="
echo "  Ativacao inteligente + fix dedup-merge"
echo "==============================================="

git add voice_agent/kommo.py voice_agent/webhook.py \
        voice_agent/ativacao_inteligente.py \
        tests/test_ativacao_inteligente.py \
        PUSH_ATIVACAO_INTELIGENTE.command

git commit -m "feat: ativacao inteligente com prova de escuta + fix dedup-merge

Fabio 12/06/2026: 'paciente que volta com lead ja preenchido nao pode
ser tratado como lead novo. Tem que demonstrar escuta do que ja
sabemos sobre ele'.

3 mudancas:

1. voice_agent/ativacao_inteligente.py - funcao
   gerar_saudacao_personalizada(lead) que monta saudacao Lia com prova
   de escuta. 3 tipos:
   - generica: sem dado nenhum (pergunta nome)
   - personalizada: cita ate 4 dados do lead (nome paciente, medico,
     convenio, unidade)
   - lacuna_longa: updated_at >180 dias reconhece gap sem dramatizar
   Principios: max 2 paragrafos, sempre termina em pergunta unica,
   NAO inventa dados ausentes, anti-constrangimento.

2. voice_agent/kommo.py - novo metodo search_leads_by_query(query,
   pipeline_id, limit) que faz GET /leads?query=... pagina ate 4
   paginas. Destrava endpoint dedup-merge (estava chamando metodo
   inexistente).

3. voice_agent/webhook.py:
   - GET /admin/ativacao-inteligente/{lead_id} - preview da saudacao
   - dedup-merge-por-telefone agora chama search_leads_by_query
     corretamente (achava 0 leads antes)

Pytest tests/test_ativacao_inteligente.py - 9 cenarios verdes
(generica, com nome, com medico Karla, com convenio aceito, lacuna
180d, convenio nao se aplica, max 2 paragrafos, pergunta no fim, caso
real Carmen 24142996)." || echo "  (nada novo)"
git push origin main 2>&1 | tail -5

echo ""
echo "Aguardando deploy (~3 min)..."
for i in $(seq 1 12); do
    sleep 20
    body=$(curl -s --max-time 15 "${AGENT}/admin/ativacao-inteligente/24142996?secret=${WEBHOOK_SECRET}" 2>/dev/null || echo "")
    if echo "$body" | grep -q '"tipo"'; then
        echo "  LIVE [${i}x20s = $((i*20))s]"
        echo ""
        echo "Preview Carmen 24142996:"
        echo "$body" | python3 -m json.tool 2>/dev/null | head -25
        break
    fi
    echo "  [${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "Para testar outros leads:"
echo "  curl '${AGENT}/admin/ativacao-inteligente/{LEAD_ID}?secret=\$WS' | jq"
echo ""
echo "Para dedup-merge:"
echo "  curl '${AGENT}/admin/dedup-merge-por-telefone/{LEAD_ID}?secret=\$WS' | jq"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
