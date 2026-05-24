# STATUS DO PROJETO — AGENTE IA BLINK

Documento de acompanhamento. Cada tópico é uma situação diferente, com o que
já foi feito e o que falta. Atualizado em 22/05/2026.

**Links de trabalho**
- Easypanel (deploy): https://6prkfn.easypanel.host/projects/blink/app/agent
- GitHub (código): https://github.com/oabphi-blip/agente-blink

Legenda: ✅ concluído · 🔄 em andamento · ⏳ pendente · 🚧 bloqueado (terceiros)

---

## TÓPICO 1 — Número oficial 8133 (WhatsApp Cloud API)

**Status: ✅ Concluído e no ar.**

- ✅ Conector da API oficial (Cloud API) criado e deployado.
- ✅ Webhook configurado no app da Meta.
- ✅ Agente recebe e responde pelo 8133 pela API oficial (confirmado nos
  logs e no celular do paciente).

---

## TÓPICO 2 — Comportamento da Lia no atendimento (7 apontamentos)

**Status: ✅ Concluído e no ar.**

- ✅ 0002 — reconhece lead com agendamento existente (não refaz triagem).
- ✅ 0003 — idade correta, em anos completos, sem repetir.
- ✅ 0005 — removida a pergunta "texto/áudio/ligação"; acolhimento espelha
  o anúncio (Facebook/Instagram/Google).
- ✅ 0007 — datas de consultas existentes citadas corretamente.
- ✅ Nome do médico sempre completo (nome + sobrenome).
- ✅ 0001 / 0004 / 0006 — campanhas, objeções e valores (seção 23 da
  instrução: sábado R$580,45, sinal 50% Pix, campanhas até 15%, catarata).
- ✅ Campo AÇÕES (encaixe) mapeado no Kommo.

---

## TÓPICO 3 — Reativação de leads frios

**Status: 🔄 Mensagens melhoradas e no ar; envio real ainda NÃO ativado.**

- ✅ Mensagens do motor de reativação reescritas (mais acolhedoras, prova
  da escuta, sem promessa de data).
- ⏳ Ativar o envio real: trocar `REACTIVATION_DRY_RUN=false` no Easypanel
  (aba Ambiente) e Implantar. Hoje está em dry-run (monta mas não envia).

---

## TÓPICO 4 — Reconciliação de etapas (Medware × Kommo)

**Status: 🔄 Módulo no ar; falta rodar o dry-run e revisar.**

- ✅ Módulo de reconciliação construído e deployado (roda em segundo plano,
  com endpoint de status). Etapa-alvo confirmada: 10-PRÓXIMA CONSULTA.
- ⏳ Rodar o dry-run (há um lembrete automático agendado para disparar).
- ⏳ Revisar o relatório (quantos leads iriam para 10-PRÓXIMA CONSULTA e
  quantos para 2-AGENDAR) e aprovar a aplicação real.

---

## TÓPICO 5 — Convivência humano × agente

**Status: 🔄 Código pronto; falta um deploy.**

- ✅ Pausa de handoff de 6 min (configurável): quando o humano responde no
  Kommo, a Lia silencia e retoma sozinha após 6 min.
- ✅ Agente DESLIGADO para leads em **7-CIRURGIAS ANDAMENTO, 8-LENTES
  ANDAMENTO e 9-FORNECEDORES** (atendimento humano / contato fornecedor).
- ✅ Orientação para o time de atendimento redigida.
- 🔄 Deploy: a pausa de handoff já está no ar; o commit que adiciona as
  etapas 8-LENTES e 9-FORNECEDORES (`c50a406`) está **pendente de Implantar**.

---

## TÓPICO 6 — Integração da agenda Medware (oferta de horários reais)

**Status: 🚧 Bloqueado — aguardando a Medware.**

- 🚧 O endpoint `Horarios/Listar` da Medware retorna lista vazia — sem
  isso o agente não consegue oferecer horários reais.
- ✅ Mensagem técnica enviada ao suporte da Medware.
- ⏳ Aguardando o retorno deles para retomar a integração.

---

## TÓPICO 7 — Áudios da equipe médica

**Status: ⏳ Roteiros prontos; aguardando gravação.**

- ✅ Roteiro de 8 áudios do **Dr. Fabrício Freitas** (catarata) pronto, com
  o momento de uso de cada um — arquivo `ROTEIRO_AUDIOS_DR_FABRICIO.md`.
- ⏳ Aguardando o Dr. Fabrício gravar e enviar os áudios.
- ⏳ Áudios da **Dra. Karla Delalíbera** (apontamento 0005) — roteiro a
  produzir quando for o momento.
- ⏳ Depois das gravações: integração no conector (envio de áudio +
  mapa áudio→gatilho).

---

## TÓPICO 8 — Marketing e anúncios

**Status: ✅ Recomendações entregues.**

- ✅ Recomendação geral para o time de marketing — arquivo
  `RECOMENDACAO_MARKETING_ANUNCIOS.md`.
- ✅ Feedback específico do anúncio de catarata (formato "onde se lê /
  leia-se").
- ⏳ Opcional: registrar na instrução mestra o padrão "anúncio que faz
  pergunta → o agente responde a pergunta na 1ª linha".

---

## TÓPICO 9 — Segurança

**Status: ⏳ Pendente — ação sua.**

- ⏳ O token da Meta (WhatsApp) foi colado no chat e está comprometido.
  Recomendado: gerar um novo token no Usuário do Sistema e trocá-lo no
  Easypanel (`WHATSAPP_CLOUD_TOKEN`).

---

## TÓPICO 10 — Deploy e acesso

**Status: ✅ Decidido.**

- ✅ Deploy manual (um clique em "Implantar"). Auto-deploy avaliado e
  descartado por ora.
- ✅ Token do GitHub salvo no Easypanel.

---

## TÓPICO 11 — "Agente browser" (agent-browser-main.zip)

**Status: ⏳ A esclarecer.**

- ⏳ Arquivo enviado no início da conversa, não está mais disponível na
  sessão e nunca foi processado. Se ainda quiser, reenvie o zip e explique
  o que ele deve fazer.

---

## PRÓXIMAS AÇÕES IMEDIATAS

1. **Implantar** o commit `c50a406` (etapas 8-LENTES e 9-FORNECEDORES).
2. Revisar o relatório da reconciliação quando o lembrete disparar (Tópico 4).
3. Decidir/ativar o envio real da reativação (Tópico 3).
4. Dr. Fabrício gravar e enviar os 8 áudios (Tópico 7).
5. Rotacionar o token da Meta (Tópico 9).
6. Aguardar retorno da Medware sobre a agenda (Tópico 6).
