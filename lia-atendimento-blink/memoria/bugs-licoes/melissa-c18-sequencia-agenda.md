# Bug C-18 (Melissa) — Lia pergunta turno+período ANTES de ofertar slot

> **Data:** 10/06/2026
> **Lead:** 22779280 (Melissa de Almeida Ramos)
> **Commit fix:** `489328a` fix(prompt): Bug C-18 sequência agenda
> **Indexado por:** Agente Guardião (execução diária)

## Sintoma
Paciente sugeriu "semana de 29/06". Em vez de buscar a agenda real da Dra. Karla
(Asa Norte, 31 horários reais na semana) e oferecer 2 imediatamente, a Lia ignorou
e perguntou "qual médico? qual unidade? qual motivo?" — empurrando carga decisória
pro paciente e ficando "indo e vindo sem definição".

## Causa raiz
O `_agenda_block` em `responder.py` não tinha a sequência obrigatória explícita.
O modelo, em estado AGENDA, escolhia perguntar preferências antes de mostrar
qualquer horário concreto. Anti-padrão: 3 perguntas (dia → turno → período) em 3
turnos separados, sobrecarregando o paciente.

## Fix
Regra sequencial obrigatória escrita no `_agenda_block`:
- **PASSO 1:** ofertar 2 horários concretos imediatamente (1 manhã + 1 tarde do dia
  mais próximo da preferência).
- **PASSO 2:** só se o paciente recusar os 2 OU pedir dia/hora fora da oferta,
  perguntar JUNTOS numa só mensagem dia da semana + turno + período, já
  contextualizado com {{MÉDICO}} e {{UNIDADE}}.
- **PASSO 3:** com a resposta, escolher 2 novos horários que casem.

Objetivo: AGILIDADE, não "indo e vindo sem definição".

## Cenário pytest
`tests/test_bug_c18_sequencia_agenda.py` — 5 cenários verde.
- PASSO 1→2→3 + anti-padrão "indo e vindo".

## Tags
`bug-fix` `responder` `agenda` `sequencia-slots` `prompt` `agilidade` `bug-c18`
