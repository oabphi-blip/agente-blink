#!/bin/bash
# Push consolidado sessão tarde 10/06/2026
# Bugs C-20 (nome contato) + C-21 (protocolo médico) + C-22 (omissão convênio não aceito)
# + KB 14 árvore T1→T2→T3→T4 + apresentação canônica Karla
# Duplo-clique pra rodar.

set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push consolidado — 10/06/2026 tarde"
echo "==============================================="
echo ""
echo "▶ git status"
git status --short
echo ""

echo "▶ git add (arquivos consolidados)"
git add \
  CLAUDE.md \
  voice_agent/responder.py \
  voice_agent/contato_nome.py \
  voice_agent/knowledge_base/14_funil_sem_convenio.md \
  voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
  voice_agent/knowledge_base/01_medicos_e_especialidades.md \
  voice_agent/knowledge_base/11_tom_e_conversao.md \
  voice_agent/knowledge_base/31_sdp_fluxo_excecao.md \
  voice_agent/knowledge_base/40_clinica_estrabismo.md \
  voice_agent/kommo.py \
  tests/test_bug_c18_sequencia_agenda.py \
  tests/test_bug_c20_contato_nome.py \
  tests/test_bug_c22_convenio_omissao.py \
  scripts/batch_ferias_julho.py \
  scripts/auditar_batch_julho_protocolo.py \
  INSTALAR_LIA_ENGINEER.command \
  AUDITAR_BUG_C21.command \
  PUSH_PROMPT_KARLA_AGORA.command \
  PUSH_CONSOLIDADO_10-06.command \
  BATCH_FERIAS_JULHO.command \
  MENSAGEM_SUPORTE_MEDWARE_10-06-2026.md 2>/dev/null || true
echo "  ✓ add ok"
echo ""

echo "▶ commit"
git commit -m "fix(prompt+code): C-20 nome contato + C-21 protocolo médico + C-22 convênio não aceito

C-20 — voice_agent/contato_nome.py:
  - nome_contato_invalido() detecta vazio/Você/Inbra/Cliente/Test/números/equipe
  - saudacao_segura() cai pra 'Olá' puro sem fallback genérico
  - Regra E1.5 no _MASTER_INSTRUCTION.md

C-21 — scripts/batch_ferias_julho.py:
  - protocolo_medico_ja_definido(lead) bloqueia se 1.MÊS PRÓX CONSULTA preenchido
    OU 1.DIA CONSULTA <6m atrás
  - Counter SKIP_PROTOCOLO no log
  - Regra E1.6 no _MASTER_INSTRUCTION.md
  - Script auditoria scripts/auditar_batch_julho_protocolo.py
  - AUDITAR_BUG_C21.command pra rodar nos 81 disparos do batch 10/06 16:39

C-22 — voice_agent/responder.py:
  - Filtro _viola_omitiu_resposta_convenio_nao_aceito detecta inbound paciente
    mencionando conv NÃO aceito + outbound Lia SEM marcas de reconhecimento
  - 'gdf' sozinho adicionado ao _CONVENIOS_NAO_ACEITOS_KB18
  - KB 14 reescrita com árvore T1→T2→T3→T4:
    * T1 = template Meta 1019_sem_convenio (2 botões)
    * T2 = motivo (APV→R\$800, catarata→R\$445, outro→T3)
    * T3 = qtde (1-2=R\$611, 3+=sábado família R\$511 — AN penúltimo, AC último)
    * T4 = escada objeção [1]parcel→[2]família→[3]urgência? (URGENTE=R\$611 regular; SEM=campanha incentivo)
  - Regra E4-NA no _MASTER_INSTRUCTION.md

Pytest: 93/93 verde (Bug C-18 + C-20 + C-22)." || echo "  (nada novo pra commitar)"
echo ""

echo "▶ push origin main"
git push origin main 2>&1 | tail -20
echo ""

echo "==============================================="
echo "  ✓ PUSH COMPLETO"
echo "==============================================="
echo ""
echo "  Easypanel auto-deploy: ~2-5 min"
echo "  Acompanhar: https://6prkfn.easypanel.host/projects/blink/app/agent"
echo "  Validar:    curl -s https://blink-agent.6prkfn.easypanel.host/health"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
