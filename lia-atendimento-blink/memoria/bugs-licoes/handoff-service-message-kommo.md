# Bug handoff — Lia respondeu por cima do humano (gate só via etapa)

> **Data:** 01/06/2026
> **Detectado por:** Fábio
> **Commit fix:** `4ec7a7c`

## Sintoma
Lia respondeu POR CIMA da mensagem de um atendente humano. Quando o atendente
escreve no chat SEM mover o lead para a etapa humana, a Lia ignorava e
respondia junto.

## Causa raiz
Em 29/05/2026 o gate `agent_paused_for_lead` foi simplificado para usar SÓ
`ST_AGENT_OFF` (etapa-humana):

```python
if caller_context.get('status_id') in ST_AGENT_OFF:
    return 'etapa-humana'
return None
```

O sinal `service_message` automático do Kommo ("🛑 Agentes de IA foram
desativados neste chat"), que aparece quando o humano escreve manualmente, sempre
existiu mas não era usado pelo gate principal.

> Distinto da lição `lia-interfere-handoff-humano.md` (Talita, janela temporal vs
> ATIVADO IA). Aqui o problema é o gate ignorar o service_message.

## Fix
`voice_agent/kommo.py` — gate com DUAS regras (OR):
1. `status_id in ST_AGENT_OFF` → `'etapa-humana'` (sem custo extra).
2. `ia_status_from_notes(lead_id) == 'DESATIVADO'` → `'humano-escreveu-no-chat'`
   (captura o service_message automático do Kommo).

Trade-off: +200–500ms por `GET /leads/{id}/notes`. Aceito — custo de falar por
cima é maior. Etapa-humana tem precedência (evita a chamada extra de notes).
Exception silenciosa não derruba o gate (degrada graciosa).

## Cenário pytest
`tests/test_kommo_handoff_humano.py` — 10 casos. Sentinela adicional: cenário C6
"evita-falar-fora-tempo" em `smoke_continuous.py`. 696 verdes.

## Tags
`bug-fix` `kommo` `handoff-humano` `service-message` `gate` `critico`
`interferencia`
