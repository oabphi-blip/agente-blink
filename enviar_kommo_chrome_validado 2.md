# Enviar mensagem WhatsApp via Chrome MCP no Kommo — sequência validada

> **Bug C-11 (05/06/2026)** — 14 mensagens viraram notas internas porque pulei essa sequência.
> Toda vez que for enviar mensagem via Chrome MCP no Kommo, SEGUIR aqui passo a passo.

---

## Passo 1 — Navegar pro lead

```
mcp__Claude_in_Chrome__navigate → https://univeja.kommo.com/leads/detail/{lead_id}
wait 3s
```

## Passo 2 — Identificar o seletor de canal (PRÉ-clique)

Antes de clicar na caixa de mensagem, **ler a página** procurando o componente "Bate-papo com **todos os**:".

A palavra "todos os" é um SELETOR de canal, NÃO o canal em si.

```
mcp__Claude_in_Chrome__read_page → filter: "interactive" → procurar elemento com texto "todos os"
```

Se aparecer apenas "todos os" sem WhatsApp/Business específico ao lado → caixa está em modo NOTA INTERNA.

## Passo 3 — Trocar seletor pra canal específico do paciente

Clicar em "todos os" → dropdown abre listando canais disponíveis:
- **WhatsApp Business** (canal WA real) — usar este pra mensagem chegar
- Nota interna (= "Todos") — equivalente a comentário interno

```
mcp__Claude_in_Chrome__find → "todos os" no rodapé do chat
mcp__Claude_in_Chrome__computer left_click no ref encontrado
screenshot pra confirmar dropdown aberto
identificar opção com ícone WhatsApp + nome do contato
left_click nessa opção
screenshot pra confirmar que o cabeçalho agora mostra o canal específico
```

## Passo 4 — Validar visualmente ANTES de digitar

**Sinais de canal correto (mensagem WhatsApp real):**
- Header da caixa mostra "WhatsApp Business" ou "WhatsApp" + nome do contato
- Quando mensagem aparece no histórico depois: bolha verde lado direito + ícone WhatsApp

**Sinais de canal ERRADO (vai virar nota):**
- Header mostra apenas "Bate-papo com todos os:" sem canal específico
- Mensagem aparece como "De: [seu nome] para: Todos" + fundo branco/cinza

## Passo 5 — Digitar mensagem

```
left_click na textarea
type → mensagem
screenshot pra confirmar texto digitado
```

## Passo 6 — Enviar + validar resultado

```
left_click no botão Enviar
wait 3s
screenshot
```

**Validar no histórico que apareceu uma das opções:**
- ✅ Bolha verde + canal WhatsApp + "Para: [contato]" → SUCESSO
- ❌ Fundo branco + "para: Todos" → FALHA (virou nota, repetir)

## Passo 7 — CANARY OBRIGATÓRIO se for batch

Se o pedido é mandar pra ≥ 3 leads:

1. Fazer só o **PRIMEIRO** lead completo (passos 1-6).
2. Tirar screenshot do histórico após Enviar.
3. **Escrever no chat:** "Piloto enviado pra lead {id}. Screenshot anexo. Aguardando confirmação do canal correto antes dos outros N-1."
4. **PARAR.** Não emendar com próximo lead.
5. Só seguir com o resto APÓS Fábio confirmar explicitamente ("ok", "pode continuar", "sim", etc).

---

## Padrão de FALHA conhecido (Bug C-11, 14 leads)

Sequência ERRADA que eu fiz hoje 05/06/2026:

```python
for lead_id in 14_leads:
    navigate(f"/leads/detail/{lead_id}")
    left_click(965, 770)  # clica direto na caixa SEM trocar seletor
    type("Olá! ...")
    left_click(688, 780)  # Enviar
    # ↑ TODAS as 14 viraram notas internas porque seletor estava em "Todos"
```

## Padrão CORRETO

```python
# Lead 1 (canary)
navigate("/leads/detail/{lead_1}")
find("todos os")
left_click no seletor
screenshot  # validar dropdown
left_click na opção "WhatsApp Business + {nome}"
screenshot  # validar header trocou
type("Olá! ...")
left_click(Enviar)
wait 3s
screenshot  # validar bolha verde no histórico
# REPORTAR pro Fábio + PARAR

# (só depois da confirmação) Leads 2-N
for lead_id in restantes:
    # mesma sequência completa, NÃO pular passos 2-3
```

---

## Quando NÃO usar Chrome MCP (preferir alternativas)

1. **Quando agent em prod estiver funcional** → usar `/admin/disparar-template/{lead_id}` (template Meta aprovado, mais robusto).
2. **Quando só quiser ATIVAR IA do lead** → MCP Kommo `kommo_update_leads_batch` com `ATIVADO IA = Ativado` (não dispara WhatsApp, mas prepara lead pra Lia responder no próximo inbound).
3. **Quando precisar bypass de janela 24h fechada** → template Meta via `/admin/disparar-template`, não texto livre.

Chrome MCP é último recurso quando agent não funciona — e nesse caso o canary obrigatório vale dobrado.
