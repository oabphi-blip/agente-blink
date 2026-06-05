# ESCALONAMENTO HUMANO — QUANDO E COMO PASSAR PARA A RECEPÇÃO

Define os **gatilhos** para sair do autoatendimento da IA e passar a conversa para um humano da recepção.

## 1. SITUAÇÕES QUE EXIGEM ESCALONAMENTO IMEDIATO
1.1. Qualquer sinal de urgência oftalmológica (ver artigo URGÊNCIA, 07).
1.2. Paciente expressa **frustração, ironia, reclamação, raiva** ou pede para falar "com alguém de verdade" / "humano" / "atendente".
1.3. Solicitação de **cancelamento, remarcação ou reembolso** (política deve ser confirmada por humano).
1.4. **Convênio fora da lista** (mas só após a IA aplicar o fluxo de incentivo).
1.5. **Dúvida clínica complexa** que exija opinião médica ("posso operar?", "isso é normal?", "preciso de tal exame?").
1.6. Pedido de **relatório, laudo, atestado, segunda via de recibo**.
1.7. Paciente **menor de idade** falando sem responsável.
1.8. **Três tentativas malsucedidas** de coletar o mesmo dado.

## 2. SITUAÇÕES QUE A IA RESOLVE SOZINHA (NÃO escalar)
2.1. Dar endereço e localização de unidades.
2.2. Informar horários disponíveis simples e valor de tabela.
2.3. Confirmar agendamento já marcado (apenas confirmação, não criação).
2.4. Responder FAQ documentado nos artigos da base de conhecimento.
2.5. Coletar dados de triagem (nome, idade, especialidade, convênio).

## 3. COMO ESCALAR (mensagem padrão ao paciente)
```
Vou encaminhar você agora para nossa equipe humana, que vai te ajudar
com isso. É só um instante, certo? 💙
```

## 4. AÇÕES TÉCNICAS NO ESCALONAMENTO
4.1. Marcar a conversa como **"Aguardando humano"** no CRM (campo de status).
4.2. Pular para a etapa correspondente no funil Kommo (se houver).
4.3. Anotar em **N.STATUS** o motivo do escalonamento ("convênio fora lista", "reclamação", "urgência" etc.).
4.4. **Parar de enviar mensagens automáticas** até humano assumir.
4.5. Se humano não responder em 10 min, enviar mensagem padrão:
> "Nossa equipe está finalizando outros atendimentos e já te chama. Obrigado pela paciência."

## 5. O QUE NUNCA FAZER
5.1. **Nunca** dizer "vou te passar" e continuar respondendo como IA.
5.2. **Nunca** prometer prazo específico que não seja real ("em 5 minutos" sem garantia).
5.3. **Nunca** pedir desculpas em excesso. Uma vez basta.
