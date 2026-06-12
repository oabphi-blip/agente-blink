#!/bin/bash
# Push Bug C-27 - 3 fixes:
# 1. Indexar Bug C-27 no CLAUDE.md (duplicacao + notas vazias + KOMMO_TOKEN 403)
# 2. Endpoint /admin/dedup-merge-por-telefone/{lead_id}
# 3. Pendente: ativacao inteligente com prova de escuta (proxima sessao)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Bug C-27 - duplicacao + nota vazia + dedup"
echo "==============================================="

git add CLAUDE.md voice_agent/webhook.py PUSH_BUG_C27.command
git commit -m "fix(bug-c27): indexar duplicacao+nota vazia + endpoint dedup-merge

Origem: Fabio 12/06/2026, leads Samuel 10275014 e Pryscilla/Pedro
24142668. Confirmado: telefone +556182060168 tem 6 leads diferentes
desde abril/2024. Webhook Kommo cria lead novo a cada chat_id novo
sem dedup por telefone.

3 fixes desta sessao:

1. CLAUDE.md: Bug C-27 indexado no topo do rolling log com 3 sintomas
   (duplicacao + notas vazias + KOMMO_TOKEN 403) e plano de fix.

2. webhook.py: endpoint GET /admin/dedup-merge-por-telefone/{lead_id}
   busca outros leads do mesmo telefone, ranqueia por ativos vs
   finalizados + recencia, retorna sugestao de merge ou manter
   separado. Atendente humano decide com base no racional.

3. PENDENTE pra proxima sessao: 'ativacao inteligente com prova de
   escuta'. Quando paciente volta com URL DA CONVERSA pre-preenchida,
   Lia deve ler historico de notas anteriores e gerar resposta tipo
   'Vi que voce ja conversou em [data] sobre [assunto], vamos
   continuar de onde paramos?' em vez de tratar como lead novo.

Ainda dependendo do usuario:
- Renovar KOMMO_TOKEN no Easypanel (resolve HTTP 403 add_note)
- Setar TRACING_ENABLED=1 (resolve replay vazio)" || echo "  (nada novo)"
git push origin main 2>&1 | tail -5

echo ""
echo "Apos deploy ~3min, testar:"
echo "  curl 'https://blink-agent.6prkfn.easypanel.host/admin/dedup-merge-por-telefone/24142668?secret=\$WS' | jq"
echo ""
echo "Pendente Fabio Easypanel:"
echo "  1. Renovar KOMMO_TOKEN (Kommo > API > Token de Acesso)"
echo "  2. Setar TRACING_ENABLED=1"
echo "  3. Implantar"
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
