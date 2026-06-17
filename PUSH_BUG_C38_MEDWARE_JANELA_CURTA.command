#!/bin/bash
# Bug C-38 — Reduzir janela default Medware 90 → 21 dias.
#
# Causa raiz (diagnóstico LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md):
# Medware VM Light estoura ReadTimeout em janela de 90 dias.
# Janela de 7 dias = ok. 90 dias = timeout SQL sem índice adequado.
#
# Resultado em prod: ctx.agenda=[] → filtro C-30A escala
# "dificuldade técnica + encaminhar humano" (lead 24113652 hoje 22:08).
#
# Fix:
# - voice_agent/medware.py linha 660: dias default 90 → 21
# - env MEDWARE_DIAS_DEFAULT (1-90) override pra ajustar sem deploy
# - janela_fonte reflete o número real

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH BUG C-38 — Medware janela default 90→21d"
echo "==============================================================="
echo ""

# Sanity check
grep -q "dias: int = 21" voice_agent/medware.py \
    || { echo "ERRO: fix não está em medware.py"; exit 1; }
grep -q "MEDWARE_DIAS_DEFAULT" voice_agent/medware.py \
    || { echo "ERRO: env override não está em medware.py"; exit 1; }
test -f tests/test_bug_c38_medware_janela_curta.py \
    || { echo "ERRO: pytest faltando"; exit 1; }
python3 -c "import ast; ast.parse(open('voice_agent/medware.py').read())" \
    || { echo "ERRO: syntax error em medware.py"; exit 1; }

echo "✓ Sanity check OK"
echo ""

# Roda pytest local (no Mac do Fábio não tem deadlock iCloud)
echo "→ Rodando pytest local..."
python3 -m pytest tests/test_bug_c38_medware_janela_curta.py -v 2>&1 | tail -20
echo ""

read -p "Pytest passou? Pressiona ENTER pra continuar push, Ctrl+C pra abortar: "

# Git
git add voice_agent/medware.py \
        tests/test_bug_c38_medware_janela_curta.py \
        PUSH_BUG_C38_MEDWARE_JANELA_CURTA.command \
        LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md 2>/dev/null || true

git diff --staged --stat
echo ""

git commit -m "fix(C-38): Medware janela default 90→21d — causa raiz hesitacao prod

Origem: diagnostico LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md
(coletado 17/06 10h via httpx contra endpoint real Medware).

Causa raiz confirmada com medicao:
- GET /Medware/Horarios/Listar 7 dias  -> HTTP 200 ~5s (ok)
- GET /Medware/Horarios/Listar 90 dias -> ReadTimeout (estouro)

Servidor Medware roda 'Versao Light' em VM Windows/IIS/SQL Server
sem indice adequado em (dataInicio, dataFim, codMedico, codUnidade).
Janela longa = table scan = CPU 100% = timeout cliente.

Impacto em producao:
- ctx.agenda=[] quando janela default 90d estoura
- Filtro C-30A dispara: 'dificuldade tecnica + encaminhar humano'
- Lead 24113652 (Fabio testando hoje 22:08 BRT): essa frase exata.
- Padrao C-30A repetiu 5x entre 21:45 e 22:08 BRT.

Fix:
1. voice_agent/medware.py::horarios_para_agente
   - dias: int = 21 (era 90)
   - env MEDWARE_DIAS_DEFAULT override (1-90)
   - janela_fonte reflete numero real (default_21d, etc.)
   - Mantida compat retroativa (param dias= explicito, data_inicio/fim)

2. tests/test_bug_c38_medware_janela_curta.py — 9 cenarios
   - Default 21d (nao 90)
   - Env override 30d
   - Env override 90d (rollback path)
   - Env invalida (0, >90, lixo) cai pro default 21
   - Preferencia paciente vence default (compat C-30)
   - Param dias= explicito ainda funciona

3. Documento de diagnostico LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md
   versionado como evidencia tecnica.

Rollback sem revert:
- Set env MEDWARE_DIAS_DEFAULT=90 no Easypanel — volta ao default antigo.

Impacto positivo esperado:
- Janela 21d cabe no tempo de resposta da VM Light
- Pacientes que pedem 'segunda-feira' tipicamente querem proxima
  segunda (dentro de 14d, coberto pela janela)
- Reduz frequencia do filtro C-30A em ~90% (estimativa)
- Reduz carga CPU no Medware: requests menos pesados

Nao resolve:
- Pacientes que pedem agendamento 30-90 dias a frente. Esses caem no
  fluxo de preferencia (C-30) que aceita data_inicio/fim explicitos
  via janela_preferencia.py. Sem preferencia explicita = 21d.

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
echo "VALIDACAO POS-DEPLOY:"
echo "  1. Aguarde 3min."
echo "  2. Manda 'oi' pelo WhatsApp do paciente teste."
echo "  3. Esperado: Lia oferece 2 slots concretos SEM 'deixa eu consultar'."
echo "  4. Grep logs Easypanel: '[MEDWARE REQ]' deve mostrar janela ~21d."
echo ""
echo "ROLLBACK (se algo der errado):"
echo "  Easypanel -> blink/agent -> Ambiente -> MEDWARE_DIAS_DEFAULT=90"
echo "  Implantar. Janela volta ao default antigo."
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
