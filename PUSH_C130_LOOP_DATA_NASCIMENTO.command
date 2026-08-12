#!/bin/bash
# C-130 — Anti-loop pergunta data nascimento (12/08/2026)
# Fix duplo:
#   1. data_nascimento_ok() aceita "27/012/2024" (3 dígitos no mês)
#   2. _inbound_responde_ultima_pergunta_c130: quando paciente responde
#      a última pergunta de dado do C-125, retorna None → LLM extrai
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-130 + C-125 + master ==="
python3 -m pytest \
  tests/test_bug_c130_data_nasc_loop.py \
  tests/test_bug_c125_prova_escuta_uma_pergunta.py \
  -v --tb=short -q

echo ""
echo "=== Commit C-130 ==="
git add \
  voice_agent/blindagens_deterministicas.py \
  voice_agent/checklist_dados_minimos.py \
  tests/test_bug_c130_data_nasc_loop.py

git add -f PUSH_C130_LOOP_DATA_NASCIMENTO.command

git commit -m "fix(C-130): anti-loop pergunta data nascimento — 2 fixes

Fix duplo para loop 'Qual a data de nascimento?' (lead 24447784 Bento):

Fix 1 — checklist_dados_minimos.py::data_nascimento_ok():
  ANTES: regex r'^\d{1,2}/\d{1,2}/\d{2,4}$' rejeitava '27/012/2024'
         (3 dígitos no mês) → campo visto como pendente → C-125 perguntava de novo
  DEPOIS: regex leniente r'^\d{1,2}[/\-.]\d{1,4}[/\-.]\d{2,4}$'
          aceita typos de mês (012, 01, 1) — validação estrita fica no Medware

Fix 2 — blindagens_deterministicas.py::deve_perguntar_dados_pendentes():
  _inbound_responde_ultima_pergunta_c130(): detecta quando inbound
  responde à última pergunta C-125 (data/CPF/nome/convênio) →
  retorna None → LLM extrai com tolerância a typos, sem C-125 interceptar

Regex C-130:
  _RE_DATA_RESP_C130: casa 27/012/2024, 27/12/2024, 2024-12-27, 12-27-2024
  _RE_ULTIMA_PERGUNTOU_DATA_C130: detecta 'data de nascimento' no outbound

Pytest: 27/27 C-130 verde, 69/69 C-130+C-125 combinado verde

Rollback: sem toggle — revert commit se necessário"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-130 em produção."
echo ""
echo "Sem variáveis de ambiente novas."
echo "Resultado: loop 'Qual a data de nascimento?' eliminado (lead 24447784 Bento)"
