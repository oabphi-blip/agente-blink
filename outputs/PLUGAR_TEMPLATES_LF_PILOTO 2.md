# Templates LF A-H plugados — pronto pra deploy + piloto

**Data**: 05/06/2026
**Tasks**: #236 ✅ #237 ✅ #238 (piloto) · #239 (cron)

---

## O que mudou no código

3 arquivos:

1. **`voice_agent/templates_meta.py`** — adicionados `TEMPLATE_LF_A` … `TEMPLATE_LF_H` + dict `TEMPLATES_LF` + função `resolver_template_lf(categoria, **dados)`. Slugs override via env `WHATSAPP_TEMPLATE_LF_X_NAME`.

2. **`voice_agent/webhook.py`** — `_disparar_template_aprovado_para_lead(...)` aceita novo param `categoria_lf`. Quando setado, busca convênio do Kommo (cat A só) + chama `resolver_template_lf()`. Endpoint `/admin/disparar-categoria` recebe query `template_lf=A..H`.

3. **`tests/test_templates_lf_a_h.py`** (novo) — 24 cenários verde.

---

## Sequência de deploy (no Mac)

```bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
git add voice_agent/templates_meta.py voice_agent/webhook.py tests/test_templates_lf_a_h.py outputs/PLUGAR_TEMPLATES_LF_PILOTO.md
git commit -m "feat(lf): plugar 8 templates LF A-H + roteador categoria→template (tasks #236 #237)

- templates_meta.py: TEMPLATES_LF dict + resolver_template_lf()
- webhook.py: _disparar_template_aprovado_para_lead aceita categoria_lf
- /admin/disparar-categoria recebe query template_lf=A..H
- pytest 24/24 verde"
git push
```

Easypanel pega auto-deploy em 2-5 min. Validar com:

```bash
curl -s https://blink-agent.6prkfn.easypanel.host/health | jq
```

---

## Piloto (#238) — sequência segura

**Sempre começar com `dry_run=true`** pra ver o que SERIA disparado antes do envio real.

### Piloto categoria C/B (particular)

```bash
# Preview
curl -s "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=C&template_lf=B&max=5&dry_run=true&secret=$WEBHOOK_SECRET" | jq

# Real (depois de validar preview)
curl -X POST "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=C&template_lf=B&max=5&dry_run=false&secret=$WEBHOOK_SECRET" | jq
```

### Piloto categoria E/A (convênio aceito)

```bash
curl -s "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=E&template_lf=A&max=5&dry_run=true&secret=$WEBHOOK_SECRET" | jq
```

### Piloto categoria C/F (catarata + Dr. Fabrício)

```bash
curl -s "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=C&template_lf=F&medico=fabricio&max=5&dry_run=true&secret=$WEBHOOK_SECRET" | jq
```

### Piloto categoria R/G (reagendar cliente conhecido)

```bash
curl -s "https://blink-agent.6prkfn.easypanel.host/admin/disparar-categoria?categoria=R&template_lf=G&max=5&dry_run=true&secret=$WEBHOOK_SECRET" | jq
```

---

## Quando ligar campanha automática semanal (#239)

Depois que 1-2 pilotos manuais validarem que mensagens chegam corretas e pacientes respondem:

**Easypanel → blink/agent → Ambiente → Add:**

```
CAMPANHA_SEMANAL_ENABLED=1
CAMPANHA_SEMANAL_CATEGORIA=R
CAMPANHA_SEMANAL_MAX=20
```

Aí toda segunda 9h-10h BRT o cron interno dispara automático.

---

## Riscos conhecidos (mitigados)

- **Slugs Meta podem variar** — se Meta renomear template após aprovar, basta sobrescrever env `WHATSAPP_TEMPLATE_LF_X_NAME=<novo_slug>` sem deploy.
- **Categoria A sem convênio** → `resolver_template_lf` devolve `None`, endpoint retorna `ok:false, motivo:"categoria_lf=A sem dados suficientes"`. Lead pula pra próximo. Sem envio errado.
- **Categoria D sem 2º paciente** → mesma proteção.
- **Convênio Inas/GDF/Cassi etc** → endpoint já filtra na heurística de `excluir_keywords` (linhas 3991+ do webhook.py).

---

## Métricas pra acompanhar pós-piloto

| Métrica | Onde ver |
|---|---|
| Disparos OK | `detalhes[].wamid` no JSON de retorno |
| Falhas Meta | `detalhes[].motivo` (ex.: "send_template falhou: template_name_does_not_exist") |
| Resposta paciente | Lia entra em conversa automática (ATIVADO IA = Ativado) |
| Cancelamento em massa | Se >30% bounce → reverter env `WHATSAPP_TEMPLATE_LF_X_NAME` ou desligar campanha |
