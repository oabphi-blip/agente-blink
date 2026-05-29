# Bug duplo — Lia inventou dia da semana E Medware não gravou

**Lead**: 24038029 (Karla Delalibera Pacheco) · **Data**: 29/05/2026
**Médico oferecido**: Dra. Karla Delalibera (Águas Claras) · **Slot escolhido**: 02/06 10:30

## Sintoma 1 — Dia da semana errado

Lia ofereceu:
- "1️⃣ terça-feira, **03/06** às 10:30" ← 03/06/2026 é **QUARTA**
- "2️⃣ quinta-feira, 04/06 às 11:00" ✅
- "3️⃣ terça-feira, **10/06** às 11:15" ← 10/06/2026 é **QUARTA**

Paciente percebeu, Lia corrigiu pra "terça-feira 02/06, 09/06, 16/06" — datas corretas.

## Causa raiz #1
`responder.py` linha 759-761 tinha `JANELA DE OFERTA DE AGENDA` **desativada** com nota errada ("Lia não oferece datas"). O KB tem fluxo E7 (AGENDA DISPONÍVEL) que **pede** oferta. Sem janela injetada (fonte de verdade do calendário), Lia inventa dia da semana.

## Fix #1 — janela religada
Linha 762-765 do `responder.py`:
```python
system_prompt = self._base_system_prompt + _today_brt_block()
system_prompt += _caller_context_block(caller_context)
system_prompt += _build_janela_agenda()  # ← REATIVADO
```

## Fix #2 — filtro `_viola_dia_semana` (rede de segurança final)
Mesmo com janela religada, modelo pode escorregar. Filtro pós-geração detecta padrão "<dia>, DD/MM" e valida com `datetime` Python. Se Lia escreveu errado, BLOQUEIA e força regenerar via `_DIA_SEMANA_FALLBACK`.

---

## Sintoma 2 — Medware NÃO gravou

Lia confirmou "✨ Agendamento confirmado!" no chat (Kommo nota 28929863), com resumo completo. **Mas o Medware não tem o slot 02/06 10:30 da Karla** — só Ana Paula 08:30 e Eduardo 10:00. E **não tem nota "GRAVAÇÃO MEDWARE FALHOU"** no Kommo — significa que a função sequer foi chamada.

## Causa raiz #2
`agendamento.py` linha 83-85 abortava cedo:
```python
if not medico:
    return None  # Sem médico, não há como agendar.
```

E `medico` vem de `caller_context.known.medico`, que é populado pelo Kommo. No lead 24038029:
- Lead criado 22:06 (paciente novo, MÉDICOS=vazio)
- Lia decidiu "Dra. Karla" via KB durante a conversa
- Campo MÉDICOS no Kommo só foi preenchido **depois** da resposta (sync assíncrono)
- caller_context (montado ANTES da resposta) estava sem médico
- → detector retornou None → Medware nunca foi chamado

## Fix #3 — detector extrai médico da mensagem da Lia
EXTRATOR_PROMPT atualizado: se ctx vazio, pede Haiku extrair médico/unidade **do texto da Lia** (que sempre mostra "Dra. Karla Delalibera" no resumo). Médicos válidos hardcoded no prompt.

Função `detectar_agendamento_confirmado`:
- Antes: abortava se `medico_ctx` vazio
- Agora: deixa Haiku extrair, prioriza ctx, fallback pra extração

```python
medico_final = medico_ctx or (data.get("medico") or "").strip()
unidade_final = unidade_ctx or (data.get("unidade") or "").strip()
if not medico_final:
    return None  # só aborta se NEM ctx NEM Haiku acharam
```

## Cenários pra pytest

1. **Dia da semana inventado** — Lia gera "terça-feira, 03/06/2026" → filtro substitui pelo fallback
2. **Medware grava mesmo sem ctx.medico** — caller_context sem médico, resposta da Lia tem "Dra. Karla" → Haiku extrai → executar_agendamento roda
3. **Janela injetada** — system_prompt contém "JANELA DE OFERTA DE AGENDA" com dia da semana correto ao lado

## Tags
`bug-fix` `agendamento` `medware` `filtro-pos-geracao` `janela-agenda` `extracao-haiku`
