#!/bin/bash
# Push Bug C-24a REVISADO — só 4 etapas inativas (Fábio 11/06 13:40)
# Atendimento Humano, Cirurgias, Lentes, Fornecedores
# Demais (REALIZADO, PRÓXIMA, Closed-won/lost) mantêm IA ativa.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push C-24a revisado — só 4 etapas inativas"
echo "==============================================="

git add CLAUDE.md voice_agent/webhook.py PUSH_BUG_C24_REVISADO.command
git commit -m "fix(bug-c24a-rev): restringir _STATUS_INATIVOS_IA a 4 etapas

Fábio 11/06/2026 13:40 BRT — Lista revisada de etapas que desativam IA
automaticamente quando lead entra. Apenas:

  • 106563343 - 1-ATENDIMENTO HUMANO
  • 106157139 - 10-CIRURGIAS ANDAMENTO
  • 106484343 - 11-LENTES ANDAMENTO
  • 106484347 - 12-FORNECEDORES

Demais etapas (8-REALIZADO CONSULTA, 09-PRÓXIMA CONSULTA, Closed-won 142,
Closed-lost 143) MANTÊM IA ATIVADA porque Lia faz follow-up, NPS e
reativação nessas etapas.

webhook.py também adiciona essas 4 etapas (REALIZADO, PRÓXIMA, Closed-won,
Closed-lost) ao set _STATUS_ATIVOS_IA pra que webhook Kommo dispare
reativação automática quando lead voltar pra elas." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo. Deploy Easypanel ~3 min."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
