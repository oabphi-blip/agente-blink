/**
 * Widget "Agente Blink" — ponte entre o Salesbot do Kommo e o agente de IA.
 *
 * Função: registrar o passo de Widget no designer do Salesbot. Ao salvar,
 * gera um fluxo que faz `widget_request` para o endpoint /kommo do agente,
 * enviando a mensagem do paciente. A resposta do agente volta pelo
 * return_url e o Salesbot a exibe no chat (handler "show").
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

      /**
       * Chamado quando o usuário salva o passo do widget no designer do
       * Salesbot. Monta o fluxo: chama o agente e segue para o próximo passo.
       */
      onSalesbotDesignerSave: function (_handler_code, params) {
        var hookUrl =
          (params && params.url) ||
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
