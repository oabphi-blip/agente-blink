# CLAUDE.md — Memória do projeto Blink Oftalmologia

> Arquivo carregado automaticamente em toda sessão Cowork no folder
> `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`.
> Resolve o problema "toda hora esquece" — regras críticas vivem aqui.

---

## 1. O que é o projeto

Lia: assistente WhatsApp da Blink Oftalmologia. Roda em Python (FastAPI),
escuta webhook do Kommo (CRM), responde via WhatsApp 8133 (Cloud) ou
0710 (Evolution legado), agenda no Medware.

Stack:
- Modelos: Claude Sonnet 4.5 (raciocínio) + Haiku 4.5 (filtros rápidos)
- Pipeline: webhook → caller_context → responder → filtros → envio
- Persistência: Redis (histórico curto) + Kommo (memória oficial)
- Conhecimento: 38 artigos KB em `voice_agent/knowledge_base/`

---

## 2. URLs e infra

| Recurso | URL |
|---|---|
| App produção | `https://blink-agent.6prkfn.easypanel.host` |
| Saúde | `/health` |
| Webhook Kommo | `/kommo` |
| Reativação status | `/reactivation/status` |
| Reativação tick | `POST /reactivation/tick` |
| Broadcast | `/broadcast/tick` |
| Easypanel | `https://6prkfn.easypanel.host/projects/blink/app/agent` |
| GitHub | `https://github.com/oabphi-blip/agente-blink` |
| Kommo | `https://univeja.kommo.com` |
| Medware API | `https://medware.blinkoftalmologia.com.br/api` |
| Pipeline ATENDE Kommo | `id 8601819` |

---

## 3. Status do motor de reativação 24h (LIVE)

Confirmado em 28/05/2026:

```
enabled: true
dry_run: false
channel: whatsapp_cloud_8133
template_name: 1089_mens_ativar_conv_parada_qz7kbz
daily_cap: 30   ← subir pra 200 (ver outputs/ATIVAR_TETO_200_E_SLACK_LOG.md)
business_hours: 8h–18h seg–sáb BRT
cold_status_ids: [96441724, 101508307, 102560495, 106184631, 106184983]
slack_log: false   ← ligar
```

Engine: `voice_agent/reactivation.py` (433 linhas). Engine é completo,
dedup via Redis, rate-limit, horário comercial, 2 canais.

**Importante**: o motor JÁ ATIVA leads sozinho. Não fazer batch manual
de ativação via `kommo_add_note` — duplica trabalho.

---

## 4. Status IDs do pipeline ATENDE (8601819) — atualizado 31/05/2026

Fábio renumerou o funil em 31/05/2026. IDs **não mudaram**, só nomes.
Detalhes em `lia-atendimento-blink/memoria/bugs-licoes/etapa-a-classificar-e-renumeracao-pipeline.md`.

| ID | Etapa atual | Tipo |
|---|---|---|
| 96441724 | 0-ETAPA ENTRADA | frio (renovação cobre) |
| **106919911** | **0-a classificar** | **fila atendente humano (motor move pra cá)** |
| 106563343 | 1-ATENDIMENTO HUMANO | handoff humano |
| 101508307 | 2.LEADS FRIO | frio (renovação cobre) |
| 102560495 | 3-AGENDAR | em conversa (renovação cobre) |
| 106184631 | 4.REAGENDAR | em conversa (renovação cobre) |
| 101507507 | 5-AGENDADO | ativo |
| 101109455 | 6-CONFIRMAR | ativo |
| 106653499 | 7.CONFIRMADO | ativo |
| 106184983 | 7.1-NO-SHOW (ATIVAR) | frio (renovação cobre) |
| 91486864 | 8-REALIZADO CONSULTA | fechado positivo |
| 142 | Closed-won | fechado positivo |
| 143 | Closed-lost | perdido |

---

## 5. Campos custom Kommo importantes

| Field ID | Nome | Uso |
|---|---|---|
| 1255723 | `1.DIA CONSULTA` (date_time) | ja_agendado camada 2 — Lia detecta retrocesso |
| (vários) | `ATIVADO IA?` | controla reativação (Solicitado/Ativado/Não ativado) |
| (vários) | `FONTE_CAPTACAO` | origem do lead (Meta/Indicação/etc) |
| (vários) | `CONVENIO` | usado pelo build_message |
| (vários) | `NO-SHOW COUNT` | sanção progressiva |

Campos sinal (em criação, task #49):
- SINAL STATUS · SINAL VALOR · SINAL DATA PIX · SINAL COMPROVANTE
- MODALIDADE AGENDA (Reserva Imediata / Fila de Encaixe)

---

## 6. Chaves Pix oficiais (allowlist — qualquer outra é alucinação)

- **Asa Norte**: `karladelaliberaoftalmo@gmail.com` (e-mail)
- **Águas Claras**: `52.303.729/0001-30` (CNPJ)

Filtro pós-geração em `responder.py` bloqueia qualquer chave fora dessa lista.

---

## 7. Filtros pós-geração ativos em `responder.py`

Substituem texto da Lia se detectarem violação:

| Filtro | Detecta | Substitui por |
|---|---|---|
| `_scrub_prohibited` | chaves Pix inválidas | fallback seguro |
| `_viola_promete_retorno_humano` | **(NOVO 31/05)** "vou registrar pra equipe finalizar" / "retorno em horário comercial" — bug Juliene | oferta de slot real OU honestidade "reconsulto em 1min" |
| `_viola_oferta_agenda` | "consultar agenda" tendo agenda real | pergunta de preferência |
| `_viola_cobranca_antes_slot` | cobrança sem slot oferecido | "Antes de qualquer pagamento, deixa eu te oferecer os horários reais..." |
| `_agenda_block` | "Um momentinho", "deixa eu consultar" | proibido — reforço no prompt |

---

## 8. Bugs históricos resolvidos (não retroceder)

| Lead | Sintoma | Fix | Commit |
|---|---|---|---|
| 24033913 (Fábio) | "Um momentinho..." sem voltar | `_viola_oferta_agenda` | maio/26 |
| 23907418 (Aurora) | Retrocesso oferecendo dia tendo agendamento | `ja_agendado` 2 camadas (status_id OR dia_consulta_ts futuro) | 118d643 |
| 24034205 | Cobrou sinal antes de oferecer slot | `_viola_cobranca_antes_slot` | maio/26 |

Cenários que devem virar testes automáticos no pytest:
- "Paciente Aurora: status_id=2-AGENDAR mas dia_consulta_ts=hoje → ja_agendado=True"
- "Lia responde: 'Vou consultar agenda...' E agenda disponível → filtro substitui"
- "Lia responde: 'Pix 305,50 chave X' SEM slot oferecido → filtro substitui"

---

## 9. Política sinal/no-show (referência rápida)

Detalhe completo: `voice_agent/knowledge_base/38_politica_sinal_remarcacao_noshow.md`
e `lia-atendimento-blink/references/politica_sinal_e_noshow.md`.

Resumo:
- **Sinal opcional**: Karla sem convênio, Fabrício avaliação catarata
- **Sinal obrigatório**: 2+ no-shows
- **50% do valor**: Karla R$ 305,50 · SDP R$ 400 · Fabrício R$ 148,50
- **Janela cancelamento**: <24h = sinal não devolvido
- **Sempre oferecer 2 opções**: Reserva Imediata 50% OU Fila de Encaixe
- **Lembretes (Salesbot, não Lia)**: D-1 14h + D-0 8h + D-0 +30min no-show

---

## 9-A. Duração do slot Medware por médico (31/05/2026)

| Médico | Duração | Cobre |
|---|---|---|
| Dra. Karla Delalíbera | **30 min** | rotina, oftalmopediatria, SDP/Prisma, estrabismo |
| Dr. Fabrício Freitas | **40 min** | avaliação inicial + pós-op catarata |
| Dra. Kátia Delalíbera | 30 min *(placeholder — em pausa)* | retina (revisar ao voltar) |

Decisões registradas: SDP NÃO tem slot separado · Catarata avaliação == pós-op no Medware.
Centralizado em `voice_agent/mensagens_ciclo.py::DURACAO_SLOT_MIN_POR_MEDICO`.
Lição: `lia-atendimento-blink/memoria/bugs-licoes/duracao-slot-medicos.md`.

---

## 9-B. Otimizadores arquiteturais (31/05/2026 — sessão noite)

A partir do bug Juliene (lead 24053159), descobrimos que os 4 filtros pós-geração existentes eram REATIVOS — pegavam padrões de bugs passados. Padrão novo escapava. Implementamos 4 camadas de defesa PREVENTIVA:

| # | Otimizador | Módulo | Toggle | Default |
|---|---|---|---|---|
| #4 | Checklist 4 dados mínimos (nome completo + data nasc + CPF + convênio) — Lia não oferece slot sem ter como gravar Medware | `voice_agent/checklist_dados_minimos.py` | sempre-on | ativo |
| #3 | Smoke contínuo: 5 cenários core (C1 saudação · C2 pediátrico · C3 Juliene-evasiva · C4 Amil · C5 remarcação) — cron 1h + Slack alert | `voice_agent/smoke_continuous.py` | `SMOKE_ENABLED=1` | off |
| #2 | State machine 7 estados Redis (TRIAGEM → DADOS → CONVÊNIO → AGENDA → CONFIRMAÇÃO → GRAVAÇÃO → POS_GRAVAÇÃO) — transições válidas auditadas, atalhos proibidos bloqueados | `voice_agent/fsm_conversa.py` | sempre-on | ativo |
| #1 | Tool calling estruturado (`oferecer_slot`, `confirmar_dados_paciente`, `gravar_agendamento_medware`) — modelo CHAMA tool, resposta humana ⊃ resultado real | `voice_agent/tools_lia.py` | `LIA_TOOLS_ENABLED=1` | off (rollout gradual) |

Envs novas pra ligar (Easypanel → Ambiente):
- `SMOKE_ENABLED=1` + `SMOKE_INTERVALO_SEG=3600` (default 1h) + `SLACK_WEBHOOK_SMOKE_URL=https://hooks.slack.com/...` (opcional)
- `LIA_TOOLS_ENABLED=1` (quando quiser ativar tool calling)
- `SMOKE_BASE_URL` (default já aponta pra produção)

Endpoint manual: `POST /admin/smoke-tick?secret=$WEBHOOK_SECRET` — roda os 5 cenários e devolve JSON.

Lição: `lia-atendimento-blink/memoria/bugs-licoes/lia-inventou-retorno-humano-quando-agenda-vazia.md`.

---

## 10. Comandos úteis

```bash
# Estado do motor de reativação
curl -s https://blink-agent.6prkfn.easypanel.host/reactivation/status | jq

# Forçar 1 tick manual (ignora horário e intervalo, NÃO ignora cap)
curl -X POST "https://blink-agent.6prkfn.easypanel.host/reactivation/tick?force=true&secret=$WEBHOOK_SECRET"

# Saúde geral
curl -s https://blink-agent.6prkfn.easypanel.host/health

# Status broadcast (unificação 8133)
curl -s https://blink-agent.6prkfn.easypanel.host/broadcast/status
```

---

## 11. Scripts de deploy

Estão no root do repo:
- `commit_fix_retrocesso_e_agenda.sh`
- `recover_e_commit.sh`
- `commit_fix_cobranca_antes_slot.sh`
- `push-to-github.sh`

Todos têm token GitHub embedded. **Token `ghp_7NNf...3H20m8` está comprometido** —
revogar e gerar novo. Salvar no Keychain do Mac, não no script.

---

## 12. O que está em construção

- Campos sinal no Kommo (task #49 manual)
- Subir `REACTIVATION_DAILY_CAP=30→200` (ver `outputs/ATIVAR_TETO_200_E_SLACK_LOG.md`)
- Ligar `SLACK_WEBHOOK_URL` pra log de cada disparo
- Testes pytest pra cenários históricos (Aurora, Fábio, cobrança antes slot)
- Webhook Meta Lead Form → Kommo (leads novos em 30s)
- Painel `gap de amanhã` (slots vazios → reativação focada)
- **Pipeline autorização antecipada do convênio** (task #81): a partir do
  `N.EXAMES` preenchido pelo `selecionar_agrupador()`, montar a guia
  eletrônica e enviar à operadora antes do dia da consulta.
- **Comparador pós-consulta** (task #81): função
  `voice_agent/auditoria.py:comparar_agrupamento()` + endpoint
  `/admin/auditoria-tick` + webhook Kommo que escuta movimentação para
  `6-REALIZADO CONSULTA` e dispara comparação por paciente.
- **Campo Kommo `N.AGRUPAMENTO ALTERADO`** (checkbox por paciente, 6 campos),
  preenchido automaticamente pela auditoria + nota detalhada
  `exames_a_mais`/`exames_a_menos`.
- **Pytest auditoria**: 4 cenários (coincide / a_mais / a_menos / fonte_vazia).
- **Observabilidade dupla checagem #auditoria-autorização** (task #82):
  bot posta discrepância no canal Slack; secretaria da unidade (Asa Norte ou
  Águas Claras) faz 1ª revisão (reaction `:white_check_mark:`); médico
  responsável (Karla/Fabrício/Kátia) faz a 2ª; `N.AUDITORIA STATUS` só vira
  `fechada` com as 2 assinaturas. Sem isso, financeiro não cobra o convênio.
  Env nova: `SLACK_WEBHOOK_AUDITORIA_URL`. (Seção 25 do `_MASTER_INSTRUCTION.md`.)

---

## 13. Regra de ouro para Claude/Lia

1. **Nunca inventar chave Pix** — só Asa Norte/Águas Claras
2. **Nunca dizer "deixa eu consultar agenda"** se Medware respondeu OK
3. **Nunca cobrar sinal antes de oferecer slot concreto**
4. **Sempre apresentar 2 opções** (Reserva Imediata + Fila de Encaixe)
5. **Respeitar `ja_agendado=True`** — não oferecer slot novo
5-A. **Nunca dizer "vou registrar pra equipe finalizar — retorno em horário comercial"** (NOVO 31/05). Sem agenda real → "deixa eu reconsultar, volto em 1 min". Com agenda → oferecer slot concreto. Sem `checklist_dados_minimos.pronto_para_oferecer_slot` → coletar dados antes.
6. **Não duplicar trabalho do motor** — não rodar batch `kommo_add_note` em
   massa, o reactivation.py já cobre a fila
7. **Convênio só agenda com 3 pré-requisitos POR PACIENTE** — `N.DATA NASC`,
   idade calculada (DATA DE HOJE Brasília injetada), `N.MOTIVO` classificado
   nas 5 categorias (Rotina/Retorno/Pré-op/Urgência/Pós-op). Sem isso, NÃO
   ofertar slot. Esses 3 dados alimentam `selecionar_agrupador()` → preenche
   `N.EXAMES` → pipeline solicita autorização ao convênio antes da consulta.
   (Seção 23 do `_MASTER_INSTRUCTION.md`.)
8. **Auditoria pós-consulta é silenciosa para o paciente** — pipeline compara
   `N.EXAMES` (planejado) vs Medware (realizado). Diferenças geram
   `N.AGRUPAMENTO ALTERADO=true` + tarefa humana de reabrir autorização. Lia
   não comenta a alteração com o paciente. (Seção 24 do
   `_MASTER_INSTRUCTION.md`.)

---

## 14. Paths do sistema (descobertos 28-29/05/2026)

| Recurso | Path |
|---|---|
| Skills Cowork (NÃO é Claude Code) | `~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/{uuid-A}/{uuid-B}/skills/` |
| Skill `lia-atendimento-blink` instalada | path acima + `/lia-atendimento-blink/` |
| Skills Claude Code (terminal) | `~/.claude/skills/user/` — **NÃO É O QUE COWORK USA** |
| Repo Mac | `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/` |
| Repo sandbox | `/sessions/{session}/mnt/AGENTE IA BLINK/` |
| Outputs sandbox | `/sessions/{session}/mnt/outputs/` |
| Knowledge Base | `voice_agent/knowledge_base/` (38 artigos) |
| Memória pasta | `lia-atendimento-blink/memoria/bugs-licoes/` |

UUIDs do skills-plugin são VOLÁTEIS — mudam por sessão. Sempre descobrir via:
```bash
find ~/Library/Application\ Support/Claude/local-agent-mode-sessions -name "SKILL.md" 2>/dev/null | head -3
```

---

## 15. Convênios — mapeamento oficial Medware ↔ Kommo (29/05/2026)

26 dos 27 convênios do Kommo (campo CONVÊNIO field_id=853206) mapeiam pra
codPlano do Medware via `voice_agent/medware.py` PLANO_CODES. Lista validada
em 45 pytest. Inas GDf não é aceito (artigo 18 KB).

| Kommo | Medware | codPlano |
|---|---|---|
| Pro ser STJ | STJ | 3 |
| TJDFT Pró-Saúde | T.J.D.F.T - DIRETO | 2 |
| Plan Assiste - MPF (MPU) | PLAN-ASSIT | 4 |
| E-vida (Luminar) | E-VIDA | 5 |
| Anafe | ANAFE | 8 |
| Bacen | BACEN | 9 |
| Care Plus | CARE PLUS | 14 |
| Casec (Codevasf) | CASEC | 15 |
| Casembrapa _ Embrapa | CASEMBRAPA | 16 |
| Conab | CONAB | 19 |
| Fascal | FASCAL | 22 |
| Omint | OMINT | 25 |
| PF Saúde | POLICIA FEDERAL | 26 |
| PLAS/JMU (STM) | STM | 27 |
| Proasa | PROASA | 28 |
| Saúde Caixa | SAÚDE CAIXA | 29 |
| Petrobrás (Saúde Petrobrás) | SAÚDE PETROBRAS | 30 |
| Serpro | SERPRO | 31 |
| SIS Senado | SIS SENADO | 32 |
| STF-Med | STF-MED | 33 |
| TRF Pró-Social | TRF | 34 |
| TRE | TRE | 35 |
| TRT | TRT | 36 |
| TST Saúde | TST | 37 |
| PróSaúde (Câmara dos Deputados) | CAMARA DOS DEPUTADOS | 39 |
| Não se aplica | .PARTICULAR | 1 |
| **Inas GDf** | **não aceito** (KB art. 18) | **0 → humano** |

---

## 16. Como Claude erra — anti-padrões observados (gravar pra não repetir)

Sessão 28/05/2026 acumulou 5+ erros do mesmo tipo. Padrão:

1. **Adivinho path em vez de checar.** Path do Cowork skill: adivinhei
   `~/.claude/skills/user/`. Errado. Tinha que rodar `find SKILL.md` no
   Application Support primeiro. **Regra:** antes de copiar arquivo pra
   path de aplicação, SEMPRE listar onde os irmãos vivem.

2. **Codifico mapeamento sem listar a fonte.** PLANO_CODES tinha 7 entradas.
   Lia falhava silenciosamente pra 24 convênios. Eu não chamei
   `listar_planos_operadoras` antes. **Regra:** antes de hardcodear lookup,
   listar o catálogo oficial.

3. **Faço múltiplas mudanças sem smoke test entre.** Editei pipeline +
   agendamento + responder + KB em sequência sem testar Medware no meio.
   Só descobriria erro com paciente real. **Regra:** após cada arquivo
   tocado, validar function isolada com smoke test antes do próximo arquivo.

4. **Mudo prompt sem rodar pytest.** Editei `_MASTER_INSTRUCTION.md` várias
   vezes hoje sem validar que regras antigas continuam disparando.
   **Regra:** após qualquer edit em KB, rodar `python -m pytest tests/ -v`
   antes de commit.

5. **Commito segredos.** CPF da Karla (013054726332) está em commits
   ded7b3e/c4e6e4e. Token GitHub `ghp_7NNf...` está em scripts e em
   `CLAUDE.md` deste projeto. **Regra:** antes de cada commit, varrer
   diff por strings que casam regex CPF (`\d{11}`) ou token (`ghp_[A-Za-z0-9]{36}`).

---

## 17. Sequência de auditoria obrigatória ao abrir nova sessão

Toda sessão Cowork futura, antes de mexer em código:

1. Ler `CLAUDE.md` (esse arquivo) — automático
2. Ler o handoff mais recente: `HANDOFF_<DD-MM>_PARA_<DD-MM-AAAA>.md` no root
3. `ls voice_agent/knowledge_base/` — ver artigos KB existentes
4. `git log --oneline -20` — ver commits recentes
5. `python -m pytest tests/ -v` — confirmar que estado atual passa testes
6. `curl https://blink-agent.6prkfn.easypanel.host/health` — confirmar prod viva

Só depois disso, começar trabalho. Sem isso = reincidência.

**Handoff mais recente**: `HANDOFF_31-05_NOITE_PARA_01-06-2026.md` (sessão noite — 4 otimizadores arquiteturais).

---

Última atualização: 31/05/2026 23:30 — sessão noite com bug Juliene 24053159,
fix 234d4c1 deployado (filtro `_viola_promete_retorno_humano` + bloco AGENDA
INDISPONÍVEL + log ERROR), 4 otimizadores arquiteturais commits 39fc250 +
3a5564f (checklist dados mínimos always-on + smoke contínuo opt-in + state
machine Redis always-on + tool calling opt-in). Total 584 testes passando,
5/5 cenários smoke manual contra prod verde.
