# Requerimento de Suporte Técnico — API Medware

**Para:** Suporte Técnico Medware Sistemas Médicos
**De:** Blink Oftalmologia
**Data:** 20/05/2026
**Assunto:** Endpoint de horários disponíveis da agenda retornando vazio na API

---

## 1. Identificação

- **Clínica:** Blink Oftalmologia
- **Ambiente da API:** `https://medware.blinkoftalmologia.com.br/api`
- **Usuário de integração:** `agendamentoweb`
- **Versão do sistema (desktop):** 3.2.0.84 / API 1.40.46
- **Rótulo da API observado:** "Versão Light"

## 2. Objetivo da integração

Estamos desenvolvendo um agente de atendimento automatizado (WhatsApp) que precisa **apresentar ao paciente, em tempo real, os horários disponíveis na agenda** de cada médico, para fazer o pré-agendamento. Para isso, a integração precisa **consultar as vagas livres** via API.

## 3. Problema técnico

O endpoint de horários livres **`GET /Medware/Horarios/Listar`** responde **HTTP 200 (sucesso), porém com lista vazia (`[]`)** em **todas** as combinações de parâmetros testadas.

### Testes realizados (todos retornaram `[]`)

- **Médicos:** codMedico 12080 (Karla Delalibera Pacheco) e 12081 (Fabricio Gomes de Freitas)
- **Unidades:** codUnidade 3 e 5 (e sem filtro de unidade)
- **Procedimentos:** 303 (Consulta Particular Dra. Karla), 13 (Consulta em consultório), 308, e genérico (0)
- **Períodos:** semana corrente (17–23/05/2026), semana seguinte (24–30/05/2026), e junho inteiro (01–30/06/2026)
- **Faixa horária:** 07:00 às 20:00
- Parâmetros `dataNasc`, `codPlano`, `codEspecialidade`, `codPaciente` preenchidos e/ou zerados — sem diferença

> Observação: quando o parâmetro `dataNasc` é enviado vazio, o endpoint retorna erro 400 ("Object reference not set to an instance of an object" em `Util.DataReplace`). Com `dataNasc` preenchido, retorna 200 com `[]`.

### Endpoints que retornam dados normalmente

- `POST /Acesso/login` — autenticação OK, token JWT gerado
- `GET /Medware/Agendamento/Listar` — retorna os agendamentos **já marcados** normalmente (ex.: 148 agendamentos na semana 17–23/05)

### Endpoints que também retornam vazio

- `GET /Medware/Medico/Listar` → `[]`
- `GET /Medware/Especialidade/Listar` → `[]`
- Listagem de planos → `[]`

### Constatação

No **software desktop** (MEDWARE Clínicas Agenda 3.2.0.84), a agenda dos médicos é exibida normalmente, **com os horários livres visíveis**. Ou seja, os dados existem no sistema — apenas **não estão sendo entregues pela API** para a conta `agendamentoweb`.

## 4. Solicitações

Pedimos orientação sobre os seguintes pontos:

1. **Como obter, via API, os horários DISPONÍVEIS (vagas livres) da agenda** de um médico/unidade em um período? O endpoint `Horarios/Listar` é o correto? Há algum parâmetro obrigatório adicional?

2. O retorno vazio é uma **limitação do plano "Versão Light"**? Se sim, qual plano/contratação habilita a consulta de horários disponíveis via API?

3. É necessária alguma **configuração/habilitação na conta `agendamentoweb`** (ou na agenda dos médicos) para que as vagas livres fiquem visíveis à API?

4. Os endpoints `Medico/Listar` e `Especialidade/Listar` também retornam vazio — isso é esperado para esta conta? Como obter a lista de médicos, especialidades e planos via API?

5. Em caso de necessidade de upgrade ou ajuste contratual, favor informar **valores e prazo**.

## 5. Contato

- **Responsável pela integração:** Fábio Philipe
- **E-mail:** oabphi@gmail.com
- **Clínica:** Blink Oftalmologia

Agradecemos o retorno e nos colocamos à disposição para uma chamada técnica, se for mais ágil.
