# Templates Meta WhatsApp — submetidos em 03/06/2026

**WABA**: Blink Oftalmologia (`1990931811727552`)
**Status**: ⏳ Aguardando aprovação Meta
**Acompanhar**: https://business.facebook.com/wa/manage/message-templates/

---

## Ciclo LEAD FRIO (categoria MARKETING — aprovação 24-72h)

| Slug | ID Meta | Variáveis |
|---|---|---|
| `blink_lf_a_convenio_aceito_v1` | `1556007516139394` | {{1}}=nome paciente · {{2}}=convênio |
| `blink_lf_b_particular_v1` | `883847984730036` | {{1}}=nome · {{2}}=convênio não aceito |
| `blink_lf_c_pediatrico_v1` | `1509571930565650` | {{1}}=nome paciente |
| `blink_lf_d_familia_v1` | `1432029288688218` | {{1}}=contato · {{2}}=paciente 1 · {{3}}=paciente 2 |
| `blink_lf_e_pausa_paciente_v1` | `1920141848697871` | {{1}}=nome · {{2}}=motivo da pausa |
| `blink_lf_f_catarata_v1` | `2488288298250716` | {{1}}=nome paciente |
| `blink_lf_g_cliente_conhecido_v1` | `1155449460090521` | {{1}}=nome paciente |
| `blink_lf_h_sem_nome_v1` | `2062674534458629` | (sem variável) |

## Ciclo CONFIRMAÇÃO + PÓS-CONSULTA (categoria UTILITY — aprovação ~24h)

| Slug | ID Meta | Variáveis |
|---|---|---|
| `blink_conf_d1_v1` | `1414643400680641` | {{1}}=contato · {{2}}=dia/hora · {{3}}=paciente · {{4}}=médico |
| `blink_loc_aguas_claras_v1` | `2044840499733796` | {{1}}=contato · {{2}}=dia/hora |
| `blink_loc_asa_norte_v1` | `2386469661844979` | {{1}}=contato · {{2}}=dia/hora |
| `blink_pos_avaliacao_asa_norte_v1` | `2465962103917077` | {{1}}=contato · {{2}}=médico · {{3}}=especialidade |
| `blink_pos_avaliacao_aguas_claras_v1` | `2045424899730403` | {{1}}=contato · {{2}}=médico · {{3}}=especialidade |
| `blink_proxima_consulta_v1` | `976544015353769` | {{1}}=contato · {{2}}=consulta anterior · {{3}}=paciente · {{4}}=intervalo |

---

## Próximos passos (na ordem)

1. ⏳ **Aguardar aprovação Meta**
   - UTILITY (6 templates): ~24h
   - MARKETING (8 templates): 24-72h
   - Acompanhar no Business Manager (link acima)
   - Se algum reprovar → ajustar texto + re-submeter via `python3 scripts/submit_meta_templates.py <slug>`

2. 🔐 **Revogar o token de submissão**
   - Acessar: Business Manager → Configurações de Negócio → Usuários do Sistema
   - Localizar o usuário que gerou o token e clicar em revogar
   - Esse token cumpriu seu papel. Deixar vivo é risco desnecessário.

3. 🔧 **Após aprovação, plugar slugs em `voice_agent/templates_meta.py`**
   - Eu adiciono os 14 como `TemplateMeta(...)` com helpers `enviar_*`.
   - 10 minutos.

4. 🚀 **Integrar nos triggers**:
   - Modelo K (avaliação Google) → webhook handler quando lead vira `8-REALIZADO CONSULTA`
   - Modelos I/J/L → cron `ciclo_comunicacao.py` (estrutura D-3/D-1/D-0 já existe)
   - Modelos A-H → dispatcher de campanha 2.LEADS FRIO (com segmentação automática)

5. 📊 **Operação imediata** (não precisa esperar Meta):
   - Stephany/Ariany podem disparar mensagens **A-L em texto livre** dentro da janela 24h (paciente que respondeu nas últimas 24h).
   - Pra abrir janela com leads frios fora dela, usa template aprovado existente (`1079_ativar_conversa_de_imediato_odlmcy`) até os novos serem aprovados.

---

## Limpeza imediata

```bash
# 1) Remover o arquivo com o token (não precisa mais)
rm scripts/.env.meta

# 2) Garantir que não foi pro Git (defesa)
git status scripts/.env.meta
# deve dizer "no such file or directory"
```

Adicione `scripts/.env.meta` ao `.gitignore` se ainda não estiver lá:

```bash
echo "scripts/.env.meta" >> .gitignore
```

---

**Resumo**: 14 templates submetidos em 30 segundos. Agora é Meta avaliar. Me avisa quando aparecerem como `APPROVED` no Business Manager que eu plugo os slugs no dispatcher.
