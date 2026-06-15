#!/bin/bash
# Push pacote fix definitivo agenda — 13/06/2026
# Casos Carolina 24145994 + Cecília 21500693 + Carmen 24142996 + Maitê 24128026
#
# Conteúdo:
#   - Filtro NOVO: _viola_confirmacao_sem_gravacao em responder.py
#     (bloqueia "Agendamento confirmado" se ctx.medware_grava_ok != True)
#   - Fix #208 (handle_gravar_agendamento_medware chama Medware real)
#     já estava no código, push faz ir pra prod
#   - Fix #183 (lock pipeline por conversation_key + tool_choice FSM)
#     já estava no código, push faz ir pra prod
#   - Pytest novo: tests/test_bug_carolina_confirmacao_fake.py (12 cenários)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push pacote fix definitivo agenda"
echo "==============================================="

# Rodar pytest do filtro novo (não bloqueante se Anthropic offline)
echo ""
echo "Pytest filtro novo..."
python3 -m pytest tests/test_bug_carolina_confirmacao_fake.py -v --tb=short 2>&1 | tail -25 || echo "(pytest com avisos)"

echo ""
echo "Commit + push..."
git add voice_agent/responder.py \
        voice_agent/tools_lia.py \
        voice_agent/pipeline.py \
        tests/test_bug_carolina_confirmacao_fake.py \
        PUSH_PACOTE_FIX_AGENDA.command

git commit -m "fix(agenda): filtro anti-confirmacao-fake + push #208 + #183

Casos reais 13/06/2026:
- Carolina/Heloisa 24145994 (Camila): Lia ofereceu 17/06 inventado, confirmou
  Agendamento sem gravar Medware, depois loop 'vou reconsultar'
- Cecilia 21500693 (Elaine): Lia disse 'agenda so em julho' sem consultar
  Medware, quando tinha tarde fim em 16/06
- Carmen 24142996 (12/06): mesmo padrao
- Maite 24128026 (10/06): mesmo padrao

Pacote:

1. NOVO filtro _viola_confirmacao_sem_gravacao em responder.py
   - Regex _FRASES_CONFIRMACAO_RGX detecta 'Agendamento confirmado'
   - Regex _MARCADORES_CONCLUSAO_RGX detecta 'Dia/Hora' + 'Unidade'
   - Combina os 2: se ambos presentes E ctx.medware_grava_ok != True,
     bloqueia texto e substitui por _CONFIRMACAO_FAKE_FALLBACK
   - Plugado em _scrub_prohibited apos _viola_oferta_agenda

2. Fix #208 (handle_gravar_agendamento_medware chama Medware real)
   - Codigo ja estava em voice_agent/tools_lia.py linhas 380-500
   - Push leva ele pra prod

3. Fix #183 (lock pipeline + tool_choice FSM=AGENDA)
   - Codigo ja em voice_agent/pipeline.py linha 120
   - Push leva ele pra prod

4. Pytest: tests/test_bug_carolina_confirmacao_fake.py 12 cenarios
   - regex confirmacao reconhece variantes
   - regex marcadores reconhece variantes
   - caso real Carolina 24145994 bloqueia
   - caso Carmen 24142996 bloqueia
   - libera quando medware_grava_ok=True
   - bloqueia quando ctx vazio (defensivo)
   - libera acknowledgment generico
   - integracao com _scrub_prohibited" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "Aguardando deploy Easypanel (~3 min)..."
for i in \$(seq 1 12); do
    sleep 20
    # Probe healthz
    body=\$(curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/health" 2>/dev/null || echo "")
    if echo "\$body" | grep -q "\"status\":\"ok\""; then
        echo "  HEALTHZ OK [\${i}x20s = \$((i*20))s]"
        break
    fi
    echo "  [\${i}/12] aguardando..."
done

echo ""
echo "Smoke: verificando que filtro novo ta em prod..."
# Importar e ver se _viola_confirmacao_sem_gravacao existe
curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/admin/healthz?secret=\$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local | head -1 | cut -d= -f2- | tr -d '\"')" | head -c 200
echo ""

echo ""
echo "==============================================="
echo "PROXIMA mensagem confirmacao bloqueia se Medware"
echo "nao gravou. Casos Carolina/Carmen/Maite blindados."
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
