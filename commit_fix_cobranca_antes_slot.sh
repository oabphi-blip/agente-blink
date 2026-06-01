#!/bin/bash
# Commit: trava cobrança antes de slot (regra 12.9 + filtro pós-geração)
# Bug origem: lead 24034205 (Fábio teste) — cobrou sinal R$ 305,50 sem
# oferecer slot concreto e sem mencionar Fila de Encaixe.
set -e

REPO_DIR="$HOME/Documents/Claude/Projects/AGENTE IA BLINK"
TOKEN="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"
USERNAME="oabphi-blip"
AUTH_URL="https://${USERNAME}:${TOKEN}@github.com/oabphi-blip/agente-blink.git"
CLEAN_URL="https://github.com/oabphi-blip/agente-blink.git"

cd "$REPO_DIR"
git stash -u || echo "(nada pra guardar)"
git pull --rebase "$AUTH_URL" main || exit 1

# Aplica o stash de volta
git stash pop 2>/dev/null || echo "(sem stash pra aplicar)"

git add voice_agent/responder.py voice_agent/knowledge_base/_MASTER_INSTRUCTION.md

git status --short
git diff --cached --stat
echo ""

read -p "Confirma commit? (s/N): " C
[[ "$C" != "s" && "$C" != "S" ]] && { echo "Cancelado"; exit 0; }

git commit -m "fix(lia): trava cobrança antes de slot concreto (regra 12.9)

_MASTER_INSTRUCTION.md:
- Regra 12.9 NOVA: ordem rígida (oferecer slot → confirmar →
  apresentar 2 opções pagamento → cobrar). Lista frases proibidas
  ANTES do paciente escolher slot ('sinal R\$', 'chave Pix',
  'comprovante pix', 'garantir horário com Pix'). Inclui exemplos
  certo/errado com referência ao lead 24034205.

responder.py:
- _COBRANCA_SINAL_PATTERNS: regex pra 'sinal de R\$', 'chave Pix',
  'comprovante pix', chaves Pix oficiais (karladelalibera@gmail,
  CNPJ 52.303.729)
- _SLOT_CONCRETO_NA_RESPOSTA: regex pra 'dia-da-semana, DD/MM às HH:MM'
- _viola_cobranca_antes_slot(): True se menciona cobrança SEM slot
  concreto na mesma mensagem E SEM mencionar 'encaixe'
- _scrub_prohibited: ativa o filtro entre etapas 0 e 1.
  Fallback: 'Antes de qualquer pagamento, deixa eu te oferecer os
  horários reais. Qual dia e turno?'

Origem: lead 24034205 (Fábio Philipe teste interno) onde Lia cobrou
R\$ 305,50 sem nunca ter oferecido slot concreto.

5/5 testes manuais OK."

git push "$AUTH_URL" main
git remote set-url origin "$CLEAN_URL" 2>/dev/null || true

echo ""
echo "✅ PUSH CONCLUÍDO! Easypanel redeploya em ~1 min."
