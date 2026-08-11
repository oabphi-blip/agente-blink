/**
 * Widget "Agente Blink IA" — ponte entre o Salesbot do Kommo e o agente de IA.
 *
 * Registra o passo de Widget no designer do Salesbot. Ao salvar, gera um fluxo
 * que faz widget_request ao endpoint /kommo do agente, enviando a mensagem do
 * paciente. A resposta do agente volta pelo return_url e o Salesbot a exibe.
 *
 * Doc: https://developers.kommo.com/docs/private-chatbot-integration
 */
define(['jquery'], function ($) {
  return function CustomWidget() {
    var self = this;

    var createStep = function (questions) {
      return { question: questions, require: [] };
    };

    this.callbacks = {
      settings: function () {},
      init: function () { return true; },
      bind_actions: function () { return true; },
      render: function () { return true; },

      onSalesbotDesignerSave: function (_handler_code, params) {
        var hookUrl =
          (params && params.text) ||
          'https://blink-agent.6prkfn.easypanel.host/kommo';

        var requestData = {
          message: '{{message_text}}',
          lead_id: '{{lead.id}}',
          from: 'widget'
        };

        var step = createStep([
          {
            handler: 'widget_request',
            params: {
              url: hookUrl,
              data: requestData
            }
          }
        ]);

        return JSON.stringify([step]);
      },

      destroy: function () {},
      onSave: function () { return true; }
    };

    return this;
  };
});
