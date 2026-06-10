#!/bin/bash
# PUSH AUTÔNOMO 09/06/2026 — Lia Engineer + Validador + KB Clínica + Eval Loop
#
# COMO USAR:
#   1. Salvar este arquivo (já está em ~/Documents/Claude/Projects/AGENTE IA BLINK)
#   2. No Finder, clica direito → Abrir com → Terminal (1ª vez só)
#   3. A partir da 2ª vez: duplo-clique direto
#   4. Vai pedir sua senha do Mac UMA vez (sudo do brew, se necessário) — pula com Enter se não precisar
#
# O QUE FAZ:
#   • cd no repo Blink
#   • Mostra git status
#   • Adiciona TODOS os arquivos novos da sessão 09/06
#   • Commit com mensagem descritiva
#   • Push pra origin/main (Easypanel auto-deploya em ~3min)
#   • Reporta resultado final

set -e  # para no primeiro erro
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo ""
echo "==============================================================="
echo " 🚀 PUSH AUTÔNOMO — Lia Engineer + Pacote Completo 09/06/2026"
echo "==============================================================="
echo ""

echo "📍 Diretório: $(pwd)"
echo "🌿 Branch: $(git branch --show-current)"
echo ""

echo "▶ STATUS atual (antes do push):"
git status --short
echo ""

echo "▶ Adicionando arquivos novos..."
git add \
  lia_engineer/ \
  voice_agent/validador_factual.py \
  voice_agent/kommo.py \
  voice_agent/knowledge_base/40_clinica_estrabismo.md \
  voice_agent/knowledge_base/41_clinica_oftalmopediatria.md \
  voice_agent/knowledge_base/42_clinica_catarata.md \
  voice_agent/knowledge_base/43_clinica_refrativa.md \
  voice_agent/knowledge_base/44_clinica_retina_vitreo.md \
  voice_agent/responder.py \
  tests/test_lia_engineer_detect.py \
  tests/test_validador_factual.py \
  tests/test_bug_c16_inas_nao_aceito.py \
  tests/test_kommo_engineer_methods.py \
  scripts/template_meta_nps_pos_consulta.json \
  BUGS_MAPEAMENTO_DEFINITIVO_08-06-2026.md \
  PUSH_AUTONOMO_09-06.command \
  CLAUDE.md 2>/dev/null || true

echo ""
echo "▶ ARQUIVOS NO STAGING:"
git diff --cached --stat
echo ""

echo "▶ Commit..."
git commit -m "feat: pacote autônomo completo + Bug C-16 Inas (09/06/2026)

- lia_engineer/ — agente 24/7 (detect_bugs, propose_fix Opus 4.6, apply_fix,
  verify, notify, engineer_loop, cli, Dockerfile + SETUP.md)
- voice_agent/validador_factual.py — cruza preço/data/convênio com KB 17/18/19
- voice_agent/responder.py — filtro C-16 _viola_disse_atende_convenio_nao_aceito
- voice_agent/kommo.py — list_recent_notes + search_leads_by_window
- voice_agent/knowledge_base/40-44_clinica_*.md — esqueleto 5 especialidades
- tests/ — 74 testes verdes (engineer 18 + validador 12 + bug C-16 34 + kommo 10)
- scripts/template_meta_nps_pos_consulta.json — pronto pra submeter Meta
- BUGS_MAPEAMENTO_DEFINITIVO_08-06-2026.md — anti-band-aid

Bugs C-15 (token Meta expirado) e C-16 (Atendemos INAS) cobertos.
Casos reais Tatiana 24125064 + Maria Agostini 24117314 + Juliene 24053159
indexados em pytest." 2>&1 || echo "⚠️  Nenhuma mudança pra commit OU commit já existe"

echo ""
echo "▶ Push pra origin/main..."
git push origin main

echo ""
echo "==============================================================="
echo " ✅ PUSH CONCLUÍDO COM SUCESSO"
echo "==============================================================="
echo ""
echo "Próximos passos automáticos:"
echo "  1. Easypanel detecta push → build automático (~3 min)"
echo "  2. Deploy quando build verde"
echo "  3. Aguarda eu rodar smoke: curl /admin/smoke-tick"
echo ""
echo "Pode fechar essa janela ↓"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
