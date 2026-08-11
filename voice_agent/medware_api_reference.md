# 📑 MEDWARE API — REFERÊNCIA PADRÃO DA INTEGRAÇÃO

> Documento-padrão (`parâmetro padrão`) da integração do agente Lia com a
> API Medware. Fonte oficial: OpenAPI v1.5.0 —
> `https://medware.blinkoftalmologia.com.br/api/swagger/v1.5.0/swagger.json`
>
> Toda mudança no `voice_agent/medware.py` deve seguir este contrato.

---

## 1. Base e autenticação

- **Base URL:** `https://medware.blinkoftalmologia.com.br/api`
- **Login:** `POST /Acesso/login` → body `{identificacao, senha}` → `{token, refreshToken}`
- Token JWT válido ~24h (personalizável). Renovar via `POST /Acesso/refreshToken`.
- Todas as requisições levam header `Authorization: Bearer <token>`.

---

## 2. Endpoints usados pelo agente

| Método | Caminho | Uso |
|---|---|---|
| GET  | `/Medware/Agendamento/Listar` | Listar agendamentos de um período |
| GET  | `/Medware/Horarios/Listar` | Vagas livres (ver §4) |
| GET  | `/Medware/Paciente/Listar` | Buscar paciente por CPF/nome |
| GET  | `/Medware/Medico/Listar` · `/Medware/Unidade/Listar` | Cadastros |
| POST | `/Medware/Agendamento/Salvar` | **Gravar agendamento (ver §3)** |
| POST | `/Medware/Agendamento/Encaixe` | Encaixe (requer licença) |
| PUT  | `/Medware/Paciente/Atualizar` | Atualizar cadastro (requer licença) |

---

## 3. GRAVAR AGENDAMENTO — `POST /Medware/Agendamento/Salvar`

Body = `AgendamentoExternoDto`. **`additionalProperties: false`** — enviar
SOMENTE os campos abaixo.

### Campos da raiz

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `codAgenda` | int | ✅ | Código da agenda (da vaga escolhida) |
| `codMedico` | int | ✅ | |
| `codProcedimento` | int | ✅ | |
| `codPlano` | int | ✅ | |
| `dataHoraAgendada` | string | ✅ | Formato **`yyyy-MM-ddTHH:mm`** |
| `codPaciente` | int | — | Paciente já cadastrado |
| `paciente` | objeto | — | Paciente novo (ver abaixo) |

### Regra do paciente (CRÍTICA)

- **Paciente JÁ cadastrado:** informe `codPaciente` na **raiz** do JSON.
  Quando `codPaciente` está presente, o objeto `paciente` é **opcional** e
  **não deve ser enviado** (dispensa nome, CPF e data de nascimento).
- **Paciente NOVO:** **omita** `codPaciente` e envie o objeto `paciente`
  (`PacienteExternoDto`) com os dados mínimos.

### `PacienteExternoDto` (só para paciente novo)

| Campo | Obrigatório p/ criar | Observação |
|---|---|---|
| `nome` | ✅ | Nome completo — exige ao menos 1 sobrenome |
| `dataNascimento` | ✅ | Formato **`yyyy-MM-dd`** (ISO) |
| `cpf` | ✅ | Somente números |
| `numeroCelularddd` | ✅ | DDD (atenção: `ddd` minúsculo) |
| `numeroCelular` | ✅ | Número sem o DDD |

### Exemplos

Paciente já cadastrado:
```json
{
  "codAgenda": 4, "codMedico": 12080, "codProcedimento": 303,
  "codPlano": 1, "dataHoraAgendada": "2026-06-01T11:00",
  "codPaciente": 405
}
```

Paciente novo:
```json
{
  "codAgenda": 4, "codMedico": 12080, "codProcedimento": 303,
  "codPlano": 1, "dataHoraAgendada": "2026-06-01T11:00",
  "paciente": {
    "nome": "JOAO DA SILVA", "dataNascimento": "1990-01-15",
    "cpf": "12345678901", "numeroCelularddd": "61",
    "numeroCelular": "998888777"
  }
}
```

---

## 4. LISTAR HORÁRIOS — `GET /Medware/Horarios/Listar`

- Obrigatórios: `dataInicio`, `dataFim` (dd/MM/yyyy), `horaInicio`,
  `horaFim` (HH:mm:ss).
- **Não enviar parâmetros zerados** (codProcedimento=0 etc.) — a "Versão
  Light" rejeita e devolve lista vazia. Mandar só o que tem valor.

---

## 5. Códigos confirmados (Blink)

| Item | Código |
|---|---|
| Médico — Dra. Karla Delalíbera | `12080` |
| Médico — Dr. Fabrício Freitas | `12081` |
| Unidade — Asa Norte | `5` (agenda `4`) |
| Unidade — Águas Claras | `3` (agenda `5`) |
| Procedimento — Consulta Particular Dra. Karla | `303` |
| Procedimento — Consulta de convênio (consultório) | `13` |
| Plano — Particular | `1` |
| Planos — convênios | SERPRO 31 · SIS SENADO 32 · TJDFT 2 · PF 26 · Plan-Assist 4 · BACEN 9 · STJ 3 · Câmara 39 |

---

## 6. Formatos de data (resumo)

| Campo | Formato |
|---|---|
| `dataHoraAgendada` | `yyyy-MM-ddTHH:mm` |
| `paciente.dataNascimento` (ExternoDto) | `yyyy-MM-dd` |
| `dataInicio` / `dataFim` (listagens) | `dd/MM/yyyy` |
| `horaInicio` / `horaFim` | `HH:mm:ss` |

---

## 7. Licença "Paciente Conectado" ⚠️

Os endpoints de **inserção** podem retornar
`"Módulo não habilitado. ... adquirir a licença do Paciente Conectado..."`.
Isso afeta `Agendamento/Salvar` (com codPaciente), `Agendamento/Encaixe` e
`Paciente/Atualizar`. É uma pendência **comercial** (setor de vendas
Medware) — não há ajuste de código que resolva. Enquanto a licença não
estiver ativa, `criar_agendamento` devolve `{ok: False}` e o agente cai
no fluxo de atendimento humano.
