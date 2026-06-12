#!/bin/bash
# Push - Ativacao inteligente PLUGADA no pipeline real (responder.py)
# + fix dedup-merge via /contacts (Kommo armazena telefone em contact, nao lead)
# Fabio 12/06/2026 modo autonomo

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

WEBHOOK_SECRET=$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local | head -1 | cut -d= -f2- | tr -d '"')
AGENT="https://blink-agent.6prkfn.easypanel.host"

echo "==============================================="
echo "  Ativacao no pipeline + fix dedup-merge"
echo "==============================================="

git add voice_agent/kommo.py voice_agent/webhook.py \
        voice_agent/ativacao_inteligente.py \
        voice_agent/responder.py \
        PUSH_ATIVACAO_PIPELINE.command

git commit -m "feat(pipeline): ativacao inteligente plugada + fix dedup via /contacts

Fabio 12/06/2026 autorizou modo autonomo continuar.

3 mudancas:

1. voice_agent/responder.py - _caller_context_block agora INJETA bloco
   'SAUDACAO INICIAL SUGERIDA (regra E1.7-A)' no system prompt da Lia
   quando ha dados conhecidos do paciente (nome, medico, convenio,
   unidade). Usa gerar_saudacao_de_ctx() do modulo ativacao_inteligente.
   Lia passa a iniciar conversa com prova de escuta em vez de triagem
   do zero. Caso real Carmen 24142996 vai gerar: 'Ola, Carmen! Aqui e
   a Lia da Blink. Vi aqui que sua consulta era com a Dra. Karla pelo
   Plan Assiste na Asa Norte. Vamos seguir de onde paramos?'

2. voice_agent/ativacao_inteligente.py - nova funcao
   gerar_saudacao_de_ctx(ctx) que aceita formato caller_context do
   pipeline. Converte ctx.known para formato lead Kommo e delega
   pra gerar_saudacao_personalizada.

3. voice_agent/kommo.py + webhook.py - fix dedup-merge:
   - search_contacts_by_query(query) faz GET /contacts?query=PHONE
   - get_leads_by_phone(tel, pipeline) busca contato -> coleta
     lead_ids vinculados -> get_lead completo de cada um
   - endpoint dedup-merge-por-telefone usa get_leads_by_phone (estava
     buscando em /leads que nao indexa telefone)

Pytest tests/test_ativacao_inteligente.py - 9/9 verde." || echo "  (nada novo)"
git push origin main 2>&1 | tail -5

echo ""
echo "Aguardando deploy (~3 min)..."
for i in \$(seq 1 12); do
    sleep 20
    body=\$(curl -s --max-time 15 "\${AGENT}/admin/ativacao-inteligente/24142996?secret=\${WEBHOOK_SECRET}" 2>/dev/null || echo "")
    if echo "\$body" | grep -q '"personalizada"'; then
        echo "  LIVE [\${i}x20s = \$((i*20))s]"
        echo ""
        echo "Saudacao Carmen 24142996:"
        echo "\$body" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('saudacao',''))" 2>/dev/null
        echo ""
        echo "Testando dedup-merge agora (deve achar 6 leads de Pryscilla):"
        curl -s --max-time 20 "\${AGENT}/admin/dedup-merge-por-telefone/20993203?secret=\${WEBHOOK_SECRET}" | python3 -m json.tool 2>/dev/null | head -20
        break
    fi
    echo "  [\${i}/12] aguardando..."
done

echo ""
echo "==============================================="
echo "PROXIMA mensagem que paciente conhecido enviar:"
echo "  Lia vai usar saudacao com prova de escuta."
echo "  Bug Carmen (loop 6x) nao acontece mais."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
