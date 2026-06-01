# Lia inventou "retorno em horário comercial" quando agenda Medware chegou vazia

**Lead**: 24053159 — Juliene Siman (filho Daniel, 3 anos, estrabismo).
**Data**: 31/05/2026 ~20:43 BRT.
**Status do funil**: 102560495 (3-AGENDAR).
**Gravidade**: alta — paciente travou no fluxo, sem slot oferecido nem
agendamento gravado. Mensagem alucinada drilou os 4 filtros existentes.

---

## Frase exata bloqueada

> "Perfeito, Juliene! Terça-feira de manhã, meio do turno.
>
> Vou registrar sua preferência para a equipe finalizar — retorno em
> horário comercial (seg–sex, 8h–18h)."

NÃO existe em nenhum arquivo do voice_agent. Alucinação pura.

---

## Causa raiz

A pipeline (`pipeline.py:198`) buscou agenda Medware via
`horarios_para_agente()` e a resposta veio vazia naquele instante (ou o
warning silencioso da exceção mascarou o fato). O `_agenda_block(ctx)` no
responder retornava string vazia quando `ctx["agenda"]` era `[]`.

Sem agenda real injetada e sem instrução POSITIVA pro caso "agenda
vazia + status AGENDAR", o modelo improvisou um caminho que parecia
útil — encaminhar pra equipe humana. Os 4 filtros existentes:

- `_viola_oferta_agenda` (só dispara se há agenda real + Lia pediu pra consultar)
- `_viola_cobranca_antes_slot` (só vê cobrança Pix)
- `_viola_afirmacao_gravacao` (só vê "gravado no Medware")
- `_viola_dia_semana` (só vê dia-data inconsistente)

…todos passaram, porque a frase não casa com nenhum deles.

Validação: chamada direta ao Medware momentos depois retornou **32 slots
livres** Karla/Águas Claras particular nas próximas 2 semanas — o
Medware funciona, era intermitência ou cache de token JWT.

---

## Fix (commit pendente)

### 1. Novo filtro pós-geração — `_viola_promete_retorno_humano`

Em `voice_agent/responder.py`. Detecta 5 padrões:

- `registrar.*preferência.*equipe.*finaliza`
- `preferência\s+(?:para|pra)\s+(?:a\s+)?equipe.*finaliza`
- `retorno em horário comercial`
- `equipe\s+(?:humana|finaliza|entra em contato).*horário comercial`
- `seg(?:unda)?...sex(?:ta)?...8h...18h`

Quando bate:

- Se `ctx["agenda"]` tem slots → reescreve oferecendo os 2 primeiros
  (dia-semana + data + hora extraídos).
- Se está vazia → mensagem honesta: "Deixa eu reconsultar a agenda real
  aqui pra você. Me responde 'oi' em 1 minuto que eu volto com 2 opções
  concretas — dia, data e hora — pra você escolher."

### 2. Instrução POSITIVA injetada em `_agenda_block` quando `agenda=[]`

Antes: retornava `""` (modelo sem norte).
Agora: injeta bloco AGENDA INDISPONÍVEL no system prompt com:

- Lista de frases proibidas (incluindo a do Juliene)
- Único caminho aceito: reconsultar + pedir 1 min + voltar com slots concretos
- Exemplo aprovado entre aspas

### 3. Log nível ERROR em `pipeline.py` quando lead em AGENDAR/REAGENDAR chega com `ctx[agenda]=[]`

Antes: `log.warning("Medware horários falhou: ...")` (silencioso, só na exception).
Agora: `log.error("[AGENDA VAZIA EM AGENDAR] ...")` quando sucesso retorna lista
vazia E status_id ∈ {102560495, 106184631}. Easypanel/Slack pegam.

### 4. Pytest sentinela

`tests/test_filtros_lia.py::TestPromessaRetornoHumano` — 16 casos
parametrizados + a frase EXATA da Juliene + 2 testes de `_scrub_prohibited`
(com agenda vs sem) + `TestAgendaBlockVazia` (3 casos do bloco preventivo).

---

## Otimizadores arquiteturais que faltam (top 4)

A diagnose honesta do Fábio: "todos os otimizadores e ambiente de teste,
memória ativa, ainda deixou isso acontecer". Os 4 filtros são REATIVOS
— cada um cobre um padrão de bug passado. Padrão novo escapa.

Pra defesa PREVENTIVA real, faltam:

1. **Tool calling estruturado** — Claude chama `oferecer_slot()`,
   `gravar_agendamento_medware()`. Resposta humana ⊃ resultado real.
   Elimina inferência via detector Haiku. ~4-6h.
2. **State machine de conversa** em Redis — TRIAGEM → DADOS → CONVÊNIO
   → AGENDA → CONFIRMAÇÃO → GRAVAÇÃO → POS_GRAVAÇÃO. Se a resposta não
   bate com o estado, regera com instrução explícita. ~3-4h.
3. **Smoke test contínuo (cron 1h)** — bate `/admin/simulate-inbound`
   com 5 cenários core + valida resposta determinística. Alerta Slack
   se quebra. ~1-2h.
4. **Coleta progressiva obrigatória** — checklist
   `dados_minimos_para_gravar` injetada no prompt. Não oferece slot
   final sem nome completo + CPF responsável + data_nasc. ~1h.

---

## Intervenção manual no lead 24053159

Às 21:56 enviei via Kommo Chat:

> Juliene, voltei aqui consultando a agenda real pra você. Pra
> Terça-feira de manhã, no horário que você pediu, tenho 2 opções com
> a Doutora Karla Delalíbera em Águas Claras:
>
> 1) Terça-feira, 02/06 às 09:00
> 2) Terça-feira, 09/06 às 09:30
>
> Qual fica melhor pra você?
>
> Pra eu já deixar tudo gravado no sistema, me confirma também:
> - Nome completo do Daniel
> - CPF dele (mesmo de criança serve)
> - Seu CPF (você como responsável)
>
> Assim que você me passar, garanto o horário e te mando a confirmação.

O pipeline auto-preencheu `1.DIA SEM CONVÊNIO=02/06 09:00` e
`2.DIA SEM CONVÊNIO=09/06 09:30` no Kommo (kommo.update_lead_fields
via detector Haiku). Logo após, Lia respondeu por cima oferecendo OS
MESMOS slots + Lista de Espera — confirma intermitência, não
quebra permanente.

---

## Sinal para a próxima sessão

Se o motor da Lia voltar a oferecer slot real consistentemente após o
deploy desse fix, a hipótese de intermitência se confirma e os 4
otimizadores arquiteturais viram a próxima onda de trabalho. Se voltar
a inventar mesmo com `_viola_promete_retorno_humano` ativo, o problema
é mais profundo — provavelmente alguma camada que dropa `caller_context`
antes do responder.
