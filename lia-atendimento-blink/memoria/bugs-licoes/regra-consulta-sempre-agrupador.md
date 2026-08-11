# Regra de negócio: consulta na Blink SEMPRE inclui exame completo

> Definida pelo Fábio em 30/05/2026. Esta é a fonte de verdade. Substitui
> qualquer documento anterior que sugira "consulta avulsa", "só consulta",
> "consulta sem exame" ou "agrupador personalizado".

## A regra única

**Na Blink Oftalmologia, não existe consulta sem exame.** Toda consulta
agendada vincula automaticamente UM dos 4 agrupadores de procedimentos:

| Faixa etária | Motivo Rotina | Motivo Urgência |
|---|---|---|
| ≥ 3 anos | Agrupador 1 (9 exames) | Agrupador 2 (6 exames) |
| < 3 anos | Agrupador 3 (6 exames) | Agrupador 4 (5 exames) |

## O que NÃO existe

- ❌ Opção "só consulta avulsa, sem exame"
- ❌ Agrupador "Personalizado" no Kommo
- ❌ Possibilidade de paciente recusar exames e ainda agendar
- ❌ Médico atender sem o pacote

## Implicações pra Lia

1. Quando paciente perguntar "vale só pagar a consulta?", responder com
   transparência: na Blink a consulta sempre inclui o exame completo
   (cite quais exames pelo agrupador correspondente). Não existe opção
   só consulta.

2. Quando convênio cobre só consulta sem cobrir exames: marcar como
   `MOTIVOS PERDA = "Convênio não cobre exames do agrupador"`. Não tentar
   agendar.

3. Pra todo paciente que chega, sempre selecionar agrupador automático
   baseado em `1.TIPO MOTIVO` (a criar) + `1.PERFIL 1º PACIENTE`.

## Implicações pro código

- `voice_agent/procedimentos.py:selecionar_agrupador` **sempre devolve**
  exatamente um dos 4 agrupadores. Não há `None`, não há "Personalizado".
- Pytest blinda os 4 cenários — qualquer mudança que introduza 5ª opção
  quebra build.
- `agendamento.executar_agendamento` deve iterar a lista de
  `codProcedimento` do agrupador e gravar um POST por exame (ou usar
  endpoint Medware de lote se disponível).

## Implicações pro Kommo

- Campo a criar: `1.AGRUPADOR EXAMES` — select com EXATAMENTE 4 opções.
- Campo a criar: `1.TIPO MOTIVO` — select com 5 opções (Rotina,
  Acompanhamento, Pré-op, Pós-op, Emergência/Urgência).
- Acrescentar enum em `MOTIVOS PERDA`: "Convênio não cobre exames do
  agrupador" e "Recusou pacote de exames".

## Lição arquitetural

Toda vez que um agente de IA opera num domínio com regras fixas como
essa ("sempre inclui X", "nunca sem Y"), a regra precisa estar:
1. Em código (módulo dedicado tipo `procedimentos.py`)
2. Em pytest blindando que nenhum cenário escapa
3. Em memória ativa (este arquivo)
4. No prompt do agente (Master Instruction)

Sem as 4 camadas, paciente eventualmente recebe oferta que viola a regra,
e clínica precisa desfazer/explicar/perder lead. Bug silencioso clássico.

Última atualização: 30/05/2026
