# ATIVAÇÃO E REATIVAÇÃO DE LEADS — PLAYBOOK COMPLETO

Funil "Ativar" do CRM. Substitui/complementa o artigo `10_reativacao_leads.md` com a estrutura real usada pela equipe.

## Mapa de cenários

| Cenário | Códigos Kommo | Quando disparar |
|---|---|---|
| Aniversário do paciente/lead | 2020 FELIZ 1º PACIENTE | Data de aniversário |
| Conectar (lead frio leve) | ANTECIPE SUA CONSULTA, VEJA DE NOVO, 1088 MENS CONECTAR | 24-72h sem resposta |
| Reenviar mensagem (não entrou) | 0000-REENVIAR A MENSAGEM | Falha de entrega |
| Ativar conversa WhatsApp API oficial | 0737 / 1003 ATIVAR CONVERSA | Após 24h da última mensagem (regra Meta) |
| Ativar 24h sem resposta | 1079 ATIVAR CONVERSA IMEDIATO | 24h sem resposta |
| Ativar especificamente catarata | ATIVAR CATARATA | Lead de catarata frio |
| Ativar sem resposta Dr. Fabrício | ATIVAR sem RESPOSTA DR. FABRICIO | Lead de catarata frio que ignorou Fabrício |
| Novo horário disponível | 1056-NOVO HORÁRIO | Quando abre slot novo na agenda |
| Grau de urgência (escalonamento) | 1039 / 0741 ATIVAR GRAU DE URGÊNCIA | Lead morno que precisa subir prioridade |
| Aos sábados | 0796 - CAMPANHA SÁBADO | Quando há atendimento sábado |
| Captação todas especialidades | 0736 / 1036 CAPTAÇÃO TODAS ESP | Campanha geral |
| Final do ano | 1074 ATIVAÇÃO FINAL DO ANO | Dezembro |

## Padrões de mensagens já vistos (referência)

### VEJA DE NOVO (reativação leve)
> Olá, [Nome], voltando por aqui! 😊 Veja de novo a oportunidade de cuidar dos seus olhos — e também dos olhos de quem você ama 💙 — com nossos especialistas em oftalmologia! 👁️✨

### ANTECIPE SUA CONSULTA (reativação com gancho de cuidado)
> Olá, [Nome]! Em continuidade ao seu atendimento 💙, vale um lembrete: hoje são telas demais 📱💻 e óculos de sol de menos 🕶️☀️ — e seus olhos pedem atenção.
>
> Quer antecipar sua consulta?

### 1098 SEM RESPOSTA R$ (objeção financeira velada)
> Olá, [Nome]! ✨ Imagino que a correria do dia a dia tenha dificultado o retorno 🏃‍♀️, ou talvez o valor do investimento tenha impactado seu planejamento. 💭

### 2020 FELIZ (aniversário do paciente)
> [Nome], hoje há um aniversariante na nossa lista de pacientes que cuidamos com carinho! 🎉🎂
>
> Que esse novo ciclo venha com saúde e visão nítida! E se você quiser comemorar com um olhar mais cuidado, temos um presente especial pra você: [oferta].

### CAMPANHA SÁBADO (0796)
> [Nome], 🗓️ esta semana abrimos atendimento aos sábados na unidade [UNIDADE]!
>
> Pra quem tem semana corrida, é a chance perfeita.
>
> Quer que eu reserve um horário?

### NOVO HORÁRIO (1056)
> [Nome], abriu uma vaga exclusiva para esta [semana/mês] na [unidade]! ⚡
>
> ✅ [DATA] às [HORA] com [MÉDICA]
>
> Posso reservar pra você?

### GRAU DE URGÊNCIA (1039 / 0741)
Eleva o tom quando paciente já demorou e tem sintoma:
> [Nome], notei que ainda não conseguimos avançar com seu agendamento. 💙
>
> Como você mencionou [sintoma], não recomendamos adiar a avaliação. Posso te encaixar [data próxima]?

## Regras de ativação

### Janela de 24h (regra Meta)
Após 24h da última mensagem do paciente, **só é possível enviar mensagem com TEMPLATE APROVADO** da Meta (não conversação livre).
- Use 0737 ou 1003 ATIVAR CONVERSA WHATSAPP API OFICIAL (templates aprovados).
- Após o paciente responder, a janela de 24h reabre e você pode conversar livre.

### Cadência sugerida
| Dia | Ação |
|---|---|
| D+0 | Última mensagem do agente |
| D+1 (24h) | Template "voltando por aqui" (VEJA DE NOVO) |
| D+3 (72h) | Empatia + ancoragem (1098 SEM RESPOSTA) |
| D+7 | Cuidado/prevenção (ANTECIPE SUA CONSULTA) |
| D+15 | Pausa OU se cancelado → retomada leve |
| D+30 | Pausa total. Reabrir só por evento (aniversário, campanha, NOVO HORÁRIO) |

### Quando NÃO ativar
- Paciente disse "não tenho interesse" → opt-out permanente.
- Lead bloqueou ou denunciou → bloquear no CRM.
- 3 rejeitos seguidos → pausar 60 dias.

### Métricas-alvo
- 25% dos leads frios respondem à 1ª reativação.
- 8% acabam agendando após 3 reativações.
- Conversão por canal sazonal (sábado, final do ano) costuma ser 2x maior.

## Catarata frio (regra especial — ATIVAR CATARATA)
Lead de catarata que sumiu requer abordagem mais robusta. Sequência:
1. **Mensagem leve** ("voltando por aqui").
2. Se não responder em 48h: **Autoridade médica** (recapitula Dr. Fabrício + Dra. Kátia + Johns Hopkins).
3. Se não responder em 7d: **Novo gancho** (vaga exclusiva, oferta de avaliação a R$ 445).
4. Se não responder em 15d: pausa.

NUNCA repetir o funil de 9 áudios do zero pra lead frio — comece de onde parou.
