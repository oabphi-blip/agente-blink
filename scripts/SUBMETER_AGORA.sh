#!/bin/bash
# Submeter os 14 templates Blink ao Meta — em 1 comando.
# Uso:
#   chmod +x scripts/SUBMETER_AGORA.sh
#   ./scripts/SUBMETER_AGORA.sh
#
# O script usa o token já preenchido. Se quiser trocar, edite a linha export
# WHATSAPP_BUSINESS_TOKEN abaixo (ou exporte antes de rodar).

set -e

cd "$(dirname "$0")/.."

# 1) Token vai no env (não fica em string visível pro usuário rodar)
if [ -z "$WHATSAPP_BUSINESS_TOKEN" ]; then
    echo "ERRO: exporte WHATSAPP_BUSINESS_TOKEN antes de rodar."
    echo "Exemplo: export WHATSAPP_BUSINESS_TOKEN='EAA...' && ./scripts/SUBMETER_AGORA.sh"
    exit 1
fi

# 2) Descobre WABA_ID se não setado
if [ -z "$WABA_ID" ]; then
    echo "==> Descobrindo WABA_ID automaticamente..."
    python3 scripts/submit_meta_templates.py --discover
    echo
    echo "Copie o id do WABA Blink Oftalmologia da lista acima e rode:"
    echo "  export WABA_ID=<id>"
    echo "  ./scripts/SUBMETER_AGORA.sh"
    exit 0
fi

# 3) Lista o que já existe
echo "==> Templates já cadastrados no WABA $WABA_ID:"
python3 scripts/submit_meta_templates.py --list
echo

# 4) Submete os 14
echo "==> Submetendo os 14 templates..."
python3 scripts/submit_meta_templates.py

echo
echo "==> Pronto. Acompanhe aprovação em:"
echo "    https://business.facebook.com/wa/manage/message-templates/"
