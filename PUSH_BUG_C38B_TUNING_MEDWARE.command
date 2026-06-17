#!/bin/bash
# Bug C-38b — Tuning do cliente Medware (17/06/2026, sugestão consultor).
#
# 3 ajustes determinísticos no voice_agent/medware.py (não é regex/prompt):
#   1. dias default 21 → 14 (janela ainda mais curta = menos timeout)
#   2. timeout httpx default 12s → 20s (dá margem antes do retry amplificar)
#   3. max_retries default 3 → 1 (fail-fast, não congestiona VM lenta)
#
# 3 envs override (ajuste sem deploy):
#   - MEDWARE_DIAS_DEFAULT (1-90)
#   - MEDWARE_TIMEOUT_S (5-60)
#   - MEDWARE_MAX_RETRIES (1-5)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH BUG C-38b — Tuning Medware (janela/timeout/retry)"
echo "==============================================================="

# Sanity
grep -q "dias: int = 14" voice_agent/medware.py \
    || { echo "ERRO: janela 14d não aplicada"; exit 1; }
grep -q "max_retries: int = 1" voice_agent/medware.py \
    || { echo "ERRO: max_retries 1 não aplicado"; exit 1; }
grep -q "timeout: float = 20.0" voice_agent/medware.py \
    || { echo "ERRO: timeout 20s não aplicado"; exit 1; }
grep -q "MEDWARE_MAX_RETRIES" voice_agent/medware.py \
    || { echo "ERRO: env override MAX_RETRIES não aplicado"; exit 1; }
grep -q "MEDWARE_TIMEOUT_S" voice_agent/medware.py \
    || { echo "ERRO: env override TIMEOUT_S não aplicado"; exit 1; }
python3 -c "import ast; ast.parse(open('voice_agent/medware.py').read())" \
    || { echo "ERRO: syntax"; exit 1; }

echo "✓ Sanity OK"
echo ""

git add voice_agent/medware.py PUSH_BUG_C38B_TUNING_MEDWARE.command

git diff --staged --stat
echo ""

git commit -m "fix(C-38b): tuning Medware client — janela 21->14d, timeout 12->20s, retry 3->1 fail-fast

Sugestao do consultor (17/06/2026 noite) baseada no diagnostico
LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md.

Causa raiz: VM Medware Light com SQL sem indice. Janela longa estoura
timeout. Retry agressivo amplifica congestionamento. Fix C-38 (janela
21d) ainda nao foi suficiente — lead 24113652 hesitou pos-deploy.

3 ajustes deterministicos em voice_agent/medware.py:

1. horarios_para_agente(dias=21) → dias=14
   Janela ainda mais curta. Cobre 2 semanas (Karla atende 9 dias
   nesse intervalo na Asa Norte = ~108 slots tipicos). Pacientes que
   pedem fora dessa janela ja caem no parser de preferencia (C-30).

2. MedwareClient(timeout=12.0) → timeout=20.0
   12s nao da margem pra query SQL pesada completar antes de
   ReadTimeout do cliente. 20s permite janela mais longa concluir
   sem cliente abortar a meio caminho.

3. horarios_para_agente(max_retries=3) → max_retries=1
   Fail-fast quando VM esta lenta. 3 retries com backoff 0.5s/1s/2s
   amplificavam o congestionamento (Medware ja estava lento, 3 hits
   seguidos pioravam). Retorno [] dispara filtro C-30A que escala
   humano — proxima mensagem do paciente vem em ctx limpo.

3 envs override (rollback sem deploy):
- MEDWARE_DIAS_DEFAULT (1-90) — janela. Volta 90 se SQL consertar.
- MEDWARE_TIMEOUT_S (5-60) — timeout httpx.
- MEDWARE_MAX_RETRIES (1-5) — agressividade do retry.

Mantida compat retroativa: param explicito dias/max_retries no chamado
ainda funciona; data_inicio/data_fim explicitos (preferencia C-30)
seguem vencendo o default.

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
echo "ROLLBACK (sem revert de codigo):"
echo "  Easypanel → blink/agent → Ambiente, setar:"
echo "  - MEDWARE_DIAS_DEFAULT=21  (volta janela 21d)"
echo "  - MEDWARE_TIMEOUT_S=12     (volta timeout 12s)"
echo "  - MEDWARE_MAX_RETRIES=3    (volta retry agressivo)"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
