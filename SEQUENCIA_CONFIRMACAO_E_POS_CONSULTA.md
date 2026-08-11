# Sequência de Confirmação + Pós-Consulta

**Data**: 03/06/2026
**Aplicação**: TODOS os agendamentos confirmados no Medware (status 5-AGENDADO em diante)
**Disparo**: automático via dispatcher do voice_agent (cron embutido) ou manual via Stephany/Ariany

---

## Linha do tempo

```
 D-1 (véspera)            D-0 06h (manhã consulta)     Evento: lead→8-REALIZADO        D+N (próxima)
       │                          │                              │                            │
       ▼                          ▼                              ▼                            ▼
   Modelo I                   Modelo J                        Modelo K                    Modelo L
 Confirmar (1/2/3)         Link localização                Avaliação Google          Lembrete próxima
                            (escolhe unidade)              (dispara IMEDIATO          (1m/3m/6m/1ano)
                                                            ao mover etapa)
```

**Gatilhos**:
- **I/J/L** = baseados em horário (cron embutido).
- **K** = baseado em **evento Kommo** — assim que o lead move pra `8-REALIZADO CONSULTA` (status_id 91486864), o webhook dispara K1 ou K2 conforme `UNIDADE`. Não espera horário.

---

## Modelo I — Confirmação D-1 (véspera da consulta)

**Quando disparar**: D-1 entre 14h e 18h BRT.
**Origem**: paciente está em `5-AGENDADO`, com `1.DIA CONSULTA` futuro.
**Variáveis necessárias**: `{{nome_contato}}`, `{{dia_hora_consulta}}`, `{{nome_paciente}}`, `{{nome_medico_completo}}`.

```
Olá! {{nome_contato}},

✨ Em continuidade ao atendimento!

Informamos os dados para confirmar consulta.

🔍 Detalhes do Agendamento:
📅 Dia/Hora: {{dia_hora_consulta}}
👤 Paciente(s): {{nome_paciente}}
👩‍⚕️ Médica: {{nome_medico_completo}}

⏳ Se não recebermos confirmação em até 2 horas após esta mensagem, chamaremos outro paciente da fila de espera. ⏰

🔄 Caso isso aconteça, entraremos em contato para remarcar seu atendimento para você e sua família. Obrigado! 🙏

1️⃣ Confirmo
2️⃣ Quero antecipar ⏩
3️⃣ Entrar na fila de espera (próx. 30 dias) ⏳
```

**Tratamento da resposta**:
- **1** → mover lead pra `7.CONFIRMADO` (status 106653499) + agendar Modelo J pra D-0 06h
- **2** → consultar agenda Medware do mesmo médico/unidade, oferecer slots mais cedo, gravar via `salvar_agendamento`
- **3** → mover pra `4.REAGENDAR` (status 106184631), agendar follow-up em 30 dias

---

## Modelo J — Link localização D-0 (06h da manhã do dia da consulta)

**Quando disparar**: D-0 às 06:00 BRT.
**Pré-requisito**: paciente confirmou (resposta "1" em Modelo I) OU já está em `7.CONFIRMADO`.

### J1 — Águas Claras

**Variáveis necessárias**: `{{nome_contato}}`, `{{dia_hora_consulta}}`.

```
Olá, {{nome_contato}}!

Para consulta prevista para data {{dia_hora_consulta}}

🔗 Para facilitar o acesso à Blink Oftalmologia, unidade Águas Claras, segue o endereço e o link de localização:

📍 Endereço: Felicittá Shopping — Rua 36 Norte, Lote 05 sn, Bloco 11, Loja 48 — Águas Claras, Brasília DF

https://maps.app.goo.gl/FRbkUtg4U4xG55q18

✅ Estaremos à disposição para atender! 😊
```

### J2 — Asa Norte

**Variáveis necessárias**: `{{nome_contato}}`, `{{dia_hora_consulta}}`.

```
Olá, {{nome_contato}}!

Para consulta prevista para data {{dia_hora_consulta}}

🔗 Para facilitar o acesso à Blink Oftalmologia, unidade Asa Norte, segue o endereço e o link de localização:

📍 Endereço: SGAN 607, Asa Norte, Bloco A Sala 123, Ed. Brasília Medical Center, CEP 70830-300

https://maps.app.goo.gl/jPfjSsXA1bHhsyw56

✅ Estaremos à disposição para atender! 😊
```

---

## Modelo K — Pós-consulta: avaliação Google

**Quando disparar**: **IMEDIATAMENTE quando a etapa do lead Kommo for movida para `8-REALIZADO CONSULTA` (status_id 91486864)**. Sem espera, sem janela horária.
**Mecanismo**: webhook Kommo `lead.status_changed` → if `new_status_id == 91486864` → dispara K1 (se UNIDADE="Asa Norte") OU K2 (se UNIDADE="Águas Claras").
**Variáveis**: `{{nome_contato}}`, `{{nome_medico_completo}}`, `{{especialidade}}`.

> **Regra de respeito**: se o lead foi movido pra 8-REALIZADO fora do horário comercial (ex: madrugada por automação), o disparo do K acontece mesmo assim — o paciente abre quando puder. Mensagem de avaliação Google não tem urgência incômoda como pix ou confirmação.

### K1 — Asa Norte

```
Olá, {{nome_contato}}!

😊 Obrigado por confiar na {{nome_medico_completo}}, especialista em {{especialidade}}.

📢 Sua opinião é muito importante para ampliar nossa visão!

Por isso, buscamos saber: como foi sua experiência na Blink Oftalmologia unidade Asa Norte clicando aqui ⬇️

https://g.page/r/CZYHYwv6CgYcEAE/review
```

### K2 — Águas Claras

```
Olá, {{nome_contato}}!

😊 Obrigado por confiar na {{nome_medico_completo}}, especialista em {{especialidade}}.

📢 Sua opinião é muito importante para ampliar nossa visão!

Por isso, buscamos saber: como foi sua experiência na Blink Oftalmologia unidade Águas Claras clicando aqui ⬇️

https://g.page/r/CdTrhQ8o4DYaEAE/review
```

---

## Modelo L — Lembrete próxima consulta

**Quando disparar**: configurável por médico/especialidade — pode ser **1 mês**, **3 meses**, **6 meses** ou **1 ano** depois da consulta realizada.
**Pré-requisito**: paciente está em `8-REALIZADO`, sem novo agendamento futuro no Medware.
**Variáveis**: `{{nome_contato}}`, `{{dia_hora_consulta_anterior}}`, `{{nome_paciente}}`, `{{intervalo}}` (texto: "1 mês", "3 meses", "6 meses", "1 (um) ano").

```
Olá, {{nome_contato}}!

Agradecemos pela realização da consulta na data de {{dia_hora_consulta_anterior}}.

A próxima consulta de {{nome_paciente}} está prevista para daqui {{intervalo}}.

Quer que eu já reserve um horário?

1️⃣ Sim, agendar essa semana
2️⃣ Sim, mas só daqui {{intervalo_curto}} (me lembre depois)
3️⃣ Vou entrar em contato eu mesma quando estiver pronta
```

**Tratamento da resposta**:
- **1** → fluxo de agendamento normal (oferecer slots Medware)
- **2** → agendar Modelo L novamente pra D+N do `{{intervalo_curto}}`
- **3** → marcar `A FAZER = Pós Consulta` no Kommo + aguardar movimentação humana

---

## Regras operacionais

1. **Nome completo do médico SEMPRE**: "Dra. Karla Delalibera" / "Dr. Fabrício Freitas" (regra herdada dos modelos de reativação).
2. **Dispatcher do voice_agent** deve respeitar:
   - Modelo I: cron — D-1 entre 14h-18h (uma única vez por consulta)
   - Modelo J: cron — D-0 às 06:00 (uma única vez, escolha J1 ou J2 conforme `UNIDADE` no Kommo)
   - Modelo K: **webhook Kommo `lead.status_changed`** — dispara IMEDIATO quando status muda pra `91486864` (uma única vez por consulta, escolha K1 ou K2 conforme `UNIDADE`). NÃO depende de cron/horário.
   - Modelo L: cron — D+N conforme política do médico (Karla Delalibera = 6 meses padrão pediatria / 1 ano adulto; Fabrício Freitas = 6 meses pós-op catarata)
3. **Dedup Redis**: `blink:msg_dispatched:{lead_id}:{modelo}:{data}` TTL 48h pra evitar duplicação.
4. **Logs Kommo**: cada disparo grava nota no lead "{Modelo X} disparado às HH:MM via WhatsApp 8133".
5. **Janela 24h WhatsApp Cloud**: se passou 24h sem inbound, usar **template aprovado Meta** (não mensagem livre).
6. **Cancelamento via "3"**: paciente que pede fila de espera (Modelo I) NÃO recebe J/K — engatilha pra `4.REAGENDAR`.

---

## Intervalos padrão por médico × especialidade (Modelo L)

| Médico | Especialidade | Intervalo padrão |
|---|---|---|
| Dra. Karla Delalibera | Oftalmopediatria (≤12 anos) | 6 meses |
| Dra. Karla Delalibera | Oftalmologia Geral (adulto) | 1 ano |
| Dra. Karla Delalibera | Estrabismo | 6 meses |
| Dra. Karla Delalibera | SDP/Prisma | 1 ano |
| Dr. Fabrício Freitas | Avaliação catarata | 6 meses (se ainda sem indicação cirúrgica) |
| Dr. Fabrício Freitas | Pós-operatório catarata | 7 dias → 30 dias → 90 dias → 1 ano |

---

## Próximos passos

1. ✅ Fábio aprovar (ou ajustar) os 4 modelos I/J/K/L.
2. 🔧 Integrar com o **dispatcher do voice_agent** (`voice_agent/ciclo_comunicacao.py` — já existe estrutura D-3/D-1/D-0).
3. 📅 Cron embutido dispara conforme janela horária.
4. 🧪 Pytest cobrindo os 4 modelos + 6 intervalos do Modelo L.
5. 📊 Painel `/admin/healthz` mostra contagem de cada modelo disparado nas últimas 24h.
