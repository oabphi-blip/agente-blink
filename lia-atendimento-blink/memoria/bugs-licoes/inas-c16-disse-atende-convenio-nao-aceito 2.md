# Bug C-16 (Inas) — Lia disse "atendemos" um convênio NÃO aceito

> **Data:** 09/06/2026
> **Leads:** Tatiana 24125064 · Maria Agostini 24117314 · Juliene 24053159
> **Commit fix:** `885ddf0` feat: pacote autônomo + Bug C-16 Inas · `b30f07e` fix(C-16)
> **Indexado por:** Agente Guardião (execução diária)

## Sintoma
Lia afirmou que a Blink atende o convênio Inas (GDF) quando na verdade NÃO atende
(KB art. 18). Paciente recebeu informação errada e seguiu o fluxo de agendamento
como se tivesse cobertura.

## Causa raiz
Não havia checagem programática cruzando a fala da Lia ("atendemos / aceitamos
seu plano") contra a allowlist real de convênios. O modelo generalizava
"atendemos seu convênio" sem validar contra os 26 convênios mapeados + exclusões
(Inas, GDF, Cassi, SulAmerica, Bradesco).

## Fix
- `voice_agent/validador_factual.py` — cruza preço/data/convênio com KB 17/18/19.
- `voice_agent/responder.py` — filtro `_viola_disse_atende_convenio_nao_aceito`:
  detecta afirmação de cobertura + convênio fora da allowlist → substitui por
  resposta honesta de que o plano não é aceito + opção particular.
- `voice_agent/kommo.py` — `list_recent_notes` + `search_leads_by_window` pra
  auditoria.

## Cenário pytest
74 testes verdes no pacote (engineer 18 + validador 12 + bug C-16 34 + kommo 10).
- Lia escreve "atendemos Inas" + convênio="Inas GDf" → filtro substitui por
  honestidade ("esse plano não é aceito").

## Tags
`bug-fix` `responder` `convenio` `inas` `validador-factual` `allowlist` `bug-c16`
