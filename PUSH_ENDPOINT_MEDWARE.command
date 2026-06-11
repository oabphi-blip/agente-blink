#!/bin/bash
# Push endpoint /admin/medware-pacientes-sem-retorno
# Server-side com auth Medware (sandbox local não tem credenciais)
# Após deploy: rodar PIPELINE_MEDWARE_RETORNO_1_ANO.command de novo

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================="
echo "  Push endpoint medware-pacientes-sem-retorno"
echo "==============================================="

git add voice_agent/webhook.py scripts/medware_pacientes_sem_retorno.py PUSH_ENDPOINT_MEDWARE.command
git commit -m "feat(medware): endpoint server-side /admin/medware-pacientes-sem-retorno

Caso urgente Fábio 11/06/2026 ('estamos sem leads pra atendimento agora'):
Medware é fonte da verdade. Sandbox/script local NÃO tem auth Medware
(precisa identificacao+senha JWT). Solução: endpoint admin server-side
no agent que já tem MedwareClient configurado.

Endpoint /admin/medware-pacientes-sem-retorno:
- Varre Medware mês a mês (default 30 meses)
- Filtra codStatusAgendamento==5 (Realizado)
- Agrupa por codPaciente
- Mantém última consulta
- Filtra: última > N meses atrás (default 12) + telefone E.164 válido
- Retorna JSON com lista pronta pra disparo

Script local scripts/medware_pacientes_sem_retorno.py agora consome
esse endpoint em vez de tentar auth local." || echo "  (nada novo)"
git push origin main 2>&1 | tail -8

echo ""
echo "  ✓ Push completo. Deploy Easypanel ~3 min."
echo "  Após deploy: rodar PIPELINE_MEDWARE_RETORNO_1_ANO.command de novo."
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
