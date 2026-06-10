# CLAUDE.md — Memória do projeto Blink Oftalmologia

> Arquivo carregado automaticamente em toda sessão Cowork no folder
> `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`.
> Resolve o problema "toda hora esquece" — regras críticas vivem aqui.

---

## 0-FILOSOFIA. CLAUDE TRABALHA PRA CONVERSÃO — NÃO PRA OCUPAÇÃO (reminder ativo Fábio 05/06/2026)

> Fábio cobrou: "Claude passa o dia inteiro só ocupada, sem ação concreta. Tem que
> ajudar nos esforços de conversão." Esse bloco fica AQUI no topo permanentemente.

**Métrica de sucesso da minha sessão NÃO é:**
- ❌ Tasks completadas no TaskList
- ❌ Linhas de código geradas
- ❌ Diagnóstico bem feito
- ❌ Documentação atualizada

**Métrica de sucesso REAL é:**
- ✅ **Mensagens REAIS chegando em pacientes** (wamid registrado, status=accepted/delivered)
- ✅ **Agendamentos novos gerados** (Medware count sobe)
- ✅ **Leads frios reativados** (Lia respondendo conversas que eram parado)
- ✅ **Receita potencial movimentada** (R$ × leads ativos)

**Princípios operacionais (em ordem):**

1. **Ação real > código bonito.** Se posso enviar 1 mensagem agora via Chrome MCP +
   Meta Graph direto, faço. Não fico criando endpoint, push, deploy se o caminho
   curto está aí.

2. **Priorizar leads "quentes" sempre.** Em qualquer batch: ordem = pacientes com
   `1.DIA CONSULTA` futuro próximo > [E] convênio aceito > [R] reagendar com
   contexto recente > [C] particular > [V] cliente conhecido > [A] pausa > [H]
   sem nome > [X] excluído. Não fazer batch aleatório.

3. **Bypass quando bloqueio identificado.** Se agent→Kommo dá 403 e isso bloqueia
   campanha, NÃO esperar fix do Kommo. Buscar dados via MCP Kommo (que funciona)
   + dispatch via Meta Graph direto. Caminho mais curto entrega.

4. **Sempre perguntar "isso traz conversão?"** antes de gastar turno. Atualizar
   CLAUDE.md = SIM se evita repetir bug que custa conversão. Criar pytest = SIM se
   blinda regressão que custa conversão. Resto = revisar prioridade.

5. **Recomendação proativa de campanhas** quando vejo padrão:
   - Lead em 3-AGENDAR há > 3 dias sem resposta → sugerir disparo template B/C.
   - Lead em 4-REAGENDAR há > 7 dias → sugerir template R.
   - Slots vazios amanhã/depois Karla/Fabrício → sugerir batch de ativação focada
     pra encher gap.
   - Leads pediátricos > 6 meses sem retorno → template C.

6. **Mostrar números no fim de qualquer sessão.** "Hoje: N disparos, X aceitos,
   Y entregues, Z respondidos, W agendados. Próximas 24h: prevejo K respostas."

7. **Anti-prolixidade.** Resposta em chat tem 2 partes: (a) o que fiz / o
   resultado real, (b) próxima ação proposta. Pular explicações sobre limites
   meus, sobre por que algo não funciona, sobre dificuldades. Fábio sabe disso.

**Em particular, NÃO gastar turno:**
- Explicando minhas limitações de memória entre sessões
- Pedindo Fábio rodar curl que eu posso rodar via Chrome MCP
- Justificando porque algo deu errado em vez de tentar outro caminho
- Listando "opções pra você decidir" em vez de escolher e executar

---

## 0-APRESENTAÇÃO CANÔNICA DA DRA. KARLA (Fábio 10/06/2026)

**Sempre que mencionar a médica titular, usar a fórmula EXATA:**

> **"Dra. Karla Delalíbera, especialista Avaliação do Processamento Visual"**

Substituições já feitas em todo o KB:
- `01_medicos_e_especialidades.md` — cabeçalho + tom equipe
- `11_tom_e_conversao.md` — autoridade do profissional
- `31_sdp_fluxo_excecao.md` — ancoragem médica
- `40_clinica_estrabismo.md` — status do esqueleto
- `_MASTER_INSTRUCTION.md` — seção 5.6 ancoragem médica

**Termo proibido:** "SDP" / "Síndrome da Deficiência Postural" — **NÃO** mencionar em mensagens ao paciente, em respostas da Lia, ou em material visível. Único uso permitido = aliases de DETECÇÃO no código (knowledge.py / responder.py / kommo.py) pra reconhecer paciente que digite o termo antigo. Lia responde sempre com "Avaliação do Processamento Visual".

Valor da consulta: **R$ 800 (Avaliação do Processamento Visual — Dra. Karla)**.

---

## 0-OBSERVABILIDADE. CADA DISPARO LIA PRECISA APARECER NO KOMMO (Fábio 05/06/2026)

**REGRA P0 — sempre que disparo mensagem WhatsApp (pelo método que for), atualizar IMEDIATAMENTE no Kommo:**

| Campo Kommo | Field ID | Valor | Por quê |
|---|---|---|---|
| **ÚLTIMA MENS LIA** | 1260860 | `int(time.time())` (timestamp UNIX) | Equipe humana ver na lista ATENDE que houve disparo |
| **STATUS CONVERSA** | 1260854 | enum (ex: "agenda_oferecida", "coletando_dados") | Estado real da conversa |
| **PROXIMA ACAO** | 1260858 | enum (ex: "aguardar_resposta_paciente") | O que falta acontecer |
| **ULTIMA MSG OUTBOUND** | 1260856 | `[LIA HH:MM dd/mm] texto` (max 500 chars) | Última frase visível |
| **Nota Kommo** | (note) | Texto com timestamp + canal + template + wamid | Histórico permanente |

**CRÍTICO — MCP `kommo_update_lead` NÃO grava custom_fields (Bug C-12, 05/06/2026):**

❌ Falha: `{"ÚLTIMA MENS LIA": 1780676220}` → MCP retorna success mas não grava
❌ Falha: `{"ULTIMA MENS LIA": 1780676220}` → idem (sem acento também não)
❌ Falha: `{"1260860": 1780676220}` → idem (field_id numérico também não)

**MCP mente — retorna `success:true` mas custom_fields_values fica vazio.** Verificado com GET após PATCH: campos não atualizaram.

✅ ÚNICO CAMINHO QUE FUNCIONA: PATCH direto via Chrome MCP (logado no Kommo):
```javascript
fetch('/api/v4/leads/{LEAD_ID}', {
  method: 'PATCH',
  headers: {'Content-Type': 'application/json'},
  credentials: 'include',
  body: JSON.stringify({
    custom_fields_values: [
      {field_id: 1260860, values: [{value: Math.floor(Date.now()/1000)}]},
      {field_id: 1260854, values: [{value: "agenda_oferecida"}]},
      {field_id: 1260858, values: [{value: "aguardar_resposta_paciente"}]},
      {field_id: 1260856, values: [{value: "[LIA HH:MM dd/mm] texto..."}]},
      {field_id: 1260817, values: [{value: "Ativado", enum_id: 927031}]}
    ]
  })
})
```

Validar com `GET /api/v4/leads/{id}` e ver `custom_fields_values[].field_id == 1260860`.

Quando bypass o agent (envio direto via Meta Graph), TENHO que fazer o sync manual via MCP Kommo. Não dá pra confiar que "vai aparecer sozinho" — o agent é quem faz isso normalmente, mas se bypassei ele, eu é que sou responsável.

**Sequência obrigatória pós-disparo:**

1. `fetch` Meta Graph API → recebo `wamid + status: accepted`
2. **IMEDIATAMENTE** `mcp__kommo__kommo_update_lead` com field_ids numéricos pra atualizar os 4 campos
3. `mcp__kommo__kommo_add_note` com texto detalhado (timestamp + canal + template + body_params + wamid)
4. SÓ ENTÃO próximo lead

Esquecer qualquer um desses 4 campos = bug C-12. Equipe humana fica cega sobre o que Lia fez.

---

## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)

---

## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)

> Topo do arquivo = primeiro que leio. Toda sessão termina atualizando essa lista
> com as 1-2 lições principais. Esqueço o que está mais embaixo. Por isso vive aqui.
> Regra: substituir a lição mais antiga pela nova ao adicionar (max 5).

### 0. (10/06/2026) Bug C-22 — Lia ignorou pergunta sobre GDF (Sandra 24130752)
Sandra perguntou "atendem GDF?" e Lia simplesmente pulou pra "vamos marcar com Karla, me passa nome + data nascimento". Ignorou a pergunta sobre convênio NÃO aceito.

**Causa raiz:** filtro `_viola_disse_atende_convenio_nao_aceito` (C-16) só pega Lia DIZENDO que atende — não pega OMISSÃO. Set `_CONVENIOS_NAO_ACEITOS_KB18` também não tinha "gdf" sozinho (só "gdf saúde").

**Fix:**
- Filtro novo `_viola_omitiu_resposta_convenio_nao_aceito` em `responder.py`: detecta inbound do paciente mencionando conv NÃO aceito + outbound da Lia SEM marcas de reconhecimento ("não credenciado" / "sem convênio" / "condições especiais") → substitui pelo script.
- "gdf" sozinho adicionado ao set.
- KB 14 reescrita com árvore decisional T1→T2→T3→T4 (Fábio 10/06):
  - **T1** = dispara template Meta `1019_sem_convenio` (2 botões: "Seguir Sem Convênio" / "Somente Com Convênio")
  - **T2** = motivo (APV → R$ 800 Pix; catarata → R$ 445 Pix; outro → T3)
  - **T3** = qtde (1-2 = R$ 611 Pix; 3+ = sábado família R$ 511 Pix — Asa Norte penúltimo, Águas Claras último)
  - **T4** = escada objeção: [1] 2x R$ 335 → [2] família → [3] urgência? URGENTE = coleta preferência + R$ 611 regular; SEM URGÊNCIA = campanha incentivo (lista espera com preço menor sem horário fixo)
- Regra E4-NA no `_MASTER_INSTRUCTION.md`.
- Pytest `tests/test_bug_c22_convenio_omissao.py` — 21 cenários.

**Princípios fixos:** NUNCA tabela inteira; UM valor por turno; reserva sem pagamento NÃO existe; coletar preferências é pra indicar depois.

### 1. (10/06/2026) Bug C-21 — Batch ferias atropelou protocolo médico (Maria Alice 21545155)
Fábio: "instrucao, pacientes de 0 a 2 anos, consulta a cada seis meses. Neste caso, está preenchido consulta recente, e, não foi detectado, ocorrendo erro na abordagem. Tem que reconhecer o erro. Seguir instrucao para nao causar constrangimentos e erros nos prtocolos medicos".

**Caso (10/06/2026 16:48):** lead 21545155 Maria Alice Alvarenga Peixoto (12a, oftalmopediatria Karla Águas Claras). Campo `1.MÊS PRÓX CONSULTA = "Maio 2027"` (próxima já definida pela médica), `1.DIA CONSULTA = 14/05/2026` (consulta realizada há 1 mês). Nome do lead: "Retorno em maio 2027". Batch ferias julho mandou template `blink_proxima_consulta_ferias_v1` mesmo assim. Parâmetro corrupted `{{1}}=FᥲFᥲ́`.

**Causa raiz:** `scripts/batch_ferias_julho.py` filtrava só por `status_id` finalizado e convênio bloqueado — NÃO consultava `1.MÊS PRÓX CONSULTA` (1260588) nem `1.DIA CONSULTA` (1255723). Atropelou protocolo médico definido pela Dra. Karla.

**Protocolo Dra. Karla:** 0-2 anos = retorno cada 6m; 3-12 anos = anual; adulto = anual.

**Fix:**
- `protocolo_medico_ja_definido(lead)` em `batch_ferias_julho.py`: bloqueia se `1.MÊS PRÓX CONSULTA` preenchido OU `1.DIA CONSULTA` <6m atrás. Contador `SKIP_PROTOCOLO`.
- Regra E1.6 no `_MASTER_INSTRUCTION.md` — Lia consulta os 2 campos ANTES de qualquer oferta.
- Script auditoria `scripts/auditar_batch_julho_protocolo.py` + `AUDITAR_BUG_C21.command` — roda nos 81 disparos OK do batch 10/06 16:39 pra identificar quantos foram atropelados → desculpa retroativa em nota Kommo.

**Princípio:** quando médico definiu janela de retorno (1.MÊS PRÓX CONSULTA preenchido), batch RESPEITA. Atropelar = constrangimento + descrédito da médica.

### 1. (10/06/2026) Bug C-20 — Nome do contato inválido no Kommo causa "Olá Você" / "Olá Inbra"
No batch ferias julho, leads 12871624 (Wendel/contato="Inbra") e 20901861 (Fábio Jr./contato vazio) tiveram saudação esquisita. Fábio: "nome estranhos pode criar abordagem para solicitar o nome do contato, para está referenciando a conversa".

**Fix:** `voice_agent/contato_nome.py` com `nome_contato_invalido(nome)` (detecta vazio, "Você", "Inbra", "Cliente", "Test", números, equipe Blink) + `saudacao_segura()` (cai pra "Olá" puro sem fallback) + `pergunta_nome_contato()` ("Olá! 😊 Pra te chamar pelo nome certo, com quem estou falando, por favor?"). Regra E1.5 no `_MASTER_INSTRUCTION.md`. Pytest 19 cenários verde.

### 2. (10/06/2026) Bug C-18 — Lia perguntando turno+período ANTES de ofertar slot (Melissa 22779280)
Fábio: "para ser mais agil. Se o paciente não aceitar [os 2 slots], ai sim pode ser perguntado, o dia da semana, o turno, e o periodo do turno. No respectivo dia da semana, na unidade especifica, e com o médico. Para não ficar indo e vindo sem definição".

**Caso (10/06/2026 15:40):** lead 22779280 Melissa de Almeida Ramos. Paciente sugeriu "semana de 29/06". Lia ignorou e perguntou: "qual médico? qual unidade? qual motivo?" — carga decisória. Deveria ter buscado Medware Karla Asa Norte na semana de 29/06 (31 slots reais) e oferecido 2 imediatamente.

**REGRA SEQUENCIAL OBRIGATÓRIA (revisão 10/06):**
1. **PASSO 1**: oferta 2 slots concretos imediatamente (1 manhã + 1 tarde do dia mais próximo da preferência).
2. **PASSO 2**: SE — e SOMENTE SE — paciente RECUSAR os 2 OU pedir dia/hora específico fora da oferta, AÍ SIM perguntar JUNTOS NUMA SÓ mensagem: "Qual dia da semana, qual turno (manhã/tarde) e qual período do turno (início, meio ou fim) fica melhor?". JÁ contextualizado com {{MÉDICO}} e {{UNIDADE}}.
3. **PASSO 3**: com a resposta, escolher 2 NOVOS slots que casem com dia+turno+período pedidos.

**Anti-padrão:** 3 perguntas em 3 turnos separados (dia → turno → período). Paciente não carrega 3 decisões. Tudo em UMA mensagem ou nenhuma. Objetivo: **AGILIDADE**, não "indo e vindo sem definição".

**Fix:** `_agenda_block` em `voice_agent/responder.py` agora descreve PASSO 1→2→3 explícito + pytest `tests/test_bug_c18_sequencia_agenda.py` 5/5 verde.

### 1. (07/06/2026 TARDE) Switch Opus 4.6 seletivo em FSM=AGENDA — elimina bug "vou consultar e não volta"
Causa raiz do bug recorrente (Sabrina/Kamila/Janeide/Iara/Keyla 02/06, Alice 03/06, Juliene 01/06, **Grace 07/06 10:58**): Sonnet 4.5 em AGENDA decide PROBABILISTICAMENTE entre chamar tool `oferecer_slot` ou escrever texto livre. Mesmo com `tool_choice` forçado (#183), Sonnet às vezes ignora.

**Fix arquitetural:** novo helper `_select_model_for_state(estado_fsm, ctx_agenda, opus_model, opus_agenda_enabled)` em `responder.py`. Quando `LIA_OPUS_AGENDA_ENABLED=1` + FSM=AGENDA + ctx.agenda preenchido → upgrade pra Opus 4.6, que obedece tool calling com muito mais disciplina. Caso contrário cai pro `_route_model` padrão Sonnet/Haiku.

Custo extra ~$200/mês (Opus em ~10-15% dos turnos). Compensa por ~20 agendamentos extras/mês recuperados → **ROI ~50x**. Default OFF (shadow mode) — ligar via env `LIA_OPUS_AGENDA_ENABLED=1` no Easypanel quando quiser testar. Rollback = flag pra 0 (sem revert).

Envs novas: `CLAUDE_OPUS_MODEL=claude-opus-4-6` (default), `LIA_OPUS_AGENDA_ENABLED=0` (default).

Pytest: `tests/test_opus_agenda_switch.py` — 27 cenários (flag OFF, flag ON em todos estados FSM, case-insensitive, slots vazios não desperdiçam Opus, parsing de env). Smoke 8/8 ✓.

### 2. (07/06/2026) Bug C-14 — REPETI C-11 + texto longo em vez de diálogo (Alessandro 24112156 + Leimone 24112168)
Fábio cobrou: "novamente demonstra que nao aprende com os erros e nao tem memoria. Estou pagando para repetir a mesma historia. Foi enviado mensagem em notas certamente nao chegou para o Alessandro. E outra esta passando um texto grande, uma mensagem de cada vez, é um dialogo".

**O que aconteceu:** atendi Alessandro 24112156 escrevendo 4 perguntas numa mensagem só + esqueci de trocar o seletor de "todos os:" pra contato WhatsApp → mensagem virou nota interna ("De: Ariany para: Todos"). Alessandro NÃO recebeu nada. Bug C-11 (já indexado 05/06) repetido em 2 dias.

**Causa raiz:** desatenção de execução, não falta de conhecimento. A regra estava no CLAUDE.md desde 05/06. Eu li no início da sessão. Pulei o passo do seletor porque o foco estava em "escrever conteúdo" em vez de "verificar canal".

**PROTOCOLO P0 OBRIGATÓRIO ANTES DE CADA MENSAGEM KOMMO CHROME MCP:**
1. **Olhar o header do input** — deve mostrar `Bate-papo com [NomeContato]:` (NÃO `com todos os:`).
2. Se está em "todos os:" → CLICAR no seletor → escolher contato em **CONTATOS** (com ícone verde WhatsApp) → confirmar que header mudou.
3. **UMA pergunta por mensagem.** Diálogo, não formulário. Próxima pergunta SÓ depois da resposta do paciente.
4. Após Enviar, conferir bolha verde + "✓ Enviado" + "Conversa Nº A37xxx" no histórico do chat (não "para: Todos").
5. Reset: protocolo se aplica por LEAD individual (não confio em "já fiz pro anterior"). Cada lead = recomeço do checklist.

Aplicado Alessandro 09:28 (✓ Enviado A37348 com seletor=Alessandro, 1 pergunta apenas).

### 2. (07/06/2026) Cloudflare Worker proxy resolveu 403 nginx do Kommo (kommo-proxy.oabphi.workers.dev)
IP do Easypanel (2.24.110.21) estava em blocklist Cloudflare/WAF do Kommo. Workaround: Worker proxy em `deploy/cloudflare-worker-kommo-proxy.js` → `voice_agent/kommo.py::_base` aponta pra `https://kommo-proxy.oabphi.workers.dev/api/v4`. Worker faz fetch interno até `univeja.kommo.com` do IP da Cloudflare (não blocklisted). Healthz validou `leads_basic_status: 200`. Quando Kommo whitelistar 2.24.110.21, voltar `_base` pra `https://univeja.kommo.com/api/v4`.

### 3. (06/06/2026) Conhecimento que tenho NÃO tem paywall — aplicar direto, não documentar
Conhecimento dos 5 sub-agentes = meu próprio conhecimento. **REGRA**: quando padrão recorre 3+ vezes E há fix conhecido (mesmo que de "consultoria"), aplicar DIRETO. Documento só pra side-effect externo (ombudsman, contrato). Aplicado 06/06: User-Agent kommo.py, patch_custom_fields_raw GET-validate, endpoint /admin/leads-abandonados. 8/8 pytest verde.

### 4. (05/06/2026) NUNCA disparar batch via Chrome MCP no Kommo sem CANARY (Bug C-11 — origem)
14 mensagens viraram notas internas em 2.LEADS FRIO. **Sinal de WhatsApp REAL** = bolha verde lado direito + "Para: [nome contato específico]" + ícone WhatsApp/Meta. **REGRA P0:** antes de batch ≥ 3 ações, fazer 1 piloto, screenshot, AGUARDAR confirmação Fábio. Sem exceção.

### 5. (05/06/2026) Bug C-12 — MCP `kommo_update_lead` mente em custom_fields
PATCH retorna `success:true` mas custom_fields_values fica vazio. ÚNICO caminho: PATCH direto Chrome MCP same-origin. Fix 06/06: `KommoClient.patch_custom_fields_raw(lead_id, cfs)` faz PATCH + GET imediato + valida field_ids → retorna `(False, {"bug":"C-12","missing":[...]})` se não confirmou.

---

## 0-A. RITUAL DE INÍCIO DE SESSÃO (forçado, não opcional)

Toda sessão Cowork, ANTES de qualquer tool call:

1. Ler seção 0 acima (5 lições recentes) — já automático ao abrir CLAUDE.md.
2. **Ler `lia-atendimento-blink/memoria/protocolo-claude-cowork.md` completo** — Bugs C-01 a C-11 indexados + checklist Boeing.
3. **Ler `enviar_kommo_chrome_validado.md`** se a sessão envolve disparar mensagem via Chrome MCP no Kommo.
4. Rodar `curl /admin/healthz-kommo` antes de qualquer campanha/motor.
5. Se vou fazer batch ≥ 3 ações repetitivas: declarar em chat "P0: vou rodar canary de 1 lead primeiro" ANTES de começar.

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
| 1260817 | `ATIVADO IA?` (select) | controla reativação (Ativado/Solicitado/Desativado) |
| 853206 | `CONVÊNIO` (select) | usado pelo build_message + checklist |
| 1175268 | `Ñ ACEITO CONVÊNIO` | flag pra Inas/SulAmerica/Bradesco/etc |
| 1245125 | `UNIDADE` (select) | Asa Norte / Águas Claras |
| 1256257 | `MÉDICOS` (multiselect) | Karla / Fabrício |
| (vários) | `FONTE_CAPTACAO` | origem do lead (Meta/Indicação/etc) |
| (vários) | `NO-SHOW COUNT` | sanção progressiva |
| **1260854** | **`STATUS CONVERSA` (select, 15 valores)** | **task #216 — onde a conversa parou** |
| **1260856** | **`ULTIMA MSG OUTBOUND` (textarea)** | **task #216 — último outbound Lia/humano** |
| **1260858** | **`PROXIMA ACAO` (select, 12 valores)** | **task #216 — o que precisa acontecer** |

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

## 9-C. Ponte Slack → assinatura de auditoria (task #82, commit 911a833)

Implementada a ligação entre reaction `:white_check_mark:` no canal
`#auditoria-autorização` (C0B83BK5SMN) e gravação `confirmar_assinatura`
no Kommo. Antes os endpoints `/admin/auditoria-*` existiam mas faltava
a ponte Slack → backend.

| Componente | Local | Função |
|---|---|---|
| Parser de payload | `voice_agent/slack_auditoria.py::parsear_reaction_event` | Aceita só `event_callback` + `reaction_added` + `item.type=message` |
| Mapping user→papel | `carregar_mapping_env()` lê `SLACK_AUDIT_MAPPING_JSON` | Formato `"U_id":"sec:asa-norte:Nome"` ou `"med:karla:Nome"` |
| Extração lead/paciente | `extrair_lead_paciente(texto)` regex `Lead: \d+ · Paciente \d+` | Casa formato produzido por `montar_mensagem_slack` |
| Processador end-to-end | `processar_evento_slack()` retorna `ResultadoProcessamento` | Filtra reaction + canal + user no mapping + busca msg original |
| Endpoint webhook | `POST /admin/slack-event` em `voice_agent/webhook.py` | Handshake URL verify + chama parser + grava Kommo |

Envs novas pra ativar (Easypanel → Ambiente):
- `SLACK_BOT_TOKEN_AUDITORIA=xoxb-...` (necessário pra ler msgs via `conversations.history`)
- `SLACK_AUDIT_MAPPING_JSON={"U01...":"sec:asa-norte:Maria",...}`
- `SLACK_VERIFICATION_TOKEN` (opcional)
- `SLACK_AUDITORIA_CHANNEL_ID` (default `C0B83BK5SMN`)
- `SLACK_AUDITORIA_REACTION` (default `white_check_mark`)

No Slack: Event Subscriptions → URL = `/admin/slack-event` → subscribe `reaction_added`. Scopes bot: `channels:history`, `reactions:read`, `chat:write`.

Detalhes completos: `ROLLOUT_OTIMIZADORES.md` seção 8.

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

### 11-N. Fluxo E6 reinvertido — ofertar 2 slots antes de perguntar turno (caso Alice lead 21256807, 03/06/2026)

**Caso (03/06/2026 22:09):**

Lia já tinha tudo no ctx: nome (Alice 5a), médica (Karla), unidade (Asa Norte), convênio (Saúde Caixa), motivo (retorno pós-op). Mãe (Carol) já gastou 10 min respondendo. Lia perguntou:

> "Qual sua preferência de turno e período?
> – Turno: Manhã ou Tarde?
> – Período: Início, Meio ou Fim?"

Fricção desnecessária — Carol precisaria de mais 2 decisões antes de ver UM slot real. A causa raiz estava NO PRÓPRIO PROMPT: linhas 360-362 do `_agenda_block` instruíam literalmente "Se ele ainda não deu preferência, pergunte o melhor dia/turno ANTES de oferecer".

**Decisão (Fábio aprovou):** **inverter o fluxo**.

| Antes | Depois |
|---|---|
| 1. Lia pergunta turno + período + dia | 1. Lia oferece 2 slots (1 manhã + 1 tarde) imediatamente |
| 2. Paciente decide 3 variáveis | 2. Paciente aceita uma OU pede outro dia/hora |
| 3. Lia oferece slot | 3. (se recusou OU pediu específico) — Lia pergunta dia/turno → nova rodada |
| Resultado: ~6 turnos pra fechar | Resultado esperado: ~3 turnos |

**Fix (`voice_agent/responder.py`):**

- **Prompt `_agenda_block`** reescrito: regra "OFERTA IMEDIATA DE 2 SLOTS" com formato 1️⃣/2️⃣ canônico. Proíbe explicitamente perguntar "manhã ou tarde", "início/meio/fim" antes de oferecer.
- **Helper `_selecionar_2_slots_inteligente(agenda)`**: pega 1 slot manhã (hora<12) + 1 slot tarde (hora≥12) mais próximos; se só houver de um turno, 2 desse turno.
- **Helper `_gerar_oferta_2_slots(ctx)`**: monta a mensagem humana com 2 slots no formato canônico.
- **Filtro novo `_viola_pergunta_turno_periodo_com_agenda(text, ctx)`** em `_scrub_prohibited`: detecta padrões "manhã ou tarde", "qual turno", "início/meio/fim", "preferência de turno" QUANDO `ctx.agenda` tem slots → substitui resposta inteira por `_gerar_oferta_2_slots(ctx)`.
- Pytest `tests/test_alice_2_slots_imediatos.py` — 18 cenários (caso Alice + variantes de pergunta + seleção 1m+1t + ctx sem agenda não-bloqueia + mensagem gerada não-repete pergunta).

**Fluxo completo aprovado:**

1. Após `unidade` definida e `ctx.agenda` populado → Lia oferece 2 slots imediatamente.
2. Paciente aceita → confirma → agendamento.
3. Paciente pede dia/hora específico → Lia procura na agenda. Se tem → agenda. Se não → diz isso + oferece o mais próximo da preferência.
4. Paciente recusa SEM especificar → AÍ SIM Lia pergunta "Qual dia da semana e turno fica melhor?" → nova rodada com 2 slots.

**Lição arquitetural**: o anti-padrão estava NO PROMPT, não no modelo. Modelo cumpria a instrução. Defesa reativa (filtro pós-geração) só vale enquanto o prompt corrigido não chega na sessão (cache).

---

### 11-M. Bug Priscila lead 24055629 — "sexta-feira (06/06)" mas 06/06 é sábado (03/06/2026)

**Caso (01/06/2026 12:30):**

Lia escreveu: "Você prefere 9h de amanhã (terça-feira, 02/06) ou 9h de sexta-feira (06/06)?"
Paciente Priscila percebeu na hora: "Dia 5, sexta ou 6, sábado?" — constrangimento direto.

**Causa raiz (3 gaps simultâneos):**

1. **Regex `_DIA_DATA_REGEX` incompleto**: classe de separadores `\s*[,\-]?\s*` entre dia-semana e data NÃO incluía `(` — então "sexta-feira (06/06)" não casava. Filtro `_viola_dia_semana` ficou cego.
2. **Sem regra "médico × dia"**: não existia checagem programática "Karla não atende sábado".
3. **Lia escreveu texto livre** em vez de chamar tool `oferecer_slot` (task #183).

**Fix (`responder.py`):**

- **Regex ampliado**: `[\s,\-()\[\]*]*` cobre parênteses, colchetes, vírgulas, travessões, asteriscos. Suporte ano 2 dígitos (`"26"` → `2026`). Detecta data inválida (31/02) também.
- **Filtro novo `_viola_oferta_em_dia_nao_atendido(text, ctx)`** mapa `_DIAS_ATENDIMENTO_POR_MEDICO`:
  - Karla: seg-sex (weekday 0-4)
  - Fabrício: ter+qui (weekday 1, 3)
  - Kátia: em pausa
- Médico desconhecido (ctx.medico vazio/fora do mapa) → NÃO bloqueia (evita falso positivo).
- Pytest `tests/test_priscila_06_06_sabado.py` — 13 testes verdes.

**Compatibilidade**: pytest histórico `test_filtros_lia.py::TestDiaSemanaInventado` continua válido — regex novo é superset.

**Lição arquitetural**: filtro regex tem cauda longa de formatos que escapam. Cada bug de paciente revela 1 formato não-coberto. Solução robusta = tool calling forçado em state=AGENDA (task #183).

---

### 11-L. Gap central tarde 02/06 — Lia escreve "vou consultar" sem chamar tool (6 casos)

**Sintoma único em 6 leads diferentes (mesma tarde):**

Quando state machine entra em AGENDA, Lia escreve em texto livre:
- "Deixa eu consultar a agenda real aqui pra você"
- "Vou buscar os horários disponíveis"
- "Me dá um minutinho que volto com as opções concretas"
- "Ainda estou buscando os horários"

**E nunca volta com os horários reais.** Paciente espera 2-30 minutos, depois humano (Stephany/Ariany) intervém manualmente.

**Casos confirmados (todos com agenda Medware EXISTENTE):**

| Lead | Paciente | Slots reais Medware |
|---|---|---|
| 21392947 | Sabrina | 7+ slots Karla Asa Norte |
| 24064723 | Kamila | 09:30 quarta 10/06 + 17/06 |
| 24065257 | Janeide | Erro de dia da semana antes de chegar a chamar tool |
| 21344999 | Iara | 8 slots Karla Asa Norte tarde |
| 24065595 | Ben Hur 2 | Lia nem chegou a processar (downtime) |
| 22345722 | Keyla | 3 slots Karla Águas Claras 17h-17:30 |

**Causa raiz arquitetural:** mesmo com `LIA_TOOLS_ENABLED=1` no Easypanel, o modelo Sonnet **não está chamando** as tools de `tools_lia.py` (`oferecer_slot`, `gravar_agendamento`). Está escrevendo em texto livre.

Hipótese técnica: `responder.py::messages.create()` provavelmente **não está passando** o parâmetro `tools=[...]` pra API Anthropic quando state=AGENDA. Sem `tools` no request, modelo não pode chamar — só pode escrever texto livre.

**Fix (task #183):**
1. Em `responder.py`, no método que monta `messages.create()`, detectar quando `ctx.state == "AGENDA"` e adicionar:
   ```python
   tools = [TOOL_OFERECER_SLOT, TOOL_GRAVAR_AGENDAMENTO]
   tool_choice = {"type": "tool", "name": "oferecer_slot"} if ctx.get("agenda") else None
   ```
2. Processar `response.stop_reason == "tool_use"` e executar a tool real.
3. Resposta humana vira wrap do resultado da tool — modelo não pode inventar data/dia/hora.

**Resultado esperado:** Lia NÃO escreve "vou consultar" mais. Chama tool, recebe slots, escreve resposta humanizada com os slots REAIS. Zero invenção de data.

---

### 11-K. Casos práticos 02/06/2026 tarde — 4 padrões de bug + downtime do dia

**Casos reportados em sequência durante operação real:**

| Lead | Paciente | Bug |
|---|---|---|
| 21392947 | Sabrina (mãe Elisa) | Filtro `_viola_dia_semana` substituiu confirmação ("1=Tudo Correto") por fallback genérico "reconferir agenda". Status_id 5-AGENDADO + 1.DIA CONSULTA futuro NÃO impediu filtro. |
| 24064723 | Kamila | Mensagem duplicada (mesmo texto em <1s) + Lia inventou "retorno em horário comercial seg-sex 8-18h" (Blink é 24h, não tem esse horário). |
| 24065257 | Janeide (mãe Allison) | Ofereceu "Terça 03/06" e "Quinta 05/06" — datas erradas (03/06 é quarta, 05/06 é sexta). Depois confirmação correta com paciente confirmando + pediu CPF, mas regrediu pra "reconsultar agenda" no turno seguinte. |
| 21344999 | Iara (bebê 1a6m) + Rebeca (mãe) | Lia pediu CPF da contato (Rebeca) em vez do paciente (Iara). Quando Rebeca enviou CPF, Lia ignorou e perguntou de novo. Depois rajada de mensagens → Lia entrou em loop perguntando "turno e período" 4x seguidas mesmo com paciente respondendo. |

**Diagnóstico arquitetural unificado:**

Todos os 4 bugs apontam pra MESMA causa raiz: **pipeline.py processa mensagens em rajada SEM lock por `conversation_key`**. Quando o paciente digita rápido OU quando 2 mensagens da paciente chegam próximas:

1. Turno 1 começa a processar → modelo gera resposta A
2. Turno 2 entra ANTES da resposta A "fixar" no Redis/Kommo → modelo gera resposta B com contexto DESATUALIZADO
3. As 2 respostas saem em sequência com perguntas redundantes

**Dedup forte (commit a37ffb8) só pega texto IDÊNTICO** (hash). Quando o modelo varia "Ótimo!" / "Perfeito!" / "Entendi!" no início, todas passam.

**Fix arquitetural (próxima sessão):**

Adicionar lock Redis em pipeline.py:
```python
lock = redis.set(f"blink:lock_pipeline:{conv_key}", "1", nx=True, ex=30)
if not lock:
    # outra requisição já está processando essa conversa
    # opção: enfileirar ou descartar (com log)
    return PipelineResult(sent=False, error="conversation_locked")
```

Isso elimina concorrência por conversa. Lock TTL 30s evita travamento eterno.

**Bug colateral causado por minha cadeia de deploys (lição importante):**

Hoje fiz 12+ commits/deploys em sequência. Cada deploy do Easypanel reinicia o container (~2-5 min downtime). Resultado: **agent ficou OUT 11:33-12:00 BRT (27 min)** — leads que entraram nesse intervalo (Tatiana 11:56, Iara 11:59, Ben Hur 2 11:59) ficaram sem resposta ou com gravação Kommo incompleta.

**Regra de processo:** rate-limit em commits/deploys. Não fazer mais de 2 deploys por hora durante operação ativa. Janela de manutenção = horário sem atendimento.

**Regras de prompt detectadas pra refinar (não imediato):**

1. `_MASTER_INSTRUCTION.md` E2 — frase exemplo "preciso do CPF" é AMBÍGUA quando paciente é bebê/criança. Trocar pra "preciso do CPF do paciente ({{nome_paciente}})".
2. Adicionar regra: "Quando paciente é menor (perfis Bebê 0-2 ou Criança 3-12), CPF é DO PACIENTE — NÃO peça do responsável."
3. Onde "horário comercial" / "seg-sex 8-18h" mora (27 arquivos têm essa string). Blink é 24h — limpar isso do prompt/KB.

---

### 11-J. Caso Kamila lead 24064723 — 3 bugs simultâneos (02/06/2026 11:24 BRT)

**Cenário:**
- 11:21 Stephany (humana) mandou template "Com base em suas preferências... 10/06 09:30 ou 24/06 10:00. Escolha uma opção!"
- 11:23 Kamila respondeu: "3" (paciente quis dizer "3 horários por favor?" ou se confundiu)
- 11:24 Lia mandou **DUAS mensagens IDÊNTICAS** sequenciais: "Kamila, ainda estou buscando os horários disponíveis para quarta-feira de manhã com a Dra. Karla na Asa Norte. Aguarda só mais um pouquinho que já te passo as opções concretas, ok?"
- 11:24 Ariany moveu pra 1-ATENDIMENTO HUMANO

**Bug 1 — Lia ignorou intervenção humana (Stephany):**
Stephany JÁ tinha enviado horários reais. Lia continuou como se nada tivesse acontecido. Camada de detecção "humano enviou template Conclusão / oferta" não pegou esse formato com emoji 1️⃣ 2️⃣.

**Bug 2 — DUPLICAÇÃO: mesma mensagem 2 vezes em <1s.**
Provável falha do dedup no pipeline. Cada inbound do paciente disparou um turn, e ambos geraram mesma resposta sem checar idempotência.

**Bug 3 — "ainda estou buscando" SEM ter buscado.**
Lia escreveu promessa de retorno mas nunca chamou Medware. Frase de espera infinita — paciente nunca recebe os horários reais. É exatamente o mesmo padrão do bug Juliene (24053159) que motivou o filtro `_viola_promete_retorno_humano`. Mas esse filtro está DESLIGADO desde commit 796ba2a (FILTROS_LEGACY=0).

**Lição:** desligar TODOS os filtros legacy sem ativar tool calling ainda foi prematuro. Sem tools, Lia volta a "prometer e não cumprir" que o filtro evitava.

**Próximas ações (não imediato):**
1. Detectar template emoji 1️⃣ 2️⃣ humano antes de gerar resposta (camada 6 ja_handoff)
2. Dedup forte por hash da resposta+conversation_key+5s
3. Confirmar tool calling efetivamente ativo em prod (`LIA_TOOLS_ENABLED=1`)

---

### 11-U. KB limpa de "horário comercial" + Watchdog 24h (04/06/2026, tasks #184/#178)

**Problema histórico (bug Juliene 24053159, 02/06):**
Lia inventava "retorno em horário comercial seg-sex 8h-18h" — frase causava experiência ruim. Blink ATENDE 24h via Lia (e equipe humana em rodízio paralelo).

**Limpeza KB (#184):**
6 arquivos com menção a "horário comercial 8-18h" ajustados:
- `22_agenda_dra_karla.md` linha 69 → "Deixa eu reconsultar a agenda aqui, volto em 1 minuto."
- `34_agenda_dr_fabricio.md` linha 73 → mesma frase
- `38_atestados_e_documentos_medicos.md` linha 19 → "Logo te respondem!"
- `37_escalonamento_humano.md` linha 33 → removido "em horário comercial"
- `08_audio_e_escalonamento.md` linha 56 → removido "em horário comercial"
- `_MASTER_INSTRUCTION.md` linhas 336 e 436 → mantidas (são regras PROIBINDO uso)

**Watchdog 24h (#178):**
`voice_agent/watchdog_lia.py` atualizado:
- Removida restrição seg-sáb 8h-18h — `_eh_horario_comercial()` sempre `True` por default
- Toggle reversa: `WATCHDOG_RESTRINGIR_HORARIO=1` reativa janela antiga
- Novo nível CRÍTICO: `SILENCIO_CRITICO_SEG = 30 * 60` (30 min)
- Configurável via env `WATCHDOG_SILENCIO_CRITICO_SEG`

**Pytest:** `tests/test_watchdog_24h.py` — 6 cenários. **64/64 total verde.**

---

### 11-T. Autonomia total — Cron semanal + Kommo webhook trigger (04/06/2026, tasks #218/#219)

**Origem:** Fábio: "chega de babá. autonomia total".

**PARTE 1 — Cron interno semanal (`voice_agent/cron_interno.py`):**

Worker `_worker_campanha_semanal_loop` adicionado. Checa a cada 30min se é segunda 9h-10h BRT. Se sim + dedup Redis OK + `CAMPANHA_SEMANAL_ENABLED=1` → executa `_executar_campanha_semanal()` que filtra leads por categoria + dispara template aprovado em batch.

**Envs novas (Easypanel → Ambiente):**
- `CAMPANHA_SEMANAL_ENABLED=1` (toggle, default off)
- `CAMPANHA_SEMANAL_CATEGORIA=R` (default R; aceita E, C)
- `CAMPANHA_SEMANAL_MAX=20` (max 200)
- `CAMPANHA_SEMANAL_UNIDADE=Asa Norte` (opcional)
- `CAMPANHA_SEMANAL_MEDICO=Karla` (opcional)

Zero config Easypanel UI cron. Bastam as envs acima + redeploy.

**PARTE 3 — Endpoint `/admin/kommo-trigger-disparar`:**

Recebe webhook do Kommo Automation. Aceita 2 formatos:

1. **JSON body** (preferido):
```json
{ "lead_id": 22982854, "template": "captar_paciente",
  "body_params": ["Déborah", "Maria Teresa", "Águas Claras", "Karla", "09/06 09:00"] }
```

2. **Form-urlencoded** (formato nativo Kommo Automation):
```
leads[update][0][id]=22982854
```

Quando recebe → chama `_disparar_template_aprovado_para_lead()` → dispara template + grava nota Kommo automática.

**Como configurar no Kommo Automation:**
1. Kommo → Configurações → Automações → Add
2. Quando: campo "Disparar Template" = "Sim" (ou status muda pra X)
3. Ação: Webhook HTTP POST
4. URL: `https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-disparar?secret=$WEBHOOK_SECRET`
5. Salvar

**PARTE 2 — Allowlist sandbox Anthropic:** depende da Anthropic adicionar `*.easypanel.host` no proxy allowlist do Cowork. Fora do controle do Blink. Workaround: usar Chrome MCP do Fábio pra fetch direto.

**Pytest:** `tests/test_campanha_semanal_e_kommo_trigger.py` — 8 cenários (toggles, categoria default/custom, max cap, sanity check). **58/58 total verde.**

---

### 11-R. Endpoints batch + categoria — Opção A+C (04/06/2026, tasks #213/#214)

**Origem:** Fábio: "estamos sem atendimento humano, dispara automático".

**Opção A — `/admin/disparar-batch`** (1 curl manda N leads):

```bash
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-batch?secret=$WS" \
  -H "Content-Type: application/json" \
  -d '{"lead_ids": [22982854, 21710873], "dry_run": false, "forcar": true}'
```

Retorna `{total, ok, falhas, dry_run, forcar, detalhes:[{lead_id, ok, telefone, estrategia, motivo}]}`.

**Opção C — `/admin/disparar-categoria`** (filtro inteligente):

```bash
curl "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=R&unidade=Asa%20Norte&max=10&secret=$WS"
```

Categorias suportadas:
- `R` — REAGENDAR / REMARCAÇÃO / FALTOU / DESMARCOU
- `E` — COM CONVÊNIO
- `C` — SEM CONVÊNIO / PARTICULAR

Filtros opcionais: `unidade`, `medico`, `max` (default 30, max 200), `dry_run`.

Excluídos automaticamente: Inas, GDF, Cassi, SulAmerica, Bradesco.

**Cron Easypanel sugerido (1x/semana):**

Easypanel → app `blink/agent` → Crons → Add:
- Nome: `Campanha REAGENDAR Asa Norte`
- Schedule: `0 9 * * 1` (toda segunda 9h BRT)
- Command:
```
curl -fsS -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=R&unidade=Asa%20Norte&max=20&secret=$WEBHOOK_SECRET"
```

**Pytest:** `tests/test_disparar_batch_categoria.py` — 25 cenários (categoria R/E/C + exclusões Inas/GDF/etc + edge cases).

---

### 11-Q. Endpoint `/admin/disparar-lead/{lead_id}` — disparo autônomo (04/06/2026)

**Origem:** task #212. Fábio: "estamos sem atendimento humano, tem que disparar de forma automática e aparecer a mensagem em notas".

**O que faz:**
- Aceita só `lead_id` na URL (path param). Sem precisar montar telefone/nome.
- Busca contato principal via `KommoClient.get_lead_main_contact(lead_id)` (método novo) → retorna `{telefone, nome, status_id}`.
- Normaliza E.164 (prefixo `55` se faltar).
- Monta `SnapshotLead` e chama `dispatch_renovacao(dry_run=false, forcar=true)` por padrão.
- Dispatcher já grava nota Kommo automaticamente com timestamp + canal + estratégia + texto enviado (task #95).

**Como usar:**

```bash
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-lead/{LEAD_ID}?secret=$WEBHOOK_SECRET"
```

Query params opcionais:
- `dry_run=true` → simula sem enviar (debug)
- `forcar=false` → respeita dedup Redis 24h (default ignora)

**Retorno:**
```json
{
  "ok": true,
  "lead_id": 22982854,
  "telefone": "5561...",
  "nome": "...",
  "status_id": 101508307,
  "dispatch_result": { "ok": true, "estrategia_usada": "...", "nota_kommo_id": ... }
}
```

**Erros tratados:**
- Sem telefone no contato → 400 com `info_recebida` pra debug
- Sem kommo_client → 500
- Secret errado → 401

**Pytest:** `tests/test_get_lead_main_contact.py` — 6 cenários (telefone+nome+status, sem contato, lead inexistente, wrapper get_lead_main_phone).

**Diferença vs `/admin/renovacao-dispatch`:** o antigo exige `telefone`, `nome_contato`, `status_id` no querystring (stateless). O novo busca tudo do Kommo — pensado pra uso operacional direto sem montar payload.

---

### 11-P. FIX GAP CRÍTICO 15 DIAS — Lia grava agendamento Medware sozinha (04/06/2026)

**Origem:** task #208. Bug recorrente em 15 dias: Lia confirmava agendamento com paciente, escrevia nota Kommo, mas **NÃO gravava no Medware** — sempre dependia de Stephany/Ariany clicar manualmente.

**Causa raiz:** `voice_agent/tools_lia.py::handle_gravar_agendamento_medware` (linhas 362-381) era um STUB que só escrevia flag Redis `blink:tool_gravacao_solicitada:{convo}` e DELEGAVA pra `executor_agendamento.py` — arquivo que **NUNCA EXISTIU NO REPO**.

**Fix:**
- Adicionados `COD_MEDICO_POR_NOME` (Karla=12080, Fabrício=12081) e `COD_UNIDADE_POR_NOME` (Asa Norte=5, Águas Claras=3) com helpers `cod_medico_por_nome()` / `cod_unidade_por_nome()` aceitando variantes (case, abreviação, com/sem "Dra.").
- `handle_gravar_agendamento_medware` agora chama `medware_client.criar_agendamento()` direto, com args extraídos do `caller_context.known` (nome, CPF, data_nasc, celular, convênio, médico, unidade).
- Dedup Redis 24h via `blink:agendamento_gravado:{convo_key}` — segunda tool call não regrava.
- Sucesso → log `[GRAVAR-MEDWARE] OK convo=X cod_ag=Y med=Z uni=W` + setex Redis.
- Falha Medware → retorna `ResultadoTool(erro="medware_falhou: <motivo>")`, escala humano via circuit breaker existente.
- Exception → `ResultadoTool(erro="medware_exception: ...")` — não quebra conversa.
- Fallback: sem `medware_client` (modo teste), volta a escrever flag Redis legado.

**Validação:**
- Pytest novo `tests/test_gravar_agendamento_medware_real.py` — 15 cenários (maps, sucesso, falha, exception, dedup, fallback).
- Pytest antigo `tests/test_tools_lia.py::TestGravarAgendamento::test_tudo_ok_chama_medware_e_marca_dedup` reescrito.
- **41/41 verde em 0.04s.**

**Riscos pós-deploy (mitigados):**
- Primeiro agendamento real pode dar 400 do Medware → log estruturado + circuit breaker já existente (3 falhas → escala humano).
- CPF duplicado → `criar_agendamento` já trata via `buscar_paciente_por_cpf` (linha 543 de medware.py).
- Convênio fora do PLANO_CODES → retorno `motivo:"convenio_desconhecido"` (Lia sabe escalar).

**Próximas ações pós-merge:**
1. Confirmar `LIA_TOOLS_ENABLED=1` em prod (Easypanel → Ambiente).
2. Smoke E2E com canary lead (1 agendamento + cancel imediato).
3. Monitorar `[GRAVAR-MEDWARE]` em logs primeiras 24h.

---

### 11-O. Enums Kommo são case-sensitive — value exato (04/06/2026)

**Sintoma:** `kommo_update_lead` com `{"ATIVADO IA?": "DESATIVADO"}` ou `{"1260817": 927035}` retornou HTTP 400 `NotSupportedChoice`. Só funcionou com `{"ATIVADO IA?": "Desativado"}` (texto exato como aparece na config do field).

**Regra:** ao passar enum select pelo MCP Kommo:
1. Use o **nome do campo** como chave (case-sensitive: `"ATIVADO IA?"` com `?`).
2. Use o **value text exato** do enum (Title Case como aparece em `kommo_list_custom_fields`).
3. Enum_ids numéricos (927031/927033/927035) **não funcionam** via essa interface — só os textos.

Confirmados em 04/06:
- `"Ativado"` → 927031
- `"Solicitado"` → 927033
- `"Desativado"` → 927035

Aplicado: leads 22703954 + 23235182 (Inas GDF) marcados como `Desativado` pra excluir do motor de reativação.

---

### 11-I. Campo Kommo "ATIVADO IA?" — ID renovado 1260635→1260817 (02/06/2026 tarde)

**Sintoma:** "muitos casos de falta de resposta" reportado pelo Fábio. Lead 24064359 (Ana Caroline) sem resposta há 2h.

**Causa raiz descoberta:** o campo `ATIVADO IA?` foi RECRIADO no Kommo em algum momento. O ID antigo (1260635, hardcoded em `kommo.py::FIELD_ATIVADO_IA`) deixou de existir na API. ID atual é **1260817**. Pipeline write turn-by-turn (webhook.py:2985+3080, pipeline.py:622, reactivation.py:428) seguia tentando gravar no ID morto — fail silently.

**Resultado prático:** equipe humana perdeu visibilidade de IA on/off por lead. Bug Elisa-like se acumulando invisivelmente.

**Fix (commit `3adb920`):**

```python
FIELD_ATIVADO_IA = (1260817, {
    "ATIVADO": 927031, "ATIVA": 927031, "ATIVO": 927031, "ON": 927031,
    "SOLICITADO": 927033, "SOLICITAR": 927033, "PENDENTE": 927033,
    "DESATIVADO": 927035, "DESATIVADA": 927035, "OFF": 927035,
})
```

Type confirmado: `select` (era `multiselect` no comentário antigo).

**Como descobrir ID de campo Kommo deletado/renovado:**
1. Abrir lead no Kommo via Chrome
2. JavaScript no console: `document.querySelectorAll('[class*=linked-form__field]').forEach(e => console.log(e.getAttribute('data-id'), e.textContent.substring(0,50)))`
3. Confirmar via `GET /api/v4/leads/custom_fields/{id}` que retorna o JSON completo do campo

**Lição de processo:** quando código usa `FIELD_X = (id, enums)` hardcoded, monitorar com `/admin/healthz` se o ID ainda existe na API custom_fields. Se Kommo retornar 404 no field_id, ALERTAR no Slack — código está gravando em buraco.

---

### 11-H. Escopos PAT GitHub — `repo` + `workflow` (02/06/2026 tarde)

**Lição:** push falhou com `remote rejected ... refusing to allow a Personal Access Token to create or update workflow .github/workflows/test.yml without workflow scope`.

Causa: token gerado só com escopo `repo`. GitHub Actions YML em `.github/workflows/` exige escopo **independente** chamado `workflow` — `repo` NÃO o inclui automaticamente.

**Regra para todo PAT deste repo** (https://github.com/settings/tokens/new):
- ☑ `repo` (caixa pai inteira)
- ☑ `workflow` (caixa separada logo abaixo de repo)

Sem `workflow`, qualquer commit que toque `.github/workflows/*.yml` é rejeitado no servidor mesmo com `repo` marcado.

Também: token comprometido em chat = revogar imediatamente após uso. Token `ghp_WH3VgKbW3mc4...` foi exposto e deve ser deletado.

---

### 11-E. Regra "shadow mode" — defesa nova SÓ entra em prod após validação real (02/06/2026)

**Origem do princípio:** sessão 02/06 manhã. Juiz Haiku 4.5
adversarial (ligado 01/06 noite com `JUIZ_HAIKU_ENABLED=1`, limiar
70) vetou em série respostas legítimas da Lia. Leads afetados:
Larissa/Lis/Samuel (10513560) — 2 fallback genéricos seguidos.
Adriana (24063769) — 4 turnos de enrolação antes de responder valor.
Causa: pytest unitário passou, mas juiz não foi testado com 100+
turnos reais. LIMIAR=70 em Haiku 4.5 deu falso positivo demais em
casos borderline normais.

**Regra a partir de 02/06:** nenhuma camada nova de defesa que
SUBSTITUI resposta da Lia entra em prod sem:

1. Rodar em **modo shadow** por pelo menos 24h: apenas LOGA o que
   substituiria, sem substituir de fato.
2. Métrica de aprovação: < 2% dos turnos teriam sido substituídos.
3. Revisão dos textos substituídos pra ver se são falsos positivos.
4. Aprovação explícita do Fábio antes de ativar `ENABLED=1`.

Aplicação retroativa: `JUIZ_HAIKU_ENABLED=0` e `MEMORIA_BUGS_ENABLED=0`
em prod desde 02/06 ~9h BRT (desligados via Easypanel manualmente).
Defesa atual = 13 filtros regex + retry Medware + circuit breaker
+ checklist 4 dados mínimos + state machine FSM. Suficiente.

### 11-F. Bug recorrente "pergunta redundante de convênio" — Adriana (02/06/2026)

Lead 24063769. Paciente perguntou valor. Lia fez 4 turnos pedindo
"com ou sem convênio?" quando `ctx.known.convenio = "Não se aplica"`
já estava no Kommo. Triagem ignorou o ctx.

**Fix:**
- Artigo KB `voice_agent/knowledge_base/39_valores_consulta.md` com
  tabela oficial R$ 611 Karla / R$ 297 Fabrício catarata / R$ 800 SDP.
- Filtro `_viola_pergunta_redundante_convenio(text, ctx)` em
  `responder.py`: regex detecta "com ou sem convênio" + ctx tem
  convenio → substitui.
- `_gerar_resposta_valor_sem_repergunta(ctx)`: usa ctx (médico +
  especialidade + convênio) pra responder com R$ direto, sem
  repergunta. Convênio aceito = "coberta pelo seu plano". Particular
  = R$ exato + Pix.
- 13 testes em `tests/test_pergunta_redundante_convenio.py`.

### 11-G. CI/CD gate de regressão — GitHub Actions (02/06/2026)

**Origem:** Fábio "como evitar Lia regredir como aluno que volta a
errar 1ª série depois de chegar na 3ª".

Hoje pytest roda só manual no Mac do Fábio. Auto-deploy Easypanel
faz docker build sem rodar pytest. Resultado: regressão chegava em
prod sem barrar.

**Fix:** `.github/workflows/test.yml` — roda pytest completo + lint
em cada push pra main + PR. Status check do GitHub. Easypanel pode
ser configurado pra respeitar check (já tem auto-deploy ON desde
01/06 → trigger só se main verde). Memória ativa preventiva.

### 11-D. ja_agendado — 5 camadas (02/06/2026 manhã)

Bug recorrente: atendente humano agenda no Medware mas esquece de
mover etapa / preencher 1.DIA CONSULTA. Lia ficava cega e oferecia
slot novo. Clínica reportou como bug Blink. Solução em 5 camadas
independentes, em OR (qualquer uma dispara `ja_agendado=True`):

| Camada | Fonte | Cobre |
|---|---|---|
| 1 | `status_id ∈ ST_JA_AGENDADO` | 5-AGENDADO, 6-CONFIRMAR, 7.CONFIRMADO, 8-REALIZADO, 10-PRÓXIMA CONSULTA |
| 2 | `1.DIA CONSULTA` futuro (field 1255723) | Bug Aurora original |
| 3 | Nota humana com "agendei + data" (72h) | Atendente escreveu nota livre |
| 4 | **Template "Conclusão de Agendamento"** (parser regex Blink) | Caso Graziela/Enzo do Fábio |
| 5 | Histórico genérico (palavra-chave conclusão + data, humano) | Fallback pra mensagem improvisada |

Funções principais em `voice_agent/kommo.py`:
- `_ja_agendado_por_nota_humana(notas, janela_h=72)` → camada 3
- `detectar_template_conclusao_agendamento(texto)` → camada 4 (extrai
  paciente, médico, especialidade, convênio, unidade, data, hora;
  auto-popula `known.*` sem sobrescrever)
- `detectar_conclusao_no_historico(mensagens, janela_h=72)` → camada 5
- `get_lead_notes(lead_id)` + `get_lead_messages(lead_id)` → varredura

Cenário canary #15 "Graziela/Enzo" replica o fluxo: atendente envia
template → paciente responde "1. Tudo Correto" → Lia confirma data
marcada, não refaz triagem.

Pytest: 36 testes (14 template + 12 nota humana + 10 histórico).

### 11-B. Easypanel — Deploy automático e envs novos (01/06/2026 noite)

- **Auto-Deploy GitHub→Easypanel ATIVADO** em 01/06/2026 ~21:00 BRT. Push em `main` agora dispara build automático em 2-5min. Antes estava off → commits ficavam presos no Mac.
- **Envs novas no agent** (Ambiente):
  - `SMOKE_ENABLED=1` + `SMOKE_INTERVALO_SEG=3600` — smoke contínuo bate 6 cenários core de 1 em 1h.
  - `JUIZ_HAIKU_ENABLED=1` + `JUIZ_HAIKU_LIMIAR=70` — juiz adversarial Haiku 4.5 julga cada resposta da Lia (#157, módulo `voice_agent/juiz_adversarial.py`).
  - `LIA_TOOLS_ENABLED=1` — tool calling estruturado.
- **Validação pós-deploy** (rodar nessa ordem):
  1. `curl /health` — espera 200 OK.
  2. `curl /admin/healthz?secret=$WS` — espera `integrations.kommo/medware/wa_cloud/redis: true`.
  3. `curl /admin/smoke-tick` — espera `{"total":6,"ok":6}`.
  4. `curl /admin/audit/frios-com-agendamento?limit=500` — lista leads em 2.LEADS FRIO que têm `1.DIA CONSULTA` preenchido (inconsistência pra mover pra 5-AGENDADO).

### 11-C. Juiz adversarial Haiku — segundo olhar pré-envio (01/06/2026 noite)

Módulo `voice_agent/juiz_adversarial.py`. Origem: discussão Fábio "como aproveitar ML pra defesa contra bug?". Os 13 filtros regex em `responder.py` são reativos — cada bug novo escapa. Haiku 4.5 dá segundo olhar semântico:

- Recebe (resposta da Lia, ctx do lead, mensagem do paciente).
- Devolve JSON `{risco: 0-100, motivos: [...], recomendado: enviar|substituir}`.
- Se `risco >= LIMIAR` (default 70), Lia troca pelo `FALLBACK_SUBSTITUICAO` seguro.
- Erro/timeout não bloqueia — Lia segue.
- Custo ~$0.001/turno (~$0.20/dia em volume Blink).
- Veredictos com risco >= 30 ficam em Redis `blink:juiz:veredicto:{lead_id}:{ts}` por 7 dias pra análise.

Plugado em `_scrub_prohibited` como filtro #4 (último, depois dos 13 regex). Pytest 23 casos: `tests/test_juiz_adversarial.py`.

### 11-A. Rotação de chaves — histórico (01/06/2026)

- **OPENAI_API_KEY rotacionada** em 01/06/2026 14:33 BRT.
  - Antiga `sk-proj-VDF6Q...WcIA` (criada 19/05/2026) — **REVOGADA via OpenAI dashboard.**
  - Nova `sk-proj-EbB4M...DyMA` (nome `blink-agent-rotacao-01-06-2026`, tracking `key_xDdiVvnrWck3d…`) — ativa.
  - Substituída na linha 1 do bloco "Variáveis de Ambiente" do app `blink/agent` no Easypanel.
  - Validação pós-rotação: `/health` 200 OK, `/admin/smoke-tick` 6/6 verde em 26,7s.
- **Procedimento padrão de rotação** (próximas vezes):
  1. OpenAI dashboard → Create new secret key com nome `blink-agent-rotacao-DD-MM-AAAA`.
  2. Copiar imediatamente (só aparece 1 vez).
  3. Easypanel → `blink/agent` → Ambiente → substituir linha `OPENAI_API_KEY=`.
  4. Salvar → Implantar → aguardar ~60s.
  5. `curl /health` + `curl /admin/smoke-tick` — esperar 6/6.
  6. Voltar pro OpenAI → revogar chave antiga.
  7. Registrar nesta seção (data + sufixo terminal da chave antiga e nova).

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

### 11-X. Reativação automática IA por mudança de etapa (05/06/2026, task #233)

**Origem:** Fábio 05/06 — sugestão arquitetural depois de inspecionar lead
10513560 (Larissa/Lis/Samuel) que estava em 6-CONFIRMAR com
`ATIVADO IA = Desativado` há semanas porque humano tinha enviado msg
manual lá em 09/04/2026 e ninguém reativou.

**Fluxo completo (3 partes):**

**Parte 1 — Handoff humano move pra 1-ATENDIMENTO HUMANO** (`pipeline.py`):
quando `agent_paused_for_lead` retorna motivo (humano detectado), além de
desativar IA, MOVE o lead pra status_id 106563343 (1-ATENDIMENTO HUMANO).
Equipe vê concentrado nessa etapa o que precisa terminar. Exceções: lead
já está lá ou em etapa final (142/143/91486864).

**Parte 2 — Webhook reativa ao sair de ATENDIMENTO HUMANO** (`webhook.py`):
endpoint `POST/GET /admin/kommo-trigger-status-change` recebe webhook do
Kommo "Status do lead alterado". Se nova etapa ∈ STATUS_ATIVOS_IA
(0-ENTRADA, 0-a classificar, 2.LEADS FRIO, 3-AGENDAR, 4.REAGENDAR,
5-AGENDADO, 6-CONFIRMAR, 7.CONFIRMADO, 7.1-NO-SHOW) → seta
`ATIVADO IA = Ativado`. Etapa "1-ATENDIMENTO HUMANO" NÃO está na lista
(humano ainda atuando lá).

**Parte 3 — Batch one-shot pra limpar acumulado** (`webhook.py`):
endpoint `/admin/reativar-ia-batch` varre TODOS leads atuais em etapas
ativas com `ATIVADO IA = Desativado` e ativa em massa. Dry-run default.

**Webhook Kommo a configurar (após push + deploy):**
- URL: `https://blink-agent.6prkfn.easypanel.host/admin/kommo-trigger-status-change`
- Evento: **Status do lead alterado**

**Pytest:** `tests/test_reativacao_ia_automatica.py` — 12 cenários
(etapas ativas, etapa humana ignorada, fechadas ignoradas, caso real
lead Larissa 10513560).

---

### 11-W. 4 campos Kommo visíveis na lista + webhook humano (05/06/2026, tasks #231/#232)

**Origem:** Fábio adicionou 3 colunas customs na lista do funil ATENDE
(STATUS CONVERSA + ULTIMA MSG OUTBOUND + PROXIMA ACAO) e mais 2 campos
date_time (ÚLTIMA MENS LIA + ULTIMA MENS HUMANO) pra equipe humana
enxergar estado de cada lead sem abrir o card.

**Field IDs:**
| Campo | ID | Tipo | Preenchido por |
|---|---|---|---|
| STATUS CONVERSA | 1260854 | select 15 enums | Lia a cada turn |
| ULTIMA MSG OUTBOUND | 1260856 | textarea | Lia a cada turn |
| PROXIMA ACAO | 1260858 | select 12 enums | Lia a cada turn |
| ÚLTIMA MENS LIA | 1260860 | date_time | Lia a cada turn |
| ULTIMA MENS HUMANO | 1260862 | date_time | webhook Kommo |

Enums confirmados via API em `voice_agent/campos_acompanhamento.py`.

**Mapeamento estado FSM → enums** (em `mapear_status_e_proxima`):
| FSM | STATUS CONVERSA | PROXIMA ACAO |
|---|---|---|
| TRIAGEM | coletando_dados | coletar_dados_minimos |
| DADOS | coletando_dados | coletar_dados_minimos |
| CONVENIO | validando_convenio | validar_convenio |
| AGENDA | agenda_oferecida | aguardar_resposta_paciente |
| CONFIRMACAO | confirmando_horario | aguardar_resposta_paciente |
| GRAVACAO | gravando_medware | aguardar_resposta_paciente |
| POS_GRAVACAO | agendado_aguarda_consulta | confirmar_horario_d-1 |

Overrides: `ja_agendado=True`, `convenio_nao_aceito=True`,
`cobrar_sinal=True`, `paciente_desistiu=True` vencem o caminho FSM.

**Onde código pluga:**
- `voice_agent/pipeline.py::_sync_kommo_safely` resolve FSM atual via
  `FSMManager.get(convo_key)`, chama `campos_acompanhamento.montar_dict_campos()`
  e injeta no `update_lead_fields()`.
- `voice_agent/kommo.py::update_lead_fields` processa 5 chaves novas:
  `status_conversa`, `proxima_acao`, `ultima_msg_outbound`, `ts_ultima_msg_lia`,
  `ts_ultima_msg_humano`.

**Webhook humano** (task #232):
- Endpoint: `POST /admin/kommo-trigger-msg-humano`
- Auth: secret OPCIONAL (operação não-destrutiva, só carimba timestamp)
- Aceita JSON `{lead_id: N}` OU form `leads[update][0][id]=N`
- Atualiza `ULTIMA MENS HUMANO` com `int(time.time())`
- Configurado em Kommo → Webhooks → URL acima + evento "Mensagem de saída enviada"

**IMPORTANTE — Bug C-09:** Kommo VALIDA URL antes de salvar webhook
(faz GET no endpoint). Endpoint precisa estar LIVE em prod antes de
configurar o webhook. Sequência: push → deploy → confirma 200 → cria webhook.

**Pytest:** `tests/test_campos_acompanhamento.py` — 25 cenários (enums
corretos, mapeamento FSM completo, formatador timestamp, overrides).

---

### 11-V. Dedup leads frio por telefone — endpoint server-side (05/06/2026, task #228)

**Origem:** Fábio 05/06 — lead Lene 22398836 (96121-411) tem 7+ leads
duplicados no funil 2.LEADS FRIO. Cada família = 1 número → 1 lead.

**Endpoint:** `POST/GET /admin/deduplicar-leads-frio`

Params: `dry_run` (default true), `max_leads` (default 500, max 800),
`status_id` (default 101508307), `status_destino` (default 143).

**Lógica:** enriquece cada lead com telefone+notas_count+campos_preenchidos+updated_at,
agrupa por telefone normalizado, escolhe MASTER via score `notas×10 + campos×5 +
updated_at/86400×0.5` (desempate por id maior). Duplicados ganham rename
`[DUP→{master_id}] {nome}` + nota explicativa + move pra Closed-lost (143).
**Reversível** — não deleta.

**Comandos:**
```bash
# Dry-run (preview):
curl "https://blink-agent.6prkfn.easypanel.host/admin/deduplicar-leads-frio?dry_run=true&max_leads=500&secret=$WEBHOOK_SECRET" | jq

# Aplicar:
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/deduplicar-leads-frio?dry_run=false&max_leads=500&secret=$WEBHOOK_SECRET" | jq
```

**Pytest:** `tests/test_deduplicar_leads.py` — 19 cenários.

---

## 16-A. PROTOCOLO ANTI-OMISSÃO E ANTI-REPETIÇÃO (04/06/2026)

**OBRIGATÓRIO**: ler `lia-atendimento-blink/memoria/protocolo-claude-cowork.md` no início de toda sessão Cowork. Esse arquivo contém:

- **Checklist 10 itens pré-ação operacional** (Boeing rule) — verificar TODAS antes de enviar msg WhatsApp / gravar Medware / ofertar slot
- **Anti-desculpability** — regras de comunicação (não dizer "vou consultar e volto" sem voltar, não pedir Fábio rodar curl quando posso usar MCP, etc)
- **Bugs C-01 a C-07 indexados** — bugs MEUS (Claude Cowork operando), não da Lia. NÃO REPETIR.
- **Protocolo de indexação** — toda vez que cometo bug operacional, adiciono entrada Bug C-NN ANTES de seguir
- **Ritual de início de sessão** — leitura obrigatória

Origem: Fábio 04/06/2026 — "Já passou o tempo de errar a mesma coisa. Demonstra falta de qualidade." Zero tolerância pra bugs repetidos.

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

**Handoff mais recente**: `HANDOFF_02-06_MANHA_PARA_TARDE_2026.md` (sessão prática — juiz Haiku desligado por falso positivo, fix Adriana, regra shadow mode, CI GitHub Actions).

---

Última atualização: 01/06/2026 22:00 — sessão dia/noite. Bug Esther
24060221 (re-oferta de slot pós-AGENDADO via handler de imagem)
blindado com filtro `_viola_oferta_apos_agendado` (commit `e636a84`).
Decisão Fábio: só Lia em notas Kommo, paciente sai do feed (commit
`689314c`). Endpoint `/admin/audit/frios-com-agendamento` pra contar
372 leads em 2.LEADS FRIO com `1.DIA CONSULTA` preenchido (commit
`1840549`). **Virada arquitetural**: juiz adversarial Haiku 4.5
pré-envio em `voice_agent/juiz_adversarial.py` — defesa semântica em
vez de só regex, ~$0.001/turno, opt-in via `JUIZ_HAIKU_ENABLED=1`
(commit `d8f6167`, 23 testes). Easypanel: **Auto-Deploy GitHub
ATIVADO**, envs novos `SMOKE_ENABLED=1`, `JUIZ_HAIKU_ENABLED=1`,
`JUIZ_HAIKU_LIMIAR=70`. Total **771 testes verdes** (+187 desde
31/05). Smoke prod 6/6 em 19,3s. 4 commits aguardando push do Fábio
pra entrar em prod.
