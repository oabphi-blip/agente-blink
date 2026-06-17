#!/bin/bash
# Push: Protocolo Remarcação/Encaixe unificado (Fábio 17/06/2026)
# E1.7-A: Encaixe → 4.REAGENDAR + atualiza 1.PREFERÊNCIA + override humano

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH PROTOCOLO ENCAIXE — 4.REAGENDAR (unifica C-26)"
echo "==============================================================="
echo ""

# Sanity check
test -f voice_agent/knowledge_base/_MASTER_INSTRUCTION.md || { echo "ERRO: _MASTER não existe"; exit 1; }
test -f tests/test_protocolo_encaixe_4_reagendar.py || { echo "ERRO: pytest não existe"; exit 1; }

grep -q "E1.7-A — RESUMO DO PROTOCOLO REMARCAÇÃO" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: seção E1.7-A não está no prompt"; exit 1; }
grep -q "2026-06-17-protocolo-encaixe-4-reagendar" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: VERSAO_PROMPT não bumpada"; exit 1; }
grep -q "106184631" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: status_id 4.REAGENDAR não referenciado"; exit 1; }

echo "✓ Sanity check OK"
echo ""

git add voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        tests/test_protocolo_encaixe_4_reagendar.py \
        PUSH_PROTOCOLO_ENCAIXE_4_REAGENDAR.command

git commit -m "fix(prompt): protocolo remarcação/encaixe unifica C-26 com instrução Fábio 17/06

Mudanças no _MASTER_INSTRUCTION.md::E1.7:

1. Encaixe agora move pra 4.REAGENDAR (status_id 106184631), não mais
   2.LEADS FRIO (101508307). 4.REAGENDAR é a etapa operacional correta
   pra equipe humana localizar pacientes aguardando encaixe.

2. Atualiza 1.PREFERÊNCIA (dia da semana, turno, período) quando paciente
   mencionar mudança — mantém histórico de preferência atualizado pra
   equipe usar no encaixe.

3. Nova seção E1.7-A consolidando o protocolo em 3 passos sequenciais:
   - A FAZER = Encaixe (Kommo update)
   - Status → 4.REAGENDAR
   - Mensagem padrão Fábio de confirmação

4. Override humano explicitamente permitido: equipe pode pular protocolo
   e ofertar horário direto em casos específicos.

5. Anti-padrão documentado: NÃO deixar lead parado em 5-AGENDADO quando
   paciente desistiu.

Preservado da regra C-26:
- Investigação de motivo antes de ação (4 ramos)
- Sem interesse → Closed-lost (143)
- Sintoma novo → 1-ATENDIMENTO HUMANO + URGENTE
- Problema autorização → 1-ATENDIMENTO HUMANO

VERSAO_PROMPT bumpada pra 2026-06-17-protocolo-encaixe-4-reagendar
(invalida cache Anthropic SDK).

Pytest: 14 cenários (10 protocolo + 4 preservação C-26).

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
