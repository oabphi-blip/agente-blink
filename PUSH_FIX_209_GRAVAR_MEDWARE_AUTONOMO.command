#!/bin/bash
# Push fix #209 — Gravação Medware autônoma
# Único objetivo: Lia chamar medware.criar_agendamento() de verdade.
# Sem isso, ela confirma com paciente mas agendamento não entra no Medware.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH FIX #209 — Gravação Medware Autônoma"
echo "==============================================================="
echo ""

# 1. Sanity — confirmar que o fix está no código local
test -f voice_agent/tools_lia.py || { echo "ERRO: tools_lia.py não existe"; exit 1; }

grep -q "medware_client.criar_agendamento" voice_agent/tools_lia.py \
    || { echo "ERRO: fix #208 não está em tools_lia.py"; exit 1; }

python3 -c "import ast; ast.parse(open('voice_agent/tools_lia.py').read())" \
    || { echo "ERRO: syntax error em tools_lia.py"; exit 1; }

echo "✓ Sanity check OK"
echo ""

# 2. Atualizar repo local com origem (caso tenha commits novos)
echo "→ git pull origin main (sync)"
git pull origin main --rebase --no-edit 2>&1 | tail -5
echo ""

# 3. Status atual
echo "→ git status:"
git status --short
echo ""

# 4. Stage tools_lia.py + arquivos relacionados
git add voice_agent/tools_lia.py \
        PUSH_FIX_209_GRAVAR_MEDWARE_AUTONOMO.command

# Se houver tests/test_gravar_agendamento_medware_real.py, adiciona também
test -f tests/test_gravar_agendamento_medware_real.py && \
    git add tests/test_gravar_agendamento_medware_real.py

# 5. Verifica se há algo pra commitar
if git diff --staged --quiet; then
    echo "✓ Nada novo pra pushar — fix #209 já está em prod."
    echo ""
    echo "Validar em prod:"
    echo "  curl https://blink-agent.6prkfn.easypanel.host/health"
    echo ""
    read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
    exit 0
fi

# 6. Commit + push
echo "→ Há mudanças pra pushar."
git diff --staged --stat
echo ""

git commit -m "fix(#209): gravação Medware autônoma — handle_gravar_agendamento_medware chama criar_agendamento real

Origem: task #208 finalizada em 05/06/2026, push pendente há 10 dias.

Antes:
- handle_gravar_agendamento_medware era STUB
- Só escrevia flag Redis blink:tool_gravacao_solicitada
- Delegava pra voice_agent/executor_agendamento.py — arquivo que NUNCA existiu no repo
- Resultado: Lia confirmava com paciente, mas Medware ficava sem o agendamento

Agora:
- handle_gravar_agendamento_medware chama medware_client.criar_agendamento direto
- Args extraídos do caller_context.known (nome, CPF, data_nasc, celular, convênio, médico, unidade)
- COD_MEDICO_POR_NOME e COD_UNIDADE_POR_NOME mapeiam Karla=12080, Fabrício=12081, Asa Norte=5, Águas Claras=3
- Dedup Redis 24h via blink:agendamento_gravado:{convo_key}
- Falha Medware → ResultadoTool(erro='medware_falhou'), escalonamento via circuit breaker
- Fallback retrocompatível: sem medware_client, volta a escrever flag Redis (modo teste)

Pre-req pra funcionar 100%:
- LIA_TOOLS_ENABLED=1 no Easypanel — força Sonnet chamar tool em vez de escrever 'deixa eu consultar'

Sem isso, fix #208 fica inerte porque tool nunca é chamada.

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
echo "PRÓXIMO PASSO MANUAL:"
echo "  1. Easypanel → app blink/agent → Ambiente"
echo "  2. Adicionar (se não existir): LIA_TOOLS_ENABLED=1"
echo "  3. Salvar → Implantar"
echo ""
echo "DEPOIS DO DEPLOY:"
echo "  curl https://blink-agent.6prkfn.easypanel.host/health"
echo "  Lia em prod vai chamar medware.criar_agendamento de verdade."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
