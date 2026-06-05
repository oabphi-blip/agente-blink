---
title: "Protocolo Claude Cowork — leitura obrigatória ANTES de qualquer ação operacional"
tags: [protocolo, anti-padrao, claude-cowork, taxa-erro-zero]
data_criacao: 2026-06-04
data_revisao: 2026-06-04
prioridade: P0
---

# Protocolo Claude Cowork — Anti-omissão e Anti-repetição

> **OBRIGATÓRIO ler no início de toda sessão Cowork no folder Blink.**
> Origem: Fábio 04/06/2026 — Claude repete bugs, omite informação, gasta turnos com desculpas.
> Status: zero tolerância pra repetir bugs registrados aqui.

---

## A. CHECKLIST PRÉ-AÇÃO OPERACIONAL (verificar TODAS antes de agir)

Antes de **qualquer** uma destas ações:
- Enviar mensagem WhatsApp via Chrome MCP
- Gravar agendamento Medware
- Renomear lead em massa
- Disparar template
- Ofertar slot de agenda

**Verificar nesta ordem (Boeing rule):**

1. **Cronologia:** estou ofertando o slot/data **mais próxima cronologicamente**? Se há vaga em D+7 e ofereci D+30, é bug.
2. **Médico × dia × unidade:** Karla = seg/qua/sex Asa Norte + ter/qui Águas Claras. Fabrício = ter/qui Asa Norte. NUNCA atende sábado/domingo.
3. **Águas Claras NÃO tem noite** — só Manhã ou Tarde (regra Fábio 04/06).
4. **Convênio:** aceito? Inas/GDF/Cassi/SulAmérica/Bradesco/Unimed = NÃO. CPF dispensável se convênio aceito.
5. **Regra de ouro #3 da Blink:** NUNCA cobrar/ofertar valor antes de oferecer slot concreto. Inclui R$ 611 da consulta (não só R$ 305 do sinal).
6. **Repetição:** já perguntei isso antes nessa conversa? Já ofertei esse slot?
7. **Canal correto:** se Chrome MCP no Kommo, o destinatário está em **Pedro M / paciente** ou caiu pra "todos os" (= nota interna)? **CONFIRMAR antes de clicar Enviar.**
8. **Dúvida conceitual do paciente:** se paciente pergunta "o que é X" (convênio, sinal, etc), **EXPLICAR primeiro**, depois retomar a coleta. Nunca repetir a pergunta original.
9. **Dia da semana × data:** validar `weekday()` antes de citar dia da semana junto com data. Erro recorrente "sexta (06/06)" quando 06/06 é sábado.
10. **Memória da sessão:** já busquei agenda Medware? Os slots vistos antes ainda valem? Não pular pra slots mais distantes esquecendo os próximos.

**Falhar em qualquer um = NÃO agir, refazer o raciocínio.**

---

## B. ANTI-DESCULPABILITY — REGRAS DE COMUNICAÇÃO

| ❌ NÃO fazer | ✅ Fazer em vez |
|---|---|
| "Desculpa, vou consultar a agenda e volto" | Buscar agenda agora (Medware tem MCP, é 1 call) |
| "Vou ver na próxima sessão" pra coisa que sei | Entregar AGORA |
| "Posso implementar se você topar" | Implementar e mostrar resultado |
| "Pode haver" / "talvez" / "acho que" | Confirmar via tool + entregar fato |
| Repetir explicação que já dei nessa sessão | Linkar mensagem anterior |
| Pedir pra Fábio rodar curl que eu poderia ter rodado | Rodar via Chrome MCP / MCP local |
| Gastar turno explicando trade-off | Escolher o melhor, agir, explicar 1 frase |

---

## C. BUGS MEUS INDEXADOS (Claude Cowork operando) — NÃO REPETIR

### Bug C-01 (04/06/2026 21:55) — Cronologia errada na oferta de slots
**Caso:** lead 24102510 Pedro Miguel pediu "dia 29 segunda". Pulei direto pra terça 30/06 e quinta 02/07.
**Erro:** quinta 11/06 (mesma semana!) tinha 7 slots tarde disponíveis. Ignorei.
**Regra:** sempre ofertar **data MAIS PRÓXIMA cronologicamente** que case com a preferência do paciente. Distância temporal vence preferência exata da data.
**Prevenção:** helper `_ordenar_slots_por_proximidade` + filtro `_viola_data_distante`.

### Bug C-02 (04/06/2026 21:59) — Mensagem virou nota interna (não WhatsApp)
**Caso:** lead 24102510 Pedro Miguel. Mandei "Pedro Miguel, deixa eu corrigir..." mas foi como **nota interna** ("Ariany para Todos") em vez de WhatsApp.
**Erro:** seletor de destinatário estava em "todos os" — paciente nunca viu.
**Regra:** ANTES de clicar Enviar no Kommo Chrome MCP, **CONFIRMAR via screenshot que o destinatário é o paciente (ex: Pedro M)**, não "todos os".
**Prevenção:** sempre clicar em "todos os" → escolher contato do paciente ANTES de digitar.

### Bug C-03 (04/06/2026 22:03) — Lia ignorou dúvida conceitual do paciente
**Caso:** lead 24102510 Pedro perguntou "o que é convênio?". Lia repetiu "qual é o nome do seu convênio?" sem explicar.
**Regra:** se paciente faz pergunta com "o que é" / "como funciona" / "não entendi" — **EXPLICAR o conceito antes** de retomar coleta.
**Prevenção:** regra `_MASTER_INSTRUCTION.md` seção nova "DÚVIDA CONCEITUAL DO PACIENTE" + state machine permitir ramificação BACKUP_EXPLICACAO.

### Bug C-04 (sessões anteriores, recorrente) — Cobrar valor antes de slot
**Caso:** lead 24102510 Lia ofereceu R$ 611 sem ter ofertado slot real.
**Regra:** filtro `_viola_cobranca_antes_slot` deve pegar **R$ XXX via Pix** e variantes, não só palavra "sinal".

### Bug C-05 (sessões anteriores) — "Vou consultar agenda" sem voltar
**Caso:** Juliene 24053159, Alice 21256807 — Lia disse "vou consultar agenda" e parou.
**Regra:** filtro `_viola_promete_retorno_humano` existe. Validar se está ATIVO em prod.

### Bug C-06 (04/06/2026 10h+) — Renomeação manual via tool calls é inviável
**Caso:** Fábio pediu renomear 368 leads. Comecei via tool calls sequenciais (kommo_search_leads + kommo_update_lead).
**Erro:** 368 × 2 calls = 736+ turnos. Custo de contexto inviável.
**Regra:** operações de massa (>20 itens) SEMPRE via endpoint server-side. Implementei `voice_agent/renomear_leads.py` + `/admin/renomear-leads-frio`. Padrão pra próximas.

### Bug C-08 (05/06/2026) — Subagent custom não funciona no Cowork
**Caso:** criei `.claude/agents/qa-blink.md` achando que ia ser invocável via `Agent(subagent_type="qa-blink")`. Falhou: `Agent type 'qa-blink' not found`.
**Erro arquitetural:** Cowork só carrega subagents pré-definidos (claude, claude-code-guide, Explore, general-purpose, Plan, statusline-setup). Arquivos `.claude/agents/*.md` no projeto NÃO são carregados como subagents nem mesmo se pushados.
**Workaround:** usar `Agent(subagent_type="general-purpose")` e injetar o prompt do qa-blink.md como `prompt`. Mesmo efeito, 1 nível de indireção.
**Regra:** ao criar "agente especializado" pra Cowork, é template de prompt, não subagent registrável. Documentar como tal.

### Bug C-07 (recorrente) — Pedir push pro Fábio em vez de usar MCP local
**Caso:** sandbox bloqueia `*.easypanel.host`. Toda sessão peço Fábio rodar curl.
**Solução:** MCP local `blink-bridge` (task #220) — bloqueado por Python 3.9 no Mac do Fábio.
**Regra:** pendência arquitetural — quando Python 3.11 instalado + MCP carregado, NÃO pedir mais curl.

---

## D. PROTOCOLO DE INDEXAÇÃO DE NOVOS BUGS

Toda vez que cometo um erro operacional **nesta sessão**, **ANTES** de seguir adiante:

1. Adicionar entrada nova em seção C deste arquivo (formato Bug C-NN)
2. Atualizar CLAUDE.md seção 16 (anti-padrões observados)
3. Se erro persistente → criar task pendente pra fix arquitetural

**Sem isso = bug se repete. Não aceito mais.**

---

## E. RITUAL DE INÍCIO DE SESSÃO COWORK

Toda sessão Cowork no folder Blink **DEVE** começar com:

1. Ler CLAUDE.md (auto-carregado)
2. Ler ESTE arquivo (`protocolo-claude-cowork.md`)
3. Verificar tasks `in_progress` e `pending` recentes (TaskList)
4. Verificar último handoff em `HANDOFF_*.md`

Se pular qualquer um → bugs repetem.
