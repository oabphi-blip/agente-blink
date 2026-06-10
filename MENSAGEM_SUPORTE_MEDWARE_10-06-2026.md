# Mensagem para o Suporte Medware — Instabilidade API 10/06/2026

**Cliente:** Blink Oftalmologia (Brasília-DF)
**Responsável técnico:** Fábio Martins — oabphi@gmail.com — (61) 9xxxx-xxxx
**Data/hora do incidente:** 10/06/2026, observado a partir das 16:00 BRT (19:00 UTC), ainda em curso às 16:20 BRT.

---

## Versão CURTA (pra colar em chamado / WhatsApp suporte)

Olá, equipe Medware,

Estamos com **instabilidade contínua na API Medware há mais de 1 hora** (a partir das 16h BRT 10/06/2026). Todas as chamadas ao endpoint `/Medware/Horarios/Listar` retornam **HTTP 503** com body vazio. O endpoint de status (`/status`) também devolve **503**, o que indica indisponibilidade ampla, não bloqueio por parâmetro.

Impacto na operação Blink: nosso assistente de WhatsApp (Lia) não consegue oferecer horários reais às pacientes em conversa ativa. Já registramos pacientes parados aguardando agenda (lead exemplo: paciente Sarah, 16:08 BRT — abandono da conversa por timeout).

Podem confirmar o status dos servidores e o ETA de retorno? Se houver janela de manutenção planejada, agradecemos aviso.

Obrigado,
Fábio Martins / Blink Oftalmologia

---

## Versão LONGA (e-mail formal pro suporte / N1 técnico)

**Assunto:** [URGENTE] API Medware retornando HTTP 503 em massa desde 16h BRT 10/06/2026 — Blink Oftalmologia

Prezada equipe de suporte Medware,

Sou Fábio Martins, responsável técnico pela operação da **Blink Oftalmologia** (Brasília-DF). Venho relatar uma **instabilidade contínua na API Medware** que está impactando diretamente o atendimento das nossas pacientes nesta data.

### Resumo do incidente

| Item | Detalhe |
|---|---|
| **Início observado** | 10/06/2026, ~16h BRT (19h UTC) |
| **Status atual (16:20 BRT)** | Ainda indisponível |
| **Endpoint afetado (confirmado)** | `GET /Medware/Horarios/Listar` |
| **Endpoint afetado (confirmado)** | `GET /status` (servidor) |
| **Código HTTP retornado** | `503 Service Unavailable` |
| **Body da resposta** | Vazio (`""`) |
| **Origem das requisições** | `https://medware.blinkoftalmologia.com.br/api` |

### Evidências

1. **Chamada ao endpoint de horários disponíveis** (parâmetros válidos, mesmos usados há meses sem falha):

```
GET /Medware/Horarios/Listar
?dataInicio=15/06/2026
&dataFim=15/06/2026
&horaInicio=08:00
&horaFim=12:00
&codMedico=12080  (Dra. Karla Delalíbera)
&codUnidade=5    (Asa Norte)
&codPlano=1      (.PARTICULAR)
```

Resposta:
```json
{
  "ok": false,
  "status": 503,
  "error": "",
  "path": "/Medware/Horarios/Listar"
}
```

2. **Healthcheck do servidor Medware**:

```
GET /status
→ HTTP 503, body vazio
```

3. **Impacto operacional medido**: nosso pipeline de atendimento (FastAPI em `https://blink-agent.6prkfn.easypanel.host`) tem circuit breaker que, após 3 falhas seguidas no Medware, escala a conversa pra atendimento humano. Mas em janela de instabilidade prolongada (>30 min), as pacientes ficam aguardando enquanto a equipe humana não consegue dar vazão.

### Caso concreto (lead Sarah Cordeiro Barros)

- Paciente em conversa ativa desde 15:51 BRT.
- Tentativa de oferta de horário pra **segunda-feira manhã, 15/06/2026, Dra. Karla, Asa Norte**.
- Lia (nosso bot) tentou `Horarios/Listar` 3 vezes (16:06, 16:07, 16:08 BRT) — todas retornaram 503.
- Paciente desistiu da conversa após espera de ~10 min.
- Lead no CRM (Kommo): ID `24129498`.

### Pedidos

1. **Confirmação de incidente**: vocês têm ciência da indisponibilidade? Há manutenção em curso?
2. **ETA de retorno do serviço**: precisamos comunicar nossa equipe operacional.
3. **Status page / monitoramento público**: caso exista, podem compartilhar o link?
4. **Procedimento de aviso futuro**: existe lista de e-mail pra comunicado de janela de manutenção planejada? Hoje não recebemos aviso prévio.
5. **SLA da API**: qual o SLA contratual da API pra leitura de agenda? Estamos avaliando dependência operacional.

### Contato pra resposta rápida

- **E-mail:** oabphi@gmail.com (Fábio Martins, responsável técnico)
- **WhatsApp:** [inserir telefone]
- **Endpoint de healthcheck do nosso lado** (pra correlação caso peçam): `https://blink-agent.6prkfn.easypanel.host/health` — campo `medware.ok` reflete a situação real do consumo da API.

Permanecemos à disposição pra fornecer logs adicionais (User-Agent, headers de request, payloads completos) caso seja útil ao diagnóstico de vocês.

Agradeço a atenção e fico no aguardo de retorno o quanto antes — temos atendimento ativo agora.

Atenciosamente,
**Fábio Martins**
Blink Oftalmologia · Brasília-DF
oabphi@gmail.com
