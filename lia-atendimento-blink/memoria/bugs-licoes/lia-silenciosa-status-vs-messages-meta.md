# Lia silenciosa: NameError oculto em `responder.py`

> **Data:** 30/05/2026
> **CAUSA RAIZ REAL:** linha 970 de `voice_agent/responder.py` chamava `_build_janela_agenda()` mas a função **nunca foi definida**. Toda `responder.reply` lançava NameError, answer vazio, fallback "instabilidade", e como o dedup do fallback é 24h por convo_key, a mensagem parou de aparecer no Kommo — virou silêncio puro.
> **Origem:** commit do task #20 ("Re-injetar JANELA DE OFERTA DE AGENDA"). Adicionou a CHAMADA mas esqueceu de adicionar a FUNÇÃO.
> **Tempo até diagnóstico:** ~5h perseguindo Meta webhook (causa falsa). **30 segundos com `/admin/simulate-inbound` dry_run** — o ambiente de teste estrutural.

## Verdade técnica (Plan agent, validada)

O endpoint `/whatsapp` do voice_agent recebe **dois tipos** de payload do Meta:

1. **`entry[].changes[].value.messages[]`** — mensagem inbound real do paciente (precisa processar)
2. **`entry[].changes[].value.statuses[]`** — eventos de entrega/leitura/falha das mensagens que A EMPRESA enviou (precisa só ack 200)

`_wa_parse` em `voice_agent/whatsapp_cloud.py:373` **só itera `value.messages`**. Quando o payload é só `statuses`, o loop em `webhook.py:1059` **não roda nada**. Retorna 200 OK silencioso. **Zero log.**

## Sintoma observado

Logs Easypanel mostravam dezenas de `INFO: 10.11.0.4:xxxx - "POST /whatsapp HTTP/1.1" 200 OK` sem nenhum `[WA_INBOUND]`, sem `responder.reply`, sem `wa_cloud.send_text`. Lia parecia silenciada mas estava só **recebendo eventos de status** das próprias respostas anteriores.

## Diagnóstico falso que persegui

Eu chutei 5+ hipóteses antes da certa:
- ❌ "KWID desinstalado quebrou o Salesbot Kommo" (KWID era widget independente)
- ❌ "Webhook URL apontando errado" (handshake do `/whatsapp` retorna challenge OK)
- ❌ "Campo `messages` desinscrito" (estava `Assinado` azul)
- ❌ "Inscrição App↔WABA caiu" (deploy de endpoint Graph API pra re-assinar não mudou nada)
- ✅ **Real: Meta entregando só `statuses` porque o paciente real não mandou mensagem nova — todos os "oi" de teste vinham do Kommo (outbound) ou de números que já estavam em conversa fechada**

## Métodos que evitariam essa perseguição

1. **Análise estática ANTES de runtime debug**: ler o fluxo inbound inteiro (5 estágios: parse → dedup → enqueue → debounce → process_cloud → reply → send → kommo note) em vez de adicionar log e re-deploy 3 vezes.
2. **Plan agent em paralelo**: usar `Task` tool com Plan subagent pra mapear silently-swallow points em <250 palavras. Custou 30s e me deu a resposta direta.
3. **Teste de mensagem real**: pedir paciente real OU pessoa diferente mandar do celular pessoal, não do próprio Kommo. Mensagem do Kommo é **outbound** — gera só status update.
4. **MCP memória ativa + Obsidian**: consultar lições anteriores antes de chutar (este arquivo agora existe).

## Pontos onde mensagem pode ser silenciosamente descartada (mapa)

| Local | Cenário | Tem log? |
|---|---|---|
| `whatsapp_cloud.py:373` `_wa_parse` | payload é só `statuses[]` | NÃO |
| `webhook.py:1054` body não-JSON | webhook malformado | NÃO |
| `webhook.py:1067` `if not phone: continue` | sem número remetente | sim |
| `webhook.py:1071` dedup `mark_seen` False | replay do mesmo `mid` em <5min | sim (após patch debug bcb57e4) |
| `webhook.py:1077-1095` modo `_ingest["armed"]` | sandbox de áudios admin | só em INGEST |
| `webhook.py:1096-1119` tipo não casado (`reaction`, `interactive`) | tipos novos do Meta | NÃO |
| `webhook.py:519-532` `agent_paused_for_lead` | etapa `ST_AGENT_OFF` (cirurgia/lentes/fornecedor/CONFIRMAR/CONFIRMADO) | sim |
| `webhook.py:594-601` fallback instabilidade já enviado 24h | Claude API falhando | sim |
| `webhook.py:610-611` `if not answer: return` | answer vazio sem fallback | NÃO |

## Pytest pra blindar (não pode mais regredir)

Cenários a adicionar em `tests/test_filtros_lia.py`:

- `TestPayloadStatusVsMessage::test_payload_so_statuses_nao_processa` — POST /whatsapp com payload contendo só `value.statuses[]` retorna 200 OK e NÃO chama responder.reply
- `TestPayloadStatusVsMessage::test_payload_messages_inbound_processa` — POST /whatsapp com `value.messages[]` chama responder.reply 1x
- `TestPayloadStatusVsMessage::test_payload_messages_E_statuses_so_processa_messages` — mistura, só processa o de fato inbound
- `TestLogObservabilidade::test_wa_inbound_log_emitido_em_toda_mensagem_real` — garante que `[WA_INBOUND]` log aparece pra cada `messages[]` (lock do patch bcb57e4)

## Regra de ouro pós-incidente

> Antes de adicionar mais um log de debug em produção: ler com Plan agent o caminho inteiro do dado, listar todos pontos de descarte silencioso, e perguntar "qual o teste real reproduz o sintoma?". Mensagem de teste vinda do Kommo NÃO é teste de inbound.

Última atualização: 30/05/2026 ~10:30 BR
