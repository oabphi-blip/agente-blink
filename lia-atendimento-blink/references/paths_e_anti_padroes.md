# Paths do sistema + anti-padrões Claude

> Carrega automaticamente quando skill `lia-atendimento-blink` ativa.
> Resolve o problema "Claude adivinha path/comando errado toda sessão".

## Paths críticos

### Aplicação (produção)
- Voice agent: `https://blink-agent.6prkfn.easypanel.host`
- Webhook Kommo: `/kommo`
- Saúde: `/health`
- Reativação: `/reactivation/status` e `/reactivation/tick`
- Easypanel UI: `https://6prkfn.easypanel.host/projects/blink/app/agent`

### Integrações externas
- Kommo: `https://univeja.kommo.com` · pipeline ATENDE id 8601819
- Medware API: `https://medware.blinkoftalmologia.com.br/api`
- GitHub repo: `https://github.com/oabphi-blip/agente-blink` · branch `main`

### Sistema Mac (Cowork)
- Repo: `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/`
- Skills Cowork: `~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/{uuid-A}/{uuid-B}/skills/`
  - UUIDs são por sessão. Descobrir sempre com:
    `find ~/Library/Application\ Support/Claude/local-agent-mode-sessions -name "SKILL.md" 2>/dev/null | head -3`
- Skills Claude Code (terminal, diferente do Cowork): `~/.claude/skills/user/`

### Sandbox sessão (caminhos vivos só durante essa sessão)
- Repo: `/sessions/{nome-da-sessão}/mnt/AGENTE IA BLINK/`
- Outputs (lixeira temporária): `/sessions/{nome}/mnt/outputs/`
- Uploads usuário: `/sessions/{nome}/mnt/uploads/`

## Convênios — onde está a fonte de verdade

- Lista oficial Medware: `voice_agent/medware.py` PLANO_CODES (validada
  contra `listar_planos_operadoras` em 29/05/2026)
- Enum Kommo: campo CONVÊNIO field_id=853206
- Validação pytest: `tests/test_filtros_lia.py` class `TestConveniosMapeados`

Antes de codar qualquer mapeamento novo: rodar `mcp__medware__listar_planos_operadoras` ou `medware.listar_planos_operadoras()` direto. NUNCA adivinhar.

## Antipadrões Claude (não repetir)

### 1. Adivinhar path de aplicação
**Quando ocorre:** copiar arquivo pra pasta de skill, plugin, config.
**Sintoma:** comando "ok" no terminal mas app não detecta.
**Cura:** rodar `find` pelos irmãos primeiro. Onde vive `skill-creator/SKILL.md`?
Aí ali é onde a Lia tem que ficar.

### 2. Hardcodear lookup sem ler o catálogo oficial
**Quando ocorre:** PLANO_CODES, MEDICO_CODES, UNIDADE_CODES, status_id Kommo.
**Sintoma:** alguns valores funcionam, outros silenciosamente retornam 0.
**Cura:** chamar API que lista o catálogo (listar_planos_operadoras,
listar_medicos, list_pipelines_and_stages) e gerar mapeamento por código.

### 3. Editar prompt KB sem rodar pytest depois
**Quando ocorre:** ajuste fino em `_MASTER_INSTRUCTION.md` ou artigos KB.
**Sintoma:** regra antiga deixa de disparar, bug histórico volta.
**Cura:** após qualquer edit em KB, rodar `python -m pytest tests/ -v` e
só commit se passou.

### 4. Múltiplas mudanças no mesmo commit sem smoke test entre
**Quando ocorre:** fix de Gap 1+2+3+4+5 num push só.
**Sintoma:** algo quebrado mas não sei qual mudança causou.
**Cura:** commit pequeno. Após cada arquivo tocado, smoke test isolado da
função alterada.

### 5. Commitar segredo
**Quando ocorre:** CPF, token, password, Pix em texto literal no código/doc.
**Sintoma:** segredo público no GitHub (LGPD + auth break).
**Cura:** antes de cada commit, rodar:
```bash
git diff --cached | grep -E "\b\d{11}\b|ghp_[A-Za-z0-9]{36}|github_pat_|sk-[A-Za-z0-9]{40,}|claude-[a-z]+-key|password\s*=" | head -5
```
Se achou algo, parar.

## Sequência obrigatória ao abrir sessão nova

1. Ler CLAUDE.md (auto)
2. Ler esse arquivo (auto via skill)
3. `ls voice_agent/knowledge_base/` — ver artigos KB
4. `git log --oneline -20` — ver últimos commits
5. `python -m pytest tests/ -v` — estado atual passa?
6. `curl /health` — prod viva?

Só depois disso, mexer em código.

## Endpoints Medware mais usados (referência rápida)

| Função | Endpoint | Read/Write |
|---|---|---|
| listar_planos_operadoras | `/Medware/Planos/ListarOperadoras` | R |
| listar_horarios_livres | `/Medware/Horarios/Listar` | R |
| criar_agendamento | `/Medware/Agendamentos/Salvar` | W |
| cancelar_agendamento | `/Medware/Agendamentos/Cancelar` | W |
| buscar_paciente_por_cpf | `/Medware/Pacientes/BuscarPorCPF` | R |

CodMedico: Karla=12080 · Fabrício=12081
CodUnidade: Asa Norte=5 · Águas Claras=3

Última atualização: 29/05/2026 02:30 BRT
