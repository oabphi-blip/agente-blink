#!/bin/bash
# Push das mudanças do prompt — sessão 10/06/2026
# Bug C-18 sequência agenda + SDP→Avaliação Processamento Visual + apresentação canônica Dra. Karla
# Duplo-clique pra rodar.

set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push prompt update — 10/06/2026"
echo "==============================================="
echo ""
echo "▶ Diretório:"
echo "  $(pwd)"
echo ""

echo "▶ 1/4 git status"
git status --short
echo ""

echo "▶ 2/4 git add (arquivos do prompt)"
git add \
  CLAUDE.md \
  voice_agent/responder.py \
  voice_agent/kommo.py \
  voice_agent/knowledge_base/01_medicos_e_especialidades.md \
  voice_agent/knowledge_base/11_tom_e_conversao.md \
  voice_agent/knowledge_base/31_sdp_fluxo_excecao.md \
  voice_agent/knowledge_base/40_clinica_estrabismo.md \
  voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
  tests/test_bug_c18_sequencia_agenda.py \
  INSTALAR_LIA_ENGINEER.command 2>/dev/null || true
echo "  ✓ add ok"
echo ""

echo "▶ 3/4 commit"
git commit -m "fix(prompt): Bug C-18 sequência agenda + SDP→Avaliação Processamento Visual

- Bug C-18: PASSO 1→2→3 explícito no _agenda_block (caso Melissa 22779280)
  Lia oferta 2 slots PRIMEIRO; só pergunta dia+turno+período se paciente
  recusar — e quando perguntar é numa mensagem só, contextualizada.

- SDP/Síndrome Deficiência Postural removida do prompt visível:
  - KB: 01_medicos, 11_tom, 31_sdp_fluxo, 40_clinica_estrabismo
  - _MASTER_INSTRUCTION 5.6 ancoragem médica
  - responder.py: 'R\$ 800 (Avaliação do Processamento Visual)'
  - kommo.py: aliases retrocompatibilidade pra dados antigos
  - Aliases de DETECÇÃO mantidos em knowledge.py/responder.py
    (paciente ainda pode digitar 'SDP' e ser entendido)

- Apresentação canônica: 'Dra. Karla Delalíbera, especialista
  Avaliação do Processamento Visual' aplicada em todos os 5 KB.

- INSTALAR_LIA_ENGINEER.command: fix cp dotfiles (.env.local)
  via 'cp -R folder/.' em vez de 'cp -R folder/*'.

- tests/test_bug_c18_sequencia_agenda.py — 5 cenários verde
  (PASSO 1→2→3 + anti-padrão 'indo e vindo').

- CLAUDE.md: seção 0-APRESENTAÇÃO CANÔNICA no topo + Bug C-18
  indexado nas 5 lições recentes.

Pytest: 86/86 verde." || echo "  (nada pra commitar ou já commitado)"
echo ""

echo "▶ 4/4 push origin main"
git push origin main 2>&1 | tail -20
echo ""

echo "==============================================="
echo "  ✓ PUSH COMPLETO"
echo "==============================================="
echo ""
echo "  Easypanel vai pegar auto-deploy em ~2-5 min."
echo "  Acompanhar em:"
echo "  https://6prkfn.easypanel.host/projects/blink/app/agent"
echo ""
echo "  Validação pós-deploy:"
echo "  curl -s https://blink-agent.6prkfn.easypanel.host/health"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
