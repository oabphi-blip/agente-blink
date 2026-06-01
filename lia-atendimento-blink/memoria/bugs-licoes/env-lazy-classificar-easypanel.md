# Env cacheada no import + Easypanel descarta env nova → classificar quebrado

> Registrada pelo Guardião em 31/05/2026 a partir dos commits
> `2809a5b`, `73aca6c`, `99817e4`, `eca10ec`. Cluster de 4 fixes no
> mesmo dia, todos no worker `classificar-tick`.

## Sintoma

O worker de classificação (`classificar-tick`, move lead parado →
`0-a classificar` 106919911) não movia ninguém. `debug_env_value` no
endpoint retornava erro. Feature parecia "desligada" mesmo com a env
`KOMMO_STATUS_A_CLASSIFICAR_ID=106919911` configurada no Easypanel.

## Causa raiz

Dois problemas encadeados:

1. **Env lida no import (top-level).** `STATUS_A_CLASSIFICAR_ID` era
   avaliada uma única vez quando o módulo carregava. Se a env não
   estivesse presente naquele instante (ou o módulo importasse antes do
   env estar disponível), o valor ficava `None` e nunca mais relia.
   Default `"0" or None` → `None` → feature OFF silenciosa.

2. **Easypanel descarta env nova após rebuild.** Mesmo configurando a
   env no painel, cada rebuild da imagem a perdia, então o container
   subia sem `KOMMO_STATUS_A_CLASSIFICAR_ID`. Combinado com (1), o
   destino ficava `None` permanentemente.

3. **Regressão `import os` faltando** (`99817e4`/`eca10ec`): durante o
   refactor, `voice_agent/webhook.py` perdeu o `import os` e quebrou o
   `debug_env_value` do classificar-tick. Commitado e revertido 2x no
   mesmo dia — sintoma de editar sem smoke test entre mudanças.

## Fix

- `voice_agent/classificar.py`: substituídas as constantes top-level por
  **funções lazy** (`get_status_a_classificar_id()`,
  `get_pipeline_atende_id()`, `get_timeout_classificar_horas()`) que
  releem `os.environ` a cada chamada. Endpoints passam a chamar a função,
  não a constante.
- **Hardcode defensivo do default** = `106919911` (etapa 0-a classificar)
  dentro de `get_status_a_classificar_id()`, com override por env
  explícita. Resolve o Easypanel descartando env: o valor correto vive no
  código, a env só sobrescreve.
- `voice_agent/webhook.py`: restaurado `import os`.
- `REDIS_TTL_SEG_PADRAO` fixado em `25 * 3600` (não depende mais da
  constante lida no import).

## Cenário pytest (a adicionar)

- "env ausente no import → `get_status_a_classificar_id()` retorna
  106919911 (default hardcoded), não None"
- "env explícita `KOMMO_STATUS_A_CLASSIFICAR_ID=101508307` →
  função retorna 101508307 (override funciona)"
- "env com valor inválido ('abc') → retorna default 106919911, não crash"
- "`monkeypatch.setenv` APÓS import do módulo → função relê e devolve o
  novo valor (prova que a leitura é lazy, não snapshot)"

## Tags

`#classificar` `#env` `#easypanel` `#lazy-loading` `#import-os`
`#regressao` `#worker-cron` `#106919911`

## Regra para não retroceder

1. **Nunca ler env em constante top-level** se a feature pode ser
   ligada/desligada em runtime ou se o deploy é Easypanel. Use função
   lazy.
2. **Valores críticos de pipeline têm default hardcoded no código**, não
   só na env — Easypanel descarta env nova após rebuild.
3. **`import os` faltando = smoke test não rodou.** Após refactor que
   toca webhook + classificar, rodar `python -c "import voice_agent.webhook"`
   antes de commit.
