# Bug C-26 — Protocolo desmarcação: investigar motivo ANTES de oferecer encaixe

**Data:** 12/06/2026
**Commit:** 3c4e31b `fix(bug-c26): protocolo desmarcação - investigar motivo antes de encaixe`
**Casos reais:** Sophia 23845330 (TJDFT, bebê) · Tito / Aline Weber 24130572 (particular)

## Sintoma
Quando o paciente sinalizou que ia desmarcar, Lia ofereceu "remarcar imediato" /
"deixa eu te mostrar outras opções de data". Isso viola o protocolo da clínica: oferta
de remarcação imediata passa a percepção de "é fácil desmarcar e marcar de novo" →
vira no-show comportamental.

## Causa raiz
Não havia passo de **investigação do motivo** antes do encaixe. Lia pulava direto pra
agenda. Faltava bifurcar a resposta por fluxo (COM convênio × SEM convênio) e por ramo
(imprevisto / autorização-financeiro / sem interesse / urgência).

## Fix — Regra E1.7 reescrita no `_MASTER_INSTRUCTION.md`

**PASSO 1 — Mensagem-gatilho personalizada:**
- COM convênio: a pergunta menciona `{nome_convenio}` explicitamente.
- SEM convênio: a pergunta menciona "questão financeira" explicitamente.

**PASSO 2 — Classificar a resposta em 4 ramos por fluxo:**

COM CONVÊNIO:
- Imprevisto → 2.LEADS FRIO + A FAZER=Encaixe + IA Off
- Autorização → 1-ATENDIMENTO HUMANO + IA Off
- Sem interesse → Closed-lost + IA Off
- Sintoma / urgência → 1-ATENDIMENTO HUMANO + Urgente + IA Off

SEM CONVÊNIO (particular):
- Imprevisto → 2.LEADS FRIO + Encaixe + IA Off
- Financeiro → escada 3 turnos (2x R$ 335 → sábado família R$ 511 → fila incentivo)
- Sem interesse → Closed-lost + IA Off
- Urgência → 1-ATENDIMENTO HUMANO + Urgente + IA Off

**7 frases PROIBIDAS:** "antes de cancelar", "tenho disponibilidade em outros dias",
"talvez consiga encaixar", "prefere que eu te mostre outras opções de data", "quer ver
a agenda", "deixa eu reconsultar a agenda real", "vou te mostrar opções".

**Anti-loop:** se o paciente não responder a pergunta de motivo em 1 turno, Lia segue
pro encaixe genérico sem repetir a pergunta.

`template_texts.py::PROXIMOS_PASSOS` atualizado pra nota Kommo refletir os 2 fluxos.

## Cenário pytest
`tests/test_bug_c26_desmarcacao_motivo.py` — 10 cenários verdes (fluxos COM/SEM, frases
proibidas, escada financeira, 4 ramos por fluxo, ações Kommo concretas, anti-loop, casos
reais Sophia e Tito).

## Tags
#desmarcacao #no-show #protocolo-clinica #encaixe #convenio #particular #E1.7
