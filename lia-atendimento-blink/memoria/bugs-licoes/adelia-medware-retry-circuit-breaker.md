# Bug Adélia — Lia copiou exemplo literal do prompt + Medware silencioso

> **Data:** 01/06/2026
> **Lead:** 24056883 (Adélia Alexandra Vaz) — STF-Med, Asa Norte, rotina, quarta manhã
> **Commit fix:** `f0efe06`

## Sintoma
Paciente passou triagem completa, mas a Lia copiou LITERALMENTE o "exemplo
aprovado" do bloco AGENDA INDISPONÍVEL do prompt — "Deixa eu reconsultar a
agenda real aqui pra você. Me responde 'oi' em 1 minuto..." — porque
`ctx[agenda]` chegou vazio (mesmo bug Medware silencioso do caso Juliene).
Validação: o Medware TINHA 3 slots reais para Karla / Asa Norte / STF-Med na
faixa pedida (10/06 09:30, 12/06 08:30, 17/06 10:00) — só não respondeu na hora.
Além disso, o campo 1.EXAMES/Grupo nunca era preenchido (o
`selecionar_agrupador` só rodava no `agendamento.salvar`, que muitas vezes não
chega).

## Causa raiz
1. Medware respondeu vazio por instabilidade transitória, sem retry.
2. O prompt continha uma frase literal copiável — o LLM reproduziu palavra por
   palavra em vez de reconsultar.
3. `selecionar_agrupador` dependia do salvamento Medware, que não acontece em
   leads ainda "em conversa".

## Fix
`f0efe06` — 4 fixes:
1. **Retry no Medware** (`medware.py horarios_para_agente`): 3 tentativas, backoff
   0.5s→1s→2s; retry em resposta vazia OU exception; médico não mapeado retorna
   `[]` direto sem retry.
2. **Circuit breaker** (`pipeline.py`): contador Redis
   `blink:agenda_vazia_seq:{convo}` TTL 30min; após 3 `ctx[agenda]=[]`
   consecutivos → `caller_context['escalonar_humano_medware_off']=True`; sucesso
   zera o contador.
3. **Agrupador early** (`pipeline.py` + `procedimentos.py`): quando perfil +
   motivo estão no ctx, chama `selecionar_agrupador` imediatamente e grava
   1.MOTIVO + 1.EXAMES via thread daemon (não bloqueia).
4. **Prompt sem exemplo literal** (`responder.py _agenda_block`): removido
   "Exemplo aprovado:"; substituído por guideline "use SUAS PRÓPRIAS PALAVRAS",
   "DIVERSIFIQUE as palavras a cada conversa".

## Cenário pytest
`tests/test_medware_retry_e_breaker.py` — 13 casos novos. 709 verdes. Bug Adélia
e bug Juliene blindados.

## Nota de ativação
Fábio recomendou ligar `LIA_TOOLS_ENABLED=1` no Easypanel — tool calling
estruturado substitui o detector Haiku semântico por chamadas atômicas.

## Tags
`bug-fix` `medware` `agenda-vazia` `retry` `circuit-breaker` `prompt-literal`
`agrupador` `critico` `recidiva-juliene`
