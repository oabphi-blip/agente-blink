#!/bin/bash
# Bug C-36 (Fábio 17/06/2026, lead 22071351 Karina):
# 1.DIA CONSULTA no passado tratado como consulta futura.
# Fix em 3 camadas: ativacao_inteligente + _MASTER_INSTRUCTION + filtro responder.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH BUG C-36 — Histórico ≠ Consulta Ativa"
echo "==============================================================="

# Sanity
test -f voice_agent/ativacao_inteligente.py || { echo "ERRO: ativacao_inteligente.py"; exit 1; }
test -f tests/test_bug_c36_historico_nao_eh_consulta.py || { echo "ERRO: pytest"; exit 1; }

grep -q "0-AB. NUNCA TRATAR HISTÓRICO" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: seção 0-AB não está no prompt"; exit 1; }
grep -q "_viola_afirmou_consulta_ativa_c36" voice_agent/responder.py \
    || { echo "ERRO: filtro C-36 não está plugado"; exit 1; }
grep -q "2026-06-17-c36" voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
    || { echo "ERRO: VERSAO_PROMPT não bumpada"; exit 1; }

python3 -c "import ast; ast.parse(open('voice_agent/responder.py').read()); ast.parse(open('voice_agent/ativacao_inteligente.py').read())" \
    || { echo "ERRO: syntax error"; exit 1; }

echo "✓ Sanity check OK"
echo ""

git add voice_agent/knowledge_base/_MASTER_INSTRUCTION.md \
        voice_agent/ativacao_inteligente.py \
        voice_agent/responder.py \
        tests/test_bug_c36_historico_nao_eh_consulta.py \
        PUSH_BUG_C36_HISTORICO.command

git commit -m "fix(prompt+code): Bug C-36 — histórico ≠ consulta ativa (lead 22071351 Karina)

Origem: lead 22071351 Karina (17/06/2026 11:58 BRT). Lead tinha
1.NOME PACIENTE=Julia Akemi, MEDICOS=Karla, CONVENIO=TJDFT Pró-Saúde,
UNIDADE=Águas Claras, 1.DIA CONSULTA=23/09/2025 (9 meses passado).
ja_agendado=False corretamente (lógica kommo.py linha 1906 já tava OK).

Mas a Lia disse 'Vi aqui que a consulta da Julia Akemi estava marcada
com a Dra. Karla pelo TJDFT na Águas Claras. Está tudo certo para
comparecer?' — tratou campos do histórico como agendamento ativo.

Atendente humana anotou: 'IA se atrapalhando'.

Fix em 3 camadas:

1. ativacao_inteligente.py — gerar_saudacao_personalizada agora
   verifica 1.DIA CONSULTA. Se está no passado (> 1 dia atrás), troca
   'Vi aqui que sua consulta era com Dra. Karla' por 'Vi aqui que você
   já passou pelo nosso atendimento com a Dra. Karla'. Limpa 'era com'
   pra evitar repetição com 'passou pelo atendimento'.

2. _MASTER_INSTRUCTION.md seção 0-AB — regra explícita PRIORIDADE
   ABSOLUTA: campos do lead podem ser HISTÓRICO, não consulta ativa.
   Só 'consulta marcada' quando ja_agendado=True OU bloco 🚨 ATENÇÃO
   MÁXIMA aparece. Inclui contra-exemplo lead 22071351 + regra contato
   ≠ paciente.

3. responder.py — filtro _viola_afirmou_consulta_ativa_c36 sempre-ON
   pega 'consulta está/estava marcada', 'está agendada', 'tudo certo
   para comparecer' quando ja_agendado=False. Substitui por saudação
   histórica clara.

VERSAO_PROMPT bumpada pra 2026-06-17-c36-historico-nao-eh-consulta-ativa
(invalida cache Anthropic SDK).

Pytest tests/test_bug_c36_historico_nao_eh_consulta.py — 12 cenários
cobrindo frase real Karina + edge cases (ja_agendado=True não bloqueia,
frase inocente passa, saudação Karla com/sem convênio).

🤖 Generated with Claude Cowork"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Easypanel auto-deploy ~3min."
echo "==============================================================="
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
