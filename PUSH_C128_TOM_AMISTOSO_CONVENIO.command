#!/bin/bash
# C-128 — Tom amistoso em _montar_recusa_convenio (12/08/2026)
# Nome do contato + nome do paciente + "incentivos especiais" + ordem invertida
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-128 + C-127 ==="
python3 -m pytest \
  tests/test_bug_c123_convenio_recusado.py \
  tests/test_bug_c127_tom_conversacional.py \
  -v --tb=short

echo ""
echo "=== Commit C-128 ==="
git add \
  voice_agent/blindagens_deterministicas.py \
  tests/test_bug_c123_convenio_recusado.py \
  CLAUDE.md
git add -f PUSH_C128_TOM_AMISTOSO_CONVENIO.command

git commit -m "feat(C-128): tom amistoso em _montar_recusa_convenio — nome + empatia + ordem invertida

Upgrade _montar_recusa_convenio() em blindagens_deterministicas.py:

Mudanças C-128:
  - Abertura: 'Entendi, {nome_contato}.' quando nome disponível
  - Referência ao paciente: 'não quero deixar o {nome_paciente} sem solução'
    (ou 'você' quando sem ctx.known.nome_paciente)
  - 'incentivos especiais' substitui 'condições diferenciadas'
  - 'Como prefere seguir?' substitui 'Qual a sua preferência?'
  - ORDEM INVERTIDA: 1️⃣ Seguir sem convênio / 2️⃣ Somente com convênio
    (conversão positiva agora em primeiro)

Regex atualizadas:
  - _RE_ESCOLHA_SEM_CONVENIO_C123: 1️⃣/1 agora = Seguir sem convênio
  - _RE_ESCOLHA_SO_CONVENIO_C123: 2️⃣/2 agora = Somente com convênio
  - _ultima_msg_era_recusa_convenio: regex em vez de exact match
    (backward compat com leads mid-conversation no formato antigo)

Caso real: lead 24446300 Juliene/Daniel/Amil
  Saída: 'Entendi, Juliene. O **Amil** ainda não está credenciado...
          Mas não quero deixar o Daniel sem solução — temos incentivos
          especiais... Como prefere seguir?
          1️⃣ Seguir sem convênio
          2️⃣ Somente com convênio'

Pytest: 57/57 C-123 verde + 32/32 C-127 verde

Rollback: revert deste commit (sem toggle separado)"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-128 em produção."
echo ""
echo "Sem variáveis de ambiente novas. Rollback = revert commit."
