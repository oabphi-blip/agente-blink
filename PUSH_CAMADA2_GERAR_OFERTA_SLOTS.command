#!/bin/bash
# Camada 2 — Endpoint /admin/gerar-oferta-slots/{lead_id}
#
# Substitui o ciclo Cowork manual. Lê lead Kommo, identifica
# médico+unidade+preferência, bate Medware janela curta (7d, fail-fast),
# retorna 2 slots ordenados + mensagem canônica 1️⃣/2️⃣ pronta +
# opcionalmente posta nota no próprio lead.
#
# Vive 24h no agent do Easypanel — atendente humana usa direto.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH CAMADA 2 — /admin/gerar-oferta-slots/{lead_id}"
echo "==============================================================="

# Sanity
test -f voice_agent/gerar_oferta_slots.py \
    || { echo "ERRO: gerar_oferta_slots.py faltando"; exit 1; }
test -f tests/test_gerar_oferta_slots.py \
    || { echo "ERRO: pytest faltando"; exit 1; }

grep -q "/admin/gerar-oferta-slots" voice_agent/webhook.py \
    || { echo "ERRO: endpoint não está em webhook.py"; exit 1; }

python3 -c "
import ast
for f in [
    'voice_agent/gerar_oferta_slots.py',
    'voice_agent/webhook.py',
    'tests/test_gerar_oferta_slots.py',
]:
    ast.parse(open(f).read())
print('syntax OK')
" || { echo "ERRO syntax"; exit 1; }

echo "✓ Sanity OK"
echo ""

# Rodar pytest local
echo "→ Rodando pytest local..."
python3 -m pytest tests/test_gerar_oferta_slots.py -v 2>&1 | tail -40
echo ""
read -p "Pytest passou? ENTER pra commit/push, Ctrl+C aborta: "

# Git
git add voice_agent/gerar_oferta_slots.py \
        voice_agent/webhook.py \
        tests/test_gerar_oferta_slots.py \
        PUSH_CAMADA2_GERAR_OFERTA_SLOTS.command \
        Como_Incluir_Agenda_Medware_no_Claude_Cowork.docx

git diff --staged --stat
echo ""

git commit -m "feat(camada-2): endpoint /admin/gerar-oferta-slots/{lead_id}

Camada 2 do plano Cowork — destrava operação 24h sem depender
da Lia em prod funcionar 100%.

Lê lead Kommo (1.NOME PACIENTE + MEDICOS + UNIDADE +
DIA/TURNO/PERIODO ⚠️), parsea preferência (dia + turno + período),
bate Medware com janela curta (7d, fail-fast — sem timeout),
filtra slots por preferência (manhã/tarde, início/meio/fim),
seleciona 2 slots + monta mensagem canônica 1️⃣/2️⃣ pronta pra
colar no WhatsApp. Opcionalmente posta como nota no próprio lead.

Endpoint REST autenticado (secret) — atendente humana abre
WhatsApp do paciente, chama o endpoint, cola a mensagem.
Funciona enquanto fix arquitetural (LangChain) não chega.

USO:
  curl -X POST 'https://blink-agent.6prkfn.easypanel.host/admin/gerar-oferta-slots/24113652?secret=\$WEBHOOK_SECRET&postar_nota=true'

  → {
      'ok': true,
      'paciente': 'Fábio Philipe Costa Martins',
      'medico': 'Dra. Karla Delalíbera',
      'unidade': 'Asa Norte',
      'preferencia': {'descritivo': 'segunda-feira manhã início', ...},
      'slots': [
        {'data': '29/06', 'dia_semana': 'segunda-feira', 'hora': '09:00',
         'codAgenda': 4, 'codMedico': 12080, 'codUnidade': 5},
        {'data': '29/06', 'dia_semana': 'segunda-feira', 'hora': '09:30', ...}
      ],
      'mensagem_pronta': 'Fábio! Os horários disponíveis com a Dra. Karla...',
      'nota_kommo_id': 28994700
    }

Query params:
  - postar_nota (default true) — grava como nota Kommo
  - janela_dias (1-14, default 7) — janela Medware
  - medico (opcional) — força médico, ignora ctx do lead
  - unidade (opcional) — força unidade

Estratégia de fallback se preferência não retorna slots:
  filtrados < 2 → relaxa pra lista sem filtro de preferência
  filtrados = 0 → retorna primeiros slots disponíveis na janela

Pytest tests/test_gerar_oferta_slots.py — 21 cenários:
  - Parser preferência (5 variantes)
  - Filtro dia/turno/período (4)
  - Seleção 2 slots com fallback (3)
  - Formatação (2)
  - Mensagem canônica (2)
  - Helpers (3)
  - Integração mock end-to-end (7)

Inclui documento Word com proposta de 4 camadas:
Como_Incluir_Agenda_Medware_no_Claude_Cowork.docx

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
echo "VALIDACAO POS-DEPLOY (rodar daqui ~3min):"
echo ""
echo "  curl -X POST 'https://blink-agent.6prkfn.easypanel.host/admin/gerar-oferta-slots/24113652?secret=\$WEBHOOK_SECRET&postar_nota=false' | jq"
echo ""
echo "  Espera ver: ok=true, slots=[2 itens], mensagem_pronta com 1️⃣ e 2️⃣."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
