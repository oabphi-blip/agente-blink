# Bug Kommo — campo "ATIVADO IA?" recriado, ID antigo morto (falta de resposta)

> **Data:** 02/06/2026 (tarde)
> **Lead exemplo:** 24064359 (Ana Caroline) — sem resposta há 2h
> **Commit fix:** `3adb920` fix(kommo) · doc `44b5454` (lição 11-I)

## Sintoma
"Muitos casos de falta de resposta" reportado pelo Fábio. Equipe humana perdeu
visibilidade de IA on/off por lead. Bug tipo Elisa acumulando invisivelmente.

## Causa raiz
O campo `ATIVADO IA?` foi RECRIADO no Kommo. O ID antigo (1260635, hardcoded em
`kommo.py::FIELD_ATIVADO_IA`) deixou de existir na API. ID atual é **1260817**.
O pipeline write turn-by-turn (webhook.py:2985+3080, pipeline.py:622,
reactivation.py:428) seguia gravando no ID morto — **fail silently**.

## Fix
`voice_agent/kommo.py`:
```python
FIELD_ATIVADO_IA = (1260817, {
    "ATIVADO": 927031, "ATIVA": 927031, "ATIVO": 927031, "ON": 927031,
    "SOLICITADO": 927033, "SOLICITAR": 927033, "PENDENTE": 927033,
    "DESATIVADO": 927035, "DESATIVADA": 927035, "OFF": 927035,
})
```
Type confirmado: `select` (era `multiselect` no comentário antigo).

## Como descobrir ID de campo Kommo deletado/renovado
1. Abrir lead no Kommo via Chrome.
2. Console JS: `document.querySelectorAll('[class*=linked-form__field]').forEach(e => console.log(e.getAttribute('data-id'), e.textContent.substring(0,50)))`
3. Confirmar via `GET /api/v4/leads/custom_fields/{id}` (JSON completo do campo).

## Lição de processo
Quando código usa `FIELD_X = (id, enums)` hardcoded, monitorar com
`/admin/healthz` se o ID ainda existe na API custom_fields. Se Kommo retornar
404 no field_id, ALERTAR no Slack — código está gravando em buraco.

## Cenário pytest
- Mock custom_fields sem 1260635 → healthz detecta field órfão e alerta.
- Write turn-by-turn usa 1260817 com enum SOLICITADO=927033.

## Tags
`bug-fix` `kommo` `custom-fields` `field-id-orfao` `fail-silently` `falta-de-resposta` `monitoramento`
