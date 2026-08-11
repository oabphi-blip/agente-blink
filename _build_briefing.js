const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, PageOrientation, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType, PageNumber,
  PageBreak,
} = require("docx");
const fs = require("fs");

const border = (color = "BFBFBF") => ({ style: BorderStyle.SINGLE, size: 1, color });
const bordersAll = (color) => ({
  top: border(color), bottom: border(color), left: border(color), right: border(color),
});

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { before: opts.before || 0, after: opts.after || 120 },
    alignment: opts.align || AlignmentType.LEFT,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics, size: opts.size || 22, color: opts.color || "000000" })],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, bold: true, size: 36, color: "1F3864" })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 160 },
    children: [new TextRun({ text, bold: true, size: 28, color: "2E5395" })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 120 },
    children: [new TextRun({ text, bold: true, size: 24, color: "365F91" })],
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level }, spacing: { after: 80 },
    children: [new TextRun({ text, size: 22 })],
  });
}
function numbered(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "numbers", level }, spacing: { after: 80 },
    children: [new TextRun({ text, size: 22 })],
  });
}

function codeBlock(text) {
  const lines = text.split("\n").map(line =>
    new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: line || " ", font: "Courier New", size: 18 })] })
  );
  return new Table({
    width: { size: 9360, type: WidthType.DXA }, columnWidths: [9360],
    rows: [new TableRow({ children: [new TableCell({
      borders: bordersAll("BFBFBF"),
      shading: { fill: "F2F2F2", type: ShadingType.CLEAR },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      width: { size: 9360, type: WidthType.DXA },
      children: lines,
    })] })],
  });
}

function spacer() { return new Paragraph({ spacing: { after: 120 }, children: [new TextRun(" ")] }); }

function makeTable(matrix, colWidths) {
  const totalWidth = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA }, columnWidths: colWidths,
    rows: matrix.map((row, ri) => new TableRow({
      tableHeader: ri === 0,
      children: row.map((cellText, ci) => new TableCell({
        borders: bordersAll(),
        width: { size: colWidths[ci], type: WidthType.DXA },
        shading: ri === 0
          ? { fill: "1F3864", type: ShadingType.CLEAR }
          : (ri % 2 === 0 ? { fill: "F2F6FC", type: ShadingType.CLEAR } : { fill: "FFFFFF", type: ShadingType.CLEAR }),
        margins: { top: 100, bottom: 100, left: 160, right: 160 },
        children: [new Paragraph({ spacing: { after: 0 }, children: [new TextRun({
          text: cellText, bold: ri === 0, color: ri === 0 ? "FFFFFF" : "000000", size: ri === 0 ? 22 : 20,
        })] })],
      })),
    })),
  });
}

const content = [];

// CAPA
content.push(new Paragraph({ spacing: { before: 2400, after: 200 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "BLINK OFTALMOLOGIA", bold: true, size: 28, color: "1F3864" })] }));
content.push(new Paragraph({ spacing: { after: 600 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Briefing Tecnico Lovable Fase 2", bold: true, size: 56, color: "1F3864" })] }));
content.push(new Paragraph({ spacing: { after: 200 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Ponte arquitetural Lovable <-> Agent Lia <-> Kommo/Medware", size: 28, italics: true, color: "595959" })] }));
content.push(new Paragraph({ spacing: { before: 800, after: 80 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Versao 1.0 - 27/06/2026", size: 22, color: "808080" })] }));
content.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Autor: Fabio Philipe Martins (Diretoria Blink) + Claude Cowork", size: 22, color: "808080" })] }));
content.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Destinatario: equipe Lovable (build agent)", size: 22, color: "808080" })] }));
content.push(new Paragraph({ children: [new PageBreak()] }));

// 1. SUMARIO EXECUTIVO
content.push(h1("1. Sumario Executivo"));
content.push(p("A Blink Oftalmologia opera um agente conversacional (Lia) que atende pacientes 24h via WhatsApp, integrado a 3 sistemas: Kommo (CRM), Medware (ERP clinico) e Meta Cloud (WhatsApp). Apos cerca de 30 dias de producao, 4 padroes de falha persistem mesmo apos multiplas correcoes:"));
content.push(bullet("Incoerencia na retomada de mensagens enviadas pelo humano - Lia ignora o historico humano-paciente e refaz triagem (caso Larissa/Lis/Samuel)."));
content.push(bullet("Incoerencia apos o agendamento - Lia escreve respostas contraditorias em leads ja em 5-AGENDADO. Caso Thamilla 23811372: afirma consulta confirmada as 11:26 e as 21:33 escreve 'AMIL nao credenciado, encerro?'."));
content.push(bullet("Falta de envio confiavel de disponibilidade de agenda - Lia diz 'deixa eu reconsultar a agenda' e nunca volta com slots reais. Caso Victor 24147566: 12 promessas vazias em 12 dias."));
content.push(bullet("Falta de gravacao consistente - Bug C-12 (Kommo retorna success:true sem gravar) e Fix #208 (Lia nao grava Medware autonomamente, depende de intervencao humana ou Cowork)."));
content.push(spacer());
content.push(p("Este briefing propoe uma arquitetura em 4 fases (~3 semanas) onde o Lovable atua como camada de dados, cache e regras de negocio entre o agente Python (Lia) e os sistemas finais. O agente Lia continua sendo o cerebro conversacional; o Lovable vira o backend de dados que ele consome via 2 endpoints HTTP autenticados."));
content.push(p("Resultado esperado pos-implementacao:", { bold: true, before: 120 }));
content.push(bullet("Bug Victor (oferta de slot) - resolvido em 95%."));
content.push(bullet("Bug Thamilla (memoria/coerencia) - resolvido em 70%."));
content.push(bullet("Bug C-12 e #208 (gravacao) - resolvidos em 100% por design."));
content.push(bullet("Bug C-42 (pos-agendamento) - resolvido em 100% por design."));
content.push(p("Os 5% e 30% que restam sao limitacoes arquiteturais do agente Python atual (race condition entre turns paralelos - Bug #183) que ainda precisam de pipeline_lock no pipeline.py. Lovable nao resolve essa parte e nem deve tentar.", { italics: true, before: 120 }));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 2. CONTEXTO
content.push(h1("2. Contexto Operacional Atual"));
content.push(h2("2.1. Arquitetura real (nao a teorica)"));
content.push(p("Quem responde o paciente HOJE nao e o Salesbot/AI do Kommo. E:"));
content.push(bullet("Agente Python (voice_agent/) rodando em container Docker no Easypanel."));
content.push(bullet("Webhook do Meta WhatsApp Cloud (8133) ou Evolution API (0710) entrega cada mensagem inbound no agent."));
content.push(bullet("Agent chama Anthropic Claude (Sonnet 4.5 / Opus 4.6) com prompt mestre em _MASTER_INSTRUCTION.md + tools estruturadas + filtros reativos pos-geracao."));
content.push(bullet("Agent chama Medware diretamente via medware.py (com cache Redis 5min, retry 1x fail-fast, circuit breaker 3 falhas escalando humano)."));
content.push(bullet("Kommo serve como CRM espelho: humano ve historico, intervem manual, atualiza campos via webhooks bidirecionais."));
content.push(p("O Salesbot AI nativo do Kommo esta desativado desde maio/2026.", { italics: true, before: 80 }));

content.push(h2("2.2. Os 4 problemas em detalhe"));
content.push(h3("2.2.1. Memoria entre Lia e humano (Bug Thamilla 23811372)"));
content.push(p("Em 26/06/2026, a Lia escreveu 2 mensagens diretamente contraditorias num lead ja em 5-AGENDADO:"));
content.push(codeBlock(
  "26/06 11:26 - Lia (WhatsApp):\n" +
  '  "Sua consulta com a Dra. Karla Delalibera pelo Saude Caixa esta\n' +
  '   confirmada para quinta-feira 02/07/2026 as 16:30 na unidade\n' +
  '   Aguas Claras."  CORRETO\n\n' +
  "26/06 21:33 - Lia (WhatsApp):\n" +
  '  "Thamilla, preciso te corrigir uma informacao: o AMIL nao esta\n' +
  "   credenciado na nossa rede... Como prefere seguir?\n" +
  "   1) Seguir sem convenio\n" +
  "   2) Somente com convenio (encerro o atendimento aqui)\""
));
content.push(p("Causa raiz: o campo Kommo N ACEITO CONVENIO=Amil (historico de meses atras) foi lido como sinal do turn atual. O caller_context.py do agent mistura snapshots de momentos diferentes sem timestamping.", { before: 120 }));

content.push(h3("2.2.2. Disponibilidade de agenda (Bug Victor 24147566)"));
content.push(p("De 13/06 a 25/06, em 12 oportunidades, a Lia escreveu variantes de:"));
content.push(codeBlock(
  '"Deixa eu consultar a agenda real aqui pra voce - volto em 1 minuto."\n' +
  '"Vou buscar os horarios disponiveis. Me da um minutinho."\n' +
  '"Desculpa a demora, a agenda esta com lentidao no momento."\n' +
  '"Estou trabalhando para conseguir os horarios disponiveis."\n' +
  '"Vou priorizar 16/06 na busca."\n' +
  '... 7 outras variantes'
));
content.push(p("E nunca voltou com slots concretos. Em 11 das 12 vezes, atendente humana (Ariany/Stephany) interveio manual.", { before: 80 }));
content.push(p("Causa raiz: a chamada Medware tem latencia variavel (3-15s) e timeout do agent e 12s. Quando estora, agent escapa pra texto livre. Filtros reativos (_viola_oferta_agenda) existem mas estao atras de gate em prod (FILTROS_LEGACY=0).", { before: 120 }));

content.push(h3("2.2.3. Pos-agendamento (Bug C-42)"));
content.push(p("Em status 5-AGENDADO, a Lia nao tem motivo legitimo pra rodar o fluxo de triagem inicial, mas continua entrando nele. Cada turn le fields do Kommo com semantica errada e gera 'opcoes' invalidas como encerrar atendimento de paciente ja com consulta marcada."));
content.push(p("Fix imediato (commit 323bbb7, 26/06): adicionados 5-AGENDADO/6-CONFIRMAR/7.CONFIRMADO ao set _STATUS_INATIVOS_IA. Quando lead muda pra essas etapas, ATIVADO IA=Desativado automaticamente. Tampao - confirmacao D-1 vira responsabilidade humana ate filtros C-42 reativos estarem prontos.", { italics: true, before: 80 }));

content.push(h3("2.2.4. Gravacao (Bug C-12 + Fix #208)"));
content.push(p("Dois sub-problemas independentes:"));
content.push(numbered("Bug C-12: MCP kommo_update_lead retorna success:true mas custom_fields_values fica vazio. Workaround atual: PATCH direto via Chrome MCP."));
content.push(numbered("Fix #208: handle_gravar_agendamento_medware em tools_lia.py era um stub que escrevia flag Redis e delegava pra executor_agendamento.py (arquivo que NUNCA existiu). Por 15 dias seguidos a Lia confirmava agendamento mas nao gravava nada no Medware. Caso Milena 24182212 (20/06): bebe 7 meses, trauma ocular, urgencia - agendamento gravado manual pelo Cowork via mcp__medware__agendar_encaixe."));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 3. ARQUITETURA
content.push(h1("3. Arquitetura Recomendada"));
content.push(h2("3.1. Visao de 3 hops"));
content.push(p("Substituir o fluxo atual:"));
content.push(codeBlock(
  "ATUAL:\n" +
  "Paciente <-> WhatsApp <-> Agent Python <-> Kommo (fragil)\n" +
  "                                       <-> Medware (lento)\n" +
  "                                       <-> Redis (cache local)"
));
content.push(p("Por:", { before: 80 }));
content.push(codeBlock(
  "PROPOSTO:\n" +
  "Paciente <-> WhatsApp <-> Agent Python <-> Lovable Backend\n" +
  "                                              v (cron)\n" +
  "                                          Supabase\n" +
  "                                              ^ (sync)\n" +
  "                                       Kommo + Medware"
));
content.push(p("Pontos importantes da nova arquitetura:", { before: 120, bold: true }));
content.push(bullet("Agent Python continua intacto como cerebro conversacional. So muda o que ele consome via HTTP."));
content.push(bullet("Lovable nao recebe webhook direto do WhatsApp - quem recebe e o agent Python. Lovable e backend de dados que o agent consulta."));
content.push(bullet("Kommo e Medware viram fontes de origem, sincronizadas em batch pelo Lovable. Acesso direto a eles e excecao (so pra escritas que precisam de blindagem)."));
content.push(bullet("Supabase Postgres e a fonte unica de verdade pra estado consolidado de paciente."));

content.push(h2("3.2. Decisoes arquiteturais nao-obvias"));
content.push(h3("3.2.1. Endpoint publico assinado (nao publico de fato)"));
content.push(p("Todo endpoint Lovable exposto pra o agent Python tem autenticacao por header:"));
content.push(codeBlock(
  "Header obrigatorio:\n" +
  "  X-Blink-API-Key: <secret>\n\n" +
  "Secret reutiliza o KOMMO_WEBHOOK_SECRET que ja esta no\n" +
  "Supabase Secrets (b035819d617d... - 64 chars hex).\n\n" +
  "Endpoint sem esse header retorna 401 Unauthorized."
));
content.push(p("Sem isso, concorrentes scrapeiam a agenda da Blink em segundos.", { italics: true, before: 80 }));

content.push(h3("3.2.2. Tabela events append-only (nao UPDATE em patients)"));
content.push(p("Toda mudanca de estado de paciente vira UM evento na tabela events. A tabela patients e apenas snapshot consolidado (view materializada), nunca editada diretamente."));
content.push(p("Vantagem: rastreabilidade temporal completa. Quando paciente reclama 'mas eu nao pedi AMIL', ve-se em SQL exatamente quem registrou AMIL, quando e a partir de qual mensagem.", { before: 80 }));

content.push(h3("3.2.3. Shadow mode obrigatorio por 48h antes de cada switch"));
content.push(p("Toda nova entidade (endpoint, tabela, regra) entra primeiro em SHADOW: agent chama o NOVO e o ANTIGO em paralelo, compara resultados, loga divergencias. So faz switch quando divergencia menor que 1% por 48h consecutivas."));
content.push(p("Regra introduzida no projeto por incidente do Juiz Haiku 4.5 (Bug 02/06/2026): defesa nova vetando respostas legitimas em producao sem validacao real.", { before: 80, italics: true }));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 4. FASE 1
content.push(h1("4. Fase 1 - Endpoint Disponibilidade de Agenda"));
content.push(p("Duracao estimada: 3 dias uteis. Resolve 95% do Bug Victor.", { italics: true }));
content.push(h2("4.1. Objetivo"));
content.push(p("Substituir a chamada direta do agent Python ao Medware (latencia 3-15s) por chamada ao Lovable (latencia alvo menor que 200ms) que serve da tabela medware_agenda previamente sincronizada."));

content.push(h2("4.2. Schema do endpoint"));
content.push(h3("4.2.1. Request"));
content.push(codeBlock(
  "GET /api/public/agenda/disponiveis\n\n" +
  "Headers:\n" +
  "  X-Blink-API-Key: <secret>\n" +
  "  Accept: application/json\n\n" +
  "Query string:\n" +
  "  medico        string  obrigatorio   karla | fabricio\n" +
  "  unidade       string  obrigatorio   asa_norte | aguas_claras\n" +
  "  janela_dias   int     opcional      default 14, max 30\n" +
  "  hora_inicio   string  opcional      default 07:00 (HH:MM)\n" +
  "  hora_fim      string  opcional      default 19:00 (HH:MM)\n" +
  "  convenio      string  opcional      ver lista canonica abaixo\n" +
  "  lead_id       int     opcional      pra filtrar slots ja\n" +
  "                                      ofertados a esse lead\n" +
  "                                      (regra E6-B)"
));

content.push(h3("4.2.2. Response 200 OK"));
content.push(codeBlock(
  "{\n" +
  '  "ok": true,\n' +
  '  "slots": [\n' +
  "    {\n" +
  '      "data_iso": "2026-07-02",\n' +
  '      "hora": "10:30",\n' +
  '      "cod_agenda": 4,\n' +
  '      "cod_medico": 12080,\n' +
  '      "cod_unidade": 5,\n' +
  '      "duracao_min": 30,\n' +
  '      "especialidade": "Oftalmologia Geral"\n' +
  "    }\n" +
  "  ],\n" +
  '  "metadata": {\n' +
  '    "total_disponivel": 8,\n' +
  '    "janela_inicio": "2026-06-27",\n' +
  '    "janela_fim": "2026-06-30",\n' +
  '    "cache_age_seconds": 142,\n' +
  '    "ultimo_sync_medware": "2026-06-27T13:55:00Z"\n' +
  "  }\n" +
  "}"
));

content.push(h3("4.2.3. Response 503 (Medware indisponivel ha mais de 10min)"));
content.push(codeBlock(
  "{\n" +
  '  "ok": false,\n' +
  '  "erro": "medware_indisponivel",\n' +
  '  "ultimo_sync_ok": "2026-06-27T10:30:00Z",\n' +
  '  "minutos_desde_ultimo_sync": 32,\n' +
  '  "acao_recomendada": "escalar_humano"\n' +
  "}"
));
content.push(p("Importante: 503 com ultimo_sync_ok e DIFERENTE de 200 com slots vazios. O agent Lia precisa distinguir esses 2 casos pra escolher a mensagem certa.", { italics: true, before: 120 }));

content.push(h2("4.3. Regras de negocio aplicadas no servidor"));
content.push(numbered("Karla Delalibera atende: seg/qua/sex em Asa Norte; ter/qui em Aguas Claras."));
content.push(numbered("Fabricio Freitas atende: ter/qui em Aguas Claras + Asa Norte conforme escala mensal."));
content.push(numbered("Excluir slots entre 12:00 e 13:00 (almoco)."));
content.push(numbered("Excluir slots com convenio incompativel: paciente Saude Caixa nao ve slot reservado a particular se medico restringiu."));
content.push(numbered("Excluir slots em blink:slots_ja_ofertados:{lead_id} (Regra E6-B - 10min de reserva temporaria)."));
content.push(numbered("Excluir slots em dias de ferias do medico (consultar tabela medico_ferias)."));
content.push(numbered("Default ordenacao: data crescente, hora crescente (slot mais proximo primeiro)."));

content.push(h2("4.4. Tabelas Supabase necessarias"));
content.push(codeBlock(
  "-- 1. Espelho da agenda Medware (sincronizado por cron)\n" +
  "CREATE TABLE medware_agenda (\n" +
  "    agenda_id BIGSERIAL PRIMARY KEY,\n" +
  "    cod_agenda INT NOT NULL,\n" +
  "    cod_medico INT NOT NULL,\n" +
  "    cod_unidade INT NOT NULL,\n" +
  "    data DATE NOT NULL,\n" +
  "    hora TIME NOT NULL,\n" +
  "    duracao_min INT DEFAULT 30,\n" +
  "    especialidade TEXT,\n" +
  "    status TEXT DEFAULT 'disponivel',\n" +
  "    cod_paciente_reservado INT,\n" +
  "    medware_sync_ts TIMESTAMPTZ DEFAULT NOW(),\n" +
  "    UNIQUE(cod_medico, cod_unidade, data, hora)\n" +
  ");\n" +
  "CREATE INDEX agenda_data_med ON medware_agenda(data, cod_medico);\n\n" +
  "-- 2. Ferias e escala dos medicos (config manual + cron)\n" +
  "CREATE TABLE medico_ferias (\n" +
  "    id BIGSERIAL PRIMARY KEY,\n" +
  "    cod_medico INT,\n" +
  "    data_inicio DATE,\n" +
  "    data_fim DATE,\n" +
  "    motivo TEXT\n" +
  ");\n\n" +
  "-- 3. Log de sincronizacoes Medware (saude do cron)\n" +
  "CREATE TABLE medware_sync_log (\n" +
  "    sync_id BIGSERIAL PRIMARY KEY,\n" +
  "    started_at TIMESTAMPTZ DEFAULT NOW(),\n" +
  "    ended_at TIMESTAMPTZ,\n" +
  "    sucesso BOOLEAN,\n" +
  "    slots_atualizados INT,\n" +
  "    erro TEXT\n" +
  ");"
));

content.push(h2("4.5. Sincronizacao Medware -> Supabase"));
content.push(bullet("Cron a cada 5 minutos chama Medware Agenda/Listar pra janela de 30 dias."));
content.push(bullet("Faz upsert na tabela medware_agenda por chave (cod_medico, cod_unidade, data, hora)."));
content.push(bullet("Grava resultado em medware_sync_log (saude monitoravel)."));
content.push(bullet("Se 3 sincronizacoes consecutivas falharem, alerta no Slack #bugs-agent automaticamente."));

content.push(h2("4.6. Metricas pos-deploy (alvos)"));
content.push(makeTable([
  ["Metrica", "Antes", "Alvo pos-Fase-1"],
  ["Latencia media de 'consultar disponibilidade'", "8 a 15 segundos", "menor que 200 ms"],
  ["Taxa de 'deixa eu reconsultar' / 1000 turns", "Aprox. 6%", "menor que 0,5%"],
  ["Slots oferecidos por conversa de AGENDA", "Aprox. 0,3", "maior que 1,8"],
  ["Conversao 'oferta -> confirma slot'", "Aprox. 28%", "maior que 45%"],
], [4400, 2400, 2560]));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 5. FASE 2
content.push(h1("5. Fase 2 - Memoria Temporal (Tabela Events)"));
content.push(p("Duracao estimada: 1 semana. Resolve 70% do Bug Thamilla.", { italics: true }));
content.push(h2("5.1. Objetivo"));
content.push(p("Eliminar o problema 'campo Kommo historico interpretado como sinal atual'. Toda decisao da Lia passa a consultar uma view materializada que separa explicitamente: O QUE E ATUAL x O QUE E HISTORICO."));

content.push(h2("5.2. Schema de events"));
content.push(codeBlock(
  "CREATE TABLE events (\n" +
  "    event_id BIGSERIAL PRIMARY KEY,\n" +
  "    lead_id BIGINT NOT NULL,\n" +
  "    tipo TEXT NOT NULL,         -- ver enum abaixo\n" +
  "    payload JSONB NOT NULL,\n" +
  "    ts TIMESTAMPTZ DEFAULT NOW(),\n" +
  "    source TEXT NOT NULL,       -- lia_inbound|lia_outbound\n" +
  "                                -- |humano|sistema|paciente\n" +
  "    turn_id UUID,               -- mesma rodada de processamento\n" +
  "    snapshot_ctx_known JSONB    -- o que a Lia sabia no momento\n" +
  ");\n" +
  "CREATE INDEX events_lead_ts ON events(lead_id, ts DESC);\n" +
  "CREATE INDEX events_tipo ON events(tipo, ts DESC);\n\n" +
  "-- Enum de tipos (validacao no application layer):\n" +
  "-- convenio_discutido     paciente mencionou nome de convenio\n" +
  "-- convenio_definido      confirmado e gravado em CONVENIO Kommo\n" +
  "-- slot_ofertado          Lia ou humano enviou slot ao paciente\n" +
  "-- slot_confirmado        paciente disse 'sim' a um slot\n" +
  "-- medware_gravado        agendamento gravado com sucesso\n" +
  "-- kommo_status_change    lead mudou de etapa\n" +
  "-- humano_interveio       atendente humano enviou mensagem\n" +
  "-- ia_desativada          ATIVADO IA mudou pra Desativado\n" +
  "-- ia_ativada             ATIVADO IA mudou pra Ativado"
));

content.push(h2("5.3. View materializada vw_pacient_estado_atual"));
content.push(codeBlock(
  "CREATE MATERIALIZED VIEW vw_pacient_estado_atual AS\n" +
  "WITH ultimo_convenio AS (\n" +
  "  SELECT DISTINCT ON (lead_id) lead_id,\n" +
  "         payload->>'valor' AS convenio,\n" +
  "         ts AS convenio_definido_em\n" +
  "    FROM events\n" +
  "   WHERE tipo = 'convenio_definido'\n" +
  "   ORDER BY lead_id, ts DESC\n" +
  "),\n" +
  "ultima_consulta AS (\n" +
  "  SELECT DISTINCT ON (lead_id) lead_id,\n" +
  "         (payload->>'data')::TIMESTAMPTZ AS consulta_data,\n" +
  "         ts AS consulta_confirmada_em\n" +
  "    FROM events\n" +
  "   WHERE tipo = 'slot_confirmado'\n" +
  "     AND (payload->>'data')::TIMESTAMPTZ > NOW()\n" +
  "   ORDER BY lead_id, ts DESC\n" +
  ")\n" +
  "SELECT\n" +
  "  p.lead_id,\n" +
  "  p.nome,\n" +
  "  p.telefone_e164,\n" +
  "  uc.convenio AS convenio_atual,\n" +
  "  uc.convenio_definido_em,\n" +
  "  ucon.consulta_data,\n" +
  "  ucon.consulta_confirmada_em,\n" +
  "  (ucon.consulta_data IS NOT NULL) AS ja_agendado\n" +
  "  FROM patients p\n" +
  "  LEFT JOIN ultimo_convenio uc ON uc.lead_id = p.lead_id\n" +
  "  LEFT JOIN ultima_consulta ucon ON ucon.lead_id = p.lead_id;\n\n" +
  "-- Refresh: REFRESH MATERIALIZED VIEW CONCURRENTLY a cada 30s"
));

content.push(h2("5.4. Integracao com o agent Python"));
content.push(p("Refactor do caller_context.py:"));
content.push(codeBlock(
  "# ANTES (mistura tudo):\n" +
  "def build_caller_context(phone, lead_id):\n" +
  "    kommo_data = kommo.get_lead(lead_id)\n" +
  "    return Context(known=kommo_data['custom_fields'])\n\n" +
  "# DEPOIS (separa atual de historico):\n" +
  "def build_caller_context(phone, lead_id):\n" +
  "    estado = supabase \\\n" +
  "        .table('vw_pacient_estado_atual') \\\n" +
  "        .select('*') \\\n" +
  "        .eq('lead_id', lead_id) \\\n" +
  "        .single().execute()\n" +
  "    \n" +
  "    historico = supabase \\\n" +
  "        .table('events') \\\n" +
  "        .select('tipo,payload,ts,source') \\\n" +
  "        .eq('lead_id', lead_id) \\\n" +
  "        .order('ts', desc=True) \\\n" +
  "        .limit(50).execute()\n" +
  "    \n" +
  "    return Context(\n" +
  "        known=estado.data,        # decisoes usam SO isso\n" +
  "        history=historico.data,   # contexto narrativo apenas\n" +
  "        kommo_raw=kommo.get_lead(lead_id)  # fallback\n" +
  "    )"
));

content.push(h2("5.5. Atualizacao do prompt mestre"));
content.push(p("Adicionar regra no _MASTER_INSTRUCTION.md:"));
content.push(codeBlock(
  "# REGRA TEMPORAL CRITICA\n\n" +
  "Voce ve dois blocos no contexto:\n\n" +
  "1. ctx.known - estado ATUAL consolidado do paciente.\n" +
  "   Decisoes SAO baseadas exclusivamente nesse bloco.\n\n" +
  "2. ctx.history - eventos passados ordenados por timestamp.\n" +
  "   Serve apenas pra contexto narrativo. NUNCA tome\n" +
  "   decisao (de convenio, de horario, de gravacao)\n" +
  "   baseada em algo do ctx.history isoladamente.\n\n" +
  "Exemplo de uso correto:\n" +
  '  ctx.known = {convenio_atual: "Saude Caixa", ja_agendado: true}\n' +
  "  ctx.history = [{tipo:'convenio_discutido',\n" +
  "                  payload:{valor:'AMIL'},\n" +
  "                  ts:'2026-05-18'}]\n\n" +
  '  Resposta: "Sua consulta com Saude Caixa esta confirmada"\n' +
  '            (nao menciona AMIL - e historico antigo)'
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 6. FASE 3
content.push(h1("6. Fase 3 - Endpoint de Gravacao Blindada"));
content.push(p("Duracao estimada: 1 semana. Resolve 100% do Bug C-12 e Fix #208.", { italics: true }));
content.push(h2("6.1. Objetivo"));
content.push(p("Substituir o orquestracao manual Kommo + Medware no pipeline.py por UM endpoint Lovable que faz as 2 escritas com guardiao Pydantic, GET pos-PATCH e rollback automatico."));

content.push(h2("6.2. Schema do endpoint"));
content.push(codeBlock(
  "POST /api/public/agendamento/salvar\n\n" +
  "Headers:\n" +
  "  X-Blink-API-Key: <secret>\n" +
  "  Content-Type: application/json\n\n" +
  "Body:\n" +
  "{\n" +
  '  "lead_id": 24182212,\n' +
  '  "cod_paciente": 6980,\n' +
  '  "cod_agenda": 4,\n' +
  '  "data_iso": "2026-07-02",\n' +
  '  "hora": "10:30",\n' +
  '  "cod_medico": 12080,\n' +
  '  "cod_unidade": 5,\n' +
  '  "cod_plano": 1,\n' +
  '  "cod_procedimento": 303,\n' +
  '  "convenio_validado": false,\n' +
  '  "sinal_pix_comprovado": true,\n' +
  '  "valor_sinal_brl": 335.00,\n' +
  '  "comprovante_pix_url": "https://..."\n' +
  "}"
));

content.push(h2("6.3. Validacoes servidor (livro Cap. 4.5 - Guardiao)"));
content.push(p("Regra inegociavel (Bug C-41): rejeita o request se ambos convenio_validado E sinal_pix_comprovado forem false. Sem cobertura financeira, nao grava."));
content.push(codeBlock(
  "# Pydantic strict\n" +
  "class GravarAgendamentoInput(BaseModel):\n" +
  "    lead_id: int = Field(..., ge=1)\n" +
  "    cod_paciente: int = Field(..., ge=1)\n" +
  "    cod_agenda: int = Field(..., ge=1)\n" +
  "    data_iso: str = Field(..., pattern=r'^\\d{4}-\\d{2}-\\d{2}$')\n" +
  "    hora: str = Field(..., pattern=r'^\\d{2}:\\d{2}$')\n" +
  "    cod_medico: Literal[12080, 12081]  # so Karla ou Fabricio\n" +
  "    cod_unidade: Literal[3, 5]  # so Asa Norte ou Aguas Claras\n" +
  "    cod_plano: int = Field(..., ge=1)\n" +
  "    cod_procedimento: int = Field(..., ge=1)\n" +
  "    convenio_validado: bool = False\n" +
  "    sinal_pix_comprovado: bool = False\n\n" +
  "    @field_validator('sinal_pix_comprovado')\n" +
  "    @classmethod\n" +
  "    def exige_cobertura(cls, v, info):\n" +
  "        convenio = info.data.get('convenio_validado', False)\n" +
  "        if not (convenio or v):\n" +
  "            raise ValueError('BUG_C41_RESERVA_SEM_COBERTURA')\n" +
  "        return v"
));

content.push(h2("6.4. Fluxo de gravacao (transacional)"));
content.push(numbered("Valida input via Pydantic. Se falhar, retorna 422 + motivo."));
content.push(numbered("Inicia transaction Postgres. Insere evento medware_gravacao_iniciada em events."));
content.push(numbered("Chama Medware agendar_encaixe (descoberta caso Milena: salvar_agendamento retorna 'horario nao disponivel' falso negativo, encaixe funciona com mesmos params)."));
content.push(numbered("Se Medware falhar: rollback transaction + insere evento medware_gravacao_falhou + retorna 502."));
content.push(numbered("Se Medware OK: PATCH Kommo com 5 campos (1.DIA CONSULTA, 1.UNIDADE, MEDICOS, CONVENIO, STATUS CONVERSA)."));
content.push(numbered("GET imediato Kommo + comparacao field_id vs valor. Se Kommo 'mentiu' (Bug C-12), retorna 502 + erro 'kommo_silent_failure' + tenta rollback Medware via cancelar_agendamento."));
content.push(numbered("Se ambos OK: commit transaction + insere evento medware_gravado + insere evento kommo_atualizado + retorna 200."));

content.push(h2("6.5. Response 200 OK"));
content.push(codeBlock(
  "{\n" +
  '  "ok": true,\n' +
  '  "cod_agendamento_medware": 99887,\n' +
  '  "kommo_updated": true,\n' +
  '  "fields_confirmados": [\n' +
  '    "1.DIA CONSULTA",\n' +
  '    "1.UNIDADE",\n' +
  '    "MEDICOS",\n' +
  '    "CONVENIO",\n' +
  '    "STATUS CONVERSA"\n' +
  "  ],\n" +
  '  "event_id_medware_gravado": 9013,\n' +
  '  "event_id_kommo_atualizado": 9014\n' +
  "}"
));

content.push(h2("6.6. Por que isso elimina C-12 e #208 por design"));
content.push(p("Bug #208 (handle_gravar_agendamento_medware era stub): impossivel repetir porque a unica forma de gravar agora e via esse endpoint. Nao da pra 'pular' a chamada - quem decide que existe e o Lovable, nao cada arquivo do agent."));
content.push(p("Bug C-12 (Kommo mente em custom_fields): impossivel repetir porque o endpoint sempre faz GET pos-PATCH e levanta erro explicito se valor nao bateu. Nao e tarefa do agent verificar - e tarefa do endpoint blindado.", { before: 80 }));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 7. FASE 4
content.push(h1("7. Fase 4 - Vista vw_lead_agendado + Filtros Integrados"));
content.push(p("Duracao estimada: 3 dias. Resolve 100% do Bug C-42.", { italics: true }));
content.push(h2("7.1. Objetivo"));
content.push(p("Eliminar definitivamente o cenario Thamilla (Lia em modo triagem em lead ja agendado). View consolidada do Supabase computa ja_agendado baseado em 3 fontes simultaneas. Agent e filtros reativos consultam essa unica fonte."));

content.push(h2("7.2. View vw_lead_agendado"));
content.push(codeBlock(
  "CREATE OR REPLACE VIEW vw_lead_agendado AS\n" +
  "SELECT\n" +
  "  p.lead_id,\n" +
  "  (\n" +
  "    p.status_kommo IN (101507507, 101109455, 106653499)\n" +
  "    OR EXISTS (\n" +
  "      SELECT 1 FROM events e\n" +
  "       WHERE e.lead_id = p.lead_id\n" +
  "         AND e.tipo = 'slot_confirmado'\n" +
  "         AND (e.payload->>'data')::TIMESTAMPTZ > NOW()\n" +
  "    )\n" +
  "    OR (p.consulta_data IS NOT NULL\n" +
  "        AND p.consulta_data > NOW())\n" +
  "  ) AS ja_agendado,\n" +
  "  p.status_kommo,\n" +
  "  p.consulta_data,\n" +
  "  (\n" +
  "    SELECT MAX(e.ts) FROM events e\n" +
  "     WHERE e.lead_id = p.lead_id\n" +
  "       AND e.tipo = 'slot_confirmado'\n" +
  "  ) AS ultimo_slot_confirmado_em\n" +
  "  FROM patients p;"
));

content.push(h2("7.3. Filtros reativos integrados ao Lovable"));
content.push(p("Antes de cada response Lia sair pra producao, agent chama:"));
content.push(codeBlock(
  "GET /api/public/coerencia/validar?lead_id=23811372&texto=<resposta>\n\n" +
  "Response 200 OK (resposta valida):\n" +
  '{\n' +
  '  "ok": true,\n' +
  '  "texto_aprovado": "<mesmo texto>",\n' +
  '  "filtros_checados": ["c30a", "c41", "c42", "c36"]\n' +
  '}\n\n' +
  "Response 200 OK (resposta substituida):\n" +
  '{\n' +
  '  "ok": false,\n' +
  '  "motivo": "c42_lead_ja_agendado",\n' +
  '  "texto_aprovado": "<texto de fallback canonico>",\n' +
  '  "filtros_disparados": ["c42"]\n' +
  '}'
));
content.push(p("Vantagem: regras de coerencia centralizadas no Lovable. Atualizar uma regra nao exige redeploy do agent - basta editar a Edge Function.", { before: 120 }));

content.push(h2("7.4. Lista de filtros migrados pra Lovable"));
content.push(makeTable([
  ["Filtro", "O que detecta", "Origem do bug"],
  ["c30a", "'Deixa eu reconsultar' com ctx.agenda vazio", "Victor 24147566"],
  ["c41", "Combinado/Resumo sem cobertura financeira", "Milena 24182212"],
  ["c42", "Encerro/triagem em lead ja agendado", "Thamilla 23811372"],
  ["c36", "Afirma consulta marcada com 1.DIA CONSULTA passada", "Karina 22071351"],
  ["c35", "Dia da semana inventado para a data", "Lote de 12 leads"],
], [1800, 4800, 2760]));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 8. MIGRACAO
content.push(h1("8. Roteiro de Migracao - Shadow Mode"));
content.push(p("Cada fase entra em producao em 3 estagios obrigatorios."));
content.push(h2("8.1. Estagio 1 - Shadow puro (24h)"));
content.push(bullet("Agent Python chama Lovable E sistema antigo (Kommo direto / Medware direto) em paralelo."));
content.push(bullet("Resposta usada: sempre a do sistema antigo. Lovable e so observador."));
content.push(bullet("Toda divergencia loga no Slack #bugs-agent com payload completo de ambos."));
content.push(bullet("Criterio de saida: divergencia menor que 5% em 24h consecutivas + zero erro 5xx do Lovable."));
content.push(h2("8.2. Estagio 2 - Switch gradual com fallback (24h)"));
content.push(bullet("Agent chama Lovable primeiro. Se 200 OK em menos de 500ms, usa essa resposta."));
content.push(bullet("Se Lovable retornar 5xx ou exceder timeout, fallback automatico pro sistema antigo."));
content.push(bullet("Criterio de saida: menor que 1% de fallbacks acionados em 24h."));
content.push(h2("8.3. Estagio 3 - Switch completo (permanente)"));
content.push(bullet("Sistema antigo e removido da rota critica."));
content.push(bullet("Mantem funcao de auditoria 1x/dia comparando 100 leads aleatorios."));
content.push(bullet("Rollback e flag toggle no Easypanel (nao revert de codigo)."));
content.push(h2("8.4. Decisao fast-rollback"));
content.push(p("Se qualquer estagio mostrar divergencia maior que 15% OU taxa de erro maior que 2%, rollback imediato pra sistema antigo. Investiga em ambiente staging antes de retomar."));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 9. RISCOS
content.push(h1("9. Riscos e Mitigacao"));
content.push(h2("9.1. Risco - race condition entre turns paralelos"));
content.push(p("Lovable nao resolve Bug #183 (5 turns sendo processados em paralelo cada um com snapshot ctx diferente)."));
content.push(p("Mitigacao: pipeline_lock por conversation_key continua sendo responsabilidade do agent Python. Esta em codigo no repo (commit ja em main), falta confirmar deploy em prod e validar via /admin/replay. Sem isso, mesmo com Supabase como fonte unica, 2 turns paralelos podem ler estados ligeiramente diferentes.", { before: 80 }));

content.push(h2("9.2. Risco - divergencia cache Medware x Medware real"));
content.push(p("Cron 5min implica ate 5min de defasagem. Outra clinica/atendente pode pegar slot no Medware enquanto Lovable ainda mostra disponivel."));
content.push(p("Mitigacao: validacao on-write - endpoint /api/public/agendamento/salvar faz GET no Medware no momento da gravacao. Se slot foi tomado, retorna 409 Conflict + sugere proximo slot disponivel.", { before: 80 }));

content.push(h2("9.3. Risco - endpoint publico de agenda exposto"));
content.push(p("Mesmo com X-Blink-API-Key, vazamento do secret expoe a agenda da clinica."));
content.push(p("Mitigacao: rotacionar secret a cada 90 dias. Adicionar rate limit (100 reqs / min por API key). Log de cada request com IP origem. Em caso de vazamento, rotacao imediata + investigacao de quem teve acesso ao Supabase Secrets.", { before: 80 }));

content.push(h2("9.4. Risco - Lovable Edge Function fora do ar"));
content.push(p("Supabase Edge Functions tem SLA 99.5% (Pro tier). 0.5% = 3.6h/mes de downtime potencial."));
content.push(p("Mitigacao: agent Python tem fallback configurado pra cada endpoint. Se Lovable retornar 5xx, agent usa caminho legado (Kommo direto + Medware direto) automaticamente. Operacao degrada mas nao para.", { before: 80 }));

content.push(h2("9.5. Risco - custo Supabase escala"));
content.push(p("Tabela events cresce indefinidamente. Em 6 meses pode ter 500k+ eventos. View materializada lenta."));
content.push(p("Mitigacao: particionamento por mes (events_2026_07, events_2026_08). Archive eventos > 12 meses pra storage frio. Refresh da view so nas linhas modificadas (CONCURRENTLY).", { before: 80 }));

content.push(new Paragraph({ children: [new PageBreak()] }));

// 10. GLOSSARIO
content.push(h1("10. Glossario - Referencia de Bugs Mencionados"));
content.push(p("Esta secao lista bugs especificos do projeto Blink referenciados no documento, pra alinhamento de vocabulario com a equipe Lovable."));
content.push(makeTable([
  ["ID", "Descricao", "Caso real"],
  ["C-12", "MCP kommo_update_lead retorna success:true mas custom_fields_values fica vazio", "Lote diversos leads"],
  ["C-30A", "Lia escreve 'deixa eu reconsultar agenda' com ctx.agenda vazio", "Sofia 24158652"],
  ["C-35", "Dia da semana inventado para a data oferecida", "Warley + 11 outros"],
  ["C-36", "Lia afirma consulta marcada mas 1.DIA CONSULTA esta no passado", "Karina 22071351"],
  ["C-41", "Lia firma reserva sem convenio definido nem sinal Pix", "Milena 24182212"],
  ["C-42", "Lia continua em triagem inicial em lead ja agendado", "Thamilla 23811372"],
  ["#183", "Race condition entre turns paralelos no pipeline.py", "Lote diversos leads"],
  ["#208", "handle_gravar_agendamento_medware era stub", "Lote diversos (15 dias sem gravar)"],
], [1200, 5400, 2760]));

content.push(spacer());
content.push(p("Documentacao completa de cada bug no arquivo CLAUDE.md do repositorio (secao rolling log). Cada bug tem nome do paciente afetado + commit do fix + licao arquitetural.", { italics: true }));
content.push(spacer());

content.push(h2("Proximo passo concreto"));
content.push(p("Aprovacao deste briefing pela equipe Lovable + criacao de issue por fase no GitHub. Inicio da Fase 1 imediatamente apos aprovacao. Estimativa de entrega completa das 4 fases: 3 semanas corridas (15 dias uteis)."));
content.push(p("Contato tecnico: Fabio Philipe Martins (oabphi@gmail.com) + Claude Cowork (canal Slack #bugs-agent).", { italics: true, before: 80 }));

const doc = new Document({
  creator: "Blink Oftalmologia - Claude Cowork",
  title: "Briefing Tecnico Lovable Fase 2",
  description: "Spec arquitetural pra integracao Lovable <-> Agent Lia",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Calibri", color: "1F3864" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Calibri", color: "2E5395" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Calibri", color: "365F91" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
        ] },
      { reference: "numbers",
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
        ] },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "Blink - Briefing Lovable Fase 2 - v1.0", size: 18, color: "808080" })],
      })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Pagina ", size: 18, color: "808080" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080" }),
        ],
      })] }),
    },
    children: content,
  }],
});

Packer.toBuffer(doc).then(buf => {
  const outPath = process.argv[2] || "BRIEFING_LOVABLE_FASE2_BLINK.docx";
  fs.writeFileSync(outPath, buf);
  console.log("OK Doc salvo em", outPath, "-", (buf.length / 1024).toFixed(1), "KB");
});
