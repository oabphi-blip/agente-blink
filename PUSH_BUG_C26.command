#!/bin/bash
# Push Bug C-26 — desmarcação protocolo da clínica
# 2 fluxos diferenciados (COM convênio vs SEM convênio) + matriz 4 ramos cada
# + frases proibidas + anti-loop. pytest 10/10 verde.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Bug C-26 — protocolo desmarcação (Fábio 12/06)"
echo "==============================================="

git add voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        voice_agent/template_texts.py \
        tests/test_bug_c26_desmarcacao_motivo.py \
        PUSH_BUG_C26.command
git commit -m "fix(bug-c26): protocolo desmarcação - investigar motivo antes de encaixe

Origem: Fábio 12/06/2026, leads Sophia 23845330 (TJDFT, bebê) e
Tito/Aline Weber 24130572 (particular). Lia ofereceu 'remarcar
imediato' violando protocolo da clínica que diz: oferta de
remarcação imediata passa percepção de 'fácil desmarcar e marcar
de novo' → vira no-show comportamental.

Regra E1.7 reescrita no _MASTER_INSTRUCTION.md:

PASSO 1 — Mensagem-gatilho personalizada:
  • COM convênio: pergunta menciona {nome_convenio} explicitamente
  • SEM convênio: pergunta menciona 'questão financeira' explicitamente

PASSO 2 — Classificar resposta em 4 ramos por fluxo:
  COM CONVÊNIO:
    - Imprevisto → 2.LEADS FRIO + A FAZER=Encaixe + IA Off
    - Autorização → 1-ATENDIMENTO HUMANO + IA Off
    - Sem interesse → Closed-lost + IA Off
    - Sintoma/urgência → 1-ATENDIMENTO HUMANO + Urgente + IA Off
  SEM CONVÊNIO (particular):
    - Imprevisto → 2.LEADS FRIO + Encaixe + IA Off
    - Financeiro → escada 3 turnos (2x R\$ 335 → sábado família
      R\$ 511 → fila incentivo)
    - Sem interesse → Closed-lost + IA Off
    - Urgência → 1-ATENDIMENTO HUMANO + Urgente + IA Off

7 frases proibidas listadas explicitamente: 'antes de cancelar',
'tenho disponibilidade em outros dias', 'talvez consiga encaixar',
'prefere que eu te mostre outras opções de data', 'quer ver a
agenda', 'deixa eu reconsultar a agenda real', 'vou te mostrar
opções'.

Anti-loop: se paciente não responder pergunta de motivo em 1 turno,
Lia segue pro encaixe genérico sem repetir pergunta.

template_texts.py PROXIMOS_PASSOS atualizado pra nota Kommo refletir
os 2 fluxos completos.

Pytest tests/test_bug_c26_desmarcacao_motivo.py — 10 cenários, todos
verdes (fluxos COM/SEM, frases proibidas, escada financeira, ramos
4 por fluxo, ações Kommo concretas, anti-loop, casos reais Sophia
e Tito)." || echo "  (nada novo)"
git push origin main 2>&1 | tail -5

echo ""
echo "✓ Push completo. Deploy Easypanel ~3 min."
echo ""
echo "Impacto:"
echo "  • Lia daqui pra frente NÃO oferece remarcação imediata"
echo "  • Pergunta motivo PRIMEIRO, depois classifica em 4 ramos"
echo "  • Fluxo diferente pra paciente com vs sem convênio"
echo "  • Atendente humano vê fluxo completo na nota Kommo"
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
