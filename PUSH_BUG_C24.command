#!/bin/bash
# Push Bug C-24 — 2 fixes:
# C-24a: webhook auto-desativa IA quando lead muda pra etapa inativa
# C-24b: Fabrício atende 50+, não "exclusivamente catarata"
# Duplo-clique pra rodar.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Bug C-24 — IA off em etapas inativas + Fabrício 50+"
echo "==============================================="

git add CLAUDE.md voice_agent/knowledge_base/_MASTER_INSTRUCTION.md voice_agent/webhook.py PUSH_BUG_C24.command
git commit -m "fix(bug-c24): auto-desativar IA em etapas inativas + Fabrício 50+

C-24a — Equipe humana reclamava que mesmo movendo lead pra
1-ATENDIMENTO HUMANO / 10-CIRURGIAS / 11-LENTES / 12-FORNECEDORES,
Lia continuava respondendo. webhook.py:
- Adiciona _STATUS_INATIVOS_IA set = {106563343, 91486864, 106157327,
  106157139, 106484343, 106484347, 142, 143}
- Endpoint /admin/kommo-trigger-status-change agora bifurca:
  • status em INATIVOS → ATIVADO IA = Desativado
  • status em ATIVOS  → ATIVADO IA = Ativado
- Webhook Kommo continua o mesmo, só amplia comportamento

C-24b — Regra E5.7-A no _MASTER_INSTRUCTION.md reescrita:
- Pediátrico → Karla
- Adulto 18-49 rotina → Karla APV
- Adulto 50+ qualquer motivo → Fabrício (especialista 50+)
- Catarata declarada qualquer idade → Fabrício
- APV/Prisma/Estrabismo qualquer idade → Karla
- PROIBIDO 'Fabrício exclusivamente catarata' (restritivo)
- Comunicação correta: 'para adultos 50+ é com Dr. Fabrício'
- Razão: paciente pode não saber que tem catarata; Fabrício avalia

CLAUDE.md: Bug C-24 indexado." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo."
echo "  • Easypanel auto-deploy ~3 min"
echo "  • Webhook Kommo precisa estar configurado pra status-change"
echo "    (já estava na task #233; só amplia comportamento)"
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
