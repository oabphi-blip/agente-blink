#!/bin/bash
# ============================================================
# Commit: fix retrocesso (ja_agendado) + fix "fake agenda lookup"
# Bugs resolvidos:
#  - Lead Aurora (23907418): Lia perguntou "qual dia da semana" 5x
#    pra paciente com consulta JÁ MARCADA pra hoje.
#  - Lead Fábio (24033913): Lia disse "Um momentinho..." sem
#    apresentar slots.
#
# Arquivos modificados:
#  1. voice_agent/kommo.py
#     - FIELD_DIA_CONSULTA_1 = 1255723
#     - get_caller_context_by_lead extrai dia_consulta_ts +
#       seta ja_agendado=True se consulta é hoje/futuro
#  2. voice_agent/responder.py
#     - _agenda_block reforçado (frases proibidas listadas)
#     - _caller_context_block alerta ja_agendado mostra DATA exata
#     - _scrub_prohibited detecta "fake agenda lookup" e substitui
#     - _viola_oferta_agenda nova função detectora
#
# Uso: bash commit_fix_retrocesso_e_agenda.sh
# ============================================================
set -e

REPO_DIR="$HOME/Documents/Claude/Projects/AGENTE IA BLINK"
TOKEN="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"
USERNAME="oabphi-blip"
AUTH_URL="https://${USERNAME}:${TOKEN}@github.com/oabphi-blip/agente-blink.git"
CLEAN_URL="https://github.com/oabphi-blip/agente-blink.git"

cd "$REPO_DIR"
echo "📁 Diretório: $(pwd)"
echo ""

echo "📦 Stash de scripts auxiliares (se houver)..."
git stash -u || echo "   (nada pra guardar)"
echo ""

echo "⬇️  Pull --rebase do remote..."
git pull --rebase "$AUTH_URL" main || {
  echo "⚠️ Conflito ou erro no pull --rebase. Resolva e rode 'git rebase --continue', depois rode este script novamente."
  exit 1
}
echo ""

FILES=(
    "voice_agent/kommo.py"
    "voice_agent/responder.py"
)
echo "📋 Verificando arquivos..."
for f in "${FILES[@]}"; do
    [[ -f "$f" ]] && echo "   ✅ $f" || { echo "   ❌ FALTA: $f"; exit 1; }
done
echo ""

echo "📦 Stage..."
git add "${FILES[@]}"
echo ""
echo "📊 Diff resumido:"
git diff --cached --stat
echo ""

read -p "Confirma o commit? (s/N): " CONFIRM
if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
    echo "❌ Cancelado. 'git reset' pra desfazer o stage se quiser."
    exit 0
fi

git commit -m "fix(lia): retrocesso ja_agendado + fake agenda lookup

kommo.py:
- FIELD_DIA_CONSULTA_1=1255723 mapeado
- get_caller_context_by_lead extrai dia_consulta_ts do campo
  1.DIA CONSULTA do Kommo
- ja_agendado=True quando dia_consulta_ts é hoje ou futuro
  (camada 2 além do status_id) — protege casos como lead Aurora
  (23907418) que tinha consulta marcada pra hoje mas status
  ainda em 2-AGENDAR

responder.py:
- _agenda_block reforçado: lista frases proibidas explicitamente
  ('deixa eu consultar', 'um momentinho', 'vou verificar',
  'estou sem acesso à agenda')
- _caller_context_block alerta ja_agendado agora mostra a DATA
  exata da consulta marcada e dá exemplo de boa resposta
- _viola_oferta_agenda + _FAKE_AGENDA_LOOKUP_FALLBACK: filtro
  pós-geração detecta quando Lia disse 'consultar agenda' tendo
  agenda real disponível e substitui por pergunta de preferência
- _scrub_prohibited agora recebe ctx pra ativar essa detecção

Origem: leads 23907418 (Aurora — retrocesso) e 24033913
(Fábio — Lia travou em 'Um momentinho' sem oferecer slots)"

echo ""
echo "🚀 Push..."
git push "$AUTH_URL" main

echo ""
git remote set-url origin "$CLEAN_URL" 2>/dev/null || true

echo "✅ ✅ ✅ PUSH CONCLUÍDO!"
echo ""
echo "Próximo: Easypanel detecta e faz redeploy em ~1 min."
echo "Validar no log: grep '\\[FILTRO\\] FAKE AGENDA' e grep 'ja_agendado=True por camada 2'"
