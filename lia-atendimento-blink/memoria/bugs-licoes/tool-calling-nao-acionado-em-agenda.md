# Bug central — Lia escreve "vou consultar" mas NÃO chama a tool (state=AGENDA)

> **Data:** 02/06/2026 (tarde)
> **Leads:** 21392947 (Sabrina), 24064723 (Kamila), 24065257 (Janeide), 21344999 (Iara), 24065595 (Ben Hur 2), 22345722 (Keyla) — 6 casos na mesma tarde
> **Commit fix:** `2000e19` feat(tool-choice) · doc `b025af7` (lição 11-L)

## Sintoma
Quando a state machine entra no estado AGENDA, a Lia escreve em texto livre
("Deixa eu consultar a agenda real", "Vou buscar os horários", "Me dá um
minutinho que volto com as opções concretas", "Ainda estou buscando os
horários") e **nunca volta com os horários reais**. Paciente espera 2-30 min,
depois um humano (Stephany/Ariany) intervém manualmente. Todos os 6 leads
tinham agenda Medware EXISTENTE (Sabrina 7+ slots, Keyla 3 slots Águas Claras,
Iara 8 slots, etc.).

## Causa raiz
Mesmo com `LIA_TOOLS_ENABLED=1` no Easypanel, o modelo Sonnet **não estava
chamando** as tools de `tools_lia.py` (`oferecer_slot`, `gravar_agendamento`).
`responder.py::messages.create()` provavelmente não estava passando o parâmetro
`tools=[...]` quando `state == AGENDA`. Sem `tools` no request à API Anthropic, o
modelo não tem como chamar — só pode escrever texto livre. É a mesma família do
bug Juliene (24053159) que motivou `_viola_promete_retorno_humano`, mas
arquitetural: a defesa real é forçar a tool, não filtrar a frase depois.

## Fix
`voice_agent/responder.py`, no método que monta `messages.create()`:
- Detectar `ctx.state == "AGENDA"` e adicionar `tools = [TOOL_OFERECER_SLOT,
  TOOL_GRAVAR_AGENDAMENTO]`.
- `tool_choice = {"type": "tool", "name": "oferecer_slot"}` quando `ctx.get("agenda")`
  existe — força o modelo a chamar em vez de escrever texto livre.
- Processar `response.stop_reason == "tool_use"`, executar a tool real, e a
  resposta humana vira um wrap do resultado da tool. Modelo não pode inventar
  data/dia/hora.

## Cenário pytest
- `state=AGENDA` + `ctx.agenda` com slots → `messages.create()` recebe `tools` e
  `tool_choice="oferecer_slot"` → resposta contém slots REAIS, zero invenção.
- `state=AGENDA` sem agenda → modelo não promete "vou consultar"; reconsulta.
- Regressão dos 6 leads acima: nenhuma resposta com "vou buscar/consultar" sem
  tool chamada.

## Tags
`bug-fix` `tool-calling` `responder` `state-machine` `agenda` `critico` `recidiva-juliene`
