# Templates Meta WhatsApp Business — pronto pra submeter

**Data**: 03/06/2026
**Total**: 14 templates (8 lead frio + 6 ciclo confirmação/pós-consulta)
**Idioma**: pt_BR
**Como submeter**: Meta Business Manager → WhatsApp → Modelos de mensagem → "Criar modelo" → colar nome/categoria/body conforme cada bloco abaixo.

---

## Regras Meta respeitadas

- ✅ Placeholders numerados sequencialmente: `{{1}}`, `{{2}}`, `{{3}}`
- ✅ Body não começa nem termina com placeholder
- ✅ Sem placeholders adjacentes (`{{1}} {{2}}` proibido — texto entre eles)
- ✅ Quick Reply: máximo 3 botões, texto até 25 chars cada
- ✅ Footer (quando usado) até 60 chars, sem placeholder
- ✅ Body até 1024 chars
- ✅ Categoria correta (UTILITY = transação iniciada pelo cliente; MARKETING = reativação/promo)
- ✅ Médico SEMPRE nome+sobrenome (regra Blink)

---

## CICLO LEAD FRIO (categoria MARKETING — reativação fora da janela 24h)

### Template 1 — `blink_lf_a_convenio_aceito_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink Oftalmologia. Seu convênio {{2}} cobre consulta com a Dra. Karla Delalibera — sem sair do bolso.

Tenho horário pra essa semana ainda. Como prefere?

1. Asa Norte
2. Águas Claras
3. Prefiro que me liguem

Responde com 1, 2 ou 3 que eu já organizo.
```

**Botões (Quick Reply, máx 3):**
- `Asa Norte`
- `Águas Claras`
- `Me liguem`

**Exemplos pro Meta:**
- `{{1}}` = `Maria Teresa`
- `{{2}}` = `Plan Assiste — MPF`

---

### Template 2 — `blink_lf_b_particular_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink Oftalmologia. Sei que o convênio {{2}} não cobre aqui — mas temos uma condição particular com sinal de 50% via Pix pra reservar o horário.

Valor consulta Dra. Karla Delalibera: R$ 611 (sinal R$ 305,50). Vale a tranquilidade de fechar com a melhor.

Como prefere seguir?

1. Agendar essa semana
2. Agendar pra próximas 2 semanas
3. Receber link de avaliação online primeiro

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Essa semana`
- `Próximas 2 semanas`
- `Link avaliação`

**Exemplos:**
- `{{1}}` = `Beatriz`
- `{{2}}` = `Inas GDF`

> **Observação**: para pacientes SEM convênio nenhum (não "convênio não aceito"), passar `{{2}}` = `"sem convênio"` — frase fica natural.

---

### Template 3 — `blink_lf_c_pediatrico_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá! Aqui é a Blink Oftalmologia, sobre a consulta do(a) {{1}}.

Avaliação oftalmológica precoce na infância é o que evita problemas de aprendizado e desenvolvimento depois. A Dra. Karla Delalibera é oftalmopediatra — atende criança calminha, sem demora.

Como podemos seguir?

1. Marcar essa semana
2. Marcar nas próximas 2 semanas
3. Me passe info sobre como é a consulta primeiro

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Essa semana`
- `Próximas 2 semanas`
- `Como é a consulta`

**Exemplos:**
- `{{1}}` = `Helena Maria`

---

### Template 4 — `blink_lf_d_familia_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink Oftalmologia. Vi que vocês querem consulta pra {{2}} e {{3}} — posso encaixar os dois no mesmo dia, em horários seguidos, pra você não voltar duas vezes.

Como prefere?

1. Mesmo dia essa semana
2. Mesmo dia nas próximas 2 semanas
3. Em datas separadas mesmo

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Essa semana`
- `Próximas 2 semanas`
- `Datas separadas`

**Exemplos:**
- `{{1}}` = `Luana`
- `{{2}}` = `Helena Maria`
- `{{3}}` = `Vicente`

---

### Template 5 — `blink_lf_e_pausa_paciente_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink. Lembrei de você — da última vez você comentou que ia {{2}}.

Sem pressão. Só quero deixar reservado um espaço quando você estiver pronta. Me avisa:

1. Já resolvi, pode agendar essa semana
2. Ainda preciso de mais 2-3 semanas
3. Te aviso eu mesma quando estiver

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Já resolvi`
- `Mais 2-3 semanas`
- `Aviso depois`

**Exemplos:**
- `{{1}}` = `Circe`
- `{{2}}` = `tirar o siso`

---

### Template 6 — `blink_lf_f_catarata_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink Oftalmologia. Vi que você tinha interesse em avaliar a catarata com o Dr. Fabrício Freitas, especialista em cirurgia refrativa e de catarata.

A avaliação completa é R$ 297 — define se tem indicação cirúrgica e qual a melhor lente. Quanto antes a avaliação, mais opções de tratamento.

Como prefere?

1. Avaliação essa semana
2. Avaliação nas próximas 2 semanas
3. Quero entender melhor antes

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Essa semana`
- `Próximas 2 semanas`
- `Entender melhor`

**Exemplos:**
- `{{1}}` = `João da Silva`

---

### Template 7 — `blink_lf_g_cliente_conhecido_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Aqui é a Blink Oftalmologia. Já faz mais de um ano da sua última consulta com a Dra. Karla Delalibera — está na hora do check-up anual pra acompanhar o grau e a saúde dos olhos.

Já reservei essa janela pra você. Como prefere?

1. Marcar essa semana
2. Marcar nas próximas 2 semanas
3. Me avisa um dia antes pra eu confirmar

Responde 1, 2 ou 3.
```

**Botões (Quick Reply):**
- `Essa semana`
- `Próximas 2 semanas`
- `Avisar antes`

**Exemplos:**
- `{{1}}` = `Circe`

---

### Template 8 — `blink_lf_h_sem_nome_v1`

**Categoria**: MARKETING
**Idioma**: pt_BR

**Body:**
```
Olá! Aqui é a Blink Oftalmologia.

Vi que você entrou em contato sobre consulta com a gente e acabou ficando pendente — estou retomando pra fechar.

Pra eu te oferecer o horário certo:

1. A consulta é pra você ou pra outra pessoa? Me passa o nome.
2. É por convênio ou particular?
3. Prefere Asa Norte ou Águas Claras?

Responde 1, 2 e 3 em uma mensagem só que eu já organizo o horário.
```

**Botões**: nenhum (esse template pede texto livre como resposta).

**Exemplos**: sem variáveis.

> **Observação**: por não ter variáveis, esse template é o mais fácil de aprovar.

---

## CICLO CONFIRMAÇÃO + PÓS-CONSULTA (categoria UTILITY — transação iniciada pelo cliente)

### Template 9 — `blink_conf_d1_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Em continuidade ao atendimento, informamos os dados para confirmar a consulta.

Detalhes do Agendamento:
- Dia/Hora: {{2}}
- Paciente: {{3}}
- Médica: {{4}}

Se não recebermos confirmação em até 2 horas após esta mensagem, chamaremos outro paciente da fila de espera.

Caso isso aconteça, entraremos em contato para remarcar seu atendimento. Obrigado!

1. Confirmo
2. Quero antecipar
3. Entrar na fila de espera (próx. 30 dias)
```

**Botões (Quick Reply):**
- `Confirmo`
- `Quero antecipar`
- `Fila de espera`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `20/04/2026 13:30`
- `{{3}}` = `Valentina Raulino Coelho Vilaça`
- `{{4}}` = `Dra. Karla Delalibera`

---

### Template 10 — `blink_loc_aguas_claras_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Para a consulta prevista em {{2}}, segue o endereço e o link de localização da Blink Oftalmologia, unidade Águas Claras:

Endereço: Felicittá Shopping — Rua 36 Norte, Lote 05 sn, Bloco 11, Loja 48 — Águas Claras, Brasília DF

Estaremos à disposição para atender!
```

**Footer**: nenhum.

**Botões (CTA URL):**
- Tipo: `URL`
- Texto botão: `Ver no Google Maps`
- URL: `https://maps.app.goo.gl/FRbkUtg4U4xG55q18`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `20/04/2026 13:30`

---

### Template 11 — `blink_loc_asa_norte_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Para a consulta prevista em {{2}}, segue o endereço e o link de localização da Blink Oftalmologia, unidade Asa Norte:

Endereço: SGAN 607, Asa Norte, Bloco A Sala 123, Ed. Brasília Medical Center, CEP 70830-300

Estaremos à disposição para atender!
```

**Botões (CTA URL):**
- Tipo: `URL`
- Texto botão: `Ver no Google Maps`
- URL: `https://maps.app.goo.gl/jPfjSsXA1bHhsyw56`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `20/04/2026 13:30`

---

### Template 12 — `blink_pos_avaliacao_asa_norte_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Obrigado por confiar na {{2}}, especialista em {{3}}.

Sua opinião é muito importante para ampliar nossa visão. Buscamos saber como foi sua experiência na Blink Oftalmologia, unidade Asa Norte.
```

**Botões (CTA URL):**
- Tipo: `URL`
- Texto botão: `Avaliar no Google`
- URL: `https://g.page/r/CZYHYwv6CgYcEAE/review`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `Dra. Karla Delalibera`
- `{{3}}` = `Oftalmopediatria`

---

### Template 13 — `blink_pos_avaliacao_aguas_claras_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Obrigado por confiar na {{2}}, especialista em {{3}}.

Sua opinião é muito importante para ampliar nossa visão. Buscamos saber como foi sua experiência na Blink Oftalmologia, unidade Águas Claras.
```

**Botões (CTA URL):**
- Tipo: `URL`
- Texto botão: `Avaliar no Google`
- URL: `https://g.page/r/CdTrhQ8o4DYaEAE/review`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `Dra. Karla Delalibera`
- `{{3}}` = `Oftalmologia Geral`

---

### Template 14 — `blink_proxima_consulta_v1`

**Categoria**: UTILITY
**Idioma**: pt_BR

**Body:**
```
Olá, {{1}}!

Agradecemos pela realização da consulta na data de {{2}}.

A próxima consulta de {{3}} está prevista para daqui {{4}}.

Quer que eu já reserve um horário?

1. Sim, agendar essa semana
2. Sim, mas só daqui um tempo (me lembre depois)
3. Vou entrar em contato eu mesma quando estiver pronta
```

**Botões (Quick Reply):**
- `Agendar agora`
- `Lembrar depois`
- `Eu entro em contato`

**Exemplos:**
- `{{1}}` = `Kaliana`
- `{{2}}` = `20/04/2026 13:30`
- `{{3}}` = `Benicio Raulino Coelho Vilaça`
- `{{4}}` = `1 (um) ano`

---

## JSON pronto pra POST direto na Cloud API (alternativa ao Business Manager)

Salvar como `templates_meta_post.json` e usar com `curl` ou via SDK Meta. Substituir `{WABA_ID}` e `{ACCESS_TOKEN}`:

```bash
curl -X POST \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @blink_lf_a_convenio_aceito_v1.json \
  "https://graph.facebook.com/v18.0/{WABA_ID}/message_templates"
```

### Exemplo: `blink_lf_a_convenio_aceito_v1.json`

```json
{
  "name": "blink_lf_a_convenio_aceito_v1",
  "language": "pt_BR",
  "category": "MARKETING",
  "components": [
    {
      "type": "BODY",
      "text": "Olá, {{1}}!\n\nAqui é a Blink Oftalmologia. Seu convênio {{2}} cobre consulta com a Dra. Karla Delalibera — sem sair do bolso.\n\nTenho horário pra essa semana ainda. Como prefere?\n\n1. Asa Norte\n2. Águas Claras\n3. Prefiro que me liguem\n\nResponde com 1, 2 ou 3 que eu já organizo.",
      "example": {
        "body_text": [["Maria Teresa", "Plan Assiste — MPF"]]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        { "type": "QUICK_REPLY", "text": "Asa Norte" },
        { "type": "QUICK_REPLY", "text": "Águas Claras" },
        { "type": "QUICK_REPLY", "text": "Me liguem" }
      ]
    }
  ]
}
```

---

## Ordem de submissão recomendada

| Prioridade | Templates | Categoria | Motivo |
|---|---|---|---|
| 🔴 Alta (semana 1) | Templates 8, 9, 10, 11 | UTILITY + 1 MARKETING simples | UTILITY aprova rápido (24h); 8 (sem nome) também porque não tem variável |
| 🟡 Média (semana 1-2) | Templates 1, 3, 7 | MARKETING | Cobrem ~60% dos leads frios |
| 🟢 Baixa (semana 2) | Templates 2, 4, 5, 6, 12, 13, 14 | MARKETING + UTILITY | Cobrem segmentos menores ou pós-consulta |

---

## Próximos passos

1. ✅ Fábio revisa os 14 textos finais (alguma mudança?).
2. 📤 Submeter pelo **Meta Business Manager** ou via **API Cloud** (JSON acima).
3. ⏳ Aguardar aprovação Meta (24-72h por template).
4. 🔧 Quando aprovados, adicionar slugs em `voice_agent/templates_meta.py` (já existe estrutura `TemplateMeta`).
5. 🚀 Dispatcher usa template aprovado pra abrir janela 24h → Lia continua em texto livre dentro da janela.

---

## Limites Meta a considerar

- **Categoria MARKETING**: até **1000 conversas iniciadas/24h** sem custo extra (depois disso = custo por conversa).
- **Categoria UTILITY**: sem limite duro, mas Meta monitora frequência por número destinatário.
- **Reprovação comum**: emoji em excesso no body principal (✅ esses textos foram suavizados — emojis 1️⃣ 2️⃣ 3️⃣ viraram "1.", "2.", "3.").
- **Bloqueio rápido**: se taxa de bloqueio (block rate) > 2%, Meta restringe envio até resolver. Por isso a segmentação A-H é crítica.
