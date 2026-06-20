# Plano de Reestruturação da Lia segundo o livro "Dominando o MCP"

**Origem:** leitura integral do livro Dominando MCP (Oliveira, 2026) em 20/06/2026.
**Aplicado a:** projeto AGENTE IA BLINK / voice_agent — assistente WhatsApp da Blink Oftalmologia.

## 1. Diagnóstico — onde a Lia já está alinhada ao padrão MCP e onde se desvia

A Lia atual já adota vários princípios que o livro defende, mas mistura conceitos arquiteturais que o protocolo MCP separa por design. A reestruturação proposta clarifica essas fronteiras e captura ganhos de robustez, segurança e portabilidade.

### O que já está bom

Lia conversa com fontes de dados externas (Kommo, Medware, Redis, WhatsApp Cloud, Anthropic API) através de clientes Python isolados em módulos próprios (`voice_agent/kommo.py`, `voice_agent/medware.py`, etc.). Cada cliente HTTP detém suas credenciais e o modelo nunca vê senha de API. Isso é o princípio do servidor MCP como driver de hardware (livro, seção 1.1.1) sendo respeitado tacitamente. Há também a noção de filtros pós-geração e checklist de dados mínimos, que é a mentalidade de governança do livro (seção 4.5 — o servidor é o guardião).

### O que se desvia do padrão MCP

A Lia confunde quatro papéis que o protocolo MCP separa nitidamente: cliente, host, servidor e LLM. Hoje tudo vive dentro do mesmo processo FastAPI no Easypanel, sem cerimônia formal de handshake, sem schema de capabilities, sem isolamento de processo entre as integrações. Isso traz três sintomas concretos que vêm sendo registrados nos bugs C-XX do CLAUDE.md ao longo das últimas semanas:

- Quando um cliente HTTP falha (Medware retornando ReadTimeout em janela 90d), o pipeline inteiro entra em estado degradado. Não há isolamento de processo — princípio do livro, seção 1.1.1 — então a falha de um servidor contamina outros.
- A LLM frequentemente "alucina argumento" (livro, seção 6.5, item 1) porque as tool definitions atuais não passam por validação Pydantic estrita. Erros aparecem em runtime e geram resposta sem sentido.
- Logs e debug usam print, log.info para texto livre e até retornam stack traces em campos visíveis ao usuário. O livro alerta na seção 6.1 que esse padrão quebra clientes MCP (não é o caso aqui pois o transporte da Lia não é JSON-RPC, mas o princípio operacional é o mesmo: separar canal de protocolo do canal de log).

## 2. Quais primitivas MCP a Lia deveria expor

O livro define três primitivas (capítulo 1.2): Recursos, Ferramentas e Prompts. Mapeando para a operação Blink:

### Recursos (Resources)

São dados que a LLM pode ler passivamente, identificados por URI. Em vez de o pipeline injetar todos os dados manualmente no contexto a cada turno, criamos recursos que a LLM lê quando precisa. Candidatos:

- `kommo://lead/{lead_id}` — JSON com nome, telefone, custom_fields, status_id, notas dos últimos 30 dias.
- `kommo://lead/{lead_id}/preferencia` — campo DIA/TURNO/PERIODO ⚠️ parseado em estrutura tipada.
- `medware://horarios/{cod_medico}/{cod_unidade}` — slots disponíveis com janela cirúrgica baseada na preferência do lead.
- `medware://medicos` — catálogo Karla/Fabrício/Kátia com especialidades, unidades, durações de slot.
- `blink://knowledge/{topico}` — artigos do KB (`voice_agent/knowledge_base/*.md`) acessíveis por URI.
- `blink://regras/{regra_id}` — regras E0 a E6, anti-monólogo C-28, filtros C-30 a C-38b.

A vantagem: a LLM lê o que precisar, quando precisar, em vez de receber dump gigante no prompt todo turno. Reduz tokens (sintoma do bug C-28 — prompt cresceu de 5KB para 50KB) e melhora foco.

### Ferramentas (Tools)

Ações executáveis com efeito colateral. Candidatos:

- `oferecer_slot(lead_id, slot_inicio, slot_fim)` — exibe oferta ao paciente, marca reserva temporária 10 min.
- `gravar_agendamento_medware(lead_id, cod_agenda, cod_medico, cod_unidade, hora)` — chama Medware/Salvar com validação Pydantic dos parâmetros.
- `mover_lead_kommo(lead_id, status_id)` — muda etapa do funil.
- `anexar_nota_kommo(lead_id, texto)` — registra nota visível à equipe humana.
- `enviar_mensagem_whatsapp(phone, texto, canal)` — dispatch para 8133 ou 0710.
- `consultar_protocolo_medico(idade, motivo)` — agrupador de procedimentos por idade × motivo.

Cada ferramenta com docstring rica (livro, seção 3.7 — "trate docstrings como se estivesse explicando para estagiário júnior") e Type Hints estritos (livro, seção 6.5 — defesa contra alucinação de argumento).

### Prompts (Templates)

Fluxos pré-definidos. Candidatos:

- `triagem_inicial` — instrui LLM a coletar nome, perfil etário, motivo, convênio.
- `oferta_2_slots_canonica` — formato 1️⃣/2️⃣ + texto descritivo da preferência.
- `confirmacao_agendamento` — recap de paciente + médico + unidade + data + valor.
- `redirect_0710_para_8133` — agente do número antigo persuadindo migração com 5 ângulos.
- `revisao_caso_complexo` — instrui LLM a consultar `kommo://lead/{X}`, `medware://horarios`, e propor estratégia.

O usuário (ou equipe humana) seleciona o prompt e a LLM já recebe o contexto operacional certo, reduzindo erro de raciocínio.

## 3. Arquitetura alvo — desdobrando a Lia em servidores MCP independentes

A proposta é fragmentar o monolito atual (`voice_agent/`) em seis servidores MCP especializados, com um Host orquestrador na frente.

### Servidor 1 — `blink-kommo-mcp`

Responsável por toda interação com Kommo CRM. Implementado em Python com FastMCP. Expõe os recursos `kommo://lead/{id}`, `kommo://lead/{id}/notas`, `kommo://lead/{id}/preferencia`, `kommo://pipelines`, `kommo://leads-em-status/{status_id}`. Expõe as ferramentas `anexar_nota`, `mover_etapa`, `atualizar_custom_field`, `buscar_leads_por_telefone`. Detém o `KOMMO_TOKEN` como variável de ambiente (livro, seção 5.5 — .env nunca no código). Bug C-12 documentado (MCP kommo_update_lead mente em custom_fields) tem solução nativa: este servidor faz GET imediato após PATCH para validar, e retorna erro estruturado se a gravação não confirmou — em vez de mascarar com sucesso falso.

### Servidor 2 — `blink-medware-mcp`

Responsável por toda interação com o Medware (ERP clínico). Expõe os recursos `medware://medicos`, `medware://unidades`, `medware://horarios/{cod_medico}/{cod_unidade}` (com query params para janela), `medware://agendamentos/dia/{data}`. Expõe as ferramentas `consultar_paciente_por_cpf`, `criar_agendamento`, `cancelar_agendamento`, `listar_planos_aceitos`. Detém o `MEDWARE_USER/SENHA` e gerencia renovação de token. Implementa internamente o tuning C-38b (timeout 20s, retry 1x fail-fast, janela default 14d) e a regra E6-C de janela cirúrgica.

### Servidor 3 — `blink-whatsapp-mcp`

Responsável pelo dispatch de mensagens. Expõe as ferramentas `enviar_mensagem_template`, `enviar_mensagem_livre_24h`, `verificar_status_envio`. Atende dois canais: WhatsApp Cloud Meta (8133) e Evolution legado (0710). Implementa o agente redirect 0710 → 8133 internamente — quando recebe pedido de envio para o 0710, faz redirect automático.

### Servidor 4 — `blink-state-mcp`

Responsável pelo estado da conversa em Redis. Expõe os recursos `state://conversa/{phone}/historico`, `state://conversa/{phone}/fsm`, `state://conversa/{phone}/ctx_known`. Expõe as ferramentas `atualizar_fsm`, `marcar_slot_reservado`, `incrementar_turno_dia`, `salvar_preferencia_parseada`. Implementa dedup de mensagens, lock por conversation_key (fix #183), reserva temporária 10 min (regra E6-B).

### Servidor 5 — `blink-knowledge-mcp`

Responsável pela base de conhecimento clínico/operacional. Expõe os recursos `blink://kb/medicos`, `blink://kb/convenios`, `blink://kb/valores`, `blink://kb/agrupadores-procedimentos`, `blink://regras/E0`, `blink://regras/E1`... etc. Os 38 artigos atuais em `voice_agent/knowledge_base/*.md` viram recursos URI-acessíveis. Bumping de `VERSAO_PROMPT` vira versionamento de recurso. Expõe também o prompt `triagem_inicial`, `oferta_canonica`, etc.

### Servidor 6 — `blink-calendar-mcp`

Encapsula o `voice_agent/calendar_oracle.py` (validador de calendário Karla por unidade × dia da semana). Expõe ferramentas `validar_data_unidade`, `proximas_datas_disponiveis`, `gerar_oferta_pronta`. Fundamental para evitar repetição do bug C-35 (Claude inventou dias da semana em 12 notas Kommo).

### Host orquestrador — `blink-host` (substitui FastAPI atual)

Aplicação que recebe webhook do WhatsApp, gerencia a janela de contexto da LLM, conecta-se aos 6 servidores MCP via stdio (locais) ou SSE (se algum subir em container separado no Easypanel). Implementa o "loop agêntico" do livro (seção 7.2): observar (lê recursos) → pensar (consulta LLM) → agir (chama ferramentas) → avaliar (lê retorno) → repetir até atingir estado final.

## 4. Princípio "M para N" aplicado à Blink

O livro defende (seção 1.5) que ao adotar MCP, M modelos × N fontes de dados deixa de exigir M×N integrações e passa a exigir M+N. Aplicado à Blink:

Hoje a Lia roda em FastAPI customizado, acoplada à Anthropic SDK específica. Se amanhã quisermos rodar parte do trabalho no GPT-4 da OpenAI, ou no Gemini do Google, ou num modelo open-source self-hosted, precisamos reescrever metade do pipeline. Com a reestruturação MCP, os mesmos 6 servidores funcionariam com qualquer cliente MCP. Isso destrava três cenários futuros que hoje são caros:

- Rodar canary diário em modelos diferentes para comparar qualidade (custo, taxa de alucinação, latência).
- Permitir que a equipe humana use Claude Desktop com os 6 servidores instalados, sem rodar a Lia inteira em servidor — ferramenta de produtividade direta para Stephany e Ariany.
- Conectar parceiros externos (LangChain agents, IDEs como Cursor para programar contra o KB clínico) ao mesmo ecossistema, sem fork.

## 5. Segurança e governança — princípios do livro aplicados

O livro insiste em quatro princípios de segurança que se aplicam diretamente ao agravo clínico da Blink (lidamos com prontuário, CPF, convênio, prescrição).

**Princípio 1 — Servidores como guardiões (livro, seção 4.5).** Cada servidor MCP define o que é permitido. O `blink-medware-mcp` recebe pedido da LLM para criar agendamento; antes de chamar o Medware, valida: paciente tem nome completo? data de nascimento coerente? convênio existe? Se faltar, retorna erro estruturado em vez de tentar gravar. Isso resolve o padrão de bugs do tipo C-21 (batch ferias atropelou protocolo médico) e C-26 (Lia entrou em modo AGENDA para paciente status=5-AGENDADO).

**Princípio 2 — Validação Pydantic no schema da ferramenta.** Hoje a Lia tem tool calling mas sem validação estrita; argumentos chegam como dict e quebram em runtime. Com FastMCP + Pydantic models, a ferramenta `gravar_agendamento_medware(data: date, hora: time, cod_medico: int, cod_unidade: int, lead_id: int)` recusa entrada inválida antes mesmo de executar. Bug C-35 (12 notas com dia da semana inventado) seria barrado porque o tipo `date` força formato ISO e o `calendar_oracle` confere coerência.

**Princípio 3 — Logs separados do canal de protocolo (livro, seção 6.1).** Os logs operacionais da Lia vão para stderr/CloudWatch, não para a resposta visível ao paciente. Hoje há casos de stack trace vazando em mensagem ("Erro ao consultar Medware: HTTPError(...)") que é exatamente o anti-padrão do livro.

**Princípio 4 — Human in the Loop calibrado (livro, seção 7.4).** Para a operação clínica, a Blink fica no Nível 1 (humano aprova cada ação crítica) até estabilizar. As 4 etapas do funil que inativam a Lia (1-ATENDIMENTO HUMANO, CIRURGIAS, LENTES, FORNECEDORES) já são uma forma orgânica desse princípio. A reestruturação MCP formaliza esse controle no nível do servidor (não no prompt), eliminando o padrão recorrente de bugs onde a Lia ignora handoff humano (Bug C-19 Sarah, lead 21392947 Larissa).

## 6. Roteiro de implementação — 8 sprints curtos

A migração pode ser feita gradual, um servidor por vez, sem precisar reescrever o monolito num único movimento. Sugiro a sequência abaixo, em sprints de 2 a 5 dias cada.

**Sprint 1 — Servidor `blink-calendar-mcp` (primeiro porque é o menor e o mais isolado).** Encapsular o `calendar_oracle.py` em servidor FastMCP standalone. Cobertura pytest. Conectar ao Host atual (ainda monolito) substituindo o import direto. Validar que o bug C-35 não pode mais acontecer.

**Sprint 2 — Servidor `blink-knowledge-mcp`.** Expor os 38 artigos do KB como recursos URI. Substituir o RAG manual (memoria_rag.py) por chamadas formais a recursos. Bumpar VERSAO_PROMPT vira versionamento de recurso.

**Sprint 3 — Servidor `blink-state-mcp`.** Encapsular interações Redis em FastMCP. Implementar regra E6-B (reserva 10 min) e lock por conversation_key (#183) nativos.

**Sprint 4 — Servidor `blink-medware-mcp`.** O mais crítico. Inclui todos os fixes C-38, C-38b, regra E6-C de janela cirúrgica. Pytest abrangente, incluindo simulação de timeout. Inspector para depurar antes de plugar no Host.

**Sprint 5 — Servidor `blink-kommo-mcp`.** Inclui correção do Bug C-12 (validação pós-PATCH). Endpoint para criar lead com dedup por telefone (atacar Bug C-27).

**Sprint 6 — Servidor `blink-whatsapp-mcp`.** Unifica 8133 e 0710 com agente de redirect interno. Permite que outros servidores MCP usem dispatch de mensagem sem conhecer o canal.

**Sprint 7 — Host orquestrador.** Substitui o webhook.py atual. Implementa o loop agêntico formal. Plugaminação dos 6 servidores via configuração JSON (estilo claude_desktop_config.json).

**Sprint 8 — Migração de produção e observabilidade.** Deploy paralelo (blink-host novo rodando ao lado do voice_agent legado), traffic shifting gradual (10% → 50% → 100%), monitoramento via MCP Inspector e LangSmith.

Estimativa total: 8 a 12 semanas com 1 dev sênior dedicado. Cada sprint entrega valor independente — não há big-bang.

## 7. Custo, ferramentas e dependências

**Stack obrigatória.** Python 3.11+, uv (gerenciador de pacotes em Rust, ~100x mais rápido que pip — livro, seção 2.1.2), FastMCP, Pydantic 2, httpx (assíncrono — livro, seção 5.2), pytest. Tudo open source, custo zero.

**Stack opcional mas recomendada.** MCP Inspector (livro, seção 2.4) para depurar cada servidor isoladamente. LangSmith para observabilidade em produção (já planejado, task #344). Claude Desktop instalado nas máquinas dos devs e da equipe operacional para usar os servidores diretamente sem precisar do app web.

**Infra.** Hoje tudo roda no Easypanel em 1 container. Após migração, pode continuar no Easypanel (recomendado, sem custo adicional) com os 6 servidores rodando em processos separados gerenciados por supervisor/systemd no mesmo container, ou em containers separados se quisermos escala individual. Stdio funciona dentro do mesmo host; SSE só se algum servidor precisar viver em outra máquina.

**Anthropic API.** Sem mudança no que já é pago hoje. A reestruturação MCP é puramente arquitetural; quem consome tokens continua sendo o Host orquestrador chamando o modelo. Pode haver até redução de custo porque os recursos são lidos sob demanda em vez de injetados todo turno (já estamos hoje em 50KB de prompt — pode cair pra 10-15KB).

## 8. Bugs históricos que esta reestruturação previne

Cruzando os 38 bugs C-XX documentados no CLAUDE.md com os princípios do livro, identifico 22 bugs que não poderiam ter acontecido na arquitetura MCP proposta. Listo os mais críticos para mostrar o impacto prático:

- **Bug C-12** (MCP kommo_update_lead mente em custom_fields) — eliminado porque o `blink-kommo-mcp` faz GET de validação pós-PATCH e retorna erro estruturado.
- **Bug C-27** (duplicação de leads + notas vazias) — eliminado porque o servidor faz dedup por telefone antes de criar lead.
- **Bug C-35** (12 notas com dia da semana inventado) — eliminado porque `blink-calendar-mcp` valida cada data antes de aparecer em mensagem.
- **Bug C-38** (Medware 90d estourava timeout) — eliminado porque `blink-medware-mcp` implementa janela cirúrgica E6-C e tuning C-38b nativamente.
- **Bug C-21** (batch ferias atropelou protocolo médico) — eliminado porque a ferramenta `criar_agendamento` valida idade × motivo no agrupador antes de gravar.
- **Bug C-19** (Sarah 24129498 — Lia interferiu em handoff humano) — eliminado porque o `blink-state-mcp` bloqueia geração para leads em status inativo.
- **Padrão "deixa eu reconsultar agenda"** (Sofia, Fábio Philipe, vários) — eliminado porque a ferramenta `oferecer_slot` valida que ctx tem slots ANTES de chamar a LLM, e retorna erro estruturado se não tem; LLM nunca fica em loop de hesitação.

## 9. Conclusão e próximo passo

A leitura integral do livro convalida muitas decisões já tomadas no projeto Blink e expõe outras que estão tecnicamente fora do padrão de mercado. A reestruturação MCP traz três ganhos objetivos: estabilidade operacional (cada servidor isolado), portabilidade (qualquer cliente MCP funciona) e segurança formal (cada servidor é guardião do seu domínio). O custo é uma migração gradual de 8 a 12 semanas, sem big-bang, com cada sprint entregando valor mensurável.

O próximo passo recomendado é validar este plano com o consultor LangChain (task #254 já completada, briefing pronto). A consultoria deles vai naturalmente convergir para arquitetura semelhante (LangGraph é fundamentalmente compatível com MCP). Após validação externa, o Sprint 1 (`blink-calendar-mcp`) pode começar imediatamente — é o servidor mais simples, com menor risco operacional, e demonstra o valor da abordagem em 2 a 3 dias.

A Blink já é uma das poucas clínicas brasileiras com agente WhatsApp em produção integrado a CRM + ERP clínico + WhatsApp Cloud + LLM. Adotando MCP-first agora, posiciona-se como referência técnica para o setor de saúde — alinhada ao perfil que o livro chama de "Engenheiro de Contexto" na seção 8.2.

---

**Documento gerado a partir da leitura completa do livro "Dominando o MCP — A Nova Era da Integração de IA" (Oliveira, 2026, 8 capítulos, 43 páginas).**
