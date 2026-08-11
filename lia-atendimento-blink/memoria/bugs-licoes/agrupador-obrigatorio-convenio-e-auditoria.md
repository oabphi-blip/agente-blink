# Convênio só agenda com 3 pré-requisitos + auditoria do médico pós-consulta

> Definida pelo Fábio em 31/05/2026. Operacionaliza a regra "consulta sempre
> inclui exame completo" (ver `regra-consulta-sempre-agrupador.md`) integrando
> Kommo + Medware + autorização do convênio.

## A regra

Quando o atendimento for por convênio, a Lia NÃO pode ofertar slot da agenda
(E7) sem TER, por paciente, OS 3 dados abaixo confirmados:

1. **Data de nascimento completa** (DD/MM/AAAA) — campo Kommo `N.DATA NASC`.
2. **Idade calculada** a partir da data + "DATA DE HOJE (Brasília)".
3. **Motivo classificado** em uma das 5 categorias enum de `N.MOTIVO`:
   Rotina/Check-up · Retorno/Acompanhamento · Pré-operatório · Emergência/Urgência · Pós-Operatório.

Por que: esses 3 dados são input de
`voice_agent/procedimentos.py:selecionar_agrupador()` que escolhe
automaticamente UM dos 4 agrupadores de exames (N.EXAMES). O pipeline grava
N.MOTIVO + N.EXAMES no Kommo e dispara a SOLICITAÇÃO DE AUTORIZAÇÃO ao
convênio ANTES do dia da consulta. Sem isso, paciente chega no dia, recepção
descobre que procedimento não está autorizado, no-show técnico, conflito.

## A trava no prompt

Adicionada como seção E4.5 da espinha dorsal + seção 23 dedicada
(`voice_agent/knowledge_base/_MASTER_INSTRUCTION.md`). Lia pergunta UMA vez
em frase aberta (sem menu numerado):

> "Pra eu já solicitar a autorização do seu convênio antes do dia, o
> atendimento será: rotina, retorno, pré-operatório, urgência ou pós-operatório?"

## O que a Lia NUNCA faz aqui

- ❌ Não menciona "agrupador", "Agrupa1", "codProcedimento", "pacote de 9 exames"
  ao paciente — vocabulário interno.
- ❌ Não grava N.EXAMES por mensagem direta — pipeline preenche via
  `selecionar_agrupador()`.
- ❌ Não diz "autorização aprovada" — Lia não tem visibilidade da resposta da
  operadora. Diz: "A solicitação foi enviada à sua operadora."

## Auditoria pós-consulta (seção 24 do prompt)

Quando lead vai para `6-REALIZADO CONSULTA`, pipeline compara:

- **Planejado**: valor de `N.EXAMES` (Kommo) que a Lia mandou autorizar.
- **Realizado**: lista de `codProcedimento` que Medware registrou.

Se ambos coincidem → nota `[AUDITORIA] sem ajuste`.

Se diferem → grava `N.AGRUPAMENTO ALTERADO=true`, nota detalhada com
`exames_a_mais` + `exames_a_menos`, cria tarefa Kommo
"Reabrir autorização — agrupamento alterado paciente N — médico ajustou exames"
(09:00 próximo dia útil) e dispara telemetria Slack.

Lia NÃO comunica essa diferença ao paciente — tratativa entre equipe humana
e operadora.

## O que falta construir (task #81 + #82 — pendentes)

1. Job no pipeline que dispara solicitação de autorização para operadora
   quando `N.EXAMES` é preenchido pela primeira vez.
2. Função `voice_agent/medware.py:listar_procedimentos_realizados(agendamento_id)`.
3. Comparador `voice_agent/auditoria.py:comparar_agrupamento(planejado, realizado)`.
4. Campo Kommo a criar: `N.AGRUPAMENTO ALTERADO` (checkbox por paciente).
5. Pytest blindando os cenários (coincide / a_mais / a_menos / fonte_vazia).
6. Webhook Kommo que escuta movimentação para `6-REALIZADO CONSULTA` e
   dispara auditoria por paciente.

## Observabilidade — dupla checagem secretaria + médico (task #82)

Canal Slack `#auditoria-autorização` criado pelo Fábio em 31/05/2026.
Funcionamento (seção 25 do `_MASTER_INSTRUCTION.md`):

1. Discrepância detectada → bot posta no canal com lista a_mais / a_menos
   + link Kommo do lead.
2. Secretaria da unidade do agendamento (Asa Norte ou Águas Claras) revisa
   primeiro: reaction `:white_check_mark:` no Slack OU clique no
   `/admin/auditoria-confirma`.
3. Médico responsável (Karla / Fabrício / Kátia) faz a segunda checagem
   pelo mesmo caminho.
4. Só após DUAS assinaturas o status `N.AUDITORIA STATUS` vai para
   `fechada` e a unidade financeira pode cobrar do convênio.
5. Se algum dos dois marcar `:x:` → status vai para `divergencia` + tarefa
   manual para Fábio.
6. Timeout 48h sem secretaria → ping. Mais 48h sem médico → segundo ping.

Por que duas camadas humanas: a secretaria conhece o operacional (paciente
realmente compareceu? Que carteirinha foi usada?), o médico conhece o clínico
(por que acrescentei/retirei tal exame?). Junto, eliminam glosa por parte da
operadora.

Endpoints a implementar:
- `GET /admin/secretaria-auditoria?unidade=...` — fila por unidade.
- `GET /admin/medico-auditoria?medico=...` — fila por médico.
- `POST /admin/auditoria-confirma?...` — registra assinatura.
- `POST /admin/auditoria-tick` — cron interno, varre últimas 24h.

Env nova: `SLACK_WEBHOOK_AUDITORIA_URL`.

## Campos Kommo criados em 31/05/2026 via Chrome MCP

24 campos no group_id `leads_94241749068044` (aba Pacientes):

| Paciente | ALTERADO (checkbox) | STATUS (select) | SECRETARIA (text) | MEDICO (text) |
|---|---|---|---|---|
| 1 | 1260763 | 1260765 | 1260787 | 1260789 |
| 2 | 1260767 | 1260769 | 1260791 | 1260793 |
| 3 | 1260771 | 1260773 | 1260795 | 1260797 |
| 4 | 1260775 | 1260777 | 1260799 | 1260801 |
| 5 | 1260779 | 1260781 | 1260803 | 1260805 |
| 6 | 1260783 | 1260785 | 1260807 | 1260809 |

Enum IDs do AUDITORIA STATUS (paciente 1, demais sequenciais +10):
`aguardando_secretaria=926953`, `aguardando_medico=926955`,
`fechada=926957`, `divergencia=926959`, `fonte_vazia=926961`.

Tabela completa em `voice_agent/auditoria.py:KOMMO_AUDITORIA_STATUS_ENUMS`.
Pytest blinda em `tests/test_auditoria_pos_consulta.py::TestKommoFieldIds`
(11 testes, incluindo "field_ids únicos globalmente" como sentinel).

## Observação: nomes dos campos no Kommo

Os campos `N.EXAMES` (criados na sessão anterior) foram renomeados pelo Fábio
para `N.EXAMES/GRUPO` no Kommo. Os field_ids permanecem os mesmos
(1.EXAMES/GRUPO = 1260721, etc.). Atualizar nomenclatura no
`voice_agent/kommo.py` quando tocar o módulo (não bloqueia integração,
o lookup é por ID).

## As 4 camadas (regra arquitetural Blink)

Toda regra de negócio precisa estar em 4 lugares — só assim não vaza:

1. **Código** → `voice_agent/procedimentos.py` + (futuro) `voice_agent/auditoria.py`.
2. **Pytest** → `tests/test_procedimentos_agrupadores.py` (23 testes) +
   (futuro) `tests/test_auditoria_pos_consulta.py`.
3. **Memória ativa** → este arquivo + `regra-consulta-sempre-agrupador.md`.
4. **Prompt** → seções E4.5, 23 e 24 do `_MASTER_INSTRUCTION.md`.

Sem as 4, eventualmente paciente recebe oferta de slot sem agrupador → no-show
ou médico altera agrupamento e operadora rejeita pagamento.

Última atualização: 31/05/2026
