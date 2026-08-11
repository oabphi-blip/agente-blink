# Lia interferiu em atendimento humano — janela temporal sobrepôs ATIVADO IA?

> **Data:** 29/05/2026
> **Lead:** 24038117 (Talita)
> **Commit:** `b1d1a27`

## Sintoma
Kommo marcou "Agentes IA desativados" às 11:16. Uma atendente humana assumiu e
respondeu a paciente. **5h depois** (16:24 e 17:20) a Lia voltou a disparar
mensagem de fallback "instabilidade", interferindo no atendimento humano em
andamento — paciente recebia ruído de robô enquanto a humana cuidava dela.

## Causa raiz
`agent_paused_for_lead` só verificava `recent_human_handoff`, que usa uma
**janela temporal** (`window_min=30 min`). Passados 30 min, o código considerava
que o handoff "expirou" e **liberava a Lia de volta** — mesmo com o campo
`ATIVADO IA?` do Kommo ainda DESATIVADO. A fonte de verdade permanente foi
ignorada em favor de um timer.

## Fix
`voice_agent/kommo.py`:

1. Verifica `known.ativado_ia` **ANTES** da janela temporal.
2. Se `DESATIVADO` (qualquer case) → retorna `'ia-desativada-manual'`.
3. Silêncio **permanente** até alguém marcar ATIVADO manualmente no Kommo.

Princípio: handoff humano é estado permanente, não evento com TTL. Janela
temporal nunca pode sobrepor a flag explícita do Kommo.

## Cenário pytest
Já cobertos em `tests/test_filtros_lia.py` — `TestIaDesativadaManual` (4 cenários):
- `Desativado` → pausa
- `DESATIVADO` uppercase → pausa
- `Ativado` → deixa responder
- vazio → deixa responder

(61 testes passando no total à época: 57 anteriores + 4 novos.)

## Tags
`bug-fix` `kommo` `handoff-humano` `ativado-ia` `critico` `interferencia`
