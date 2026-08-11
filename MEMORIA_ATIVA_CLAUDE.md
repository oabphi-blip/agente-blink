# Memória Ativa Claude — Registro do Projeto

**Origem:** Fábio, 08/07/2026 23:xx BRT.
**Contexto:** 60+ dias de bugs recorrentes envolvendo LLM (Lia em prod + Claude Cowork em análise) que "esquece" o que já foi resolvido. Custo cumulativo em tempo, dinheiro e desgaste operacional.
**Autor:** Claude Cowork (implementação sob supervisão do Fábio).

---

## 1. Objetivo

Transformar o Claude Cowork (eu) e a Lia (agente em prod) numa máquina de **aprendizado contínuo evolutivo** — memória persistente, ativa, forçada — em vez de LLM probabilístico que retrocede a cada turno.

**Não-objetivo:** substituir LLM por regras cegas. LLM continua sendo o motor conversacional. O que muda é a **estrutura em volta**: hooks determinísticos ANTES e DEPOIS da resposta, e lookup semântico obrigatório em pontos de risco.

## 2. Diagnóstico honesto do estado atual

| Fato | Consequência |
|---|---|
| CLAUDE.md tem 3000+ linhas e é lido no início de cada sessão. | LLM atravessa mas não aplica mecanicamente. Retrocesso. |
| Cada resposta do LLM é probabilística. | Mesmo com regra escrita, LLM pode "achar que já sabe" e pular passos. |
| Chrome MCP tem tab volátil (perde referência entre requests). | Não consigo ler chat do Kommo com confiabilidade. |
| Sandbox bloqueia API Kommo direto via curl. | Preciso do Kommo MCP (limitado a get_lead/notes) ou Chrome MCP (instável). |
| Bugs indexados no CLAUDE.md como texto plano. | Não há busca semântica — depende de eu "lembrar" que já resolvi caso parecido. |
| Nenhum validador post-turn no Cowork. | Resposta ruim (desculpa, pergunta óbvia, invenção de dado) sai direto pra você. |

**Analogia:** o mesmo padrão do bug Mariana 08/07 (Lia inventa "reconferir com calendário") acontece comigo. A causa raiz é idêntica: **decisão livre do LLM em ponto crítico**. A solução também é idêntica: **retirar essa decisão**.

## 3. Solução — 3 camadas complementares

### Camada 1 — MCP local `blink-atendimento`

**Servidor MCP em Python** rodando no Mac do Fábio, expondo tools:

| Tool | Retorno | Uso forçado por |
|---|---|---|
| `blink_ler_chat_lead(lead_id)` | JSON `{custom_fields, notes, msgs_ultimas_30}` | Skill file com trigger `kommo.com/leads` ou `/chats/` |
| `blink_ler_msgs_whatsapp(phone_ou_lead_id, limite=30)` | Array de mensagens do Meta Graph | Idem |
| `blink_confirmar_agenda_medware(cod_medico, cod_unidade, dt_iso, hora)` | Bool + slot livre? | Antes de qualquer confirmação de horário |

**Skill file** (`~/.claude/skills/blink-atendimento-chat/SKILL.md`) descreve o trigger e o comportamento obrigatório. Cowork carrega o skill automaticamente quando URL Kommo aparece na conversa. Skill ativo = eu tenho que chamar a tool antes de responder.

**Efeito prático:** o erro "responder sem ver o chat" (que você diagnosticou no Theo/Tiago) fica **matematicamente impossível** enquanto o skill estiver ativo.

### Camada 2 — Vector store local dos bugs

**SQLite + sentence-transformers** (`all-MiniLM-L6-v2`, roda localmente, zero API externa). Não depende de Supabase inicialmente.

- Indexa cada bug do CLAUDE.md (C-01 a C-42) como chunk semântico.
- Indexa cada lição, cada frase banida, cada regra estrutural.
- Tool `blink_buscar_bug_similar(descricao_curta)` retorna top 3 chunks + fix aplicado.
- Reindex automático quando CLAUDE.md muda (watch file + hash).

**Efeito prático:** quando aparecer novo caso parecido com bug já resolvido (ex: variante da hesitação Sofia/Juliene/Mariana), o lookup semântico traz o fix registrado. **Não dependo mais de "lembrar" — é query.**

Migração futura pra Supabase pgvector é trivial se o volume crescer (mesmo schema).

### Camada 3 — Post-turn validator (skill enforcer)

**Skill file** com regras determinísticas Python que rejeitam padrões conhecidos de resposta ruim:

| Padrão detectado | Ação forçada |
|---|---|
| "vou verificar", "deixa eu checar" sem ter chamado ferramenta antes | Rejeita resposta, força chamada de tool |
| Pergunta A/B/C sobre lead sem ter chamado `blink_ler_chat_lead` | Rejeita resposta, força leitura |
| Data com dia_semana sem validação via `calendar_oracle.py` | Rejeita resposta, valida cálculo |
| Menção a slot Medware sem confirmação prévia via tool | Rejeita, força `blink_confirmar_agenda_medware` |
| "Peço desculpas", "vou tentar de outro jeito" em vez de ação concreta | Rejeita — pede ação, não meta-comentário |
| Resposta escapa 2x → escala pra você com log específico do que quebrou |

**Efeito prático:** desculpa e desvio ficam **estruturalmente impossíveis** de chegar até você. Ou chega ação concreta, ou chega log honesto do porquê a ação não foi possível.

## 4. Entregáveis por camada (como você testa)

### Camada 1

| Item | Como você valida |
|---|---|
| `mcp_servers/blink_atendimento/server.py` (~150 linhas) | AST OK + `python3 -m mcp_servers.blink_atendimento.server --smoke` |
| `~/.claude/skills/blink-atendimento-chat/SKILL.md` | Cola URL `https://univeja.kommo.com/leads/21759911` no chat → resposta minha começa com chamada de `blink_ler_chat_lead(21759911)` visível |
| Config `~/.config/claude-code/mcp.json` atualizada | `claude mcp list` mostra `blink-atendimento` |
| Pytest `tests/test_blink_atendimento_mcp.py` (10 casos) | `pytest -q` verde local |
| `INSTALAR_MEMORIA_ATIVA.command` | Duplo clique instala tudo. Você não digita nada. |

### Camada 2

| Item | Como você valida |
|---|---|
| `mcp_servers/blink_atendimento/vector_store.py` | Indexa CLAUDE.md → SQLite. Query "Lia hesita na agenda" → retorna C-30, C-30A, C-36c com fix aplicado |
| Tool `blink_buscar_bug_similar` | Aparece na saída de `claude mcp list` |
| Pytest `tests/test_vector_store_bugs.py` (10 casos) | Query semântica de cada bug retorna o próprio bug + variantes conhecidas |

### Camada 3

| Item | Como você valida |
|---|---|
| `~/.claude/skills/blink-anti-desculpa/SKILL.md` | Ao longo desta e das próximas sessões, respostas com "vou verificar", A/B/C sem chamar tool, ou desculpa ficam bloqueadas |
| Pytest `tests/test_post_turn_validator.py` (15 casos com resposta ruim histórica) | Cada resposta ruim é rejeitada |

## 5. Cronograma

| Fase | Duração | Marco |
|---|---|---|
| Documento (este arquivo) | 15 min | ✅ pronto |
| Camada 1 (MCP + skill + pytest) | 90 min | `INSTALAR_MEMORIA_ATIVA.command` funcional |
| Camada 2 (vector store + reindex) | 90 min | Query semântica retornando C-30, C-31, C-42 |
| Camada 3 (post-turn validator) | 60 min | Skill bloqueia frases banidas |
| Smoke fim-a-fim com lead 21759911 | 15 min | Fábio valida na prática |
| **Total** | **~4h30** | Entrega em 1 sessão |

## 6. Investimento

| Item | Valor |
|---|---|
| Tempo (esta sessão fechada) | ~4h30 |
| Custo mensal recorrente | **R$ 0** (tudo local: SQLite, sentence-transformers, MCP no Mac) |
| Custo migração futura opcional | ~R$ 25/mês se migrar vector store pra Supabase pgvector (não recomendado agora) |
| **Total sessão** | **~4h30 · R$ 0/mês** |

**Comparação com alternativas rejeitadas:**

| Alternativa | Tempo | Custo/mês | Resolve o bug? |
|---|---|---|---|
| Lovable + Supabase pra dashboard | Dias | R$ 100+ | Não. Dashboard é visualização, não força comportamento. |
| Consultoria LangChain/LangSmith | Semanas | R$ 500+ | Overkill. Não precisa. |
| Novo agente (LangGraph) | Semanas | R$ 500+ | Overkill. |
| **Este combo (3 camadas)** | **4h30** | **R$ 0** | **Sim.** Ataca a raiz. |

## 7. Riscos e rollback

| Risco | Mitigação |
|---|---|
| MCP local não carrega no Cowork | Config `~/.config/claude-code/mcp.json` reversível. Removi = volta ao estado anterior. |
| Skill file trigger dispara demais (falso positivo) | Regex do trigger é conservador. Se disparar demais, desabilita 1 arquivo. |
| Vector store retorna caso não relevante | Threshold de similaridade ajustável. Sem impacto na resposta se skill não confia. |
| Post-turn validator rejeita resposta legítima | Fallback: skill deixa passar após 2 rejeições consecutivas + loga pra revisão. |
| Tempo maior que 4h30 | Escopo cortado em ordem: Camada 3 → Camada 2 → Camada 1. Camada 1 sozinha já resolve o caso Theo/Tiago. |

## 8. KPIs de sucesso — 60 dias

Como saber se funcionou (métricas objetivas, não impressão):

| KPI | Baseline (últimos 60 dias) | Meta pós-implementação |
|---|---|---|
| Bugs "Claude não viu o chat antes de responder" | Fábio reporta ~1-2/dia | **0/dia** (matematicamente impossível com Camada 1) |
| Bugs "Claude repete erro já resolvido" | ~3-4/semana | **≤1/semana** (variantes 100% novas) |
| Respostas com "vou verificar" sem verificar | Fábio reporta constante | **0** (Camada 3 bloqueia) |
| Tempo Fábio corrigindo Claude | Não medido, ele reporta "horas por dia" | **Redução ≥70%** por autopercepção Fábio |

Auditoria: log local `~/.claude/blink_memoria_log.jsonl` registra cada chamada de tool, cada rejeição de validador, cada bug retomado do vector store. Consulta futura para comprovação.

## 9. O que NÃO está no escopo desta entrega

- Dashboard visual (Lovable) — separado, futuro
- Migração pra Supabase pgvector — futura, se volume crescer
- Aplicação do mesmo padrão dentro da Lia em prod (código Python do agente) — a Lia já tem o pipeline determinístico da oferta de agenda deployado hoje. Escalar pra outras decisões (cobrança de sinal, resposta a dúvidas) é obra separada, tem que ser priorizada caso a caso.

## 10. Como você acompanha

**Durante a sessão** (próximas 4h): eu executo em silêncio. Você não me vê pedindo "confirma X, confirma Y". Você não é interrompido.

**Ao final da sessão**: entrego 1 duplo-clique único (`INSTALAR_MEMORIA_ATIVA.command`) + este documento atualizado com "concluído".

**Após instalação**: você faz UM teste simples — cola URL de lead qualquer no chat comigo. Se eu não chamar `blink_ler_chat_lead` como primeira coisa antes de responder, eu falhei e você me chama. Se eu chamar, funcionou.

**60 dias**: reunião curta pra comparar KPIs. Se meta atingida, escalamos padrão pra outros pontos. Se não atingida, trago o log dos casos que escaparam pra decidir Camada 4.

---

## Histórico de alterações neste documento

| Data | O que mudou | Por |
|---|---|---|
| 08/07/2026 23:xx | Criação inicial. Escopo aprovado. | Claude Cowork sob supervisão Fábio |
| (a preencher) | Camada 1 concluída. Smoke OK. | |
| (a preencher) | Camada 2 concluída. Reindex CLAUDE.md OK. | |
| (a preencher) | Camada 3 concluída. Validator ativo. | |
| (a preencher) | Instalação final validada por Fábio. | |
