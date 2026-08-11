# Controle de Silêncio da Lia — APENAS POR ETAPA

> Decisão Fábio em 29/05/2026 (commit `d7314fa`). Esta é a fonte de
> verdade do comportamento atual. Substitui qualquer doc anterior que
> mencione campo ATIVADO IA? ou janela handoff como sinal de silêncio.

## Regra única

A Lia fica em SILÊNCIO quando, e apenas quando, o lead no Kommo está
em uma das **etapas humanas** do funil ATENDE (pipeline 8601819):

| Etapa | status_id | Quando atendente humano cuida |
|---|---|---|
| 7-CIRURGIAS | (em ST_AGENT_OFF) | Cirurgia agendada / pós-op |
| 8-LENTES | (em ST_AGENT_OFF) | Avaliação de lentes especiais |
| 9-FORNECEDORES | (em ST_AGENT_OFF) | Contato com fornecedor |

Quando o lead está em qualquer outra etapa, a Lia responde normalmente.

## O que NÃO controla mais o silêncio

Removidos os 2 sinais antigos:

- ❌ **Campo `ATIVADO IA?`** — IGNORADO. Mesmo que esteja "Desativado",
  se a etapa for normal, Lia responde.
- ❌ **Janela handoff temporal de 30 min** — REMOVIDA. Antes, se humano
  respondia, Lia ficava 30 min em silêncio depois voltava. Agora não.

## Operação humana exigida

Pra esse modelo funcionar, atendente humano TEM QUE:

1. **Mover lead pra etapa humana** ao assumir o atendimento
2. **Mover lead de volta** pra etapa normal quando terminar

Sem essa disciplina, Lia responde em paralelo no chat = bug.

### Recomendação: regra Salesbot Kommo

Pra eliminar a chance de esquecimento, configurar no Salesbot Kommo:

> Gatilho: "Atendente humano respondeu no chat do lead"
> Ação: "Mover lead para etapa humana (ex: 0-HUMANO)"

Assim o movimento é automático e a Lia silencia sozinha.

## Origem da decisão

Lead **24038117** (Talita, 29/05/2026) foi atendido por humano (Rafaela
Rodrigues) às 11:16. Kommo marcou "🛑 Agentes IA desativados". Lia
voltou a responder fallback de instabilidade às 16:24 e 17:20 (5h+
depois). Causa: 3 sinais redundantes (etapa + ATIVADO IA? + janela)
conflitavam e a janela "expirava" com tempo. Decisão foi simplificar:
1 sinal só (etapa).

## Código

`voice_agent/kommo.py` função `agent_paused_for_lead`:

```python
def agent_paused_for_lead(self, caller_context, window_min):
    if not caller_context or not caller_context.get("found"):
        return None
    if caller_context.get("status_id") in ST_AGENT_OFF:
        return "etapa-humana"
    return None
```

Pytest blindando em `tests/test_filtros_lia.py` class `TestSilencioPorEtapa`.

Última atualização: 29/05/2026
