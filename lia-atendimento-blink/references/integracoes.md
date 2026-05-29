# Integrações: Kommo CRM + Medware API

> Schemas, endpoints, exemplos de payload, códigos de erro e padrões de uso das duas
> integrações que sustentam a Lia. Leia este arquivo quando precisar diagnosticar bug de
> integração, gerar chamada manual, ou entender por que um campo não foi preenchido.

---

## Parte 1 — Kommo CRM

### URL base
`https://univeja.kommo.com`

### Pipeline ATENDE
- `id = 8601819` (is_main = true)

### Etapas (status_id)

| status_id | nome | uso |
|---|---|---|
| `67727383` | Etapa de leads de entrada | Auto-entrada inicial |
| `96441724` | **0-ETAPA ENTRADA** | Lead novo, Salesbot deveria ativar IA aqui |
| `106563343` | 0-ATENDIMENTO HUMANO | Caso humano tenha assumido |
| `101508307` | 1.LEADS FRIO | Lead sem evolução |
| `102560495` | **2-AGENDAR** | Onde a Lia opera majoritariamente |
| `106184631` | 3.REAGENDAR | Lead em remarcação |
| `101507507` | **4-AGENDADO** | Destino após `salvar_agendamento` na Medware |
| `101109455` | 5-CONFIRMAR | Aguardando confirmação D-1 |
| `106653499` | 6.CONFIRMADO | Confirmado pelo paciente |
| `106184983` | 6.1-NO-SHOW (ATIVAR) | Paciente faltou |
| `91486864` | 7-REALIZADO CONSULTA | Atendimento concluído |
| `106157139` | 8-CIRURGIAS ANDAMENTO | Catarata em pipeline |
| `106484343` | 9-LENTES ANDAMENTO | Lentes intraoculares |
| `142` | Closed - won | Ganho |
| `143` | Closed - lost | Perdido |

### Campos críticos (custom_fields)

| field_name | field_id | tipo | descrição |
|---|---|---|---|
| `1.NOME PACIENTE` | 1255757 | textarea | Nome civil completo, sem iniciais |
| `1.DATA NASCIMENTO` | 1259984 | date | Epoch seconds |
| `1.MOTIVO CONSULTA` | 1255727 | textarea | Texto livre |
| `1.PERFIL 1º PACIENTE` | 1257961 | multiselect | "Criança 3-12", "Acima 50", etc. |
| `Nº PACIENTES` | 1259118 | select | "1", "2", "3"... |
| `NUMERO TELEFONE` | 1260633 | multiselect | "81331005" (8133) ou "0710" |
| `ATIVADO IA?` | 1260635 | multiselect | "Ativado" / "Desativado" — Lia só responde se "Ativado" |
| `ATENDENTE (s)` | 1246419 | multiselect | "Lia" / nome humano |
| `MÉDICOS` | 1256257 | multiselect | "Dra. Karla Delalibera" / "Dr. Fabricio Freitas" / "Dra. Katia Delalibera" |
| `ESPECIALID` | 1259130 | multiselect | "Oftalmologia Geral" / "Oftalmopediatria" / "Catarata" / "Retina" / "SDP" |
| `CONVÊNIO` | 853206 | select | Nome do plano OU "Não se aplica" |
| `Ñ ACEITO CONVÊNIO` | 1175268 | select | Plano não aceito que o paciente trouxe |
| `UNIDADE` | 1245125 | select | "Asa Norte" / "Águas Claras" |
| `DIA/TURNO/PERÍODO ⚠️` | 1259960 | textarea | Preferência do paciente |
| `FORM PAGAMENTO` | 1241106 | multiselect | "Pix" / "Crédito 2x" |
| `VALOR KARLA` | 1259108 | multiselect | "R$ 611" / "R$ 800 SDP" / "2x R$ 335" |
| `VALOR TOTAL R$` | 1260452 | textarea | Valor final (texto livre) |
| `COD_AGENDAMENTO` | (verificar) | textarea | Retorno da Medware após salvar_agendamento |
| `AÇÕES/CORRIGIR` | 1259312 | multiselect | "Agendar Encaixe" e outros estados |

### Campos em criação (política sinal)

A serem criados manualmente no Kommo UI (task #49):
- `SINAL STATUS` (radiobutton): Aguardando solicitação · Solicitado · Pago · Não pago · Devolvido
- `SINAL VALOR R$` (textarea)
- `SINAL DATA PIX` (date_time)
- `SINAL COMPROVANTE` (URL)
- `NO-SHOW COUNT` (numeric)
- `MODALIDADE AGENDA` (select): Reserva Imediata · Fila de Encaixe

### MCP tools úteis (`mcp__kommo__*`)

| Tool | Uso típico |
|---|---|
| `kommo_get_lead` | Ler lead + notes. SEMPRE usar com `with_notes=true`. |
| `kommo_update_lead` | Atualizar custom_fields, name, status_id, pipeline_id. |
| `kommo_search_leads` | Buscar leads com filtros (pipeline_id, status_id, datas). |
| `kommo_add_note` | Adicionar nota interna (visível só pra equipe humana, não vai pro WhatsApp). |
| `kommo_list_custom_fields` | Listar todos os campos (cuidado: output gigante, ~85KB). |
| `kommo_list_pipelines_and_stages` | Decodificar status_id em nome legível. |
| `kommo_list_users` | Decodificar responsible_user_id. |
| `kommo_update_leads_batch` | Atualizar vários leads de uma vez. |

### Bug conhecido: Salesbot desativando IA

**Sintoma**: Lead chega em "0-ETAPA ENTRADA" e a Lia nunca responde. Notes mostram
`🛑 Agentes de IA foram desativados neste chat porque uma mensagem manual de saída foi
detectada no histórico do chat`.

**Causa**: O Salesbot tem gatilho falso positivo — interpreta nota interna como "mensagem
manual outgoing".

**Mitigação atual**: Setar `ATIVADO IA? = Ativado` via `kommo_update_lead`.

**Fix definitivo (pendente)**: Reconfigurar Salesbot no Kommo UI pra não disparar com notas
internas. Task #50.

---

## Parte 2 — Medware API

### URL base
`https://medware.blinkoftalmologia.com.br/api`

### Autenticação
```http
POST /Acesso/login
Content-Type: application/json

{
  "identificacao": "<user>",
  "senha": "<password>"
}
```

**Resposta**:
```json
{
  "token": "eyJhbGc...",
  "refreshToken": "..."
}
```

Token JWT válido **24h**. Em todas as outras requisições:
```
Authorization: Bearer <token>
Accept: application/json
```

### Health check
```http
GET /health/health
```
Resposta esperada: status 200 + texto contendo `"API Ativa"`.

### Endpoint principal: Horários disponíveis

```http
GET /Medware/Horarios/Listar?codProcedimento=&codMedico=12080&codUnidade=5&dataInicio=01/06/2026&dataFim=14/06/2026&horaInicio=07:00&horaFim=19:00&dataNasc=01/01/1990
```

**Parâmetros importantes**:
- `codMedico`: 12080 (Karla) ou 12081 (Fabrício)
- `codUnidade`: 5 (Asa Norte) ou 3 (Águas Claras)
- `dataInicio`, `dataFim`: formato `DD/MM/YYYY`
- `horaInicio`, `horaFim`: `HH:MM`
- `dataNasc`: default `01/01/1990` (algumas validações usam isso)

**Resposta** (array de slots):
```json
[
  {
    "data": "2026-06-02T00:00:00",
    "horario": "09:00:00",
    "horarioFim": "09:30:00",
    "codAgenda": 5,
    "codMedico": 12080,
    "nomeMedico": "Karla Delalibera Pacheco",
    "codUnidade": 3,
    "codProcedimento": "",
    "limitacoes": []
  },
  ...
]
```

**Nota sobre Versão Light**: dependendo da versão da Medware, alguns endpoints retornam
vazio. Se `Horarios/Listar` vier vazio, fallback é coletar preferência e encaminhar
humano (regra 0.10 fallback).

### Endpoint: Salvar Agendamento

```http
POST /Medware/Agendamento/Salvar
Content-Type: application/json
Authorization: Bearer <token>

{
  "codMedico": 12080,
  "codUnidade": 5,
  "dataHora": "2026-06-02T09:00:00",
  "codProcedimento": 308,
  "codPlano": 0,
  "nome": "Maria Silva",
  "dataNasc": "23/07/1976",
  "telefone": "61999998888",
  "codAgenda": 5
}
```

**Resposta sucesso**:
```json
{
  "codAgendamento": 12345,
  "status": "Agendado"
}
```

Esse `codAgendamento` deve ser gravado no campo `COD_AGENDAMENTO` do Kommo.

### Endpoint: Listar Agendamentos

```http
GET /Medware/Agendamento/Listar?dataInicio=28/05/2026&dataFim=29/05/2026&codMedico=12080
```

Usado pra verificar agendamentos já criados (ex.: confirmar que um `salvar_agendamento`
funcionou).

### Códigos importantes

**Médicos** (`codMedico`):
- `12080` — Dra. Karla Delalíbera Pacheco
- `12081` — Dr. Fabrício Gomes de Freitas

**Unidades** (`codUnidade`):
- `5` — Asa Norte (Karla seg/qua/sex; Fabrício esporádico)
- `3` — Águas Claras (Karla ter/qui; Fabrício seg-tarde/sex-manhã)

**Procedimentos** (`codProcedimento`) — exemplos comuns:
- `303` — Consulta Particular Dra. Karla
- `308` — Consulta em consultório (Particular)
- `15` — Retorno (Particular)
- `13` — Consulta em consultório (convênio)
- `302` — `<<CONVENIO AGUAS CLARAS>>` (agregador Saúde Caixa)

### MCP tools Medware (`mcp__medware__*`)

| Tool | Equivale a | Uso típico |
|---|---|---|
| `descobrir_medicos_e_unidades` | listagem mista | Quando os endpoints listar_medicos/listar_unidades retornam vazio |
| `horarios_disponiveis` | GET /Horarios/Listar | Buscar slots reais |
| `salvar_agendamento` | POST /Agendamento/Salvar | Criar agendamento |
| `listar_agendamentos` | GET /Agendamento/Listar | Verificar agendamentos no período |
| `atualizar_agendamento` | PUT /Agendamento/Atualizar | Mudar data/hora |
| `atualizar_status_agendamento` | PATCH status | Marcar realizado, no-show, cancelado |
| `cancelar_agendamento` | DELETE | Cancelar |
| `buscar_pacientes` | GET /Paciente | Procurar paciente cadastrado |
| `salvar_avaliacao` | POST /Avaliacao | Cadastrar avaliação cirúrgica |
| `status_servidor` | GET /health/health | Health check |

### Latência e instabilidade

O servidor Medware **NÃO é cloud** — é uma máquina Windows na própria clínica. Já foi
observado:
- 71% de memória em uso
- 3 instâncias duplicadas do "Agenda Medware Clínicas"
- Múltiplas sessões de AnyDesk/RemoteApp abertas

**Sintoma na Lia**: quando o servidor está sobrecarregado, `horarios_disponiveis` demora >5s,
a Lia interpreta como "agenda indisponível" e cai em fallback. Já foi visto a Lia dizer
"estou sem acesso à agenda em tempo real neste momento" — quase sempre é por isso.

**Logging instrumentado** (em `voice_agent/medware.py`):
```
[MEDWARE LATENCY] GET <path> <elapsed>s HTTP=<status>
```

Threshold:
- INFO até 3s
- WARNING 3-8s ("servidor sob estresse")
- ERROR >8s ("servidor sobrecarregado")
- TIMEOUT (12s) loga error específico

**Diagnóstico**: `grep '[MEDWARE LATENCY]' logs_easypanel.txt`.

### Refresh token

Configurado em commit anterior (task #2). O cliente em `medware.py` renova
automaticamente quando faltam <5min pro vencimento. Validade default fallback: 86400s (24h).

---

## Parte 3 — Ponte Lia ↔ Kommo ↔ Medware

### Fluxo típico (E7 → E8 → Kommo update)

```
1. Paciente em E7 escolhe slot ("o 2", "fica com a sexta")
   ↓
2. Detector Haiku identifica: data=02/06/2026, hora=09:00, médico=Karla, unidade=Asa Norte
   ↓
3. mcp__medware__salvar_agendamento({
     codMedico: 12080,
     codUnidade: 5,
     dataHora: "2026-06-02T09:00:00",
     codProcedimento: 308,
     nome: "Maria Silva",
     dataNasc: "23/07/1976",
     ...
   })
   ↓
4. Resposta: { codAgendamento: 12345 }
   ↓
5. mcp__kommo__kommo_update_lead({
     lead_id: <id>,
     status_id: 101507507,  // 4-AGENDADO
     custom_fields: {
       "COD_AGENDAMENTO": "12345",
       "VALOR TOTAL R$": "R$ 611,00",
       ...
     }
   })
   ↓
6. Lia envia mensagem final (Resumo do Atendimento §13.2)
```

### Tratamento de erros

**Medware retornou erro 5xx**:
- Não inventar `codAgendamento`. Marcar lead como "preferência registrada" e encaminhar
  humano (fallback §0.10).

**Kommo update falhou**:
- Logar erro. Não retentar de forma agressiva (limit rate). Equipe humana resolve.

**Salesbot desativou IA antes da gravação**:
- Verificar campo ATIVADO IA?. Se Desativado, reativar e re-disparar o gatilho.
