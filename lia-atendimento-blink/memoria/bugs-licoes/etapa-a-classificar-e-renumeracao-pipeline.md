# Etapa "0-a classificar" criada + renumeração do pipeline ATENDE

> Registrada em 31/05/2026 (task #96). Fábio criou a etapa nova no Kommo
> e ao mesmo tempo renumerou todo o funil pra que "A CLASSIFICAR" ficasse
> antes de "ATENDIMENTO HUMANO".

## ID da nova etapa

| Campo | Valor |
|---|---|
| Pipeline | ATENDE (8601819) |
| Nome | `0-a classificar` |
| Status ID | **`106919911`** |
| Sort | 20 (entre 0-ETAPA ENTRADA e 1-ATENDIMENTO HUMANO) |
| Cor | `#99ccff` |

## Renumeração simultânea

IDs **não mudaram**, mas os NOMES sim. Isso só afeta documentação:

| ID | Nome ANTES (≤ 30/05) | Nome AGORA (≥ 31/05) |
|---|---|---|
| 96441724 | 0-ETAPA ENTRADA | 0-ETAPA ENTRADA |
| 106919911 | *(não existia)* | **0-a classificar** ← NOVA |
| 106563343 | 0-ATENDIMENTO HUMANO | 1-ATENDIMENTO HUMANO |
| 101508307 | 1.LEADS FRIO | 2.LEADS FRIO |
| 102560495 | 2-AGENDAR | 3-AGENDAR |
| 106184631 | 3.REAGENDAR | 4.REAGENDAR |
| 101507507 | 4-AGENDADO | 5-AGENDADO |
| 101109455 | 5-CONFIRMAR | 6-CONFIRMAR |
| 106653499 | 6.CONFIRMADO | 7.CONFIRMADO |
| 106184983 | 6.1-NO-SHOW (ATIVAR) | 7.1-NO-SHOW (ATIVAR) |
| 91486864 | 7-REALIZADO CONSULTA | 8-REALIZADO CONSULTA |

Como o código usa **status_id (int)** e não nome, **nada quebrou**. Mas
qualquer documentação ou comentário com o nome antigo precisa ser
atualizado quando alguém tocar.

## Linha de corte vigente — "antes de AGENDADO"

`voice_agent/mensagens_janela.STATUS_IDS_ANTES_AGENDADO` continua igual
(os IDs não mudaram). Lista que pode receber renovação 24h:

- 96441724 — 0-ETAPA ENTRADA
- 101508307 — 2.LEADS FRIO
- 102560495 — 3-AGENDAR
- 106184631 — 4.REAGENDAR
- 106184983 — 7.1-NO-SHOW (ATIVAR)

**NÃO incluído** intencionalmente:
- `106919911` (0-a classificar) — lead JÁ recebeu renovação e foi
  qualificado pelo motor; não faz sentido disparar de novo aqui. Atendente
  humano qualifica e move pra outra etapa.
- `106563343` (1-ATENDIMENTO HUMANO) — handoff humano explícito.

## Configuração que falta no Easypanel

```
KOMMO_STATUS_A_CLASSIFICAR_ID=106919911
CLASSIFICAR_TIMEOUT_HORAS=24
```

## Os 4 lugares que precisam estar sincronizados

Se a etapa for renomeada/movida, mexer:
1. `voice_agent/classificar.py` (usa env)
2. Este arquivo (atualizar tabela)
3. `CLAUDE.md` seção 4
4. Easypanel env `KOMMO_STATUS_A_CLASSIFICAR_ID`

Última atualização: 31/05/2026 — criação inicial.
