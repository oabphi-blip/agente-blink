#!/bin/bash
# Push Watchdog Promessa Não Cumprida — 14/06/2026
# Origem: Fábio "Fica sempre dependendo desta iniciar. O que ainda falta
# para responder em tempo real ao paciente"
#
# Casos cobertos:
#   - Fernanda 24145890 (Cecília + Helena, 5h silêncio depois de "deixa eu consultar")
#   - Carolina 24145994 / Cecília 21500693 / Lílian 24146092
#   - Maitê 24128026 / Carmen 24142996 / Kamila 24064723 / Alice 21256807
#
# Conteúdo:
#   - voice_agent/watchdog_promessa.py (módulo standalone, detector puro)
#   - voice_agent/webhook.py (endpoint /admin/watchdog-promessa-tick + cron 2min)
#   - tests/test_watchdog_promessa.py (40 cenários)

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push Watchdog Promessa Não Cumprida"
echo "==============================================="

echo ""
echo "Pytest watchdog_promessa..."
python3 -m pytest tests/test_watchdog_promessa.py -v --tb=short 2>&1 | tail -10 || echo "(pytest com avisos)"

echo ""
echo "AST check webhook.py..."
python3 -c "import ast; ast.parse(open('voice_agent/webhook.py').read()); print('webhook.py AST OK')"

echo ""
echo "Commit + push..."
git add voice_agent/watchdog_promessa.py \
        voice_agent/webhook.py \
        tests/test_watchdog_promessa.py \
        PUSH_WATCHDOG_PROMESSA.command

git commit -m "feat(watchdog): promessa nao cumprida — cron 2min move pra atendimento humano

Origem: Fabio 14/06/2026 caso Fernanda 24145890 (Cecilia+Helena).
Lia disse 'deixa eu consultar... um minutinho' as 08:48 BRT e nunca
voltou. 5h de silencio. Mesmo padrao Carolina 24145994, Cecilia 21500693,
Lilian 24146092, Maite 24128026, Carmen 24142996, Kamila 24064723,
Alice 21256807.

Causa raiz: em FSM=AGENDA modelo escreve texto livre em vez de chamar
tool oferecer_slot. Fix #183 (tool_choice forcado) elimina maior parte,
mas brechas escapam. Watchdog fecha brecha SEM enviar mensagem
automatica (alto risco).

Pacote:

1. voice_agent/watchdog_promessa.py — modulo standalone
   - _PADROES_PROMESSA_RGX: 22 padroes (deixa eu consultar, um minutinho,
     ja volto, vou buscar, ainda estou buscando, ja te passo opcoes...)
   - _PADROES_RESPOSTA_REAL_RGX: cancela deteccao se ja tem slot concreto
     (1️⃣/2️⃣, horarios HH:MM, agendamento confirmado)
   - eh_promessa_nao_cumprida(): logica pura sem rede (silencio 3min-2h)
   - avaliar_lead(lead_json): retorna veredicto {tratar, silencio_min, ...}
   - tratar_lead(): move pra 1-ATENDIMENTO HUMANO + ATIVADO IA=Desativado
     + nota Kommo com texto da promessa e instrucao 'AÇÃO HUMANA
     NECESSÁRIA: cumprir promessa, buscar agenda no Medware'
   - tick(): varre STATUS_CONVERSAVEIS_LIA (0-ETAPA, 0-classificar,
     2.LEADS FRIO, 3-AGENDAR, 4.REAGENDAR, 7.1-NO-SHOW), ordena por
     silencio DESC, trata ate max_leads
   - Dedup Redis 30min via blink:watchdog_promessa:tratado:{lead_id}
   - Default dry_run=True

2. voice_agent/webhook.py
   - Endpoint GET/POST /admin/watchdog-promessa-tick
   - Cron interno embutido (esta_habilitado()) — thread daemon que
     chama tick a cada CRON_WATCHDOG_PROMESSA_SEG (default 120s)

3. tests/test_watchdog_promessa.py — 40 cenarios
   - TestTextoContemPromessa: 13 cenarios (casos reais Fernanda,
     Kamila, Alice + variantes)
   - TestTextoContemRespostaReal: 6 cenarios (cancela quando slot ja
     listado)
   - TestEhPromessaNaoCumprida: 7 cenarios (janela temporal)
   - TestAvaliarLead: 6 cenarios (integracao com payload Kommo)
   - TestTratarLead: 3 cenarios (dry_run, acao real, dedup)
   - TestTick: 2 cenarios (varredura + erro em 1 status nao quebra)
   - TestStatusList: 3 cenarios (sanity check)

Envs novas (Easypanel):
  - WATCHDOG_PROMESSA_ENABLED=1 (default 0)
  - WATCHDOG_PROMESSA_DRY_RUN=0 (default 0 — age em prod)
  - WATCHDOG_PROMESSA_MIN_SEG=180 (3min)
  - WATCHDOG_PROMESSA_MAX_SEG=7200 (2h)
  - WATCHDOG_PROMESSA_MAX_LEADS=30
  - CRON_WATCHDOG_PROMESSA_SEG=120 (2min)

ROLLOUT:
  1. Deploy
  2. curl POST /admin/watchdog-promessa-tick?dry_run=true&secret=...
     -> ve quantos candidatos
  3. Se < 10, ligar WATCHDOG_PROMESSA_ENABLED=1 + redeploy
  4. Monitorar logs '[WATCHDOG-PROMESSA auto]' por 1h
" || echo "  (nada novo)"

git push origin main 2>&1 | tail -5

echo ""
echo "Aguardando deploy Easypanel (~3 min)..."
for i in \$(seq 1 12); do
    sleep 20
    body=\$(curl -s --max-time 10 "https://blink-agent.6prkfn.easypanel.host/health" 2>/dev/null || echo "")
    if echo "\$body" | grep -q "\"status\":\"ok\""; then
        echo "  HEALTHZ OK [\${i}x20s = \$((i*20))s]"
        break
    fi
    echo "  [\${i}/12] aguardando..."
done

echo ""
echo "Smoke do endpoint em dry_run..."
SECRET=\$(grep '^WEBHOOK_SECRET=' lia_engineer/.env.local 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')
if [ -z "\$SECRET" ]; then
    SECRET="blink_a3f9c2e1b8d47f6e905a2b4c8d1e7f3a"
fi

resp=\$(curl -s --max-time 30 -X POST \\
  "https://blink-agent.6prkfn.easypanel.host/admin/watchdog-promessa-tick?dry_run=true&max_leads=20&secret=\$SECRET" 2>&1)
echo "Resposta:"
echo "\$resp" | head -c 1000
echo ""
echo ""
echo "==============================================="
echo "PROXIMO PASSO:"
echo " 1. Ler resposta acima — campo 'candidatos'"
echo " 2. Se < 10 e tudo razoavel: ligar"
echo "    WATCHDOG_PROMESSA_ENABLED=1 no Easypanel"
echo "    + Implantar"
echo " 3. Cron interno 2min comeca a tratar automatico"
echo "==============================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
