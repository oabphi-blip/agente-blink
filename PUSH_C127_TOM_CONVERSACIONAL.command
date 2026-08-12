#!/bin/bash
# C-127 — Tom conversacional (12/08/2026)
# Fix 1: message_splitter — chunks com delay
# Fix 2: anti-repetição universal no bypass chain
# Fix 3: _escuta_universal — prova de escuta nos bypasses de valor e convênio
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-127 + C-126 + C-125 + C-123 ==="
python3 -m pytest \
  tests/test_bug_c127_tom_conversacional.py \
  tests/test_bug_c126_convenio_loop_e_atendente.py \
  tests/test_bug_c125_prova_escuta_uma_pergunta.py \
  tests/test_bug_c123_convenio_recusado.py \
  -v --tb=short

echo ""
echo "=== Commit C-127 ==="
git add \
  voice_agent/blindagens_deterministicas.py \
  voice_agent/message_splitter.py \
  voice_agent/pipeline.py \
  tests/test_bug_c127_tom_conversacional.py \
  CLAUDE.md
git add -f PUSH_C127_TOM_CONVERSACIONAL.command

git commit -m "feat(C-127): tom conversacional — split + anti-repetição + prova de escuta

Fix 1 — voice_agent/message_splitter.py (NOVO):
  - split_message(): divide textos longos em 2-3 partes naturais
  - Protege blocos 1️⃣/2️⃣ (menu nunca é cortado no meio)
  - send_split(): wrapper com delay=1.2s entre chunks
  - Toggle: MESSAGE_SPLIT_ENABLED=0 desliga (default ON)
  - Plugado em pipeline.py: Evolution send usa send_split

Fix 2 — tentar_bypass_deterministico() anti-repetição:
  - Closure _repete_ultima_outbound(): overlap >= 70% → suprime bypass
  - Aplicado em: faq_endereco, faq_especialidade, faq_convenio, objecao, valor,
    endereco_pos_agenda, sinal_c114, dados_pendentes_c120
  - NUNCA suprime: aceite_slot, escolha_convenio_c123, cancelamento_24h,
    desistencia, urgencia, comprovante_pix_c116, sinal_noshow

Fix 3 — _escuta_universal() + injeção em bypasses:
  - _escuta_universal(user_text, ctx): extrai filho/bebê/convênio/unidade
    mencionados pelo paciente que ainda não estão em ctx.known
    → retorna 'Anotado — filho de 7 meses!' ou ''
  - deve_responder_valor(): abertura += escuta antes de 'Olá, {nome}'
  - _montar_recusa_convenio(escuta_pfx=...): prova de escuta antes do
    'processo de credenciamento'
  - Callers em deve_responder_faq_convenio_aceito() passam escuta

Pytest: 32/32 C-127 verde

Rollback:
  - MESSAGE_SPLIT_ENABLED=0 em Easypanel → Implantar (desliga Fix 1)
  - Fix 2/3 sem toggle — revert deste commit"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-127 em produção."
echo ""
echo "Easypanel — variáveis opcionais:"
echo "  MESSAGE_SPLIT_ENABLED=1   (padrão ON — não precisa setar)"
echo "  MESSAGE_SPLIT_DELAY=1.2   (segundos entre chunks)"
echo ""
echo "Rollback Fix 1: MESSAGE_SPLIT_ENABLED=0 → Implantar"
