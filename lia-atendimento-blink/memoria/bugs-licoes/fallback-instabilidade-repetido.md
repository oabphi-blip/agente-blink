# Bug fallback instabilidade repetido 3x — Claude API caiu, Lia mandou mesmo erro 3x

**Lead**: 24037253
**Data**: 28/05/2026
**Commit fix**: `1143504`

## Sintoma
Paciente recebeu 3 vezes em 1 hora a mesma mensagem:
> "Oi! Tivemos uma instabilidade rápida por aqui 🙏 Já voltei — me conta de novo como posso te ajudar?"

22:06, 22:15, 23:00 — todas idênticas. Lia parecia robô quebrado.

## Causa raiz
1. Crédito Anthropic API esgotando (faturas confirmam ~US$25 abastecidos esgotaram).
2. `webhook.py` linha 565-582 tem fallback genérico após 3 tentativas falhas — SEM dedup.
3. Cada nova mensagem do paciente disparava nova chamada Claude → falhava → fallback de novo.

## Fix em webhook.py (commit 1143504)
Antes de enviar o fallback, checa Redis `blink:fallback:instab:{convo_key}`:
- Se já enviou nos últimos 30 min → SUPRIME (silêncio é melhor que robô quebrado)
- Se não → envia e marca Redis com TTL 30 min

```python
_fallback_key = f"blink:fallback:instab:{convo_key}"
if _redis.exists(_fallback_key):
    log.warning("fallback suprimido (já enviado nos últimos 30 min)")
    return
_redis.set(_fallback_key, "1", ex=1800)
```

## Aprendizado meta
- Crédito Anthropic precisa ter **auto-recharge ligado** em console.anthropic.com/settings/billing
- Idealmente: monitor que alerta Slack quando saldo < US$10
- Fallbacks NUNCA devem ser repetidos sem dedup

## Cenário pra pytest
- Mock: Claude API falha sempre
- Paciente manda 3 msgs em 30 min
- Só recebe 1 fallback; as outras 2 são silenciadas

## Tags
`bug-fix` `api-falha` `credito-anthropic` `dedup`
