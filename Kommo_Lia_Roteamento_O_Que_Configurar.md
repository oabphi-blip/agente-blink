# Roteamento da Lia no Kommo — o que falta configurar

## Problema
Leads que chegam pelo Instagram (anúncios), pelo número oficial 8133 e pelo
0710 NÃO estão recebendo resposta automática da Lia. Eles ficam parados na
etapa `0-ETAPA ENTRADA` até um atendente humano abrir manualmente.

## Diagnóstico (verificado)
- O agente Lia está NO AR e saudável. Endpoint de saúde responde OK:
  https://blink-agent.6prkfn.easypanel.host/health
- O Salesbot "Claude 2.0" do Kommo ESTÁ rodando — mas só faz DISTRIBUIÇÃO
  (atribui o lead a um atendente; ex.: "Distribuidor 0240 · J1 → Rafaela
  Rodrigues").
- NÃO existe, hoje, nenhum passo/gatilho que chame a Lia para gerar a
  resposta. O painel de automação do funil ATENDE está sem gatilho na
  etapa 0-ETAPA ENTRADA ("Adicionar gatilho").
- Conclusão: não é defeito do agente. É uma LACUNA de configuração no
  Kommo — falta o passo que aciona a Lia.

## Como a Lia se conecta ao Kommo
A Lia é uma integração de chatbot privada (private chatbot integration).
O Salesbot precisa ter um passo que envie a mensagem do paciente para o
endpoint do agente e devolva a resposta no WhatsApp:

    POST  https://blink-agent.6prkfn.easypanel.host/kommo

Esse endpoint recebe o widget_request do Salesbot, gera a resposta com a
Lia e responde no return_url (mecanismo padrão de chatbot privado do Kommo).

## O que precisa ser feito (quem tem acesso pleno ao Salesbot)
1. Abrir o Salesbot "Claude 2.0" no construtor de bots do Kommo.
2. Garantir que ele dispara em TODA mensagem recebida, para TODAS as
   fontes do funil ATENDE — não só uma:
     - Blink Oftalmologia (Messenger / anúncios do Instagram)
     - +55 61 8133-1005 (Messenger / WhatsApp oficial)
     - 556196630710 (Widget / 0710)
3. No fluxo do bot, DEPOIS do passo de distribuição, adicionar o passo
   que chama a integração de chatbot da Lia (o passo de "widget" /
   chamada da integração privada). É esse passo que faz o widget_request
   para o endpoint /kommo acima.
4. Confirmar que a integração privada do agente está instalada e ativa
   na conta (Configurações → Integrações).
5. TESTAR com 1 lead real antes de confiar — enviar uma mensagem de
   teste e verificar se a Lia responde.

## Atenção / riscos
- O Salesbot "Claude 2.0" também faz a distribuição de leads. Qualquer
  alteração deve preservar esse passo — não remover a distribuição.
- Mudança de etapa pode disparar outras automações. Testar em um lead
  antes de aplicar amplamente.

## Enquanto isso não estiver pronto (medida imediata)
Os leads ESTÃO sendo distribuídos para a equipe. Regra operacional:
todo atendente, ao receber um lead atribuído, deve abri-lo e responder
em até poucos minutos em horário comercial. É o que garante que nenhum
paciente fique sem resposta hoje.
