#!/bin/bash
# Push endpoint /admin/disparar-leads-frio-direto + dispara batch real
# Fábio 11/06/2026 — caminho B aprovado
#
# Sequência: push → aguarda 3min deploy → dry-run 5 leads → produção 30 leads

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Endpoint frio-direto — push + deploy + batch"
echo "==============================================="
echo ""

# Carrega WEBHOOK_SECRET
WEBHOOK_SECRET=$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
if [ -z "$WEBHOOK_SECRET" ]; then
    echo "❌ WEBHOOK_SECRET não encontrado em lia_engineer/.env.local"
    exit 1
fi
echo "✓ WEBHOOK_SECRET carregado"

AGENT="https://blink-agent.6prkfn.easypanel.host"

echo ""
echo "▶ Passo 1/4: git push"
git add voice_agent/webhook.py PUSH_FRIO_DIRETO.command
git commit -m "feat(webhook): endpoint /admin/disparar-leads-frio-direto (B-309)

Fábio 11/06/2026 — 'estamos sem leads pra atendimento'.

/admin/disparar-categoria retorna 0 em R/E/C porque (a) renomear leads
(#227) tirou prefixo [X] do nome, (b) dedup Redis 24h ainda vigente.

Endpoint novo bypassa o filtro de prefixo: pega leads em status alvo
(default 101508307 = 2.LEADS FRIO), exclui convênio bloqueado (Inas/
GDF/Cassi/SulAmerica/Bradesco/Unimed), dispara template aprovado
(default 1020_retorno_mais_de_1_ano_v1) com body_params montados a
partir do contato Kommo. Dedup Redis 24h em chave própria.

Query params: max (cap 30, max 100), template, dry_run, skip_dedup,
status_id." || echo "  (nada novo pra commitar)"
git push origin main 2>&1 | tail -5

echo ""
echo "▶ Passo 2/4: aguardando deploy Easypanel (~3 min)"
echo "  (testa endpoint a cada 20s até responder 200)"

for i in $(seq 1 12); do
    sleep 20
    code=$(curl -sw "%{http_code}" -o /dev/null --max-time 10 \
        "${AGENT}/admin/disparar-leads-frio-direto?dry_run=true&max=1&secret=${WEBHOOK_SECRET}" || echo "000")
    if [ "$code" = "200" ]; then
        echo "  ✓ Endpoint LIVE (${i}x20s = $((i*20))s)"
        break
    fi
    echo "  [${i}/12] HTTP=$code ..."
done

if [ "$code" != "200" ]; then
    echo "  ⚠️  Endpoint ainda não disponível. Tenta manualmente em 2 min:"
    echo "     curl '${AGENT}/admin/disparar-leads-frio-direto?dry_run=true&max=5&secret=$WEBHOOK_SECRET' | jq"
    read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
    exit 1
fi

echo ""
echo "▶ Passo 3/4: dry-run 5 leads (preview do que vai disparar)"
curl -s --max-time 60 \
    "${AGENT}/admin/disparar-leads-frio-direto?dry_run=true&max=5&secret=${WEBHOOK_SECRET}" \
    | python3 -m json.tool 2>/dev/null | head -50

echo ""
echo "==============================================="
echo "  PRONTO PRA PRODUÇÃO REAL?"
echo "==============================================="
echo ""
echo "  Se OK acima, rode AGORA (cap 30 leads):"
echo ""
echo "  curl '${AGENT}/admin/disparar-leads-frio-direto?max=30&secret=\$WEBHOOK_SECRET' | jq"
echo ""
echo "  ⚠️  Vai disparar template 1020_retorno_mais_de_1_ano_v1"
echo "      pra 30 leads REAIS de 2.LEADS FRIO."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
