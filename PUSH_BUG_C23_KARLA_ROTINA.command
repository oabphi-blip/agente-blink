#!/bin/bash
# Push imediato — Bug C-23 — Lia direciona rotina/check-up SEMPRE pra Dra. Karla
# Caso real: lead 24135088 Adrielly (23 anos, rotina, particular)
# Duplo-clique pra rodar.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-23 — rotina = Karla sempre"
echo "==============================================="

git add CLAUDE.md voice_agent/knowledge_base/_MASTER_INSTRUCTION.md PUSH_BUG_C23_KARLA_ROTINA.command
git commit -m "fix(prompt): Bug C-23 rotina/oftalmologia geral SEMPRE com Dra. Karla

Caso: lead 24135088 Adrielly (23a, rotina, particular). Campo
MEDICOS no Kommo = 'Dr. Fabrício Freitas' (errado — Fabrício SÓ
catarata). Lia confusa entrou em loop 8 msg em 4 min, terminou
perguntando 'qual médico você quer' — paciente não sabe.

Fix regra E5.7-A em _MASTER_INSTRUCTION.md:
- Rotina/check-up/óculos/queixa visual geral → SEMPRE Dra. Karla
- Dr. Fabrício atende EXCLUSIVAMENTE catarata
- Mesmo que MEDICOS no Kommo venha errado, Lia ignora e anuncia
  proativamente: 'Sua consulta será com Dra. Karla Delalíbera,
  especialista Avaliação do Processamento Visual'
- PROIBIDO perguntar 'qual médico você quer' — Lia decide pela
  especialidade do motivo
- Anti-loop: nunca >3 mensagens sem resposta do paciente

CLAUDE.md: Bug C-23 indexado no rolling log." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo. Deploy ~3 min."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
