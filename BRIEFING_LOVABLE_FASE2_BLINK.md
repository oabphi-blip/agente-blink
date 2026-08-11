**BLINK OFTALMOLOGIA**

**Briefing Tecnico Lovable Fase 2**

*Ponte arquitetural Lovable \<-\> Agent Lia \<-\> Kommo/Medware*

Versao 1.0 - 27/06/2026

Autor: Fabio Philipe Martins (Diretoria Blink) + Claude Cowork

Destinatario: equipe Lovable (build agent)

**1. Sumario Executivo**

A Blink Oftalmologia opera um agente conversacional (Lia) que atende
pacientes 24h via WhatsApp, integrado a 3 sistemas: Kommo (CRM), Medware
(ERP clinico) e Meta Cloud (WhatsApp). Apos cerca de 30 dias de
producao, 4 padroes de falha persistem mesmo apos multiplas correcoes:

  - Incoerencia na retomada de mensagens enviadas pelo humano - Lia
    ignora o historico humano-paciente e refaz triagem (caso
    Larissa/Lis/Samuel).

  - Incoerencia apos o agendamento - Lia escreve respostas
    contraditorias em leads ja em 5-AGENDADO. Caso Thamilla 23811372:
    afirma consulta confirmada as 11:26 e as 21:33 escreve 'AMIL nao
    credenciado, encerro?'.

  - Falta de envio confiavel de disponibilidade de agenda - Lia diz
    'deixa eu reconsultar a agenda' e nunca volta com slots reais. Caso
    Victor 24147566: 12 promessas vazias em 12 dias.

  - Falta de gravacao consistente - Bug C-12 (Kommo retorna success:true
    sem gravar) e Fix \#208 (Lia nao grava Medware autonomamente,
    depende de intervencao humana ou Cowork).

Este briefing propoe uma arquitetura em 4 fases (\~3 semanas) onde o
Lovable atua como camada de dados, cache e regras de negocio entre o
agente Python (Lia) e os sistemas finais. O agente Lia continua sendo o
cerebro conversacional; o Lovable vira o backend de dados que ele
consome via 2 endpoints HTTP autenticados.

**Resultado esperado pos-implementacao:**

  - Bug Victor (oferta de slot) - resolvido em 95%.

  - Bug Thamilla (memoria/coerencia) - resolvido em 70%.

  - Bug C-12 e \#208 (gravacao) - resolvidos em 100% por design.

  - Bug C-42 (pos-agendamento) - resolvido em 100% por design.

*Os 5% e 30% que restam sao limitacoes arquiteturais do agente Python
atual (race condition entre turns paralelos - Bug \#183) que ainda
precisam de pipeline\_lock no pipeline.py. Lovable nao resolve essa
parte e nem deve tentar.*

**2. Contexto Operacional Atual**

**2.1. Arquitetura real (nao a teorica)**

Quem responde o paciente HOJE nao e o Salesbot/AI do Kommo. E:

  - Agente Python (voice\_agent/) rodando em container Docker no
    Easypanel.

  - Webhook do Meta WhatsApp Cloud (8133) ou Evolution API (0710)
    entrega cada mensagem inbound no agent.

  - Agent chama Anthropic Claude (Sonnet 4.5 / Opus 4.6) com prompt
    mestre em \_MASTER\_INSTRUCTION.md + tools estruturadas + filtros
    reativos pos-geracao.

  - Agent chama Medware diretamente via medware.py (com cache Redis
    5min, retry 1x fail-fast, circuit breaker 3 falhas escalando
    humano).

  - Kommo serve como CRM espelho: humano ve historico, intervem manual,
    atualiza campos via webhooks bidirecionais.

*O Salesbot AI nativo do Kommo esta desativado desde maio/2026.*

**2.2. Os 4 problemas em detalhe**

**2.2.1. Memoria entre Lia e humano (Bug Thamilla 23811372)**

Em 26/06/2026, a Lia escreveu 2 mensagens diretamente contraditorias num
lead ja em 5-AGENDADO:

<table>
<tbody>
<tr class="odd">
<td><p>26/06 11:26 - Lia (WhatsApp):</p>
<p>"Sua consulta com a Dra. Karla Delalibera pelo Saude Caixa esta</p>
<p>confirmada para quinta-feira 02/07/2026 as 16:30 na unidade</p>
<p>Aguas Claras." CORRETO</p>
<p>26/06 21:33 - Lia (WhatsApp):</p>
<p>"Thamilla, preciso te corrigir uma informacao: o AMIL nao esta</p>
<p>credenciado na nossa rede... Como prefere seguir?</p>
<p>1) Seguir sem convenio</p>
<p>2) Somente com convenio (encerro o atendimento aqui)"</p></td>
</tr>
</tbody>
</table>

Causa raiz: o campo Kommo N ACEITO CONVENIO=Amil (historico de meses
atras) foi lido como sinal do turn atual. O caller\_context.py do agent
mistura snapshots de momentos diferentes sem timestamping.

**2.2.2. Disponibilidade de agenda (Bug Victor 24147566)**

De 13/06 a 25/06, em 12 oportunidades, a Lia escreveu variantes de:

<table>
<tbody>
<tr class="odd">
<td><p>"Deixa eu consultar a agenda real aqui pra voce - volto em 1 minuto."</p>
<p>"Vou buscar os horarios disponiveis. Me da um minutinho."</p>
<p>"Desculpa a demora, a agenda esta com lentidao no momento."</p>
<p>"Estou trabalhando para conseguir os horarios disponiveis."</p>
<p>"Vou priorizar 16/06 na busca."</p>
<p>... 7 outras variantes</p></td>
</tr>
</tbody>
</table>

E nunca voltou com slots concretos. Em 11 das 12 vezes, atendente humana
(Ariany/Stephany) interveio manual.

Causa raiz: a chamada Medware tem latencia variavel (3-15s) e timeout do
agent e 12s. Quando estora, agent escapa pra texto livre. Filtros
reativos (\_viola\_oferta\_agenda) existem mas estao atras de gate em
prod (FILTROS\_LEGACY=0).

**2.2.3. Pos-agendamento (Bug C-42)**

Em status 5-AGENDADO, a Lia nao tem motivo legitimo pra rodar o fluxo de
triagem inicial, mas continua entrando nele. Cada turn le fields do
Kommo com semantica errada e gera 'opcoes' invalidas como encerrar
atendimento de paciente ja com consulta marcada.

*Fix imediato (commit 323bbb7, 26/06): adicionados
5-AGENDADO/6-CONFIRMAR/7.CONFIRMADO ao set \_STATUS\_INATIVOS\_IA.
Quando lead muda pra essas etapas, ATIVADO IA=Desativado
automaticamente. Tampao - confirmacao D-1 vira responsabilidade humana
ate filtros C-42 reativos estarem prontos.*

**2.2.4. Gravacao (Bug C-12 + Fix \#208)**

Dois sub-problemas independentes:

1.  Bug C-12: MCP kommo\_update\_lead retorna success:true mas
    custom\_fields\_values fica vazio. Workaround atual: PATCH direto
    via Chrome MCP.

2.  Fix \#208: handle\_gravar\_agendamento\_medware em tools\_lia.py era
    um stub que escrevia flag Redis e delegava pra
    executor\_agendamento.py (arquivo que NUNCA existiu). Por 15 dias
    seguidos a Lia confirmava agendamento mas nao gravava nada no
    Medware. Caso Milena 24182212 (20/06): bebe 7 meses, trauma ocular,
    urgencia - agendamento gravado manual pelo Cowork via
    mcp\_\_medware\_\_agendar\_encaixe.

**3. Arquitetura Recomendada**

**3.1. Visao de 3 hops**

Substituir o fluxo atual:

<table>
<tbody>
<tr class="odd">
<td><p>ATUAL:</p>
<p>Paciente &lt;-&gt; WhatsApp &lt;-&gt; Agent Python &lt;-&gt; Kommo (fragil)</p>
<p>&lt;-&gt; Medware (lento)</p>
<p>&lt;-&gt; Redis (cache local)</p></td>
</tr>
</tbody>
</table>

Por:

<table>
<tbody>
<tr class="odd">
<td><p>PROPOSTO:</p>
<p>Paciente &lt;-&gt; WhatsApp &lt;-&gt; Agent Python &lt;-&gt; Lovable Backend</p>
<p>v (cron)</p>
<p>Supabase</p>
<p>^ (sync)</p>
<p>Kommo + Medware</p></td>
</tr>
</tbody>
</table>

**Pontos importantes da nova arquitetura:**

  - Agent Python continua intacto como cerebro conversacional. So muda o
    que ele consome via HTTP.

  - Lovable nao recebe webhook direto do WhatsApp - quem recebe e o
    agent Python. Lovable e backend de dados que o agent consulta.

  - Kommo e Medware viram fontes de origem, sincronizadas em batch pelo
    Lovable. Acesso direto a eles e excecao (so pra escritas que
    precisam de blindagem).

  - Supabase Postgres e a fonte unica de verdade pra estado consolidado
    de paciente.

**3.2. Decisoes arquiteturais nao-obvias**

**3.2.1. Endpoint publico assinado (nao publico de fato)**

Todo endpoint Lovable exposto pra o agent Python tem autenticacao por
header:

<table>
<tbody>
<tr class="odd">
<td><p>Header obrigatorio:</p>
<p>X-Blink-API-Key: &lt;secret&gt;</p>
<p>Secret reutiliza o KOMMO_WEBHOOK_SECRET que ja esta no</p>
<p>Supabase Secrets (b035819d617d... - 64 chars hex).</p>
<p>Endpoint sem esse header retorna 401 Unauthorized.</p></td>
</tr>
</tbody>
</table>

*Sem isso, concorrentes scrapeiam a agenda da Blink em segundos.*

**3.2.2. Tabela events append-only (nao UPDATE em patients)**

Toda mudanca de estado de paciente vira UM evento na tabela events. A
tabela patients e apenas snapshot consolidado (view materializada),
nunca editada diretamente.

Vantagem: rastreabilidade temporal completa. Quando paciente reclama
'mas eu nao pedi AMIL', ve-se em SQL exatamente quem registrou AMIL,
quando e a partir de qual mensagem.

**3.2.3. Shadow mode obrigatorio por 48h antes de cada switch**

Toda nova entidade (endpoint, tabela, regra) entra primeiro em SHADOW:
agent chama o NOVO e o ANTIGO em paralelo, compara resultados, loga
divergencias. So faz switch quando divergencia menor que 1% por 48h
consecutivas.

*Regra introduzida no projeto por incidente do Juiz Haiku 4.5 (Bug
02/06/2026): defesa nova vetando respostas legitimas em producao sem
validacao real.*

**4. Fase 1 - Endpoint Disponibilidade de Agenda**

*Duracao estimada: 3 dias uteis. Resolve 95% do Bug Victor.*

**4.1. Objetivo**

Substituir a chamada direta do agent Python ao Medware (latencia 3-15s)
por chamada ao Lovable (latencia alvo menor que 200ms) que serve da
tabela medware\_agenda previamente sincronizada.

**4.2. Schema do endpoint**

**4.2.1. Request**

<table>
<tbody>
<tr class="odd">
<td><p>GET /api/public/agenda/disponiveis</p>
<p>Headers:</p>
<p>X-Blink-API-Key: &lt;secret&gt;</p>
<p>Accept: application/json</p>
<p>Query string:</p>
<p>medico string obrigatorio karla | fabricio</p>
<p>unidade string obrigatorio asa_norte | aguas_claras</p>
<p>janela_dias int opcional default 14, max 30</p>
<p>hora_inicio string opcional default 07:00 (HH:MM)</p>
<p>hora_fim string opcional default 19:00 (HH:MM)</p>
<p>convenio string opcional ver lista canonica abaixo</p>
<p>lead_id int opcional pra filtrar slots ja</p>
<p>ofertados a esse lead</p>
<p>(regra E6-B)</p></td>
</tr>
</tbody>
</table>

**4.2.2. Response 200 OK**

<table>
<tbody>
<tr class="odd">
<td><p>{</p>
<p>"ok": true,</p>
<p>"slots": [</p>
<p>{</p>
<p>"data_iso": "2026-07-02",</p>
<p>"hora": "10:30",</p>
<p>"cod_agenda": 4,</p>
<p>"cod_medico": 12080,</p>
<p>"cod_unidade": 5,</p>
<p>"duracao_min": 30,</p>
<p>"especialidade": "Oftalmologia Geral"</p>
<p>}</p>
<p>],</p>
<p>"metadata": {</p>
<p>"total_disponivel": 8,</p>
<p>"janela_inicio": "2026-06-27",</p>
<p>"janela_fim": "2026-06-30",</p>
<p>"cache_age_seconds": 142,</p>
<p>"ultimo_sync_medware": "2026-06-27T13:55:00Z"</p>
<p>}</p>
<p>}</p></td>
</tr>
</tbody>
</table>

**4.2.3. Response 503 (Medware indisponivel ha mais de 10min)**

<table>
<tbody>
<tr class="odd">
<td><p>{</p>
<p>"ok": false,</p>
<p>"erro": "medware_indisponivel",</p>
<p>"ultimo_sync_ok": "2026-06-27T10:30:00Z",</p>
<p>"minutos_desde_ultimo_sync": 32,</p>
<p>"acao_recomendada": "escalar_humano"</p>
<p>}</p></td>
</tr>
</tbody>
</table>

*Importante: 503 com ultimo\_sync\_ok e DIFERENTE de 200 com slots
vazios. O agent Lia precisa distinguir esses 2 casos pra escolher a
mensagem certa.*

**4.3. Regras de negocio aplicadas no servidor**

3.  Karla Delalibera atende: seg/qua/sex em Asa Norte; ter/qui em Aguas
    Claras.

4.  Fabricio Freitas atende: ter/qui em Aguas Claras + Asa Norte
    conforme escala mensal.

5.  Excluir slots entre 12:00 e 13:00 (almoco).

6.  Excluir slots com convenio incompativel: paciente Saude Caixa nao ve
    slot reservado a particular se medico restringiu.

7.  Excluir slots em blink:slots\_ja\_ofertados:{lead\_id} (Regra E6-B -
    10min de reserva temporaria).

8.  Excluir slots em dias de ferias do medico (consultar tabela
    medico\_ferias).

9.  Default ordenacao: data crescente, hora crescente (slot mais proximo
    primeiro).

**4.4. Tabelas Supabase necessarias**

<table>
<tbody>
<tr class="odd">
<td><p>-- 1. Espelho da agenda Medware (sincronizado por cron)</p>
<p>CREATE TABLE medware_agenda (</p>
<p>agenda_id BIGSERIAL PRIMARY KEY,</p>
<p>cod_agenda INT NOT NULL,</p>
<p>cod_medico INT NOT NULL,</p>
<p>cod_unidade INT NOT NULL,</p>
<p>data DATE NOT NULL,</p>
<p>hora TIME NOT NULL,</p>
<p>duracao_min INT DEFAULT 30,</p>
<p>especialidade TEXT,</p>
<p>status TEXT DEFAULT 'disponivel',</p>
<p>cod_paciente_reservado INT,</p>
<p>medware_sync_ts TIMESTAMPTZ DEFAULT NOW(),</p>
<p>UNIQUE(cod_medico, cod_unidade, data, hora)</p>
<p>);</p>
<p>CREATE INDEX agenda_data_med ON medware_agenda(data, cod_medico);</p>
<p>-- 2. Ferias e escala dos medicos (config manual + cron)</p>
<p>CREATE TABLE medico_ferias (</p>
<p>id BIGSERIAL PRIMARY KEY,</p>
<p>cod_medico INT,</p>
<p>data_inicio DATE,</p>
<p>data_fim DATE,</p>
<p>motivo TEXT</p>
<p>);</p>
<p>-- 3. Log de sincronizacoes Medware (saude do cron)</p>
<p>CREATE TABLE medware_sync_log (</p>
<p>sync_id BIGSERIAL PRIMARY KEY,</p>
<p>started_at TIMESTAMPTZ DEFAULT NOW(),</p>
<p>ended_at TIMESTAMPTZ,</p>
<p>sucesso BOOLEAN,</p>
<p>slots_atualizados INT,</p>
<p>erro TEXT</p>
<p>);</p></td>
</tr>
</tbody>
</table>

**4.5. Sincronizacao Medware -\> Supabase**

  - Cron a cada 5 minutos chama Medware Agenda/Listar pra janela de 30
    dias.

  - Faz upsert na tabela medware\_agenda por chave (cod\_medico,
    cod\_unidade, data, hora).

  - Grava resultado em medware\_sync\_log (saude monitoravel).

  - Se 3 sincronizacoes consecutivas falharem, alerta no Slack
    \#bugs-agent automaticamente.

**4.6. Metricas pos-deploy (alvos)**

|                                               |                 |                     |
| --------------------------------------------- | --------------- | ------------------- |
| **Metrica**                                   | **Antes**       | **Alvo pos-Fase-1** |
| Latencia media de 'consultar disponibilidade' | 8 a 15 segundos | menor que 200 ms    |
| Taxa de 'deixa eu reconsultar' / 1000 turns   | Aprox. 6%       | menor que 0,5%      |
| Slots oferecidos por conversa de AGENDA       | Aprox. 0,3      | maior que 1,8       |
| Conversao 'oferta -\> confirma slot'          | Aprox. 28%      | maior que 45%       |

**5. Fase 2 - Memoria Temporal (Tabela Events)**

*Duracao estimada: 1 semana. Resolve 70% do Bug Thamilla.*

**5.1. Objetivo**

Eliminar o problema 'campo Kommo historico interpretado como sinal
atual'. Toda decisao da Lia passa a consultar uma view materializada que
separa explicitamente: O QUE E ATUAL x O QUE E HISTORICO.

**5.2. Schema de events**

<table>
<tbody>
<tr class="odd">
<td><p>CREATE TABLE events (</p>
<p>event_id BIGSERIAL PRIMARY KEY,</p>
<p>lead_id BIGINT NOT NULL,</p>
<p>tipo TEXT NOT NULL, -- ver enum abaixo</p>
<p>payload JSONB NOT NULL,</p>
<p>ts TIMESTAMPTZ DEFAULT NOW(),</p>
<p>source TEXT NOT NULL, -- lia_inbound|lia_outbound</p>
<p>-- |humano|sistema|paciente</p>
<p>turn_id UUID, -- mesma rodada de processamento</p>
<p>snapshot_ctx_known JSONB -- o que a Lia sabia no momento</p>
<p>);</p>
<p>CREATE INDEX events_lead_ts ON events(lead_id, ts DESC);</p>
<p>CREATE INDEX events_tipo ON events(tipo, ts DESC);</p>
<p>-- Enum de tipos (validacao no application layer):</p>
<p>-- convenio_discutido paciente mencionou nome de convenio</p>
<p>-- convenio_definido confirmado e gravado em CONVENIO Kommo</p>
<p>-- slot_ofertado Lia ou humano enviou slot ao paciente</p>
<p>-- slot_confirmado paciente disse 'sim' a um slot</p>
<p>-- medware_gravado agendamento gravado com sucesso</p>
<p>-- kommo_status_change lead mudou de etapa</p>
<p>-- humano_interveio atendente humano enviou mensagem</p>
<p>-- ia_desativada ATIVADO IA mudou pra Desativado</p>
<p>-- ia_ativada ATIVADO IA mudou pra Ativado</p></td>
</tr>
</tbody>
</table>

**5.3. View materializada vw\_pacient\_estado\_atual**

<table>
<tbody>
<tr class="odd">
<td><p>CREATE MATERIALIZED VIEW vw_pacient_estado_atual AS</p>
<p>WITH ultimo_convenio AS (</p>
<p>SELECT DISTINCT ON (lead_id) lead_id,</p>
<p>payload-&gt;&gt;'valor' AS convenio,</p>
<p>ts AS convenio_definido_em</p>
<p>FROM events</p>
<p>WHERE tipo = 'convenio_definido'</p>
<p>ORDER BY lead_id, ts DESC</p>
<p>),</p>
<p>ultima_consulta AS (</p>
<p>SELECT DISTINCT ON (lead_id) lead_id,</p>
<p>(payload-&gt;&gt;'data')::TIMESTAMPTZ AS consulta_data,</p>
<p>ts AS consulta_confirmada_em</p>
<p>FROM events</p>
<p>WHERE tipo = 'slot_confirmado'</p>
<p>AND (payload-&gt;&gt;'data')::TIMESTAMPTZ &gt; NOW()</p>
<p>ORDER BY lead_id, ts DESC</p>
<p>)</p>
<p>SELECT</p>
<p>p.lead_id,</p>
<p>p.nome,</p>
<p>p.telefone_e164,</p>
<p>uc.convenio AS convenio_atual,</p>
<p>uc.convenio_definido_em,</p>
<p>ucon.consulta_data,</p>
<p>ucon.consulta_confirmada_em,</p>
<p>(ucon.consulta_data IS NOT NULL) AS ja_agendado</p>
<p>FROM patients p</p>
<p>LEFT JOIN ultimo_convenio uc ON uc.lead_id = p.lead_id</p>
<p>LEFT JOIN ultima_consulta ucon ON ucon.lead_id = p.lead_id;</p>
<p>-- Refresh: REFRESH MATERIALIZED VIEW CONCURRENTLY a cada 30s</p></td>
</tr>
</tbody>
</table>

**5.4. Integracao com o agent Python**

Refactor do caller\_context.py:

<table>
<tbody>
<tr class="odd">
<td><p># ANTES (mistura tudo):</p>
<p>def build_caller_context(phone, lead_id):</p>
<p>kommo_data = kommo.get_lead(lead_id)</p>
<p>return Context(known=kommo_data['custom_fields'])</p>
<p># DEPOIS (separa atual de historico):</p>
<p>def build_caller_context(phone, lead_id):</p>
<p>estado = supabase \</p>
<p>.table('vw_pacient_estado_atual') \</p>
<p>.select('*') \</p>
<p>.eq('lead_id', lead_id) \</p>
<p>.single().execute()</p>
<p>historico = supabase \</p>
<p>.table('events') \</p>
<p>.select('tipo,payload,ts,source') \</p>
<p>.eq('lead_id', lead_id) \</p>
<p>.order('ts', desc=True) \</p>
<p>.limit(50).execute()</p>
<p>return Context(</p>
<p>known=estado.data, # decisoes usam SO isso</p>
<p>history=historico.data, # contexto narrativo apenas</p>
<p>kommo_raw=kommo.get_lead(lead_id) # fallback</p>
<p>)</p></td>
</tr>
</tbody>
</table>

**5.5. Atualizacao do prompt mestre**

Adicionar regra no \_MASTER\_INSTRUCTION.md:

<table>
<tbody>
<tr class="odd">
<td><p># REGRA TEMPORAL CRITICA</p>
<p>Voce ve dois blocos no contexto:</p>
<p>1. ctx.known - estado ATUAL consolidado do paciente.</p>
<p>Decisoes SAO baseadas exclusivamente nesse bloco.</p>
<p>2. ctx.history - eventos passados ordenados por timestamp.</p>
<p>Serve apenas pra contexto narrativo. NUNCA tome</p>
<p>decisao (de convenio, de horario, de gravacao)</p>
<p>baseada em algo do ctx.history isoladamente.</p>
<p>Exemplo de uso correto:</p>
<p>ctx.known = {convenio_atual: "Saude Caixa", ja_agendado: true}</p>
<p>ctx.history = [{tipo:'convenio_discutido',</p>
<p>payload:{valor:'AMIL'},</p>
<p>ts:'2026-05-18'}]</p>
<p>Resposta: "Sua consulta com Saude Caixa esta confirmada"</p>
<p>(nao menciona AMIL - e historico antigo)</p></td>
</tr>
</tbody>
</table>

**6. Fase 3 - Endpoint de Gravacao Blindada**

*Duracao estimada: 1 semana. Resolve 100% do Bug C-12 e Fix \#208.*

**6.1. Objetivo**

Substituir o orquestracao manual Kommo + Medware no pipeline.py por UM
endpoint Lovable que faz as 2 escritas com guardiao Pydantic, GET
pos-PATCH e rollback automatico.

**6.2. Schema do endpoint**

<table>
<tbody>
<tr class="odd">
<td><p>POST /api/public/agendamento/salvar</p>
<p>Headers:</p>
<p>X-Blink-API-Key: &lt;secret&gt;</p>
<p>Content-Type: application/json</p>
<p>Body:</p>
<p>{</p>
<p>"lead_id": 24182212,</p>
<p>"cod_paciente": 6980,</p>
<p>"cod_agenda": 4,</p>
<p>"data_iso": "2026-07-02",</p>
<p>"hora": "10:30",</p>
<p>"cod_medico": 12080,</p>
<p>"cod_unidade": 5,</p>
<p>"cod_plano": 1,</p>
<p>"cod_procedimento": 303,</p>
<p>"convenio_validado": false,</p>
<p>"sinal_pix_comprovado": true,</p>
<p>"valor_sinal_brl": 335.00,</p>
<p>"comprovante_pix_url": "https://..."</p>
<p>}</p></td>
</tr>
</tbody>
</table>

**6.3. Validacoes servidor (livro Cap. 4.5 - Guardiao)**

Regra inegociavel (Bug C-41): rejeita o request se ambos
convenio\_validado E sinal\_pix\_comprovado forem false. Sem cobertura
financeira, nao grava.

<table>
<tbody>
<tr class="odd">
<td><p># Pydantic strict</p>
<p>class GravarAgendamentoInput(BaseModel):</p>
<p>lead_id: int = Field(..., ge=1)</p>
<p>cod_paciente: int = Field(..., ge=1)</p>
<p>cod_agenda: int = Field(..., ge=1)</p>
<p>data_iso: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')</p>
<p>hora: str = Field(..., pattern=r'^\d{2}:\d{2}$')</p>
<p>cod_medico: Literal[12080, 12081] # so Karla ou Fabricio</p>
<p>cod_unidade: Literal[3, 5] # so Asa Norte ou Aguas Claras</p>
<p>cod_plano: int = Field(..., ge=1)</p>
<p>cod_procedimento: int = Field(..., ge=1)</p>
<p>convenio_validado: bool = False</p>
<p>sinal_pix_comprovado: bool = False</p>
<p>@field_validator('sinal_pix_comprovado')</p>
<p>@classmethod</p>
<p>def exige_cobertura(cls, v, info):</p>
<p>convenio = info.data.get('convenio_validado', False)</p>
<p>if not (convenio or v):</p>
<p>raise ValueError('BUG_C41_RESERVA_SEM_COBERTURA')</p>
<p>return v</p></td>
</tr>
</tbody>
</table>

**6.4. Fluxo de gravacao (transacional)**

10. Valida input via Pydantic. Se falhar, retorna 422 + motivo.

11. Inicia transaction Postgres. Insere evento
    medware\_gravacao\_iniciada em events.

12. Chama Medware agendar\_encaixe (descoberta caso Milena:
    salvar\_agendamento retorna 'horario nao disponivel' falso negativo,
    encaixe funciona com mesmos params).

13. Se Medware falhar: rollback transaction + insere evento
    medware\_gravacao\_falhou + retorna 502.

14. Se Medware OK: PATCH Kommo com 5 campos (1.DIA CONSULTA, 1.UNIDADE,
    MEDICOS, CONVENIO, STATUS CONVERSA).

15. GET imediato Kommo + comparacao field\_id vs valor. Se Kommo
    'mentiu' (Bug C-12), retorna 502 + erro 'kommo\_silent\_failure' +
    tenta rollback Medware via cancelar\_agendamento.

16. Se ambos OK: commit transaction + insere evento medware\_gravado +
    insere evento kommo\_atualizado + retorna 200.

**6.5. Response 200 OK**

<table>
<tbody>
<tr class="odd">
<td><p>{</p>
<p>"ok": true,</p>
<p>"cod_agendamento_medware": 99887,</p>
<p>"kommo_updated": true,</p>
<p>"fields_confirmados": [</p>
<p>"1.DIA CONSULTA",</p>
<p>"1.UNIDADE",</p>
<p>"MEDICOS",</p>
<p>"CONVENIO",</p>
<p>"STATUS CONVERSA"</p>
<p>],</p>
<p>"event_id_medware_gravado": 9013,</p>
<p>"event_id_kommo_atualizado": 9014</p>
<p>}</p></td>
</tr>
</tbody>
</table>

**6.6. Por que isso elimina C-12 e \#208 por design**

Bug \#208 (handle\_gravar\_agendamento\_medware era stub): impossivel
repetir porque a unica forma de gravar agora e via esse endpoint. Nao da
pra 'pular' a chamada - quem decide que existe e o Lovable, nao cada
arquivo do agent.

Bug C-12 (Kommo mente em custom\_fields): impossivel repetir porque o
endpoint sempre faz GET pos-PATCH e levanta erro explicito se valor nao
bateu. Nao e tarefa do agent verificar - e tarefa do endpoint blindado.

**7. Fase 4 - Vista vw\_lead\_agendado + Filtros Integrados**

*Duracao estimada: 3 dias. Resolve 100% do Bug C-42.*

**7.1. Objetivo**

Eliminar definitivamente o cenario Thamilla (Lia em modo triagem em lead
ja agendado). View consolidada do Supabase computa ja\_agendado baseado
em 3 fontes simultaneas. Agent e filtros reativos consultam essa unica
fonte.

**7.2. View vw\_lead\_agendado**

<table>
<tbody>
<tr class="odd">
<td><p>CREATE OR REPLACE VIEW vw_lead_agendado AS</p>
<p>SELECT</p>
<p>p.lead_id,</p>
<p>(</p>
<p>p.status_kommo IN (101507507, 101109455, 106653499)</p>
<p>OR EXISTS (</p>
<p>SELECT 1 FROM events e</p>
<p>WHERE e.lead_id = p.lead_id</p>
<p>AND e.tipo = 'slot_confirmado'</p>
<p>AND (e.payload-&gt;&gt;'data')::TIMESTAMPTZ &gt; NOW()</p>
<p>)</p>
<p>OR (p.consulta_data IS NOT NULL</p>
<p>AND p.consulta_data &gt; NOW())</p>
<p>) AS ja_agendado,</p>
<p>p.status_kommo,</p>
<p>p.consulta_data,</p>
<p>(</p>
<p>SELECT MAX(e.ts) FROM events e</p>
<p>WHERE e.lead_id = p.lead_id</p>
<p>AND e.tipo = 'slot_confirmado'</p>
<p>) AS ultimo_slot_confirmado_em</p>
<p>FROM patients p;</p></td>
</tr>
</tbody>
</table>

**7.3. Filtros reativos integrados ao Lovable**

Antes de cada response Lia sair pra producao, agent chama:

<table>
<tbody>
<tr class="odd">
<td><p>GET /api/public/coerencia/validar?lead_id=23811372&amp;texto=&lt;resposta&gt;</p>
<p>Response 200 OK (resposta valida):</p>
<p>{</p>
<p>"ok": true,</p>
<p>"texto_aprovado": "&lt;mesmo texto&gt;",</p>
<p>"filtros_checados": ["c30a", "c41", "c42", "c36"]</p>
<p>}</p>
<p>Response 200 OK (resposta substituida):</p>
<p>{</p>
<p>"ok": false,</p>
<p>"motivo": "c42_lead_ja_agendado",</p>
<p>"texto_aprovado": "&lt;texto de fallback canonico&gt;",</p>
<p>"filtros_disparados": ["c42"]</p>
<p>}</p></td>
</tr>
</tbody>
</table>

Vantagem: regras de coerencia centralizadas no Lovable. Atualizar uma
regra nao exige redeploy do agent - basta editar a Edge Function.

**7.4. Lista de filtros migrados pra Lovable**

|            |                                                    |                   |
| ---------- | -------------------------------------------------- | ----------------- |
| **Filtro** | **O que detecta**                                  | **Origem do bug** |
| c30a       | 'Deixa eu reconsultar' com ctx.agenda vazio        | Victor 24147566   |
| c41        | Combinado/Resumo sem cobertura financeira          | Milena 24182212   |
| c42        | Encerro/triagem em lead ja agendado                | Thamilla 23811372 |
| c36        | Afirma consulta marcada com 1.DIA CONSULTA passada | Karina 22071351   |
| c35        | Dia da semana inventado para a data                | Lote de 12 leads  |

**8. Roteiro de Migracao - Shadow Mode**

Cada fase entra em producao em 3 estagios obrigatorios.

**8.1. Estagio 1 - Shadow puro (24h)**

  - Agent Python chama Lovable E sistema antigo (Kommo direto / Medware
    direto) em paralelo.

  - Resposta usada: sempre a do sistema antigo. Lovable e so observador.

  - Toda divergencia loga no Slack \#bugs-agent com payload completo de
    ambos.

  - Criterio de saida: divergencia menor que 5% em 24h consecutivas +
    zero erro 5xx do Lovable.

**8.2. Estagio 2 - Switch gradual com fallback (24h)**

  - Agent chama Lovable primeiro. Se 200 OK em menos de 500ms, usa essa
    resposta.

  - Se Lovable retornar 5xx ou exceder timeout, fallback automatico pro
    sistema antigo.

  - Criterio de saida: menor que 1% de fallbacks acionados em 24h.

**8.3. Estagio 3 - Switch completo (permanente)**

  - Sistema antigo e removido da rota critica.

  - Mantem funcao de auditoria 1x/dia comparando 100 leads aleatorios.

  - Rollback e flag toggle no Easypanel (nao revert de codigo).

**8.4. Decisao fast-rollback**

Se qualquer estagio mostrar divergencia maior que 15% OU taxa de erro
maior que 2%, rollback imediato pra sistema antigo. Investiga em
ambiente staging antes de retomar.

**9. Riscos e Mitigacao**

**9.1. Risco - race condition entre turns paralelos**

Lovable nao resolve Bug \#183 (5 turns sendo processados em paralelo
cada um com snapshot ctx diferente).

Mitigacao: pipeline\_lock por conversation\_key continua sendo
responsabilidade do agent Python. Esta em codigo no repo (commit ja em
main), falta confirmar deploy em prod e validar via /admin/replay. Sem
isso, mesmo com Supabase como fonte unica, 2 turns paralelos podem ler
estados ligeiramente diferentes.

**9.2. Risco - divergencia cache Medware x Medware real**

Cron 5min implica ate 5min de defasagem. Outra clinica/atendente pode
pegar slot no Medware enquanto Lovable ainda mostra disponivel.

Mitigacao: validacao on-write - endpoint /api/public/agendamento/salvar
faz GET no Medware no momento da gravacao. Se slot foi tomado, retorna
409 Conflict + sugere proximo slot disponivel.

**9.3. Risco - endpoint publico de agenda exposto**

Mesmo com X-Blink-API-Key, vazamento do secret expoe a agenda da
clinica.

Mitigacao: rotacionar secret a cada 90 dias. Adicionar rate limit (100
reqs / min por API key). Log de cada request com IP origem. Em caso de
vazamento, rotacao imediata + investigacao de quem teve acesso ao
Supabase Secrets.

**9.4. Risco - Lovable Edge Function fora do ar**

Supabase Edge Functions tem SLA 99.5% (Pro tier). 0.5% = 3.6h/mes de
downtime potencial.

Mitigacao: agent Python tem fallback configurado pra cada endpoint. Se
Lovable retornar 5xx, agent usa caminho legado (Kommo direto + Medware
direto) automaticamente. Operacao degrada mas nao para.

**9.5. Risco - custo Supabase escala**

Tabela events cresce indefinidamente. Em 6 meses pode ter 500k+ eventos.
View materializada lenta.

Mitigacao: particionamento por mes (events\_2026\_07, events\_2026\_08).
Archive eventos \> 12 meses pra storage frio. Refresh da view so nas
linhas modificadas (CONCURRENTLY).

**10. Glossario - Referencia de Bugs Mencionados**

Esta secao lista bugs especificos do projeto Blink referenciados no
documento, pra alinhamento de vocabulario com a equipe Lovable.

|        |                                                                                    |                                    |
| ------ | ---------------------------------------------------------------------------------- | ---------------------------------- |
| **ID** | **Descricao**                                                                      | **Caso real**                      |
| C-12   | MCP kommo\_update\_lead retorna success:true mas custom\_fields\_values fica vazio | Lote diversos leads                |
| C-30A  | Lia escreve 'deixa eu reconsultar agenda' com ctx.agenda vazio                     | Sofia 24158652                     |
| C-35   | Dia da semana inventado para a data oferecida                                      | Warley + 11 outros                 |
| C-36   | Lia afirma consulta marcada mas 1.DIA CONSULTA esta no passado                     | Karina 22071351                    |
| C-41   | Lia firma reserva sem convenio definido nem sinal Pix                              | Milena 24182212                    |
| C-42   | Lia continua em triagem inicial em lead ja agendado                                | Thamilla 23811372                  |
| \#183  | Race condition entre turns paralelos no pipeline.py                                | Lote diversos leads                |
| \#208  | handle\_gravar\_agendamento\_medware era stub                                      | Lote diversos (15 dias sem gravar) |

*Documentacao completa de cada bug no arquivo CLAUDE.md do repositorio
(secao rolling log). Cada bug tem nome do paciente afetado + commit do
fix + licao arquitetural.*

**Proximo passo concreto**

Aprovacao deste briefing pela equipe Lovable + criacao de issue por fase
no GitHub. Inicio da Fase 1 imediatamente apos aprovacao. Estimativa de
entrega completa das 4 fases: 3 semanas corridas (15 dias uteis).

*Contato tecnico: Fabio Philipe Martins (oabphi@gmail.com) + Claude
Cowork (canal Slack \#bugs-agent).*
