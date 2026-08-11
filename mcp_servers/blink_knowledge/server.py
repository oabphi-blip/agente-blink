"""blink-knowledge — Sprint 2.

Servidor MCP que expõe a base de conhecimento clínica/operacional da Blink
como recursos URI MCP. A LLM lê o artigo que precisar, quando precisar, em
vez de receber dump de 50KB no prompt todo turno (anti-Bug C-28).

Princípios do livro aplicados:
- 1.2.1: Recursos passivos (artigos KB são read-only).
- URI padronizada: blink://kb/{slug}
- 6.1: logs stderr.
- 8.2: "Engenheiro de Contexto" — KB versionada com VERSAO_PROMPT.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-knowledge - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-knowledge")


# Caminho para o KB. Em produção sobe via ENV; fallback para path padrão Mac.
import os
KB_PATH = Path(
    os.getenv(
        "BLINK_KB_PATH",
        "/Users/fabiophilipecostamartins/Documents/Claude/Projects/"
        "AGENTE IA BLINK/voice_agent/knowledge_base"
    )
)

mcp = FastMCP("blink-knowledge")


def _slug_from_filename(filename: str) -> str:
    """Converte '22_agenda_dra_karla.md' em 'agenda_dra_karla'."""
    stem = Path(filename).stem
    # Remove prefixo numérico tipo "22_"
    parts = stem.split("_", 1)
    if len(parts) > 1 and parts[0].isdigit():
        return parts[1]
    return stem


def _listar_artigos() -> list[tuple[str, Path]]:
    """Lista todos os .md do KB e seus slugs."""
    if not KB_PATH.exists():
        log.warning("KB_PATH não existe: %s", KB_PATH)
        return []
    artigos = []
    for md_file in sorted(KB_PATH.glob("*.md")):
        slug = _slug_from_filename(md_file.name)
        artigos.append((slug, md_file))
    return artigos


# ─── TOOLS ──────────────────────────────────────────────────────────

@mcp.tool()
def listar_artigos_kb() -> list[dict]:
    """Lista todos os artigos da base de conhecimento clínica/operacional.

    Use para descobrir QUE conhecimento existe antes de pedir um recurso
    específico. Cada artigo cobre um tema (médicos, convênios, valores,
    protocolo de remarcação, etc.).

    Returns:
        Lista de dicts {slug, titulo, uri, arquivo}.
    """
    artigos = _listar_artigos()
    out = []
    for slug, path in artigos:
        # Lê primeira linha como título tentativo
        try:
            with open(path, encoding="utf-8") as f:
                primeira_linha = f.readline().strip()
                titulo = primeira_linha.lstrip("# ").strip() or slug
        except Exception:
            titulo = slug
        out.append({
            "slug": slug,
            "titulo": titulo,
            "uri": f"blink://kb/{slug}",
            "arquivo": path.name,
        })
    log.info("listar_artigos_kb retornou %d artigos", len(out))
    return out


@mcp.tool()
def buscar_no_kb(termo: str, max_resultados: int = 5) -> list[dict]:
    """Busca artigos cujo conteúdo contém o termo (case-insensitive).

    Use quando não souber o slug exato. Procura literal no texto dos
    artigos. Para busca semântica avançada, use o RAG do Host.

    Args:
        termo: Termo a buscar. Ex: "Inas GDF", "catarata", "sinal".
        max_resultados: Limite de artigos a retornar. Default 5.

    Returns:
        Lista de dicts {slug, titulo, uri, trecho} ordenada por relevância
        (número de ocorrências).
    """
    if not termo or len(termo.strip()) < 2:
        raise ValueError("Termo deve ter pelo menos 2 caracteres")

    termo_lower = termo.lower().strip()
    artigos = _listar_artigos()
    matches = []

    for slug, path in artigos:
        try:
            with open(path, encoding="utf-8") as f:
                conteudo = f.read()
            contagem = conteudo.lower().count(termo_lower)
            if contagem > 0:
                # Pega trecho ao redor da primeira ocorrência
                idx = conteudo.lower().find(termo_lower)
                inicio = max(0, idx - 100)
                fim = min(len(conteudo), idx + len(termo) + 100)
                trecho = conteudo[inicio:fim].replace("\n", " ")
                matches.append({
                    "slug": slug,
                    "uri": f"blink://kb/{slug}",
                    "ocorrencias": contagem,
                    "trecho": f"...{trecho}...",
                })
        except Exception as e:
            log.warning("Erro ao ler %s: %s", path, e)

    matches.sort(key=lambda m: m["ocorrencias"], reverse=True)
    return matches[:max_resultados]


@mcp.tool()
def ler_artigo_kb(slug: str) -> str:
    """Lê artigo específico do KB pelo slug.

    Mesma operação de ler resource blink://kb/{slug}, mas como tool
    para clientes que não suportam resources nativamente.

    Args:
        slug: Identificador curto do artigo. Ex: "agenda_dra_karla".

    Returns:
        Conteúdo completo do artigo em Markdown.
    """
    artigos = _listar_artigos()
    for s, path in artigos:
        if s == slug:
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise ValueError(
        f"Artigo '{slug}' não encontrado. Use listar_artigos_kb() para ver disponíveis."
    )


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("blink://kb/index")
def kb_index() -> str:
    """Índice completo do KB com todos os slugs disponíveis."""
    artigos = _listar_artigos()
    linhas = ["BASE DE CONHECIMENTO BLINK OFTALMOLOGIA\n"]
    linhas.append(f"Total de artigos: {len(artigos)}\n")
    for slug, path in artigos:
        linhas.append(f"- blink://kb/{slug}  ({path.name})")
    return "\n".join(linhas)


@mcp.resource("blink://kb/{slug}")
def kb_artigo(slug: str) -> str:
    """Conteúdo de um artigo do KB."""
    return ler_artigo_kb(slug)


# ─── PROMPTS ────────────────────────────────────────────────────────

@mcp.prompt()
def consultar_kb_antes_responder(topico: str) -> str:
    """Prompt para forçar consulta ao KB antes de responder paciente."""
    return (
        f"Antes de responder ao paciente sobre {topico}, consulte o KB:\n"
        f"1. Chame listar_artigos_kb para ver o que existe.\n"
        f"2. Chame buscar_no_kb('{topico}') para encontrar artigos relevantes.\n"
        f"3. Leia o(s) artigo(s) relevantes via ler_artigo_kb(slug).\n"
        f"4. Responda baseado apenas no que está documentado. Se não houver "
        f"informação no KB, diga 'Vou verificar com a equipe' em vez de inventar."
    )


if __name__ == "__main__":
    log.info("Iniciando blink-knowledge MCP server. KB_PATH=%s", KB_PATH)
    mcp.run()
