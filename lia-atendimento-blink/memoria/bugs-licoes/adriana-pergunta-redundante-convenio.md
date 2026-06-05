# Bug Adriana — Lia repergunta convênio que já está no ctx (4 turnos de enrolação)

> **Data:** 02/06/2026
> **Lead:** 24063769 (Adriana)
> **Commit fix:** `24e12ad` fix(adriana)+ci · doc `0aef236` (lição 11-F)

## Sintoma
Paciente perguntou o valor. Lia fez 4 turnos pedindo "com ou sem convênio?"
quando `ctx.known.convenio = "Não se aplica"` já estava no Kommo. A triagem
ignorou o ctx e enrolou em vez de responder o valor direto.

## Causa raiz
O fluxo de valor não consultava `ctx.known.convenio` antes de reperguntar.
Sem artigo KB de valores oficiais, o modelo "jogava pra cima" perguntando
convênio repetidamente.

## Fix
- Artigo KB `voice_agent/knowledge_base/39_valores_consulta.md` — tabela oficial
  R$ 611 Karla / R$ 297 Fabrício catarata / R$ 800 SDP.
- Filtro `_viola_pergunta_redundante_convenio(text, ctx)` em `responder.py`:
  regex detecta "com ou sem convênio" + ctx tem convenio → substitui.
- `_gerar_resposta_valor_sem_repergunta(ctx)`: usa ctx (médico + especialidade +
  convênio) pra responder com R$ direto, sem repergunta. Convênio aceito =
  "coberta pelo seu plano". Particular = R$ exato + Pix.

## Cenário pytest
`tests/test_pergunta_redundante_convenio.py` — 13 testes.
- ctx.convenio="Não se aplica" + Lia escreve "com ou sem convênio" → substitui
  por valor particular direto.
- ctx.convenio="Amil" → "coberta pelo seu plano", sem repergunta.

## Tags
`bug-fix` `responder` `convenio` `pergunta-redundante` `valores` `kb` `filtro-pos-geracao`
