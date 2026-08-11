# Plano de Ação — Corrigir 7 bugs estruturais Lia (15/06/2026)

> Origem: auditoria caso Victor 24147566. Bugs identificados na sessão de 15/06 BRT.
> Objetivo: voice_agent prod respeitar regra E6-B (não-repetir slot + reserva 10min)
> e usar notas Kommo como contexto pra retomada de sessão.

---

## Sumário executivo

7 bugs estruturais que se somam — Lia produz correções em uma camada (Cowork + CLAUDE.md + notas + disparo manual) e **voice_agent prod continua rodando código antigo sem ler nada disso**.

| # | Bug | Severidade | Camada |
|---|---|---|---|
| 1 | Sessão expira → triagem do zero | 🔴 P0 | Pipeline contexto |
| 2 | Regra E6-B só no CLAUDE.md (manual EU) | 🔴 P0 | Prompt knowledge_base |
| 3 | Slot já-ofertado não tem trava | 🔴 P0 | Código + Redis |
| 4 | Gravação Medware autônoma não está em prod | 🟠 P1 | Push pendente desde 05/06 |
| 5 | Notas Lia → atendente humana só (voice_agent não vê) | 🟡 P2 | Memória persistente |
| 6 | Disparo /admin/wa-send-text paralelo ao pipeline | 🟡 P2 | Sync |
| 7 | CLAUDE.md ≠ prompt prod | 🟠 P1 | Pipeline de deploy de regras |

---

## P0 — corrigir HOJE (15/06)

### Bug 1 + 2 + 3 — combinados (mesmo deploy)

**Sintoma:** Lia ofertou novamente slots passados pra Victor; reiniciou triagem do zero a cada sessão.

**Fix técnico:**

#### 1a. Mover regra E6-B do CLAUDE.md → knowledge_base

```bash
# Adicionar regra E6-B em:
voice_agent/knowledge_base/_MASTER_INSTRUCTION.md

# Seção nova "E6-B — Reserva 10min + Não-Repetir":
# - 10 min de reserva por oferta
# - Slot já ofertado não volta a ser proposto
# - Mensagem-gatilho de expiração
# - Comunicar regra na 1ª oferta
```

Esse arquivo É carregado pelo voice_agent prod a cada turno (diferente do CLAUDE.md, que é só pra mim no Cowork).

#### 1b. Implementar Redis (task #325)

```python
# voice_agent/responder.py

# Antes de ofertar slot:
def _selecionar_2_slots_inteligente(agenda, lead_id, redis_client):
    """Filtra agenda removendo slots já ofertados a esse lead."""
    ja_ofertados = redis_client.smembers(f"blink:slots_ja_ofertados:{lead_id}")
    agenda_filtrada = [s for s in agenda if _slot_key(s) not in ja_ofertados]
    # ... seleciona 1 manhã + 1 tarde do agenda_filtrada
    return slots_escolhidos

# Quando oferecer (em handle_oferecer_slot):
def _registrar_oferta(slot, lead_id, redis_client):
    key = f"{slot['cod_med']}:{slot['cod_unid']}:{slot['data']}T{slot['hora']}"
    # Reserva 10min
    redis_client.setex(f"blink:slot_ofertado:{key}:{lead_id}", 600, "1")
    # Marca como já-ofertado (sem TTL — não repete jamais)
    redis_client.sadd(f"blink:slots_ja_ofertados:{lead_id}", key)
```

#### 1c. Worker varredura 1min (gatilho expiração)

```python
# voice_agent/worker_e6b.py — NOVO ARQUIVO

# A cada 60s, varrer reservas perto de expirar (550-600s)
# Pra cada lead com reserva expirando: mandar mensagem-gatilho
#  "{Nome}, esse horário foi liberado pra fila. Tenho outros: {SLOT_NOVO_1} ou {SLOT_NOVO_2}."

import asyncio
import time
from voice_agent.redis_client import get_redis

async def loop_expiracao():
    r = get_redis()
    while True:
        # Lista reservas com TTL entre 0-60s (prestes a expirar)
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="blink:slot_ofertado:*", count=100)
            for k in keys:
                ttl = r.ttl(k)
                if 0 < ttl < 60:
                    # Extrair lead_id da key
                    _, _, slot_key, lead_id = k.decode().split(":", 3)
                    # Dedup pra não mandar 2x
                    flag = f"blink:expiracao_mandada:{slot_key}:{lead_id}"
                    if not r.exists(flag):
                        r.setex(flag, 3600, "1")
                        await disparar_mensagem_expiracao(lead_id, slot_key)
            if cursor == 0:
                break
        await asyncio.sleep(60)
```

#### 1d. Filtro pós-geração (defesa)

```python
# voice_agent/responder.py — _scrub_prohibited adicionar:

def _viola_repete_slot_ofertado(text: str, ctx: dict, redis_client) -> bool:
    """Detecta se Lia ofereceu slot que já estava em blink:slots_ja_ofertados."""
    lead_id = ctx.get("lead_id")
    if not lead_id:
        return False
    slots_no_texto = _extrair_slots_de_texto(text)
    ja_ofertados = redis_client.smembers(f"blink:slots_ja_ofertados:{lead_id}")
    return any(s in ja_ofertados for s in slots_no_texto)
```

**Pytest pra criar:** `tests/test_e6b_reserva_10min.py` — 8 cenários (já listei na task #325)

**Como validar:**
- pytest verde
- Smoke: simulate-inbound em 2 sessões diferentes pra mesmo lead, ver se 2ª oferta NÃO repete 1ª

**Deploy:**
```bash
# .command já existe — vou criar PUSH_E6B_REDIS.command
# Após push: Easypanel auto-deploy ~3min
```

**Prazo:** D+1 (16/06 final do dia)

---

## P0/P1 — Bug 4 e 7 (deploy já em código)

### Bug 4 — Gravação Medware autônoma está pronta no Mac, falta deploy

**Task #208 está [completed]** = código local pronto.
**Task #209 está [pending] desde 05/06** = push + deploy + smoke pendente há 10 dias.

**Ação:**

```bash
# 1. Rodar PUSH_FIX_208_GRAVAR_MEDWARE.command
# 2. Easypanel auto-deploy
# 3. Smoke: simulate-inbound de paciente novo até confirmação,
#    validar que voice_agent chamou medware.criar_agendamento real
#    (não só flag Redis stub)
```

**Prazo:** D+1 (16/06 manhã)

### Bug 7 — Pipeline de deploy de regras

Toda vez que se adiciona regra de negócio nova, ela TEM QUE ENTRAR EM 2 LUGARES:
- `CLAUDE.md` (manual EU Cowork — pra eu lembrar)
- `voice_agent/knowledge_base/_MASTER_INSTRUCTION.md` (carregado pelo voice_agent — Lia respeita)

**Solução:** checklist obrigatório no fim de cada sessão:

```markdown
- [ ] Regra entrou no _MASTER_INSTRUCTION.md?
- [ ] CLAUDE.md atualizado?
- [ ] Pytest cobre cenário?
- [ ] Push + deploy executados?
- [ ] Smoke valida regra ativa em prod?
```

**Ação imediata:** auditar TODAS as regras dos últimos 10 dias do CLAUDE.md que possam estar SÓ lá e não no knowledge_base.

**Prazo:** D+2

---

## P1 — Bug 5 (24h)

### Bug 5 — Voice_agent não lê notas Kommo como contexto

**Sintoma:** Sessão 24h expira → Lia parte do zero. Notas Lia anteriores ficam órfãs.

**Fix:**

```python
# voice_agent/caller_context.py

def build_caller_context(phone, lead_kommo) -> dict:
    ctx = {...}
    # NOVO: injetar últimas 10 notas Kommo como histórico curto
    notas = kommo_client.get_lead_notes(lead_id, limit=10)
    notas_recentes = [n for n in notas if n["created_at"] > epoch_24h_atras]
    ctx["historico_notas_kommo"] = [
        {"role": "assistant", "content": n["text"]}
        for n in notas_recentes
        if n["text"].startswith("Lia (WhatsApp):")
    ]
    return ctx

# voice_agent/responder.py — append no início do messages:
def reply(ctx, user_msg):
    messages = []
    # Histórico de notas Kommo se sessão nova
    if ctx.get("historico_notas_kommo") and not ctx.get("sessao_24h_ativa"):
        messages += ctx["historico_notas_kommo"]
    messages.append({"role": "user", "content": user_msg})
    # ... resto
```

**Pytest:** `tests/test_retomada_sessao_apos_24h.py` — cenário Victor reproduzível.

**Como validar:**
- Smoke: simular paciente que já conversou ontem (notas existem). Mandar nova mensagem. Lia deve dizer "vamos seguir de onde paramos no dia X" — NÃO triagem do zero.

**Prazo:** D+1

---

## P2 — Bug 6 (48h)

### Bug 6 — /admin/wa-send-text disparo paralelo sem sync

Quando uso /admin/wa-send-text pra mandar mensagem manual, o voice_agent não sabe que aquilo aconteceu.

**Fix:**

```python
# voice_agent/webhook.py — admin_wa_send_text já existe.
# Adicionar gravação no histórico de conversa Redis:

# Após envio bem-sucedido:
from voice_agent.responder import _convos
convo_key = _conversation_key(digits)
hist = _convos.get(convo_key) or []
hist.append({
    "role": "assistant",
    "content": text,
    "ts": int(time.time()),
    "fonte": "admin_wa_send_text",
})
_convos[convo_key] = hist[-50:]  # cap em 50 mensagens
```

**Como validar:** após disparo manual, voice_agent na próxima resposta sabe "eu já mandei essa mensagem antes".

**Prazo:** D+2

---

## Cronograma

| Quando | O que entrega |
|---|---|
| **15/06 noite (hoje)** | Push fix #208 #209 (gravação Medware) — task antiga |
| **16/06 manhã** | Push regra E6-B em _MASTER_INSTRUCTION.md + Redis lock 10min + filtro |
| **16/06 tarde** | Push leitura notas Kommo no caller_context |
| **16/06 noite** | Smoke E2E completo: paciente novo agenda + reserva + expira → mensagem-gatilho |
| **17/06** | Push admin_wa_send_text → histórico Redis sync |
| **18/06** | Auditoria geral CLAUDE.md → _MASTER_INSTRUCTION.md (regras paralelas) |

---

## Mitigação imediata (enquanto deploy não rola)

**Pra cada lead "travado" tipo Victor:**

1. Desativar IA do lead via Kommo (campo ATIVADO IA = Desativado)
2. Mandar mensagem via `/admin/wa-send-text` com 2 slots NUNCA ofertados
3. Atendente humana agenda no Medware manual
4. Re-ativar IA depois pra pós-consulta (D-1 / D-0 / D+0)

---

## Métrica de sucesso

- ❌ Hoje: Victor recebeu 3x triagem do zero (13/06, 14/06, 15/06)
- ✅ Meta D+2: zero pacientes recebem >1 triagem; slots não-ofertados respeitados; gravação Medware autônoma >80% dos casos.

---

## Owner

Claude Cowork (eu) — implementação, push, smoke.
Fábio — aprovar fluxo, monitorar produção, sinalizar regressão.
