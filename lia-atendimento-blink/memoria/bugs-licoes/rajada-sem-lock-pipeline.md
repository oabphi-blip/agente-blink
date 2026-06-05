# Bug arquitetural — pipeline processa rajada SEM lock por conversa (4 padrões)

> **Data:** 02/06/2026 (tarde, operação real)
> **Leads:** 21392947 (Sabrina/Elisa), 24064723 (Kamila), 24065257 (Janeide/Allison), 21344999 (Iara bebê + Rebeca mãe)
> **Commits relacionados:** `04a50eb` (pula `_viola_dia_semana` se ja_agendado), `5559f81` (remove "horário comercial"), doc `bc654db` (lição 11-K)

## Sintoma — 4 padrões na mesma tarde
- **Sabrina (21392947):** filtro `_viola_dia_semana` substituiu a confirmação
  do paciente ("1=Tudo Correto") por fallback genérico "reconferir agenda",
  mesmo com status 5-AGENDADO + `1.DIA CONSULTA` futuro.
- **Kamila (24064723):** mensagem duplicada (mesmo texto em <1s) + Lia inventou
  "retorno em horário comercial seg-sex 8-18h" (Blink é 24h).
- **Janeide (24065257):** ofereceu "Terça 03/06" e "Quinta 05/06" — datas
  erradas (03/06 é quarta, 05/06 é sexta). Depois confirmou certo, mas regrediu
  pra "reconsultar agenda" no turno seguinte.
- **Iara (21344999, bebê 1a6m) + Rebeca (mãe):** Lia pediu CPF da contato
  (Rebeca) em vez do paciente (Iara); ignorou o CPF enviado; entrou em loop
  perguntando "turno e período" 4x mesmo com a paciente respondendo.

## Causa raiz unificada
`pipeline.py` processa mensagens em rajada **sem lock por `conversation_key`**.
Quando o paciente digita rápido ou 2 mensagens chegam próximas:
1. Turno 1 começa a processar → modelo gera resposta A.
2. Turno 2 entra ANTES de A "fixar" no Redis/Kommo → modelo gera resposta B com
   contexto DESATUALIZADO.
3. As 2 respostas saem em sequência com perguntas redundantes / retrocesso.

O dedup forte (commit `a37ffb8`) só pega texto IDÊNTICO (hash). Quando o modelo
varia "Ótimo!" / "Perfeito!" / "Entendi!" no início, todas passam.

## Fix (proposto — próxima sessão)
Lock Redis em `pipeline.py`:
```python
lock = redis.set(f"blink:lock_pipeline:{conv_key}", "1", nx=True, ex=30)
if not lock:
    return PipelineResult(sent=False, error="conversation_locked")
```
TTL 30s evita travamento eterno. Elimina concorrência por conversa.

Refino de prompt detectado (não imediato):
- E2 de `_MASTER_INSTRUCTION.md`: "preciso do CPF" é ambíguo p/ bebê/criança →
  "preciso do CPF do paciente ({{nome_paciente}})". Quando paciente é menor
  (perfis Bebê 0-2 / Criança 3-12), CPF é DO PACIENTE, não do responsável.
- Limpar "horário comercial / seg-sex 8-18h" (27 arquivos têm a string). Blink é 24h.

## Bug colateral de processo — deploys em rajada
12+ commits/deploys em sequência. Cada deploy do Easypanel reinicia o container
(~2-5 min downtime). Agent ficou OUT 11:33-12:00 BRT (27 min) — leads que
entraram (Tatiana 11:56, Iara 11:59, Ben Hur 2 11:59) ficaram sem resposta.
**Regra de processo:** máximo 2 deploys por hora durante operação ativa.

## Cenário pytest
- Duas inbound <1s mesma conv_key → segundo turno retorna `conversation_locked`,
  não gera resposta B.
- Paciente menor (perfil Bebê) → Lia pede CPF do paciente, não do responsável.
- status 5-AGENDADO + DIA CONSULTA futuro → `_viola_dia_semana` é PULADO.

## Tags
`bug-fix` `pipeline` `concorrencia` `lock-redis` `rajada` `dedup` `cpf-menor` `downtime` `critico`
