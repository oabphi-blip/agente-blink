/**
 * BLINK OFTALMOLOGIA — Setup do Formulário de Pré-Agendamento
 *
 * COMO USAR:
 * 1. Abrir o formulário: https://docs.google.com/forms/d/1V2q8fcyPUm7CRBAImGzZVmqCP7353PclCjRllx8tMDA/edit
 * 2. Clicar em "Extensões" → "Apps Script"
 * 3. Colar TODO este arquivo no editor (substituir o conteúdo padrão)
 * 4. Clicar em "Executar" com a função "configurarFormulario" selecionada
 * 5. Autorizar as permissões quando solicitado
 * 6. Aguardar a mensagem de sucesso no Log
 *
 * ATENÇÃO: executar APENAS UMA VEZ. Se executar novamente, vai duplicar os campos.
 */

var FORM_ID = '1V2q8fcyPUm7CRBAImGzZVmqCP7353PclCjRllx8tMDA';

// ─── Configuração do Kommo para integração ────────────────────────────────────
// Após o formulário estar pronto, configure o webhook abaixo com o secret do agente
var KOMMO_WEBHOOK_URL = 'https://blink-agent.6prkfn.easypanel.host/admin/form-preagendamento';
var WEBHOOK_SECRET    = 'blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a';  // mesmo do agente


// ═════════════════════════════════════════════════════════════════════════════
// PARTE 1 — Configurar campos do formulário
// ═════════════════════════════════════════════════════════════════════════════

function configurarFormulario() {
  var form = FormApp.openById(FORM_ID);

  // Limpa campos existentes (caso rode de novo por acidente)
  var itens = form.getItems();
  for (var i = itens.length - 1; i >= 0; i--) {
    form.deleteItem(itens[i]);
  }

  // ── Cabeçalho ────────────────────────────────────────────────────────────
  form.setTitle('📋 Pré-Agendamento — Blink Oftalmologia');
  form.setDescription(
    'Preencha este formulário para agilizar seu agendamento. ' +
    'Ao enviar, você garante PRIORIDADE no contato da nossa equipe! 🎯\n\n' +
    '💬 Preferência: se preferir, pode nos passar as informações diretamente pelo WhatsApp.'
  );
  form.setConfirmationMessage(
    '✅ Recebemos suas informações!\n\n' +
    'Você tem PRIORIDADE no agendamento. ' +
    'Nossa equipe entrará em contato pelo WhatsApp em breve para confirmar o horário.\n\n' +
    'Obrigado pela confiança na Blink Oftalmologia! 👁️'
  );
  form.setCollectEmail(false);
  form.setShowLinkToRespondAgain(false);

  // ── Campo 1: WhatsApp ────────────────────────────────────────────────────
  form.addTextItem()
    .setTitle('Número de WhatsApp (com DDD)')
    .setHelpText('Ex: 61 9 9999-9999 — usamos para localizar seu cadastro e confirmar o agendamento')
    .setRequired(true);

  // ── Seção 1 ──────────────────────────────────────────────────────────────
  form.addSectionHeaderItem()
    .setTitle('Dados do paciente')
    .setHelpText('Informe quem vai realizar a consulta');

  // ── Campo 2: Nome do responsável ─────────────────────────────────────────
  form.addTextItem()
    .setTitle('Seu nome completo (quem está no WhatsApp)')
    .setRequired(true);

  // ── Campo 3: Nome do paciente ────────────────────────────────────────────
  form.addTextItem()
    .setTitle('Nome completo do paciente')
    .setHelpText('Se diferente de você — ex: nome do filho, esposo(a)')
    .setRequired(true);

  // ── Campo 4: Data de nascimento ──────────────────────────────────────────
  form.addTextItem()
    .setTitle('Data de nascimento do paciente')
    .setHelpText('Formato: DD/MM/AAAA  —  Ex: 15/03/2010')
    .setRequired(true);

  // ── Campo 5: CPF ─────────────────────────────────────────────────────────
  form.addTextItem()
    .setTitle('CPF do paciente')
    .setHelpText('Apenas números  —  Ex: 123.456.789-09')
    .setRequired(true);

  // ── Seção 2 ──────────────────────────────────────────────────────────────
  form.addSectionHeaderItem()
    .setTitle('Preferências de agendamento');

  // ── Campo 6: Convênio ────────────────────────────────────────────────────
  form.addListItem()
    .setTitle('Convênio de saúde')
    .setRequired(true)
    .setChoiceValues([
      'Sem convênio (pagar particular)',
      'Anafe',
      'Bacen',
      'Care Plus',
      'Casec (Codevasf)',
      'Casembrapa / Embrapa',
      'Conab',
      'E-vida (Luminar)',
      'Fascal',
      'Omint',
      'PF Saúde',
      'PLAS/JMU (STM)',
      'Plan Assiste - MPF / MPU',
      'PróSaúde (Câmara dos Deputados)',
      'Pro ser STJ',
      'Proasa',
      'Saúde Caixa',
      'Saúde Petrobrás',
      'Serpro',
      'SIS Senado',
      'STF-Med',
      'TJDFT Pró-Saúde',
      'TRE',
      'TRF Pró-Social',
      'TRT',
      'TST Saúde',
      'Outro (informar nas observações)'
    ]);

  // ── Campo 7: Unidade ─────────────────────────────────────────────────────
  form.addMultipleChoiceItem()
    .setTitle('Unidade preferida')
    .setRequired(false)
    .setChoiceValues([
      'Asa Norte — atende Segunda, Quarta e Sexta',
      'Águas Claras — atende Terça e Quinta',
      'Sem preferência (qualquer unidade disponível)'
    ]);

  // ── Campo 8: Motivo ──────────────────────────────────────────────────────
  form.addParagraphTextItem()
    .setTitle('Motivo da consulta')
    .setHelpText('Ex: rotina, olho vermelho, dificuldade de visão, estrabismo, catarata, bebê de X meses, retorno...')
    .setRequired(false);

  // ── Campo 9: Observações ─────────────────────────────────────────────────
  form.addParagraphTextItem()
    .setTitle('Observações adicionais')
    .setHelpText('Qualquer informação extra que queira nos passar')
    .setRequired(false);

  Logger.log('✅ Formulário configurado com sucesso!');
  Logger.log('📋 Link de resposta: ' + form.getPublishedUrl());
  Logger.log('✏️  Link de edição:  ' + form.getEditUrl());
}


// ═════════════════════════════════════════════════════════════════════════════
// PARTE 2 — Webhook para o agente Blink ao receber resposta
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Instalar trigger: Extensões → Apps Script → Acionadores (relógio)
 * → Adicionar acionador → função onFormSubmit → evento: "Ao enviar formulário"
 *
 * Ou rodar uma vez a função instalarTrigger() abaixo.
 */

function onFormSubmit(e) {
  try {
    var respostas = e.response.getItemResponses();
    var dados = {};

    // Mapeia perguntas → valores
    for (var i = 0; i < respostas.length; i++) {
      var pergunta = respostas[i].getItem().getTitle();
      var resposta = respostas[i].getResponse();
      dados[pergunta] = resposta;
    }

    // Extrai campos esperados
    var payload = {
      whatsapp:         dados['Número de WhatsApp (com DDD)'] || '',
      nome_contato:     dados['Seu nome completo (quem está no WhatsApp)'] || '',
      nome_paciente:    dados['Nome completo do paciente'] || '',
      data_nascimento:  dados['Data de nascimento do paciente'] || '',
      cpf:              dados['CPF do paciente'] || '',
      convenio:         dados['Convênio de saúde'] || '',
      unidade:          dados['Unidade preferida'] || '',
      motivo:           dados['Motivo da consulta'] || '',
      observacoes:      dados['Observações adicionais'] || '',
      form_timestamp:   new Date().toISOString(),
      secret:           WEBHOOK_SECRET
    };

    // Envia para o agente Blink
    var options = {
      method: 'POST',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    var response = UrlFetchApp.fetch(KOMMO_WEBHOOK_URL + '?secret=' + WEBHOOK_SECRET, options);
    Logger.log('Webhook enviado: ' + response.getResponseCode());
    Logger.log('Resposta: ' + response.getContentText());

  } catch (err) {
    Logger.log('Erro no webhook: ' + err.toString());
  }
}


/**
 * Rodar UMA VEZ para instalar o trigger automático de envio.
 */
function instalarTrigger() {
  // Remove triggers antigos para evitar duplicata
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'onFormSubmit') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Cria trigger novo
  var form = FormApp.openById(FORM_ID);
  ScriptApp.newTrigger('onFormSubmit')
    .forForm(form)
    .onFormSubmit()
    .create();

  Logger.log('✅ Trigger instalado! Cada envio do formulário vai acionar onFormSubmit.');
}
