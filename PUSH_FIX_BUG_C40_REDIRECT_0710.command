#!/bin/bash
# PUSH FIX Bug C-40 — Plugar redirect_0710 no webhook.py + re-escrever módulo
# que estava com sintaxe quebrada por auto-formatter.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  FIX Bug C-40 — Redirect 0710 PLUGADO no webhook"
echo "==============================================================="

# Sanity — syntax check antes de subir
echo ""
echo "→ Validando sintaxe..."
python3 -c "
import ast
for f in ['voice_agent/redirect_0710.py', 'voice_agent/webhook.py']:
    try:
        ast.parse(open(f).read())
        print(f'  ✓ {f}')
    except Exception as e:
        print(f'  ❌ {f}: {e}')
        import sys; sys.exit(1)
"

# Smoke do handler
echo ""
echo "→ Smoke direto handle_inbound_0710..."
python3 -c "
from voice_agent.redirect_0710 import handle_inbound_0710
r = handle_inbound_0710(phone='5561996630710', texto='oi', enabled=True)
assert r['sent'] is True, f'esperava sent=True, recebi {r}'
print(f'  ✓ Handler retorna: sent={r[\"sent\"]}, angulo={r[\"angulo\"]}')
"

# Status do git
echo ""
echo "→ Mudanças locais:"
git status -s voice_agent/redirect_0710.py voice_agent/webhook.py

echo ""
read -p "Pode commitar e fazer push? (y/N): " resp
if [ "$resp" != "y" ] && [ "$resp" != "Y" ]; then
    echo "Cancelado."
    exit 0
fi

# Commit + push
git add voice_agent/redirect_0710.py voice_agent/webhook.py PUSH_FIX_BUG_C40_REDIRECT_0710.command

git commit -m "fix(C-40): plugar handle_inbound_0710 no webhook + reescrever redirect_0710

PROBLEMA (descoberto 20/06/2026 ~15:30):
- voice_agent/redirect_0710.py tinha auto-formatter quebrado, SyntaxError
  em multiplas funcoes. Nunca compilou em prod.
- handle_inbound_0710 nunca foi chamado pelo webhook.py.
- As 3 envs (REDIRECT_0710_ENABLED, REDIRECT_0710_ROTEAR_HANDLER,
  REDIRECT_0710_LINK_8133) nao eram lidas em lugar nenhum.
- Resultado: lead 24169428 (Fabio Philipe) escreveu no 0710 e Lia nao
  respondeu nem migrou — fluxo velho \_aviso_unificacao_se_novo nao
  disparava porque ja havia dedup persistente (180 dias).

FIX em 2 arquivos:

1. voice_agent/redirect_0710.py — re-escrito do zero:
   - Sintaxe limpa, 100% compila
   - Logica simplificada (MVP sem LLM): toggle enabled + dedup Redis +
     fallback fixo com link _LINK_OFICIAL
   - Dedup 7 dias separado do fluxo velho (180 dias)
   - Cap 3 turnos/dia + escalacao automatica
   - Helpers de etapa inativa, metricas, nota Kommo de auditoria

2. voice_agent/webhook.py — plug gate before fluxo velho:
   - Le REDIRECT_0710_ROTEAR_HANDLER
   - Quando =1, chama handle_inbound_0710 e retorna EARLY
   - Patch dinamico de _LINK_OFICIAL via env REDIRECT_0710_LINK_8133
     (corrige link hardcoded errado 556181331005 → 5561981331005)
   - Fluxo velho mantido como fallback se flag != 1

ENVS REQUERIDAS (ja setadas em prod):
  REDIRECT_0710_ENABLED=1
  REDIRECT_0710_ROTEAR_HANDLER=1
  REDIRECT_0710_LINK_8133=https://wa.me/5561981331005

VALIDACAO:
- ast.parse OK em ambos arquivos
- Smoke direto: handle_inbound_0710 retorna sent=True
- Resta: testar mensagem real no celular pelo 0710

PRoxIMO PASSO: aguardar Easypanel auto-deploy + mandar 'oi' do celular
pro 0710.

🤖 Generated with Claude Cowork — Fix critico Bug C-40"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel deve auto-deploy em ~60s."
echo "==============================================================="
echo ""
echo "PROXIMO PASSO:"
echo "  1. Aguardar Easypanel build (~90s)"
echo "  2. Pega seu celular e manda 'oi' pro 0710"
echo "     (+55 61 99683-0710)"
echo "  3. Espera ~10s — deve chegar mensagem com link wa.me/5561981331005"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
