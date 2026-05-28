# Bug "Um momentinho" — Lia travou sem oferecer horários

**Lead**: 24033913 (Fábio teste)
**Data**: maio/2026

## Sintoma
Paciente perguntou disponibilidade. Lia respondeu "Um momentinho, deixa eu consultar a agenda" e nunca mais voltou com slots. Conversa morreu.

## Causa raiz
Lia tinha aprendido (via prompt + KB) a "dar tempo" antes de responder. Mas quando o caller_context já trazia agenda real do Medware, ela emitia frases tipo "consultar agenda", "um momentinho", "vou verificar" — sem usar a info que já tinha.

## Fix
`voice_agent/responder.py`:

1. **`_agenda_block` reforçado** com frases proibidas: "deixa eu consultar", "um momentinho", "vou verificar", "estou sem acesso à agenda".

2. **`_FAKE_AGENDA_LOOKUP_FALLBACK` + `_viola_oferta_agenda()`**: filtro pós-geração detecta essas frases TENDO agenda real e substitui pela pergunta de preferência.

3. `_scrub_prohibited` agora recebe `ctx` pra ativar detecção condicional.

## Cenário pra pytest
- caller_context tem `agenda_disponivel=True`
- Lia gera resposta com "vou consultar agenda"
- Filtro substitui pela pergunta de preferência

## Tags
`bug-fix` `agendamento` `filtro-pos-geracao`
