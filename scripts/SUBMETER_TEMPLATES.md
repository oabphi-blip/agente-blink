# Como submeter os 14 templates ao Meta — 3 passos

**Tempo total**: 5-10 minutos.

---

## Passo 1 — Pegar `WABA_ID` (WhatsApp Business Account ID)

Você já tem isso. É o mesmo ID usado pelo voice_agent em produção.

```bash
# No Mac, conferir o que está configurado no Easypanel:
echo $WHATSAPP_BUSINESS_ACCOUNT_ID    # se você já exportou
# ou abrir Easypanel → blink/agent → Ambiente → procurar WHATSAPP_BUSINESS_ACCOUNT_ID
```

Se não souber de cabeça:

1. Abra https://business.facebook.com/
2. Menu lateral → **WhatsApp Manager**
3. Em cima, ao lado do nome da conta, aparece um ID (15 dígitos). Esse é o WABA_ID.

---

## Passo 2 — Pegar Access Token com permissão `whatsapp_business_management`

O token que o voice_agent usa em produção (`WHATSAPP_TOKEN`) é de **send messaging** — pode ou não ter permissão de criar templates. Vamos checar:

```bash
# Testa se o token atual já dá acesso a templates:
curl "https://graph.facebook.com/v21.0/$WABA_ID/message_templates?access_token=$WHATSAPP_TOKEN&limit=1"
```

- Se retornar JSON com `"data": [...]` → o mesmo token serve. Pula pro Passo 3 com `WHATSAPP_BUSINESS_TOKEN=$WHATSAPP_TOKEN`.
- Se retornar `"error": "...whatsapp_business_management..."` → precisa de outro token.

### Como gerar um token com permissão de templates

1. Abrir https://developers.facebook.com/tools/explorer/
2. Em "Meta App", selecionar o app da Blink
3. Em "Permissions" adicionar: `whatsapp_business_management` + `business_management`
4. Clicar **Generate Access Token**
5. Copiar o token gerado (válido 1-2h se for de teste, ou usar token permanente do System User pra produção)

Para token permanente:
- Business Manager → Configurações de Negócio → Usuários do Sistema → criar usuário "blink-template-submitter"
- Atribuir o app WhatsApp Business
- Gerar token (escopo: `whatsapp_business_management`)

---

## Passo 3 — Rodar o submissor

```bash
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

# Exportar as 2 envs:
export WABA_ID="123456789012345"
export WHATSAPP_BUSINESS_TOKEN="EAAxxxxxxxxx..."

# Conferir o que já está submetido (não submete nada):
python3 scripts/submit_meta_templates.py --list

# Dry-run (imprime JSON do que vai mandar, sem submeter):
python3 scripts/submit_meta_templates.py --dry-run

# Submeter TODOS os 14:
python3 scripts/submit_meta_templates.py

# Ou submeter UM específico:
python3 scripts/submit_meta_templates.py blink_lf_a_convenio_aceito_v1
```

### Saída esperada

```
Submetendo 14 template(s)...

✅ blink_lf_a_convenio_aceito_v1              — id=123456789
✅ blink_lf_b_particular_v1                    — id=123456790
✅ blink_lf_c_pediatrico_v1                    — id=123456791
✅ blink_lf_d_familia_v1                       — id=123456792
✅ blink_lf_e_pausa_paciente_v1                — id=123456793
✅ blink_lf_f_catarata_v1                      — id=123456794
✅ blink_lf_g_cliente_conhecido_v1             — id=123456795
✅ blink_lf_h_sem_nome_v1                      — id=123456796
✅ blink_conf_d1_v1                            — id=123456797
✅ blink_loc_aguas_claras_v1                   — id=123456798
✅ blink_loc_asa_norte_v1                      — id=123456799
✅ blink_pos_avaliacao_asa_norte_v1            — id=123456800
✅ blink_pos_avaliacao_aguas_claras_v1         — id=123456801
✅ blink_proxima_consulta_v1                   — id=123456802

Resumo: 14 sucesso(s), 0 erro(s).
Aprovação Meta: UTILITY ~24h | MARKETING 24-72h.
```

---

## E se der erro?

**Erro mais comum**: `Invalid parameter` em algum campo do body.

- O script imprime o nome do template + a mensagem exata da Meta.
- Você pode fazer **dry-run** + ajustar o texto no script (`scripts/submit_meta_templates.py` → array `TEMPLATES`) e rodar de novo só o que falhou (`python3 scripts/submit_meta_templates.py blink_lf_x_v1`).

**"already exists"** → o template já estava lá; o script ignora e continua. Isso é OK.

---

## Plano B — Submeter pelo Business Manager (UI manual)

Se não quiser mexer com token agora:

1. Abrir https://business.facebook.com/wa/manage/message-templates/
2. Botão **Criar modelo**
3. Pra cada um dos 14 templates listados em `META_TEMPLATES_PARA_SUBMISSAO.md`:
   - Nome → copiar do bloco
   - Categoria → MARKETING ou UTILITY conforme indicado
   - Idioma → Português (Brasil)
   - Body → copiar/colar
   - Botões → adicionar Quick Reply ou URL conforme indicado
   - Exemplos → copiar dos exemplos listados
4. Repetir 14 vezes (~30-40min).

---

## Status pós-submissão

- UTILITY (6 templates: blink_conf_d1, blink_loc_*, blink_pos_avaliacao_*, blink_proxima_consulta) aprova em ~24h.
- MARKETING (8 templates: blink_lf_*) aprova em 24-72h. Meta avalia tom promocional.

Quando começarem a aparecer como **APPROVED** no Business Manager, me avisa que eu plugo os slugs em `voice_agent/templates_meta.py` em 10min — o dispatcher passa a usar.
