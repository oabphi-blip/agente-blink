#!/bin/bash
# Push imediato — fix batch ferias julho NÃO cair pro nome do paciente
# Bug detectado lead 22723784 Enzo Olivi (Fábio 11/06/2026 11:56)
# Duplo-clique pra rodar.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push fix — nome do contato (lead 22723784)"
echo "==============================================="

git add scripts/batch_ferias_julho.py scripts/contar_elegiveis_fabricio.py PUSH_FIX_NOME_CONTATO.command
git commit -m "fix(batch): nunca cair pro nome do paciente como fallback

Bug detectado lead 22723784 Enzo Olivi (Fábio 11/06/2026 11:56):
batch ferias julho usava get_first_name(nome_paciente) como fallback
quando contato vazio → enviava saudação com nome do paciente em
vez do nome do contato (responsável).

Fix scripts/batch_ferias_julho.py linha 467:
  - Antes: primeiro = get_first_name(contato) or get_first_name(nome_paciente)
  - Depois: primeiro = get_first_name(contato); valida via
            voice_agent.contato_nome.nome_contato_invalido; se inválido → 'olá'

Bonus: scripts/contar_elegiveis_fabricio.py reescrito com dedup por
telefone (E.164) + score clínico (1.DIA CONSULTA + Karla + status).
Pra evitar custos Meta com leads duplicados na base 10.000+." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo. Deploy Easypanel ~3 min."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
