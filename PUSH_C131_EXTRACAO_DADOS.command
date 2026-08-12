#!/bin/bash
# C-131 — Extração determinística nome/data/CPF + C-84/C-108 reforçados (12/08/2026)
#
# Fix triplo para "repetição de perguntas" (leads 24448016 Lorena/Nicolas e 24448040 Patrícia):
#
# BUG RAIZ: C-125 perguntava "Qual a data de nascimento?" → paciente respondia 3 vezes
# → C-130 passava para LLM → LLM dizia "Anotado!" mas NÃO atualizava ctx.known["data_nasc"]
# → próximo turno: checklist via campo vazio → C-125 disparava de novo → LOOP INFINITO
#
# Fix 1 (C-131): voice_agent/extracao_resposta_c131.py (NOVO)
#   Python extrai nome/data/CPF do user_text quando a última mensagem da Lia perguntou
#   o campo, e grava em ctx.known ANTES do checklist.
#   Roda em enriquecimento_ctx.py step 19 (após todos os outros enriquecimentos).
#   Toggle: EXTRACAO_RESPOSTA_ATIVADO (default ON). Fail-open.
#
# Fix 2 (C-108): voice_agent/desistencia.py
#   Novos padrões: "não quero agendar agora", "não vou agendar", "vou decidir e procuro
#   novamente", "procuro novamente", "decido depois"
#   Caso real: lead 24448040 Patrícia disse 3× que não queria agendar — agente ignorou.
#
# Fix 3 (C-84/C-126): voice_agent/blindagens_deterministicas.py
#   Adicionado \batendimento\s+humano\b ao regex — antes só capturava \batendente\b.
#   Caso real: lead 24448016 Lorena disse "atendimento humano." e o agente não detectou.
#
# Pytest: 61/61 verde
set -e

cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "=== Rodando pytest C-131 ==="
python3 -m pytest \
  tests/test_bug_c131_extracao_dados.py \
  tests/test_bug_c130_data_nasc_loop.py \
  tests/test_bug_c125_prova_escuta_uma_pergunta.py \
  tests/test_bug_c108_desistencia_explicita.py \
  -v --tb=short -q

echo ""
echo "=== Staging ==="
git add \
  voice_agent/extracao_resposta_c131.py \
  voice_agent/enriquecimento_ctx.py \
  voice_agent/desistencia.py \
  voice_agent/blindagens_deterministicas.py \
  tests/test_bug_c131_extracao_dados.py \
  CLAUDE.md

git add -f PUSH_C131_EXTRACAO_DADOS.command

echo "=== Commit C-131 ==="
git commit -m "feat(C-131): extracao_resposta_c131 + C-108/C-84 fix — anti-repeticao nome/data/CPF

=== C-131: Extração determinística — fim do loop 'Qual a data de nascimento?' ===

Casos reais:
  Lead 24448016 Lorena/Nicolas: paciente deu data 3× incluindo 'neuvembre de fevereiro
  de 2025' escrito por extenso — C-125 repetia 'Qual a data de nascimento?' toda vez.
  Lead 24448040 Patrícia: deu nome completo — C-125 repetia 'Qual o nome completo?'.

Causa raiz: C-130 passava para LLM corretamente, mas LLM escrevia 'Anotado!' sem
atualizar ctx.known['data_nasc'] → próximo turno: checklist via campo vazio → LOOP.

voice_agent/extracao_resposta_c131.py (NOVO):
  extrair_data_nascimento(): DD/MM/YYYY, typo '27/012/2024', ISO, escrito por extenso
  extrair_nome_completo(): remove prefixos, valida 2+ palavras alfa, rejeita contexto
  extrair_cpf(): com ou sem máscara
  extrair_e_injetar_resposta_c131(ctx, user_text):
    lê ultima_msg_outbound → sabe o que C-125 perguntou
    extrai resposta do user_text → grava em ctx.known ANTES do checklist
    ctx.known['data_nasc'] preenchido = C-125 não dispara mais. Loop quebrado.

voice_agent/enriquecimento_ctx.py:
  step 19 (C-131): chama extrair_e_injetar_resposta_c131 após todos os outros steps.
  Toggle: EXTRACAO_RESPOSTA_ATIVADO (default ON). Fail-open: exceção → log.warning.

=== C-108: novos padrões de desistência (lead 24448040 Patrícia) ===

Patrícia disse 3×: 'Vou decidir e procuro novamente', 'não quero agendar agora',
'Não vou agendar' — agente ignorou todos e continuou pedindo dados.

_RE_DESISTENCIA em desistencia.py ganhou:
  'não quero agendar agora/mais/por enquanto'
  'não vou agendar'
  'vou decidir e procuro novamente'
  'procuro novamente/depois/mais tarde'
  'decido depois'
  'vou pensar e depois entro em contato/volto/procuro'

=== C-84/C-126: 'atendimento humano' detectado (lead 24448016 Lorena) ===

Lorena disse 'atendimento humano.' — não foi capturado porque o regex tinha
\\batendente\\b mas NÃO \\batendimento\\b (palavras diferentes).

blindagens_deterministicas.py: adicionado ao regex C-126:
  \\batendimento\\s+humano\\b
  quero\\s+atendimento\\s+humano
  transfere\\s+(?:para)?\\s+atendimento\\s+humano

Pytest: 61/61 C-131 verde
Rollback: EXTRACAO_RESPOSTA_ATIVADO=0 em Easypanel → Implantar (desliga C-131)"

echo "=== Push ==="
git push origin main

echo ""
echo "✅ C-131 + C-108 + C-84 em produção."
echo ""
echo "Resultado:"
echo "  C-131: loop 'Qual a data de nascimento?' eliminado"
echo "  C-131: loop 'Qual o nome completo?' eliminado"
echo "  C-108: 'não quero agendar agora' → move para 2.LEADS FRIO + desativa IA"
echo "  C-84: 'atendimento humano.' agora detectado → move para 1-ATENDIMENTO HUMANO"
echo ""
echo "Env de rollback:"
echo "  EXTRACAO_RESPOSTA_ATIVADO=0 → desliga extração C-131"
echo "  DESISTENCIA_ATIVADO=0       → desliga C-108"
