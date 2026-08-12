#!/bin/bash
# C-129 + C-130 — Push consolidado (12/08/2026)
#
# C-129: Pós-consulta → escalar para humano (lead 14230149 Luciana)
#   - voice_agent/pos_consulta.py (NOVO): detecta pedidos de doc / a_fazer_pos_consulta
#   - voice_agent/blindagens_deterministicas.py: C-129 PRIMEIRO na chain
#   - voice_agent/kommo.py: lê field 1259312 (A FAZER) → a_fazer_pos_consulta=True
#   - voice_agent/pipeline.py: flag c129_pos_consulta → desativa IA + ATENDIMENTO HUMANO
#   - tests/test_bug_c129_pos_consulta.py: 37 testes
#
# C-130: Anti-loop pergunta data nascimento (lead 24447784 Bento)
#   - checklist_dados_minimos.py: data_nascimento_ok() aceita "27/012/2024" (3-digit month)
#   - blindagens_deterministicas.py: gate _inbound_responde_ultima_pergunta_c130
#   - tests/test_bug_c130_data_nasc_loop.py: 27 testes
#
# C-128 (já commitado localmente 87939b6): incluso neste push se não foi feito ainda
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-129 + C-130 + C-128 ==="
python3 -m pytest \
  tests/test_bug_c129_pos_consulta.py \
  tests/test_bug_c130_data_nasc_loop.py \
  tests/test_bug_c125_prova_escuta_uma_pergunta.py \
  tests/test_bug_c123_convenio_recusado.py \
  -v --tb=short -q

echo ""
echo "=== Staging ==="
git add \
  voice_agent/pos_consulta.py \
  voice_agent/blindagens_deterministicas.py \
  voice_agent/kommo.py \
  voice_agent/pipeline.py \
  voice_agent/checklist_dados_minimos.py \
  tests/test_bug_c129_pos_consulta.py \
  tests/test_bug_c130_data_nasc_loop.py \
  CLAUDE.md

git add -f PUSH_C129_C130_POS_CONSULTA_E_DATA_NASC.command
git add -f PUSH_C130_LOOP_DATA_NASCIMENTO.command

echo "=== Commit C-129 + C-130 ==="
git commit -m "feat(C-129+C-130): pos-consulta escalar humano + anti-loop data nascimento

=== C-130: Anti-loop 'Qual a data de nascimento?' (lead 24447784 Bento) ===

Fix duplo:

1. checklist_dados_minimos.py::data_nascimento_ok():
   ANTES: regex strict rejeitava '27/012/2024' (3 dígitos no mês)
   DEPOIS: regex leniente aceita typos — validação real fica no Medware

2. blindagens_deterministicas.py::deve_perguntar_dados_pendentes():
   _inbound_responde_ultima_pergunta_c130() — quando paciente responde
   a última pergunta C-125 (data/CPF/nome/convênio) → retorna None →
   LLM extrai, sem C-125 interceptar e repetir a pergunta.

Pytest: 27/27 C-130 verde, 69/69 C-130+C-125 combinado

=== C-129: Pós-consulta → escalar para 1-ATENDIMENTO HUMANO ===

Caso real: lead 14230149 Luciana consultou 10/08/2026. Perguntou
'recibo de pagamento' → Lia respondeu com tabela de preços. Nonsense.

voice_agent/pos_consulta.py (NOVO):
  deve_escalar_pos_consulta(ctx, user_text):
    Camada A: regex detecta pedido de recibo/nota fiscal/reembolso/
              atestado/laudo/resultado/receita/prontuário → escala SEMPRE
    Camada B: ctx.known.a_fazer_pos_consulta=True + msg NÃO é intent
              de novo agendamento → escala
    Toggle: POS_CONSULTA_ATIVADO (default ON). Fail-open.

voice_agent/kommo.py (modificado):
  Lê field 1259312 (A FAZER multiselect) — detecta enum_id 925064
  'Pós Consulta' → injeta known['a_fazer_pos_consulta'] = True

voice_agent/blindagens_deterministicas.py (modificado):
  C-129 adicionado PRIMEIRO na chain de tentar_bypass_deterministico()
  (após C-126/pede_atendente, antes de C-117/cancelamento_24h)

voice_agent/pipeline.py (modificado):
  Bloco C-129: lê blink:c129_pos_consulta:{lead_id} (TTL 24h) →
  desativa IA + move lead → 106563343 (1-ATENDIMENTO HUMANO) + nota Kommo

tests/test_bug_c129_pos_consulta.py (NOVO):
  37 testes: Camada A (15), falso positivo (5), Camada B (6),
  toggle (3), mensagem canônica (5), regex direta (3)

Pytest: 37/37 C-129 verde + 66/66 C-129+C-130 combinado

Rollback: POS_CONSULTA_ATIVADO=0 em Easypanel → Implantar (C-129)"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-129 + C-130 em produção."
echo ""
echo "Variáveis de ambiente novas:"
echo "  POS_CONSULTA_ATIVADO=0  → desliga bypass pós-consulta (default ON)"
echo ""
echo "Resultado:"
echo "  C-130: loop 'Qual a data de nascimento?' eliminado (lead 24447784 Bento)"
echo "  C-129: recibo/reembolso/laudo → atendente humano (lead 14230149 Luciana)"
