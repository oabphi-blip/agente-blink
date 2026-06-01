# Kommo custom_fields=[] — um campo órfão derruba o PATCH inteiro

> **Data:** 30/05/2026
> **Leads afetados:** 24045059 (João Carlos, ceratocone), 24046851 (Carlos
> Oliveira, catarata) e dezenas de outros leads do dia.
> **Commits:** `40f6cea`, `5762c7c`, `cef66b4` (self-healing) + diagnóstico
> `9cc6c1e` /admin/force-resync, `cb1a910` /admin/dry-sync, `4ea754e` /admin/debug-extract.

## Sintoma
Lia conversava perfeito, o extrator extraía 12+ campos, mas o painel do Kommo
mostrava `custom_fields=[]` (vazio) no lead. Nenhum dado salvo, silenciosamente.

## Causa raiz
Os field_ids `1260635` (ATIVADO_IA) e `1260639` (HORA_ATIVACAO) **não existem
mais no Kommo** — foram deletados no Admin. Enviá-los no `PATCH /leads/{id}`
faz o Kommo retornar **HTTP 400 NotSupportedChoice**, e o Kommo **descarta o
PATCH inteiro**: nenhum dos outros 13 campos válidos é salvo. Um único campo
órfão (ou enum órfão como ATENDENTE/Lia multiselect) envenena toda a gravação.

Antipadrão clássico: hardcode de field_id sem validar contra o schema real do
Kommo. Quando o campo é deletado no Admin, o código não sabe e continua enviando.

## Fix
`voice_agent/kommo.py`:

1. **Imediato** (`40f6cea`, `5762c7c`): desativou envio de ATIVADO_IA,
   HORA_ATIVACAO e do multiselect ATENDENTE — desbloqueou os 11 campos válidos.

2. **Arquitetural self-healing** (`cef66b4`): `KommoClient` agora detecta
   `NotSupportedChoice` na resposta, extrai qual *position* do array foi
   rejeitada, marca aquele field_id como DEAD em `_KOMMO_DEAD_FIELD_IDS`
   (set class-level) e **retenta o PATCH SEM esse campo**. Até 4 retries pra
   cobrir múltiplos campos órfãos. A blacklist persiste pela vida do container,
   então chamadas seguintes pulam os campos mortos antes de tentar — sem precisar
   redeploy quando um campo é deletado no Kommo.

3. **Visibilidade**: `GET /admin/schema-check` lista os field_ids blacklistados
   pra equipe.

## Cenário pytest
Já cobertos em `tests/test_kommo_auto_skip.py` (5 cenários, todos passando):
- 1 campo órfão → blacklist + retry sucede
- Blacklist persiste — chamada seguinte pula sozinha
- 2 campos órfãos em sequência — 3 tentativas
- Erro 400 sem validation-errors → não entra em loop
- cfs vazio após skip total → retorna True sem PATCH

## Pendência arquitetural (não fechar como resolvido)
**Task #71**: schema-on-startup que ABORTA o boot se um field_id hardcoded não
existe no Kommo. O self-healing trata o sintoma em runtime; o ideal é falhar
cedo no deploy. Pra reativar ATIVADO_IA/HORA_ATIVACAO: recriar os campos no
Kommo Admin e atualizar field_ids + enums em `kommo.py`.

## Tags
`bug-fix` `kommo` `custom-fields` `self-healing` `schema-drift` `silencioso`
