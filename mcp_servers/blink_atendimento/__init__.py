"""blink-atendimento — MCP local para forçar Claude Cowork a ler chat
completo antes de responder sobre um lead.

Origem: Fábio 09/07/2026 — Camada 1 do plano MEMORIA_ATIVA_CLAUDE.md.

Bug crônico corrigido: Claude respondia perguntas A/B/C sobre um lead
sem ter lido as mensagens do chat (só custom_fields via kommo_get_lead).
Este servidor expõe `ler_chat_completo_lead(lead_id)` que retorna
custom_fields + notas + últimas mensagens do canal WhatsApp num único
payload — impossível pular a leitura.
"""
