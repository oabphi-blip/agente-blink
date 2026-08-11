#!/usr/bin/env python3
"""MCP Memória Blink — memória persistente cross-session para Claude.

Resolve o gap admitido em 29/05/2026: as 3 camadas que vendi como "memória
persistente" (CLAUDE.md + skill + Obsidian) são documentação que releio,
não memória ativa. Esse MCP é a memória REAL.

Como funciona:
- SQLite local em ~/.claude-memoria-blink.db
- 3 tools expostas via MCP:
    memoria_get(topico)        → recupera valor
    memoria_set(topico, valor) → grava valor com timestamp
    memoria_list()             → lista todos os tópicos com data de última
                                 atualização

Quando registrar:
- "ultimo-deploy" → SHA do último commit que foi deployado
- "ultima-conversa-fabio" → resumo de cada conversa importante
- "bug-em-andamento" → bug que tô investigando entre sessões
- "decisao-pendente" → decisões que Fábio precisa tomar
- "skill-instalado" → confirmação de instalação correta
- "convenios-mapeados-em" → data da última auditoria PLANO_CODES

Instalação (no Mac):
1. pip3 install mcp
2. Adicionar no config Cowork MCP:
   {"mcpServers": {"memoria-blink": {"command": "python3", "args": ["/caminho/server.py"]}}}
3. Reiniciar Cowork

Próxima sessão Claude vai ver as 3 tools automaticamente.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.claude-memoria-blink.db"))


def _conn() -> sqlite3.Connection:
    """Conexão SQLite com schema garantido."""
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS memoria (
            topico TEXT PRIMARY KEY,
            valor TEXT NOT NULL,
            tipo TEXT DEFAULT 'string',
            atualizado_em TEXT NOT NULL,
            origem_sessao TEXT
        )
    """)
    return c


def memoria_get(topico: str) -> dict:
    """Recupera valor gravado pra um tópico. Retorna dict com valor + meta."""
    c = _conn()
    try:
        row = c.execute(
            "SELECT valor, tipo, atualizado_em, origem_sessao FROM memoria WHERE topico = ?",
            (topico,),
        ).fetchone()
        if not row:
            return {"ok": False, "motivo": "topico_nao_encontrado", "topico": topico}
        valor, tipo, atualizado_em, origem = row
        if tipo == "json":
            try:
                valor = json.loads(valor)
            except (ValueError, TypeError):
                pass
        return {
            "ok": True,
            "topico": topico,
            "valor": valor,
            "tipo": tipo,
            "atualizado_em": atualizado_em,
            "origem_sessao": origem,
        }
    finally:
        c.close()


def memoria_set(topico: str, valor, origem_sessao: str = "") -> dict:
    """Grava ou atualiza um tópico. valor pode ser str, int, dict, list."""
    if not topico or not str(topico).strip():
        return {"ok": False, "motivo": "topico_vazio"}
    c = _conn()
    try:
        if isinstance(valor, (dict, list)):
            tipo = "json"
            valor_str = json.dumps(valor, ensure_ascii=False)
        else:
            tipo = "string"
            valor_str = str(valor)
        c.execute(
            "INSERT OR REPLACE INTO memoria (topico, valor, tipo, atualizado_em, origem_sessao) "
            "VALUES (?, ?, ?, ?, ?)",
            (topico.strip(), valor_str, tipo, datetime.now().isoformat(), origem_sessao or ""),
        )
        c.commit()
        return {"ok": True, "topico": topico, "tipo": tipo}
    finally:
        c.close()


def memoria_list() -> dict:
    """Lista todos os tópicos com data de última atualização."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT topico, tipo, atualizado_em, origem_sessao FROM memoria "
            "ORDER BY atualizado_em DESC"
        ).fetchall()
        return {
            "ok": True,
            "total": len(rows),
            "topicos": [
                {
                    "topico": r[0],
                    "tipo": r[1],
                    "atualizado_em": r[2],
                    "origem_sessao": r[3] or "",
                }
                for r in rows
            ],
        }
    finally:
        c.close()


def memoria_delete(topico: str) -> dict:
    """Remove um tópico (uso explícito apenas)."""
    c = _conn()
    try:
        cur = c.execute("DELETE FROM memoria WHERE topico = ?", (topico,))
        c.commit()
        return {"ok": True, "removidos": cur.rowcount}
    finally:
        c.close()


# ============================================================
# MCP Server (stdio)
# ============================================================
def _mcp_serve():
    """Loop MCP via stdio. Recebe JSON-RPC, devolve resultado."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        print(
            "ERRO: pip install mcp (no Mac: pip3 install mcp --break-system-packages)",
            file=sys.stderr,
        )
        sys.exit(1)

    import asyncio

    server = Server("memoria-blink")

    @server.list_tools()
    async def _tools():
        return [
            Tool(
                name="memoria_get",
                description=(
                    "Recupera valor gravado pra um tópico de memória persistente. "
                    "Use no início da conversa pra carregar contexto de sessões "
                    "anteriores. Ex: memoria_get('ultimo-deploy')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"topico": {"type": "string"}},
                    "required": ["topico"],
                },
            ),
            Tool(
                name="memoria_set",
                description=(
                    "Grava ou atualiza um tópico de memória persistente. "
                    "Use pra registrar decisões, deploys, bugs em andamento, "
                    "ou qualquer fato que próxima sessão precisa lembrar. "
                    "Valor pode ser texto, número, dict ou lista (auto-detect)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topico": {"type": "string"},
                        "valor": {},
                        "origem_sessao": {"type": "string"},
                    },
                    "required": ["topico", "valor"],
                },
            ),
            Tool(
                name="memoria_list",
                description=(
                    "Lista todos os tópicos com data de última atualização. "
                    "Use no início da sessão pra ver o que existe na memória."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def _call(name: str, args: dict):
        if name == "memoria_get":
            res = memoria_get(args.get("topico", ""))
        elif name == "memoria_set":
            res = memoria_set(
                args.get("topico", ""),
                args.get("valor", ""),
                args.get("origem_sessao", ""),
            )
        elif name == "memoria_list":
            res = memoria_list()
        else:
            res = {"ok": False, "motivo": "tool_desconhecida"}
        return [TextContent(type="text", text=json.dumps(res, ensure_ascii=False))]

    async def _main():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    asyncio.run(_main())


# ============================================================
# CLI standalone (sem MCP, pra teste)
# ============================================================
def _cli():
    if len(sys.argv) < 2:
        print("Uso: server.py get|set|list|delete [args]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "get" and len(sys.argv) >= 3:
        print(json.dumps(memoria_get(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "set" and len(sys.argv) >= 4:
        print(json.dumps(memoria_set(sys.argv[2], sys.argv[3]), indent=2, ensure_ascii=False))
    elif cmd == "list":
        print(json.dumps(memoria_list(), indent=2, ensure_ascii=False))
    elif cmd == "delete" and len(sys.argv) >= 3:
        print(json.dumps(memoria_delete(sys.argv[2]), indent=2, ensure_ascii=False))
    elif cmd == "mcp":
        _mcp_serve()
    else:
        print("Uso: server.py {get TOPICO | set TOPICO VALOR | list | delete TOPICO | mcp}")


if __name__ == "__main__":
    if "--mcp" in sys.argv or os.environ.get("MEMORIA_BLINK_MCP_MODE"):
        _mcp_serve()
    else:
        _cli()
