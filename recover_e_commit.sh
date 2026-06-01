#!/bin/bash
# ============================================================
# Recovery: as mudanças do fix retrocesso foram pro git stash.
# Este script aplica o stash, valida, e faz commit + push.
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

echo "📋 Stashes disponíveis:"
git stash list | head -5
echo ""

echo "♻️  Aplicando o stash mais recente (stash@{0})..."
git stash pop stash@{0} || {
    echo "⚠️ pop falhou. Talvez já foi aplicado. Vou continuar."
}
echo ""

echo "🔍 Verificando se as mudanças do fix estão nos arquivos:"
KOMMO_OK=$(grep -c "FIELD_DIA_CONSULTA_1" voice_agent/kommo.py 2>/dev/null || echo "0")
RESPONDER_OK=$(grep -c "_viola_oferta_agenda" voice_agent/responder.py 2>/dev/null || echo "0")
echo "   kommo.py FIELD_DIA_CONSULTA_1: $KOMMO_OK match(es)"
echo "   responder.py _viola_oferta_agenda: $RESPONDER_OK match(es)"

if [[ "$KOMMO_OK" == "0" ]] || [[ "$RESPONDER_OK" == "0" ]]; then
    echo ""
    echo "❌ As mudanças NÃO foram recuperadas do stash. Algo está errado."
    echo "Vou listar todos os stashes pra investigarmos manualmente:"
    git stash list
    exit 1
fi
echo "✅ Mudanças recuperadas com sucesso"
echo ""

echo "📊 Status dos arquivos:"
git status --short
echo ""

echo "📋 Diff resumido:"
git diff --stat
echo ""

read -p "Confirma o commit + push? (s/N): " CONFIRM
if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
    echo "❌ Cancelado. Mudanças continuam aplicadas no working tree."
    exit 0
fi

git add voice_agent/kommo.py voice_agent/responder.py

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

git remote set-url origin "$CLEAN_URL" 2>/dev/null || true

echo ""
echo "✅ ✅ ✅  PUSH CONCLUÍDO!"
echo "Easypanel redeploya em ~1 min."
