#!/bin/bash
# Push da reestruturação MCP completa (6 servidores + Host).
# Baseado integralmente no livro "Dominando o MCP" (Oliveira, 2026).
#
# Esta entrega é PARALELA ao monolito atual em voice_agent/. Não afeta
# produção. Sobe somente a nova pasta mcp_servers/ pra revisão.

set -e
cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"

echo "==============================================================="
echo "  PUSH RESTRUTURA MCP — 6 servidores + Host (Plano completo)"
echo "==============================================================="

# Sanity
test -f mcp_servers/README.md || { echo "ERRO: README faltando"; exit 1; }
test -f mcp_servers/pyproject.toml || { echo "ERRO: pyproject faltando"; exit 1; }
test -f mcp_servers/blink_calendar/server.py || { echo "ERRO: blink_calendar"; exit 1; }
test -f mcp_servers/blink_knowledge/server.py || { echo "ERRO: blink_knowledge"; exit 1; }
test -f mcp_servers/blink_state/server.py || { echo "ERRO: blink_state"; exit 1; }
test -f mcp_servers/blink_medware/server.py || { echo "ERRO: blink_medware"; exit 1; }
test -f mcp_servers/blink_kommo/server.py || { echo "ERRO: blink_kommo"; exit 1; }
test -f mcp_servers/blink_whatsapp/server.py || { echo "ERRO: blink_whatsapp"; exit 1; }
test -f mcp_servers/blink_host/orchestrator.py || { echo "ERRO: blink_host"; exit 1; }

# Syntax check (TODOS os 15 arquivos)
echo "→ Verificando syntax dos 15 arquivos..."
python3 -c "
import ast
import sys
arquivos = [
    'mcp_servers/blink_calendar/server.py',
    'mcp_servers/blink_calendar/models.py',
    'mcp_servers/blink_calendar/test_server.py',
    'mcp_servers/blink_knowledge/server.py',
    'mcp_servers/blink_knowledge/test_server.py',
    'mcp_servers/blink_state/server.py',
    'mcp_servers/blink_state/test_server.py',
    'mcp_servers/blink_medware/server.py',
    'mcp_servers/blink_medware/test_server.py',
    'mcp_servers/blink_kommo/server.py',
    'mcp_servers/blink_kommo/test_server.py',
    'mcp_servers/blink_whatsapp/server.py',
    'mcp_servers/blink_whatsapp/test_server.py',
    'mcp_servers/blink_host/orchestrator.py',
    'mcp_servers/blink_host/test_orchestrator.py',
]
falhas = 0
for f in arquivos:
    try:
        ast.parse(open(f).read())
    except Exception as e:
        print(f'ERRO SYNTAX {f}: {e}')
        falhas += 1
if falhas:
    sys.exit(1)
print('✓ Todos os 15 arquivos com syntax OK')
" || exit 1

echo ""
echo "→ Para rodar pytest dos servidores (opcional, requer uv + deps):"
echo "  cd mcp_servers && uv sync --all-extras && uv run pytest -v"
echo ""

read -p "Pode commitar e fazer push? (y/N): " resp
if [ "$resp" != "y" ] && [ "$resp" != "Y" ]; then
    echo "Cancelado."
    exit 0
fi

# Git
git add mcp_servers/ \
        PLANO_REESTRUTURACAO_MCP_BLINK.md \
        PUSH_MCP_RESTRUCTURE_COMPLETA.command

git diff --staged --stat
echo ""

git commit -m "feat(mcp): reestruturacao completa Lia em 6 servidores MCP + Host

Implementacao integral do plano PLANO_REESTRUTURACAO_MCP_BLINK.md
baseado no livro 'Dominando o MCP' (Oliveira, 2026).

Entrega EM PARALELO ao monolito atual (voice_agent/). Nao afeta producao.
Pasta nova: mcp_servers/.

ARQUITETURA (livro 1.1):
- 6 servidores MCP especializados (Cliente-Host-Servidor separados)
- 1 Host orquestrador (loop agentico — livro 7.2)
- Stdio transport (livro 1.3.1) — local, sem porta de rede

SERVIDORES IMPLEMENTADOS:

1. blink_calendar — Sprint 1 (Bug C-35 eliminado)
   3 tools, 3 resources, 1 prompt + Pydantic estrito
   22 cenarios pytest cobrindo dia da semana × unidade × medico

2. blink_knowledge — Sprint 2 (38 artigos KB como recursos URI)
   3 tools, 2 resources, 1 prompt
   8 cenarios pytest com KB fake

3. blink_state — Sprint 3 (Redis dedup + lock + reserva 10min)
   8 tools, 1 resource
   16 cenarios pytest com fakeredis (anti-Bug C-11, Fix #183, Regra E6-B)

4. blink_medware — Sprint 4 (tuning C-38b + janela E6-C nativos)
   3 tools, 2 resources
   16 cenarios pytest com httpx mock
   timeout 20s, retry 1x fail-fast, janela default 14d, validacao Pydantic

5. blink_kommo — Sprint 5 (fix Bug C-12 via GET pos-PATCH)
   5 tools, 2 resources
   11 cenarios pytest cobrindo o fix critico Bug C-12

6. blink_whatsapp — Sprint 6 (8133 + redirect 0710 unificados)
   2 tools, 1 resource
   10 cenarios pytest cobrindo dispatch e redirect automatico

7. blink_host — Host orquestrador
   processar_mensagem_inbound() implementa loop agentico
   6 cenarios pytest

PRINCIPIOS DO LIVRO APLICADOS:
- 1.1.1 Servidor como driver (UMA fonte de dados por servidor)
- 1.2 Recursos vs Ferramentas vs Prompts
- 3.7 Type hints + docstrings ricos (LLM le interface, nao codigo)
- 4.5 Servidor como guardiao (valida ANTES de gravar)
- 5.5 .env nunca no codigo
- 6.1 Logs stderr, nunca print (anti-quebra de protocolo JSON-RPC)
- 6.5 Pydantic estrito (anti-alucinacao de argumento)
- 7.4 Human in the Loop (4 etapas Kommo inativam IA)

BUGS HISTORICOS PREVENIDOS NATIVAMENTE:
- C-11 (dedup), C-12 (Kommo mente), C-21 (atropela protocolo),
- C-27 (duplicacao), C-35 (dia inventado), C-38/C-38b (Medware timeout),
- E6-B (reserva 10min), E6-C (janela cirurgica),
- Padrao 'deixa eu reconsultar agenda' (Sofia, Fabio Philipe)

ESTRUTURA:
  mcp_servers/
  ├── README.md (arquitetura + quick start)
  ├── pyproject.toml (mcp, pydantic, httpx, redis)
  ├── blink_calendar/  (Sprint 1)
  ├── blink_knowledge/ (Sprint 2)
  ├── blink_state/     (Sprint 3)
  ├── blink_medware/   (Sprint 4)
  ├── blink_kommo/     (Sprint 5)
  ├── blink_whatsapp/  (Sprint 6)
  └── blink_host/      (Orquestrador + config.json)

PROXIMO PASSO (apos validacao Fabio):
1. cd mcp_servers && uv sync --all-extras && uv run pytest -v
2. Conectar 1 servidor ao Claude Desktop para teste manual
3. Plugar servidores no voice_agent atual (substituicao gradual)
4. Migracao completa em 8-12 semanas (Sprint 7 e 8 do plano)

🤖 Generated with Claude Cowork — Reestruturacao MCP-first"

git push origin main

echo ""
echo "==============================================================="
echo "  ✓ Push OK. Reestruturacao MCP completa no GitHub."
echo "==============================================================="
echo ""
echo "PROXIMOS PASSOS:"
echo "  1. cd mcp_servers"
echo "  2. uv sync --all-extras"
echo "  3. uv run pytest -v"
echo "  4. Conectar 1 servidor ao Claude Desktop (ver README.md)"
echo ""
read -n 1 -s -r -p "Pressiona qualquer tecla pra fechar..."
echo ""
