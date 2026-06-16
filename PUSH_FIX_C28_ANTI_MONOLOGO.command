#!/bin/bash
# Push fix Bug C-28 — Anti-monólogo + dicas inventadas + markdown WhatsApp
# Origem: lead 24154908 (15/06/2026 18:28 BRT)
# Fábio: "foi enviado quase um livro na primeira mensagem"

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "================================================================"
echo "  PUSH FIX C-28 — Anti-monólogo (lead 24154908)"
echo "================================================================"
echo ""
echo "Arquivos alterados:"
echo "  - voice_agent/knowledge_base/_MASTER_INSTRUCTION.md (seção 0-AA)"
echo "  - voice_agent/responder.py (4 filtros sempre-ON)"
echo "  - tests/test_anti_monologo_lead_24154908.py (NOVO)"
echo "  - CLAUDE.md (lição C-28)"
echo ""

# Sanity check: garantir que arquivos existem
test -f voice_agent/knowledge_base/_MASTER_INSTRUCTION.md || { echo "ERRO: _MASTER_INSTRUCTION.md não existe"; exit 1; }
test -f voice_agent/responder.py || { echo "ERRO: responder.py não existe"; exit 1; }
test -f tests/test_anti_monologo_lead_24154908.py || { echo "ERRO: pytest não existe"; exit 1; }

# Garantir que regras novas estão lá
grep -q "0-AA. REGRAS DE OURO ANTI-MONÓLOGO" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: seção 0-AA não está no _MASTER_INSTRUCTION.md"; exit 1; }
grep -q "FILTROS C-28 ANTI-MONÓLOGO" voice_agent/responder.py \
    || { echo "ERRO: filtros C-28 não estão no responder.py"; exit 1; }

echo "✓ Sanity check OK"
echo ""

# Sintaxe Python responder.py
python3 -c "import ast; ast.parse(open('voice_agent/responder.py').read())" \
    || { echo "ERRO: responder.py tem syntax error"; exit 1; }
echo "✓ responder.py syntax OK"
echo ""

# Git
git add voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        voice_agent/responder.py \
        tests/test_anti_monologo_lead_24154908.py \
        CLAUDE.md \
        PUSH_FIX_C28_ANTI_MONOLOGO.command

git commit -m "fix(prompt): Bug C-28 — Anti-monólogo + dicas inventadas + markdown WhatsApp

Origem: lead 24154908 (15/06/2026 18:28 BRT). Lia mandou 200+ palavras
na 1ª resposta citando '60-90 minutos' (inventado), '4-6 horas dilatação'
(banido task #92), '15 anos de experiência' (fabricado), markdown ##,
pediu 4 dados de uma vez. Atendente humana: 'Mensagem muito grande'.

Fix em 3 camadas:

1. Seção 0-AA no _MASTER_INSTRUCTION.md (PRIORIDADE ABSOLUTA):
   - 0AA.1 max 60 palavras na 1ª resposta
   - 0AA.2 UMA pergunta por mensagem
   - 0AA.3 banimento textual de dicas inventadas
   - 0AA.4 zero markdown estruturado (## --- ***)
   - 0AA.5 apresentação canônica Karla=APV / Fabrício=50+
   - 0AA.6 zero info não pedida
   - 0AA.7 contra-exemplo real do lead 24154908
   - 0AA.8 primeiro turno com motivo inferido

2. 4 filtros sempre-ON em responder.py::_scrub_prohibited (executam ANTES):
   - _viola_dicas_banidas (regex blacklist com 11 padrões)
   - _viola_inicio_noite (task #223 reforço)
   - _viola_markdown_estruturado + _limpar_markdown_banido
   - _viola_primeira_mensagem_longa (>80 palavras na 1ª)

3. tests/test_anti_monologo_lead_24154908.py — 25 cenários blindados.

Bump de versão no header do prompt força re-cache do Anthropic SDK.

Causa raiz arquitetural: regras só viviam no CLAUDE.md, nunca chegavam
ao _MASTER_INSTRUCTION.md (prompt prod). Pipeline de deploy de regras
inexistente — corrigido pela própria estrutura desse commit.

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "================================================================"
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "================================================================"
echo ""
echo "Validação pós-deploy:"
echo "  1. curl https://blink-agent.6prkfn.easypanel.host/health  (espera 200)"
echo "  2. /admin/simulate-inbound com 'Vocês fazem avaliação pediátrica?'"
echo "     → resposta DEVE ter ≤80 palavras + 1 pergunta + sem '60-90' + sem '##'"
echo "  3. Watch lead reais nas próximas 2h — atendente NÃO deve escrever"
echo "     'mensagem muito grande' nas notas Kommo."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
