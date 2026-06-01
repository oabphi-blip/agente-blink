# Bug Diones — médico trocado + envenenamento de contexto

> **Data:** 01/06/2026 (~16h)
> **Lead:** 23742328 (Diones Alves Santos) — estava em 5-AGENDADO, 1.DIA CONSULTA preenchido
> **Commits fix:** `71beaa0` + `e4b157a`

## Sintoma
4 bugs combinados na mesma conversa:
1. Lia ofereceu Dr. Fabrício quando o ctx tinha "Médico: Dra. Karla".
2. Ofereceu segunda quando o paciente queria quarta (preferência ignorada).
3. Filtro `_viola_cobranca_antes_slot` disparou em mensagem legítima do paciente.
4. Lia disse "Karla atende terças e quintas" (invenção de dias fixos).

Além disso o lead estava em 5-AGENDADO com 1.DIA CONSULTA preenchido — deveria
estar em MODO CONFIRMAÇÃO, mas a Lia seguiu agendando do zero.

## Causa raiz
Dois problemas distintos:

**A) ST_JA_AGENDADO incompleto** — faltava o status `106653499` (7.CONFIRMADO).
Leads nesse status não disparavam `ja_agendado=True`.

**B) Loop de envenenamento de contexto** — `extract_lead_fields` é semântico:
pega o que aparece no histórico. Quando a Lia **alucina** um campo crítico
(médico/unidade/convênio), o texto que ela mesma escreveu vira input do
`extract` no próximo turn, que detecta como "campo presente" e grava no Kommo,
sobrescrevendo o valor correto. A partir daí a TRAVA MÉDICO/UNIDADE passa a
defender o valor errado.

## Fix
**`71beaa0`:**
- `voice_agent/kommo.py` — `ST_JA_AGENDADO` completo (adicionado 106653499).
- `voice_agent/responder.py` — bloco "TRAVA MÉDICO/UNIDADE — FONTE DE VERDADE"
  injetado no system prompt quando ctx tem `known.medico` ou `known.unidade`
  (lista campos travados, "NÃO trocar" explícito, proíbe inventar dias fixos).
- `voice_agent/responder.py` — filtro `_viola_medico_trocado`: se
  `ctx.known.medico='karla'` mas a resposta menciona "fabricio" sem "karla"
  (ou vice-versa) → substitui por `_MEDICO_TROCADO_FALLBACK` pedindo confirmação.

**`e4b157a` (anti-envenenamento):**
- `voice_agent/pipeline.py` `_sync_kommo_safely` (~linha 643): antes de
  `update_lead_fields`, para cada campo em (medico, unidade, convenio), se o ctx
  JÁ TEM valor E `fields` traz outro → remove o campo (NÃO sobrescreve) e loga
  `[ANTI-ENVENENAMENTO]`. Comparação case-insensitive. Atendente humano segue
  podendo alterar manualmente no Kommo (não passa por `_sync_kommo_safely`).

## Cenário pytest
- `tests/test_diones_medico_trocado.py` — 14 casos (ST_JA_AGENDADO, TRAVA
  MÉDICO/UNIDADE, filtro médico trocado). 723 verdes.
- `tests/test_pipeline_anti_envenenamento.py` — 8 casos. 731 verdes.

## Tags
`bug-fix` `responder` `pipeline` `kommo` `ja-agendado` `medico-trocado`
`envenenamento-contexto` `critico`
