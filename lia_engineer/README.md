# Lia Engineer Autônomo

> Engenheiro virtual rodando 24/7 que detecta bugs em produção, propõe fix, testa, commita e monitora deploy — sem humano no loop.

## Por que existe

Hoje a Lia tem 3 problemas:
1. Bugs em produção só são descobertos quando paciente reclama OU Fábio audita lead manualmente
2. Quando fix é feito, depende de sessão Cowork (eu, Claude) — sem memória entre sessões, lento, caro
3. Não tem self-healing — cada bug repete N vezes até alguém olhar

**Resultado:** Fábio fica "apagando incêndio" — não consegue sair 1 minuto da tela sem regressão.

**Lia Engineer resolve isso fazendo o trabalho de um engenheiro júnior 24/7.**

## Como funciona

```
┌─────────────────────────────────────────────────────────────┐
│  CRON Easypanel — a cada 5 minutos                          │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  detect_bugs.py                                             │
│  • Lê notas Kommo últimos 30min (filtro: autor=Lia)         │
│  • Busca padrões: "deixa eu reconsultar" / "vou consultar"  │
│    / mensagens duplicadas <10s / data×dia inconsistente     │
│  • Lê logs Sentry / Easypanel últimos 30min                 │
│  • Classifica severidade (P0/P1/P2)                         │
└──────────────────────┬──────────────────────────────────────┘
                       ▼ bugs detectados
┌─────────────────────────────────────────────────────────────┐
│  classify.py                                                │
│  • Chama Haiku → categoria (race condition / texto livre /  │
│    filtro escapou / data errada / contradição contexto)     │
│  • Cruza com `bugs-licoes/` indexado pra ver se é novo      │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  propose_fix.py                                             │
│  • Chama Opus 4.6 com: bug + código atual + KB              │
│  • Gera diff completo (arquivo.py + tests/test_xxx.py)      │
│  • Adiciona pytest cobrindo o caso real                     │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  apply_fix.py                                               │
│  • git checkout -b lia-engineer/fix-bug-NNN                 │
│  • Aplica patch                                             │
│  • Roda pytest LOCAL                                        │
│  • Se PASSA → git commit + push                             │
│  • Easypanel auto-deploy                                    │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  verify.py                                                  │
│  • Aguarda deploy (~3min)                                   │
│  • Chama /admin/smoke-tick (6 cenários core)                │
│  • Se PASSA → ✅ merge na main, fecha task                  │
│  • Se FALHA → ❌ git revert + rollback Easypanel + alert    │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  notify.py                                                  │
│  • Slack #lia-engineer: "Fix aplicado: bug X, deploy OK"   │
│  • Atualiza CLAUDE.md seção 0 com nova lição (rolling 5)    │
│  • Indexa em bugs-licoes/                                   │
└─────────────────────────────────────────────────────────────┘
```

## Custos reais

| Item | Custo estimado |
|---|---|
| Tokens Haiku (classificação) | ~$5/mês |
| Tokens Opus (fix proposal) | ~$50-100/mês (depende qtde bugs) |
| Infra Easypanel (já existe) | $0 marginal |
| **Total** | **~$60-110/mês** |

Compare com R$ 3.500/mês de uma secretária CLT pra babá. **ROI > 30x.**

## Limites honestos

- **Não substitui humano em decisões de produto** (novas features, mudança de prompt, política Blink). Só corrige bugs.
- **Não corrige bugs catastróficos** (DB perdeu dados, infra caiu). Apenas bugs de código.
- **Falha em bugs muito novos** (sem padrão similar nos `bugs-licoes/`). Nesse caso → escala humano.
- **Tem cap de 3 fixes/dia** pra evitar rabbit hole (configurável).

## Setup

Ver `SETUP.md`.

## Como saber se está funcionando

```bash
curl https://blink-engineer.6prkfn.easypanel.host/status
```

Retorna:
```json
{
  "alive": true,
  "ultimo_tick": "2026-06-09T20:45:00Z",
  "bugs_detectados_24h": 7,
  "fixes_aplicados_24h": 5,
  "rollbacks_24h": 0,
  "uptime_dias": 14
}
```
