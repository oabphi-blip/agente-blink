# Submeter template 1033 ao Meta Business Manager

Versão A aprovada por Fábio 28/06/2026. Esses são os textos exatos pra colar no Meta Business Manager (formulário de criação de template WhatsApp).

---

## URL do Meta Business Manager

https://business.facebook.com/wa/manage/message-templates/

Selecione a conta WABA da Blink → "Criar modelo" / "Create template".

---

## Campo a campo (cole exatamente)

### Nome (Name)

```
1033_retorno_anual_ferias_julho_v1
```

### Categoria (Category)

```
Utilitário (UTILITY)
```

### Idiomas (Languages)

```
Português (BR)
```

### Cabeçalho (Header) — DEIXAR SEM HEADER

(não selecione nenhum tipo de header)

### Corpo (Body)

```
Oi, {{1}}! 😊

Aqui é a Ariany, da Blink Oftalmologia. Estou organizando a agenda da Dra. Karla Delalíbera de julho/2026 e vi aqui que chegou a hora da próxima consulta do {{2}} ({{3}}).

Estamos em pleno período de férias escolares e nossa agenda na unidade {{4}} fecha rápido — famílias aproveitam o recesso pra evitar falta na escola. Restam poucos horários neste mês.

Quer que eu reserve um horário pro {{2}} agora antes de fechar a agenda de julho?
```

### Exemplos das variáveis (Examples / Sample variables)

| Variável | Exemplo |
|---|---|
| {{1}} | Lydia |
| {{2}} | Davi |
| {{3}} | 9 anos |
| {{4}} | Asa Norte |

### Rodapé (Footer)

```
Blink Oftalmologia · Asa Norte e Águas Claras
```

### Botões (Buttons) — tipo "Resposta rápida" / "Quick reply"

Botão 1:

```
Sim, reservar agora
```

Botão 2:

```
Ver outras datas
```

---

## Checklist antes de enviar

- [ ] Nome exato `1033_retorno_anual_ferias_julho_v1` (minúsculas, underscores, sem espaços)
- [ ] Categoria = `Utilitário (UTILITY)` (NÃO marketing — é lembrete sobre paciente existente)
- [ ] Idioma = `Português (BR)`
- [ ] Corpo colado com **4 variáveis numeradas** sequenciais
- [ ] **Exemplos preenchidos** pra cada uma (Meta exige)
- [ ] Rodapé colado
- [ ] **2 botões** de resposta rápida na ordem correta
- [ ] Conferir caracteres especiais: `😊` deve ter ficado como emoji, NÃO como "??" ou texto quebrado

---

## Tempo esperado de aprovação Meta

- Categoria UTILITY costuma aprovar em **15 min a 24 h**
- Notificação por e-mail quando aprovado/rejeitado
- Se rejeitado, pedir motivo e ajustar (geralmente é por categoria errada — virar UTILITY se vier sugestão MARKETING)

---

## Após aprovação — passos automáticos

1. Quando aprovado, **anote o slug exato** do template (pode vir com sufixo tipo `_abc123`).
2. Manda pra mim o slug + screenshot da tela "Aprovado".
3. Eu pluga em `voice_agent/templates_meta.py` na constante `TEMPLATE_RETORNO_ANUAL_FERIAS_JULHO`.
4. Eu crio o endpoint `/admin/disparar-batch-retorno-julho` que filtra os 51 leads JUL2026 sincados + dispara o template com:
   - `{{1}}` = nome contato (do Kommo)
   - `{{2}}` = 1.NOME PACIENTE (do Kommo, sincado pelo SYNC)
   - `{{3}}` = idade calculada da 1.DATA NASCIMENTO (sincada pelo SYNC)
   - `{{4}}` = UNIDADE (do Kommo)

---

## JSON Graph API (alternativa avançada — se for submeter via API direto)

Caso prefira não usar o Business Manager UI e tenha o token Graph API com permissão `whatsapp_business_management`:

```bash
WABA_ID="<seu_waba_id>"
TOKEN="<seu_token_graph_api>"

curl -X POST \
  "https://graph.facebook.com/v20.0/${WABA_ID}/message_templates" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "1033_retorno_anual_ferias_julho_v1",
    "language": "pt_BR",
    "category": "UTILITY",
    "components": [
      {
        "type": "BODY",
        "text": "Oi, {{1}}! 😊\n\nAqui é a Ariany, da Blink Oftalmologia. Estou organizando a agenda da Dra. Karla Delalíbera de julho/2026 e vi aqui que chegou a hora da próxima consulta do {{2}} ({{3}}).\n\nEstamos em pleno período de férias escolares e nossa agenda na unidade {{4}} fecha rápido — famílias aproveitam o recesso pra evitar falta na escola. Restam poucos horários neste mês.\n\nQuer que eu reserve um horário pro {{2}} agora antes de fechar a agenda de julho?",
        "example": {
          "body_text": [
            ["Lydia", "Davi", "9 anos", "Asa Norte"]
          ]
        }
      },
      {
        "type": "FOOTER",
        "text": "Blink Oftalmologia · Asa Norte e Águas Claras"
      },
      {
        "type": "BUTTONS",
        "buttons": [
          { "type": "QUICK_REPLY", "text": "Sim, reservar agora" },
          { "type": "QUICK_REPLY", "text": "Ver outras datas" }
        ]
      }
    ]
  }'
```

---

## Recomendação operacional

Caminho mais rápido e seguro: **submeter via Business Manager UI** (instruções acima). Demora 3 min preencher e a categoria UTILITY costuma aprovar rápido.

Caminho API só se Graph API + token estiverem já configurados pra Blink — task #199 indica que essa parte está PAUSADA aguardando WABA_ID/token.
