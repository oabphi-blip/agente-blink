# Plano E6-C — Janela cirúrgica Medware

## Origem e justificativa

Aprovado pelo Fábio em 18/06/2026, após sessão de análise técnica das limitações do Medware. Hoje a Lia em produção bate no Medware com janela ampla (14 dias × manhã + tarde × dia inteiro 07-19h). Mesmo após os fixes C-38 e C-38b, isso ainda é pesado para a VM Light. A regra E6-C ataca a causa raiz: se o paciente especificar **dia da semana + janela de horas (início e fim)** antes do agente bater o Medware, a chamada vira cirúrgica (1 dia × 2 horas) e a resposta vem em menos de 1 segundo, com redução estimada de ~90% da carga no servidor.

## Comportamento alvo

A Lia, ao entrar em estado AGENDA com médico e unidade conhecidos, segue o fluxo:

**Passo 1 — Verificar ctx.known.dia_turno_periodo.** Se contém simultaneamente dia da semana, turno e janela de horas, pula direto para a chamada cirúrgica ao Medware (Passo 4).

**Passo 2 — Se faltar informação, perguntar UMA pergunta consolidada.** Uma única mensagem de até 50 palavras com os 3 pontos juntos. Modelo recomendado:

> "Pra te oferecer o melhor horário com a Dra. Karla Delalíbera na Asa Norte, me conta:
>
> Qual dia da semana fica melhor pra você? (segunda, quarta ou sexta)
>
> E qual janela de horário? (exemplo: 9h às 11h)"

Regra dura: NUNCA quebrar em três turnos separados. O paciente responde uma vez e a Lia já dispara a chamada cirúrgica.

**Passo 3 — Parsear resposta.** Lia popula `ctx.known.dia_turno_periodo` e grava no Kommo no campo DIA/TURNO/PERIODO ⚠️ (field_id 1259960).

**Passo 4 — Chamada cirúrgica ao Medware.** Em vez de pedir 14 dias com horários 07:00-19:00, pede apenas a próxima ocorrência do dia da semana especificado, com horário restrito à janela do paciente. Exemplo: próxima quarta-feira, hora 09:00 a 11:00, codMedico=12080, codUnidade=5.

**Passo 5 — Oferta direta de 2 slots.** Formato canônico 1️⃣ + 2️⃣, sem perguntar nada mais.

**Passo 6 — Se janela cirúrgica retornar 0 slots.** Lia explica honestamente: "Nessa janela (quarta de manhã, 9h às 11h) não tenho horário aberto nas próximas semanas. Posso te oferecer quarta tarde, ou outro dia da semana — qual prefere?". Faz nova consulta cirúrgica.

## Decisão Fábio sobre "qualquer dia/horário"

**Opção A escolhida.** Se paciente responder "qualquer dia, qualquer horário, urgência", tratar como sinal de urgência. Oferecer os 2 primeiros slots disponíveis na semana atual (janela curta default 7 dias). Não fazer mais pergunta.

## Implementação técnica

### Arquivos a modificar

**1. `voice_agent/knowledge_base/_MASTER_INSTRUCTION.md`**

Adicionar regra E6-C entre as regras E6-A (sequência de oferta de 2 slots) e E6-B (reserva 10 minutos):

> **E6-C — Janela cirúrgica Medware (Fábio 18/06/2026)**: em modo AGENDA, antes de qualquer chamada ao Medware, verificar `ctx.known.dia_turno_periodo`. Se contiver simultaneamente dia da semana + turno + janela de horas (início e fim), saltar direto para a chamada cirúrgica. Caso contrário, perguntar em UMA mensagem consolidada de até 50 palavras: "Pra te oferecer o melhor horário com {médico} na {unidade}, me conta: qual dia da semana fica melhor pra você? E qual janela de horário? (exemplo: 9h às 11h)". Nunca quebrar em três perguntas separadas. Se o paciente responder "qualquer dia/horário/urgência", tratar como urgência e oferecer 2 slots da semana atual sem pergunta extra. Após resposta, parsear, popular `ctx.known.dia_turno_periodo` e disparar chamada cirúrgica.

Bumpar `VERSAO_PROMPT` para `2026-06-18-e6c-janela-cirurgica` para invalidar cache Anthropic.

**2. `voice_agent/janela_preferencia.py`**

Ampliar o parser existente para extrair `hora_inicio` e `hora_fim` em formato `HH:MM`. Suportar:

- "9h às 11h" → hora_inicio=09:00 hora_fim=11:00
- "das 14 às 16" → hora_inicio=14:00 hora_fim=16:00
- "entre 10:30 e 12:00" → hora_inicio=10:30 hora_fim=12:00
- "depois das 8h" → hora_inicio=08:00 hora_fim=12:00 (assume fim da manhã)
- "antes das 12h" → hora_inicio=07:00 hora_fim=12:00
- "manhã" (sem janela explícita) → hora_inicio=07:00 hora_fim=12:00
- "tarde" → hora_inicio=13:00 hora_fim=18:00

Sinalizadores de urgência ("qualquer dia", "urgente", "rápido", "qualquer horário") → retornar `urgencia=True` em vez de tentar parsear.

**3. `voice_agent/pipeline.py`**

Antes do bloco que chama `self.medware.horarios_para_agente(...)`:

```python
# E6-C — janela cirúrgica antes de bater Medware
pref_completa = parse_janela_preferencia(known.get("dia_turno_periodo"))
if pref_completa.urgencia:
    # Opção A: oferecer 2 slots da semana sem mais perguntar
    slots = self.medware.horarios_para_agente(
        medico_param, unidade_param,
        dias=7,
    )
elif pref_completa.tem_dia and pref_completa.tem_janela_horas:
    # Chamada cirúrgica
    slots = self.medware.horarios_para_agente(
        medico_param, unidade_param,
        data_inicio=pref_completa.data_inicio,
        data_fim=pref_completa.data_fim,
        hora_inicio=pref_completa.hora_inicio,
        hora_fim=pref_completa.hora_fim,
    )
else:
    # Pular chamada Medware — prompt E6-C vai gerar pergunta consolidada
    slots = []
    caller_context["e6c_aguardando_preferencia"] = True
```

Ajustar `voice_agent/medware.py::horarios_para_agente()` para aceitar `hora_inicio` e `hora_fim` opcionais e propagar pro request HTTP (`horaInicio`, `horaFim`).

**4. `tests/test_e6c_janela_cirurgica.py` (novo)**

Cobertura mínima de 12 cenários:

1. `dia_turno_periodo` completo ("quarta-feira 9h às 11h") → bate Medware com janela cirúrgica.
2. `dia_turno_periodo` só com dia ("quarta-feira") → pula chamada Medware, ctx flagged.
3. `dia_turno_periodo` só com janela ("9h às 11h") → pula chamada Medware, ctx flagged.
4. `dia_turno_periodo` vazio → pula chamada Medware, ctx flagged.
5. Pergunta consolidada gerada tem menos de 50 palavras.
6. Pergunta consolidada contém os 3 pontos juntos numa só mensagem.
7. Parser entende "9h às 11h" → hora_inicio=09:00 hora_fim=11:00.
8. Parser entende "das 14 às 16" → hora_inicio=14:00 hora_fim=16:00.
9. Parser entende "entre 10:30 e 12:00" → hora_inicio=10:30 hora_fim=12:00.
10. Parser entende "depois das 8h" → hora_inicio=08:00 hora_fim=12:00.
11. "qualquer dia, urgente" → trata como urgência, oferece 2 slots da semana.
12. Janela cirúrgica retornou 0 slots → fallback honesto com nova oferta.

### Sequência de implantação

1. Confirmar que o agente 0710 está deployado e estável em prod (REDIRECT_0710_ENABLED=1 + REDIRECT_0710_ROTEAR_HANDLER=1 ligadas e respondendo bem).
2. Ler `voice_agent/janela_preferencia.py` para confirmar estrutura atual do parser.
3. Ler `voice_agent/pipeline.py` para identificar exatamente onde plugar o branch E6-C (antes de `medware.horarios_para_agente`).
4. Ler `voice_agent/medware.py` para confirmar que `horarios_para_agente` aceita parâmetros `hora_inicio`/`hora_fim` ou precisa estender assinatura.
5. Atualizar `_MASTER_INSTRUCTION.md` com regra E6-C + bump VERSAO_PROMPT.
6. Ampliar `janela_preferencia.py` com parser de janela de horas.
7. Plugar branch E6-C em `pipeline.py`.
8. Criar `tests/test_e6c_janela_cirurgica.py` com 12 cenários.
9. Rodar `python3 -m pytest tests/test_e6c_janela_cirurgica.py -v` localmente. Esperar 12/12 verde.
10. Rodar pytest completo do projeto para garantir zero regressão.
11. Criar `PUSH_E6C_JANELA_CIRURGICA.command` com sanity + pytest + git commit + git push.
12. NÃO fazer push direto. Entregar o `.command` pronto.
13. Atualizar `CLAUDE.md` com nova seção 0-AC documentando regra E6-C.

### Critérios de sucesso

- Lia em modo AGENDA bate Medware com janela cirúrgica (1 dia × 2-4 horas) quando ctx.known tem dia + janela.
- Quando falta informação, Lia faz UMA pergunta consolidada (nunca 3 turnos separados).
- Tempo de resposta Medware abaixo de 1 segundo na janela cirúrgica.
- Zero retrocesso de triagem (paciente que já disse "quarta 9h-11h" não é perguntado de novo).
- Carga Medware reduzida em ~90% nas chamadas E6-C.

### Rollback sem deploy

Setar `E6C_JANELA_CIRURGICA_ENABLED=0` no Easypanel. Pipeline volta ao comportamento atual (janela 14 dias). Sem revert de código.

## Observações operacionais

- Projeto em `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK/`.
- Repositório GitHub: `https://github.com/oabphi-blip/agente-blink` (privado).
- Easypanel: `https://blink-agent.6prkfn.easypanel.host`.
- Field DIA/TURNO/PERIODO ⚠️ no Kommo: id 1259960.
- Pipeline ATENDE no Kommo: id 8601819.
- Modelo Lia atual: Claude Sonnet 4.5 / Haiku 4.5 / Opus 4.6 (route_model decide por estado FSM).
- Após implementação, monitorar logs `[MEDWARE REQ] janela_fonte=cirurgica` durante 24h para confirmar uso real.

## Instrução final para próxima sessão executar

Implementa esse plano integralmente nesta sessão. Antes de codar, lê `CLAUDE.md`, `voice_agent/janela_preferencia.py`, `voice_agent/pipeline.py` e `voice_agent/medware.py` para confirmar assinaturas atuais. Depois segue os 13 passos da sequência de implantação. Roda pytest completo ao final. Entrega `.command` de push pronto para o Fábio rodar manualmente. Não dá push direto.
