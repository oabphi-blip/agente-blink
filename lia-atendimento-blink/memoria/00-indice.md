# Memória Blink — Índice

Toda sessão Cowork futura nesse folder me carrega o `CLAUDE.md` (resumo executivo) e essa pasta `memoria/` é a biblioteca acumulativa profunda. Cada vez que descubro um bug ou aprendizado novo, escrevo aqui — assim não repetimos histórias.

## Bugs e lições aprendidas

- `bugs-licoes/aurora-retrocesso.md` — Lia oferecia dia tendo agendamento (lead 23907418, fix 118d643)
- `bugs-licoes/um-momentinho.md` — Lia travou em "Um momentinho" sem voltar (lead 24033913)
- `bugs-licoes/cobranca-antes-slot.md` — Lia cobrou sinal sem oferecer slot (lead 24034205)
- `bugs-licoes/fallback-instabilidade-repetido.md` — Mesmo erro 3x em 1h por falta de crédito + sem dedup (lead 24037253, fix 1143504)

## Arquitetura e metas

- `arquitetura/40-agendamentos-dia.md` — Cálculo reverso pra atingir meta operacional
- `arquitetura/funil-ativacao-conversao.md` — Como leads frios viram agendamento

## Regras de ouro

- Nunca inventar chave Pix — só Asa Norte/Águas Claras
- Nunca "deixa eu consultar agenda" tendo agenda Medware OK
- Nunca cobrar sinal antes de oferecer slot
- Sempre 2 opções (Reserva Imediata 50% + Fila de Encaixe)
- Respeitar `ja_agendado=True`

## Como o Agente Guardião usa essa pasta

Toda noite às 18h (via scheduled task), um agente abre uma sessão automaticamente, lê:
- Commits novos do dia (`git log --since=yesterday`)
- Notas Kommo criadas hoje (via MCP)
- Logs do `/reactivation/status`

Se detectar bug novo (paciente reclamou, erro recorrente em log, frase proibida da Lia escapando), CRIA um arquivo em `bugs-licoes/` e atualiza o `CLAUDE.md` na seção 8 (Bugs históricos). Posta no Slack: "Hoje aprendi X, atualizei memoria/bugs-licoes/X.md."

Última atualização: 28/05/2026
