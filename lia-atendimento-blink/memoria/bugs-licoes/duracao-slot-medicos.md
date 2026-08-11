# Duração do slot na agenda por médico — fonte: Medware

> Decisão registrada por Fábio em 31/05/2026 (tasks #90 + #91).
> Esta é a fonte de verdade para o tempo de consulta nas mensagens do ciclo
> (D-3, D-1, D-0). Se algum valor mudar no Medware, atualizar os 4 lugares
> listados no fim deste documento.

## Tabela vigente

| Médico | Duração | Cobre |
|---|---|---|
| Dra. Karla Delalíbera | **30 min** | oftalmopediatria, SDP/Prisma, estrabismo, rotina |
| Dr. Fabrício Freitas | **40 min** | avaliação inicial E acompanhamento pós-operatório de catarata |
| Dra. Kátia Delalíbera | **30 min** *(placeholder — em pausa)* | retina (quando voltar a atender) |

## Decisões específicas que NÃO devem ser revertidas

1. **SDP/Prisma da Karla NÃO tem slot separado** — usa os mesmos 30 min da
   consulta de rotina. Decisão consciente do Fábio em 31/05/2026.
   Era chute meu anterior dizer que SDP durava "2 horas".

2. **Pediatria/exame infantil NÃO tem estimativa de tempo nas mensagens** —
   ficamos só com a dica "trazer brinquedo ou lanche leve". O tempo
   real (30 min) sai do header `📅 Dia/Hora` automaticamente.

3. **Catarata avaliação == catarata pós-op no Medware** — mesmo slot de
   40 min, sem distinção operacional.

4. **Kátia em pausa** — 30 min é placeholder. Quando voltar, reabrir
   esta linha e a constante em `voice_agent/mensagens_ciclo.py`.

## Os 4 lugares que precisam estar sincronizados

Se a duração mudar no Medware, **mexer nos 4** ou o pytest sentinela quebra:

1. `voice_agent/mensagens_ciclo.py::DURACAO_SLOT_MIN_POR_MEDICO`
2. `tests/test_mensagens_ciclo.py::TestDuracaoSlot::test_decisao_oficial_fabio_31_05_2026`
3. Este arquivo (atualizar data + tabela)
4. `CLAUDE.md` seção "Médicos / Slot Medware"

## Por que ficar centralizado em um lugar

A duração entra em 3 mensagens (D-3, D-1, D-0). Se cada mensagem tivesse
o número hardcoded, mudar de 30 → 25 min exigiria 9 edições. Hoje é 1
edição no dict + atualizar este doc.

Última atualização: 31/05/2026 — definição inicial após Fábio confirmar.
