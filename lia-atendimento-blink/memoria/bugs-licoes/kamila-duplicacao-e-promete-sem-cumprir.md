# Bug Kamila — 3 bugs simultâneos (duplicação + ignora humano + promete sem cumprir)

> **Data:** 02/06/2026 11:24 BRT
> **Lead:** 24064723 (Kamila)
> **Commits fix:** `a37ffb8` (dedup outbound + promete sem cumprir SEMPRE ON), `e6613fc` (`_viola_promete_retorno_humano` SEMPRE ON de novo)

## Cenário
- 11:21 Stephany (humana) mandou template "Com base em suas preferências...
  10/06 09:30 ou 24/06 10:00. Escolha uma opção!"
- 11:23 Kamila respondeu: "3"
- 11:24 Lia mandou DUAS mensagens IDÊNTICAS sequenciais: "Kamila, ainda estou
  buscando os horários disponíveis para quarta-feira de manhã com a Dra. Karla
  na Asa Norte. Aguarda só mais um pouquinho..."
- 11:24 Ariany moveu pra 1-ATENDIMENTO HUMANO.

## Causa raiz
- **Bug 1 — ignorou intervenção humana:** Stephany já tinha enviado horários
  reais. A camada de detecção "humano enviou template oferta" não pegou o
  formato com emoji 1️⃣ 2️⃣.
- **Bug 2 — duplicação:** mesma mensagem 2x em <1s. Cada inbound disparou um
  turn e ambos geraram a mesma resposta sem checar idempotência (falta lock por
  conversa — ver `rajada-sem-lock-pipeline.md`).
- **Bug 3 — "ainda estou buscando" sem ter buscado:** promessa de retorno sem
  chamar Medware. Mesmo padrão do bug Juliene (24053159). O filtro
  `_viola_promete_retorno_humano` estava DESLIGADO desde `796ba2a`
  (FILTROS_LEGACY=0).

## Fix
- `a37ffb8`: dedup de OUTBOUND por hash + `_viola_promete_retorno_humano` SEMPRE
  ON. `e6613fc`: reforço (filtro voltou a ON depois de um revert `8fcf55b`).
- **Lição:** desligar TODOS os filtros legacy sem ter tool calling efetivo ainda
  foi prematuro. Sem tools, Lia volta a "prometer e não cumprir" que o filtro
  evitava. (Conectado ao fix `2000e19` / `tool-calling-nao-acionado-em-agenda.md`.)

## Próximas ações (não imediato)
1. Detectar template emoji 1️⃣ 2️⃣ humano antes de gerar resposta (camada 6 ja_handoff).
2. Dedup forte por hash da resposta + conversation_key + 5s.
3. Confirmar tool calling efetivamente ativo em prod (`LIA_TOOLS_ENABLED=1`).

## Cenário pytest
- Humano enviou template com 1️⃣ 2️⃣ → Lia NÃO gera resposta concorrente (handoff).
- Lia gera "ainda estou buscando" sem tool chamada → filtro substitui.
- Mesma resposta 2x <5s mesma conv_key → segunda é descartada (dedup outbound).

## Tags
`bug-fix` `responder` `dedup` `handoff-humano` `promete-sem-cumprir` `filtro-legacy` `critico` `recidiva-juliene`
