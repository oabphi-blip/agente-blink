# Migração para o número oficial 8133-1005 — Passo final (Bloco 3)

## Situação atual

✅ **Bloco 1** — endpoint do agente no ar: `https://blink-agent.6prkfn.easypanel.host/kommo`
✅ **Bloco 2** — widget "Agente Blink IA" criado e instalado no Kommo (chave secreta capturada)
✅ Agente renomeado para **Lia**
🔲 **Bloco 3** — configurar o Salesbot para usar o nosso agente

## O que foi descoberto

A clínica já usa um agente de IA de terceiro: o Salesbot **"GPT Agent"** (gatilho "qualquer nova conversa", ~4.400 sessões ativas). Para o **nosso** agente (Lia) assumir, é preciso:
1. Criar um Salesbot que use o nosso widget "Agente Blink IA";
2. **Desativar o Salesbot "GPT Agent"** — senão os dois respondem juntos.

---

## BLOCO 3 — passo a passo

### Parte 1 — Criar o Salesbot da Lia

1. No Kommo: **Configurações → Comunicações** (`univeja.kommo.com/settings/communications/`).
2. Na lista de Salesbots, clique em **"Criar"** (linha "+ Criar ou importar um novo robô").
3. Escolha **"Começar do zero"**.
4. No construtor, no nome do bot (canto superior esquerdo, onde aparece "SALESBOT #N"), renomeie para **`Lia - Agente Blink`**.
5. Clique no **"+"** depois de "Iniciar robô" para adicionar o primeiro passo.
6. Na lista de passos, escolha **"Widget"**.
7. Selecione o widget **"Agente Blink IA"**.
8. No campo de URL do widget, confirme: `https://blink-agent.6prkfn.easypanel.host/kommo`
9. Configure o **Gatilho** (caixa "Gatilhos" → "+ Gatilho"): selecione **"Mensagem recebida"** / **"Qualquer nova conversa"**, no canal **WhatsApp Business** (o 8133-1005).
10. Clique em **"Salvar"** (canto superior direito).

### Parte 2 — Desativar o "GPT Agent"

11. Volte para a lista de Salesbots (Configurações → Comunicações).
12. Localize o Salesbot **"GPT Agent"**.
13. **Remova o gatilho dele** (ou desative o bot) — assim ele para de disparar. NÃO exclua (o Kommo avisa para não excluir); só tire o gatilho "qualquer nova conversa".
14. Clique em **"Salvar"**.

### Parte 3 — Testar

15. Mande uma mensagem de um WhatsApp para o **8133-1005**.
16. O Salesbot "Lia - Agente Blink" dispara → chama o nosso agente → a Lia responde.
17. Confira a saúde em `https://blink-agent.6prkfn.easypanel.host/health`.

---

## Importante

- O número **0710 (Evolution)** continua funcionando com a Lia durante toda a transição.
- Se algo der errado no 8133, basta **reativar o gatilho do "GPT Agent"** que o atendimento anterior volta — nada é destruído.
- A chave secreta da integração já está comigo; numa passada final de segurança eu ativo a validação do webhook.
