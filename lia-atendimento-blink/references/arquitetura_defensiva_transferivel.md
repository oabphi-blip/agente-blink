# Arquitetura defensiva de agente IA — padrões transferíveis

> Documento de transferência para próximo agente: autorização de
> convênios via portal. Sintetiza tudo o que aprendemos blindando a
> Lia hoje (30/05/2026).

## Os 7 players da arquitetura defensiva

1. **Memória ativa documentada** — arquivos .md em local conhecido com cada bug histórico, causa raiz, pytest que blinda. Próximo Claude lê automaticamente.

2. **Ambiente de teste isolado** — endpoints /admin/simulate-X, /admin/dry-X, /admin/force-X, /admin/debug-X, /admin/schema-check. Reproduz bug sem cliente real em 30s.

3. **Pytest com cenários históricos** — cada bug vira teste que congela a interface. Bloqueia regressão.

4. **Self-healing: auto-skip com retry inteligente** — agente detecta erro do sistema externo, blacklista campo problemático em memória, retenta sem ele. Próximas chamadas pulam direto.

5. **Observabilidade /admin/healthz semafórico** — JSON com timestamps das últimas operações. Equipe vê estado sem ler logs.

6. **Subagentes (Plan/Explore) para análise paralela** — ao receber bug, antes de hipótese, spawnar Plan agent pra mapear caminho completo e pontos de descarte silencioso.

7. **Schema source-of-truth + boot fail-loud** — no boot, comparar enums hardcoded com sistema externo real. Diverge → log fail-loud + auto-blacklist.

## Anti-padrões a evitar

1. Adivinhar path em vez de checar (rodar `find`/`ls` antes)
2. Codificar mapeamento sem listar a fonte oficial via API
3. Múltiplas mudanças sem smoke test entre cada
4. Mudar prompt sem rodar pytest
5. Commitar segredos (varrer diff regex CPF/token)
6. Confiar em deploy verde sem validar runtime (testar endpoint novo)
7. Perseguir causa em vez de mapear todos pontos de falha

## A regra de ouro

> Antes de adicionar log de debug, antes de perseguir hipótese, antes de fazer deploy: spawnar Plan agent pra mapear o caminho inteiro do dado. Se a resposta não está em <30s no ambiente de teste, está em <2h depois de implementar o ambiente — não em <8h debugando logs no escuro.

## Ver mais

- Word document: `outputs/arquitetura_defensiva_agente_blink.docx`
- Bugs históricos: `lia-atendimento-blink/memoria/bugs-licoes/`
- Pytest implementados: `tests/test_*.py`
- CLAUDE.md seção 16 (anti-padrões observados)
