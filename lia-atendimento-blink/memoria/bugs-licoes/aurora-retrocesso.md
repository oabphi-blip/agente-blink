# Bug Aurora — retrocesso "qual dia da semana" tendo agendamento

**Lead**: 23907418 (Aurora)
**Data**: maio/2026
**Commit fix**: `118d643`

## Sintoma
Aurora já tinha consulta marcada (campo `1.DIA CONSULTA` populado), mas Lia continuava perguntando "qual dia da semana funciona melhor pra você?" como se fosse novo agendamento.

## Causa raiz
`ja_agendado=True` em `kommo.py` dependia SÓ do `status_id`. Aurora estava em **2-AGENDAR** porque o atendente ainda não tinha movido o card, mas `1.DIA CONSULTA` já tinha timestamp de hoje. Lia ignorava esse campo.

## Fix
`voice_agent/kommo.py`:

```python
FIELD_DIA_CONSULTA_1 = 1255723

# Em get_caller_context_by_lead:
ja_agendado_by_status = sid in ST_JA_AGENDADO
ja_agendado_by_consulta = False
for cf in (data.get("custom_fields_values") or []):
    if cf.get("field_id") == FIELD_DIA_CONSULTA_1:
        vals = cf.get("values") or []
        if vals and vals[0].get("value"):
            ts = int(vals[0]["value"])
            if ts > time.time() - 86400:  # hoje ou futuro
                ja_agendado_by_consulta = True
out["ja_agendado"] = ja_agendado_by_status or ja_agendado_by_consulta
```

## Cenário pra pytest
- lead com status_id=2-AGENDAR mas `1.DIA CONSULTA`=hoje → `ja_agendado=True`
- Lia NÃO oferece novo slot

## Tags
`bug-fix` `agendamento` `caller-context`
