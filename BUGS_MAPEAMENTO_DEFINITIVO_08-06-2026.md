# MAPEAMENTO DEFINITIVO DOS BUGS REPETIDOS — 08/06/2026

> Origem: Fábio cobrou "vamos mapear os bugs já repetidos e corrigir de forma definitiva".
> Não é band-aid. Não é filtro a mais. É **causa-raiz arquitetural**.

---

## SUMÁRIO EXECUTIVO

Mapeei 22 bugs únicos repetidos em 6 categorias de causa-raiz REAL. Dessas 6 categorias:

| Cat | Causa-raiz | Bugs | Fix definitivo aplicado | Status |
|---|---|---|---|---|
| **1** | Tool calling não usado em FSM crítico | 12 leads (L1/L3/L5/L7/L8) | Switch Opus 4.6 #1 + tool_choice forçado | ⚠️ Parcial |
| **2** | Filtros regex reativos cauda longa | 8 bugs distintos | 13 filtros `_viola_*` + juiz Haiku DESLIGADO | ⚠️ Não-definitivo |
| **3** | KB ↔ Kommo enum desincronizado | 1 (Inas hoje, mas estrutural) | Filtro C-16 + lista canônica KB18 hardcoded | ⚠️ Faltou validator startup |
| **4** | Falha silenciosa integração externa | Token Meta, KOMMO_TOKEN, telefone vazio | Sem healthz ativo periódico | ❌ Faltando |
| **5** | Bugs operacionais MEUS (C-01 a C-16) | C-11/C-14 repetidos 2x | Protocolo Boeing 10 itens | ⚠️ Depende de mim seguir |
| **6** | Conversação 1 msg = N perguntas | 1 lead (Alessandro) | Sem fix | ❌ Faltando |

**Critério de "definitivo":** não é definitivo enquanto o N+1º caso da mesma categoria escapar. Filtro regex pega 5, falha no 6º. Tool calling forçado pega TODOS.

---

## CATEGORIA 1 — Tool calling não usado em FSM crítico (12 LEADS REPETIDOS)

### Casos (todos com mesma assinatura)

| Lead | Paciente | Frase Lia | FSM esperado |
|---|---|---|---|
| 24053159 | Juliene | "vou registrar pra equipe finalizar — retorno em horário comercial" | AGENDA |
| 21392947 | Sabrina | "deixa eu reconferir agenda" | AGENDA |
| 24064723 | Kamila | "ainda estou buscando os horários" | AGENDA |
| 24065257 | Janeide | "deixa eu consultar" | AGENDA |
| 21344999 | Iara | "vou consultar agenda" | AGENDA |
| 22345722 | Keyla | "vou consultar" | AGENDA |
| 21256807 | Alice | "vou consultar" | AGENDA |
| 24112452 | Grace | "deixa eu reconsultar a agenda" | AGENDA |
| 24039387 | Karla Pacheco | "vou buscar horários" | AGENDA |
| 24117314 | Maria Agostini | "Atendemos o INAS GDF" | CONVENIO |
| 24102510 | Pedro Miguel | ofertou R$ 611 sem slot | CONVENIO/AGENDA |
| 24063769 | Adriana | perguntou convênio que já tinha no ctx | CONVENIO |

### Causa-raiz REAL

Em FSM = AGENDA ou CONVENIO, Sonnet/Haiku DECIDE PROBABILISTICAMENTE entre:
- (a) chamar tool `oferecer_slot()` / `validar_convenio()` → resposta determinística baseada em Medware/KB
- (b) escrever texto livre → inventa

Quando escolhe (b), as 12 frases acima são variantes da mesma falha.

### Fixes já tentados (cada um pega ~80% dos casos novos, deixa 20% escapar)

1. **13 filtros `_viola_*`** em `responder.py` — pegam frases conhecidas, falham em variantes.
2. **Tool calling estruturado** (task #183, `LIA_TOOLS_ENABLED=1`) — adiciona tools no API call mas modelo ainda pode escolher texto livre.
3. **Switch Opus 4.6 em AGENDA** (lição #1 07/06) — Opus obedece tool_choice com mais disciplina.
4. **Juiz Haiku adversarial** (`JUIZ_HAIKU_ENABLED=1`) — DESLIGADO por falso positivo Larissa/Adriana.

### FIX DEFINITIVO (proposto)

```python
# voice_agent/responder.py — no método reply()
if estado_fsm in ("AGENDA", "CONVENIO", "DADOS"):
    # FORÇAR tool calling — modelo NÃO pode escrever texto livre
    tools = _tools_obrigatorios_por_estado(estado_fsm)
    tool_choice = {"type": "tool", "name": _tool_nome_obrigatorio(estado_fsm)}
    # E usar Opus 4.6 (mais disciplinado com tool_choice)
    model = opus_model
```

Mais um watchdog cron 1min que detecta frases tipo "vou consultar" SEM tool call associada e auto-corrige + alerta Slack.

**Cobertura esperada:** ~99%. A última escapa via prompt injection ou tool quebrada (cobre Cat 4).

### O QUE FALTA

- [ ] Tool_choice obrigatório em CONVENIO + DADOS (hoje só em AGENDA via #183)
- [ ] Watchdog cron 1min frases-fantasma (proposta nova)
- [ ] Métrica `fsm:AGENDA:tool_used_ratio` no /admin/healthz — alerta se < 95%

---

## CATEGORIA 2 — Filtros regex reativos com cauda longa (8 bugs)

### Bugs nessa categoria

| Bug | Filtro existente | Falhou em |
|---|---|---|
| Lia "vou consultar" | `_viola_promete_retorno_humano` | Padrão "deixa eu reconsultar" (Grace) escapou — variante |
| Dia da semana errado | `_viola_dia_semana` + `_viola_oferta_em_dia_nao_atendido` | Formato "sexta-feira (06/06)" escapou Priscila por parêntese |
| Pergunta redundante convênio | `_viola_pergunta_redundante_convenio` | Funciona OK, mas só substitui FALA, modelo continua perguntando turno seguinte |
| Copia frase exemplo prompt | sem filtro | Adelia 24056883 |
| Long text 4 perguntas | sem filtro | Alessandro 24112156 |
| Atendemos INAS | `_viola_disse_atende_convenio_nao_aceito` (HOJE C-16) | NOVO — depende push |
| Ja agendado oferece slot | 5 camadas | Cobertura boa, mas reativo |
| Cobrança antes de slot | `_viola_cobranca_antes_slot` | OK, mas só pega padrões R$ |

### Causa-raiz REAL

Filtro regex é DEFINITIVAMENTE NÃO-DEFINITIVO. Cada bug novo = 1 regex a mais. Variantes escapam.

### FIX DEFINITIVO (proposto)

**Substituir 13 filtros regex por classificador semântico** = juiz Haiku adversarial JÁ EXISTE (`voice_agent/juiz_adversarial.py`).

Foi desligado em 02/06 por falso positivo Larissa/Adriana. Mas com 2 mudanças:
1. **Shadow mode primeiro** (LIA_JUIZ_SHADOW=1): só LOGA o que substituiria por 7 dias.
2. **Limiar = 85** (em vez de 70) — só substitui se risco alto.
3. **Whitelist de cenários** "tudo correto" — frases válidas tipo "1=Tudo Correto" passam direto.

Após 7 dias de shadow, ligar produção.

### O QUE FALTA

- [ ] `juiz_adversarial.py::JUIZ_SHADOW_MODE` env flag
- [ ] Limiar configurável (já existe)
- [ ] Endpoint `/admin/juiz/veredictos-shadow-7d` pra revisar antes de ligar
- [ ] Whitelist de respostas confirmação humana ("1=Tudo Correto", "✓ Enviado", etc)

---

## CATEGORIA 3 — KB ↔ Kommo enum desincronizado (1 bug — Maria HOJE)

### Caso único mas estrutural

Enum Kommo CONVÊNIO 925312 tem texto `"Inas GDf (somente Dr. Fabrício Freitas)"` contradizendo KB 18 que diz Inas NÃO aceito sem exceção. Lia leu literal → "aceito com restrição".

### Causa-raiz REAL

Kommo enums podem ser editados a qualquer momento sem sincronizar com KB. Próximos Kommo enums podem ter texto que contradiga KB 17 (aceitos) ou outras regras.

### FIX DEFINITIVO (proposto)

Validador no startup do app que:
1. Lê todos os enums `CONVÊNIO` (field 853206) via Kommo API
2. Cruza com lista canônica KB 18 + KB 17
3. Se enum tem texto que CONTRADIZ KB → log ERROR + Slack alert
4. `/admin/healthz` semafórico mostra ⚠️ amarelo até resolver

### O QUE FALTA

- [ ] `voice_agent/validador_kb_kommo.py`
- [ ] Endpoint `/admin/healthz-kb-sync`
- [ ] Cron 1x/dia roda validação

---

## CATEGORIA 4 — Falha silenciosa em integração externa (3 bugs invisíveis)

### Casos descobertos por acidente

| Integração | Bug | Quanto tempo silencioso |
|---|---|---|
| **Meta WhatsApp** | Token expirou 03/06 09h PDT | 5 dias (descoberto hoje 08/06) |
| **Kommo API** | KOMMO_TOKEN HTTP 403 (#242) | desconhecido |
| **Kommo** | `get_lead_main_contact` retorna "sem telefone" mesmo com tel cadastrado (#240) | desconhecido |

### Causa-raiz REAL

Operações exitam silenciosamente. Logs ficam no Easypanel mas ninguém olha. Resultado: 5 dias sem template Meta enviado, ninguém percebeu.

### FIX DEFINITIVO (proposto)

`/admin/healthz` expandido com testes ATIVOS a cada 5min:

```python
def healthz_externo():
    return {
        "meta_whatsapp": _ping_meta_token(),     # GET /me?access_token=...
        "kommo_api": _ping_kommo(),              # GET /api/v4/account
        "medware": _ping_medware(),              # GET /listar_unidades
        "redis": _ping_redis(),                  # SET ping/GET ping
    }
```

Cada falha → Slack `#alertas-blink` IMEDIATAMENTE.

Cron 5min bate `/admin/healthz-externo` e Slacka se status≠200.

### O QUE FALTA

- [ ] `voice_agent/healthz_externo.py`
- [ ] Endpoint `/admin/healthz-externo`
- [ ] Cron embutido 5min em `cron_interno.py`
- [ ] `SLACK_WEBHOOK_ALERTAS_URL` env nova

---

## CATEGORIA 5 — Bugs operacionais MEUS (Claude Cowork) — C-01 a C-16

### Bugs repetidos por desatenção minha

| Bug | Caso | Causa | Repeti? |
|---|---|---|---|
| C-02 / C-11 | Mensagem virou nota interna | Não verifiquei "Para: contato" | **SIM 14x (C-11) + 1x (C-14 Alessandro)** |
| C-14 | Long text + 4 perguntas | Não segui regra "1 pergunta/msg" | **SIM Alessandro 07/06** |
| C-03 | Ignorou pergunta conceitual | Não explico antes de coletar | 1x Pedro |
| C-04 | Cobrei valor antes de slot | Não verifiquei se ofertei | recorrente |
| C-12 | MCP kommo_update_lead mente | MCP broken — workaround Chrome | n/a |
| C-15 | Token Meta expirado silencioso | sem healthz | n/a |
| C-16 | Faltou ler enum Kommo antes de afirmar | Lia, não eu — mas eu também não detectei | n/a |

### Causa-raiz REAL

PROTOCOLO existe (Boeing 10 itens). Eu PULO quando estou em batch ou pressionado por urgência.

### FIX DEFINITIVO

**Não tem fix de código.** É **comportamental MEU**.

Forma de tornar definitivo:
1. **TaskCreate antes de qualquer batch ≥ 3 ações** com subject="CANARY 1 lead PRIMEIRO — protocolo Boeing"
2. **TaskUpdate completed APÓS confirmação visual do Fábio** — antes não posso processar lead 2
3. Se eu pular o passo: Fábio aponta + indexo Bug C-NN

Esse é o que eu posso fazer. O resto depende de mim seguir.

### O QUE FALTA

- [ ] Auto-criar task canary toda vez que detecto batch ≥ 3 (não dá pra automatizar — depende de mim reconhecer)
- [ ] Indexar C-15 (token Meta) e C-16 (Inas) no `protocolo-claude-cowork.md` (pendente)

---

## CATEGORIA 6 — Conversação como formulário em vez de diálogo (1 bug)

### Caso

Alessandro 24112156 (07/06) — escrevi 4 perguntas numa mensagem só. Fábio: "uma mensagem de cada vez, é um diálogo".

### Causa-raiz REAL

Não tem prompt instruindo modelo a fazer 1 pergunta/turno. Modelo gera lista pq treina em FAQs.

### FIX DEFINITIVO

Filtro `_viola_multiplas_perguntas_seguidas`:
- Conta `?` na resposta
- Se > 1 pergunta E está em FSM=DADOS/CONVENIO → log ERROR + reescreve com só a 1ª pergunta + adia restante

Mais regra no prompt _MASTER_INSTRUCTION: "MÁXIMO 1 pergunta por mensagem. Diálogo, não formulário."

### O QUE FALTA

- [ ] `_viola_multiplas_perguntas_em_dados` em responder.py
- [ ] Regra prompt _MASTER_INSTRUCTION
- [ ] Pytest cenário Alessandro

---

## PRIORIZAÇÃO POR ROI (próximas 24h)

### 🔴 P0 — Bloqueia operação HOJE
1. **Bug C-15 token Meta** — sem renovar, ZERO templates saem. Fábio renova manualmente (caminho mais rápido).
2. **Push C-16** — fix Inas no código, push pelo Fábio Mac.

### 🟡 P1 — Próximas 24h (definitivos)
3. **Cat 4 healthz externo** — proativo, evita próximos 5-dias-silenciosos. Posso implementar agora.
4. **Cat 1 tool_choice em CONVENIO+DADOS** — elimina ~80% dos bugs Lia. Posso implementar agora.
5. **Cat 6 _viola_multiplas_perguntas** — pequeno, evita reincidência Alessandro.

### 🟢 P2 — Esta semana (arquiteturais)
6. **Cat 2 juiz Haiku shadow mode 7d** — substitui 13 filtros regex.
7. **Cat 3 validador KB ↔ Kommo enums** — cron diário + alerta.

---

## EXECUÇÃO PROPOSTA AGORA (com seu OK)

Implemento P1 itens 3, 4 e 5 em sequência:
1. `voice_agent/healthz_externo.py` + endpoint + cron 5min
2. tool_choice obrigatório em CONVENIO+DADOS no `responder.py`
3. `_viola_multiplas_perguntas_em_dados`

Cada um com pytest. Tempo estimado: ~45min se sandbox NFS desbloquear.

Pra os P0, dependo de você:
- Renovar token Meta (1 minuto)
- Push C-16 do Mac (30 segundos)

---

**Última atualização:** 08/06/2026 — sessão Cowork pós-incidente Maria Agostini 24117314.
