# Bug Esther — Lia re-ofereceu slot tendo lead JÁ AGENDADO (recidiva Aurora)

> **Data:** 01/06/2026
> **Lead:** 24060221 (Esther) — estava em 5-AGENDADO, 09/06 18:30 com Dra. Karla, Águas Claras
> **Commit fix:** `e636a84`

## Sintoma
Esther já estava agendada (status 5-AGENDADO). Enviou foto da carteirinha. O
handler de webhook gerou um `user_text` sintético com "siga o atendimento
normalmente". O LLM Sonnet interpretou isso como permissão para oferecer slot e
respondeu "deixa eu trazer os horários disponíveis...". Retrocesso clássico —
recidiva do bug Aurora.

## Causa raiz
A TRAVA JA AGENDADO existe no system prompt, mas o LLM priorizou a instrução do
`user_text` sintético sobre a trava do prompt. Prompt sozinho não segura quando
há instrução conflitante no input. O filtro pós-geração é a defesa final e não
existia para este padrão.

## Fix
`voice_agent/responder.py`:

- `_viola_oferta_apos_agendado(text, ctx)` — detecta oferta de slot quando o ctx
  indica lead já agendado.
- `_gerar_oferta_pos_agendado_fallback(ctx)` — substitui por mensagem de
  confirmação em vez de re-oferta.
- Plugado em `_scrub_prohibited` como filtro **0-pré** (roda antes dos demais).

## Cenário pytest
`tests/test_oferta_pos_agendado.py` — 17 cenários. Total 748 testes verdes.

## Tags
`bug-fix` `responder` `ja-agendado` `retrocesso` `filtro-pos-geracao` `critico`
`recidiva-aurora`
