"""Vector store dos bugs históricos — Camada 2 da Memória Ativa.

Origem: Fábio 12/07/2026 — após 60 dias de bugs "Claude Cowork repete
erros passados", indexação semântica do CLAUDE.md como fonte de verdade.

Uso:
    from voice_agent.memoria_vector import buscar_bug_similar

    resultado = buscar_bug_similar("Lia mentiu agenda fora do ar")
    # → [{'bug_id': 'C-42', 'trecho': '...', 'score': 0.72,
    #     'fix_aplicado': 'FRASES_BANIDAS + regex sempre-ON'}, ...]

Design:
    - SQLite embutido (arquivo local em `~/.cache/blink_memoria_bugs.db`)
    - TF-IDF via scikit-learn (leve, sem downloads de modelos)
    - Chunks do CLAUDE.md por seção "### 0. (DATA) Bug C-NN"
    - Reindex incremental via hash MD5 (só re-indexa se conteúdo mudou)
    - Zero API externa, zero dependência de rede

Toggle: MEMORIA_VECTOR_ATIVADO (default ON).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_DEFAULT_DB = str(Path.home() / ".cache" / "blink_memoria_bugs.db")
_CLAUDE_MD = str(
    Path("/Users/fabiophilipecostamartins/Documents/Claude/Projects/"
         "AGENTE IA BLINK/CLAUDE.md")
)


def _ativado() -> bool:
    return (os.getenv("MEMORIA_VECTOR_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off", "",
    )


# ═══════════════════════════════════════════════════════════════════════
# PARSER — extrai chunks de bugs do CLAUDE.md
# ═══════════════════════════════════════════════════════════════════════

# Ex.: "### 0. (12/07/2026) Bug C-43 — Etapa nova ..."
_HEADER_BUG = re.compile(
    r"^###\s+0?\.?\s*\(([^)]+)\)\s+Bug\s+(C-\d+[a-z]?)\s*—?\s*(.+?)$",
    re.MULTILINE,
)


def extrair_chunks_bugs(texto_claude_md: str) -> list[dict[str, str]]:
    """Divide o CLAUDE.md em chunks por bug indexado.

    Cada chunk = de "### 0. (DATA) Bug C-NN" até o próximo header ###.

    Returns:
        list[dict] com chaves: bug_id, data, titulo, corpo
    """
    if not texto_claude_md:
        return []

    matches = list(_HEADER_BUG.finditer(texto_claude_md))
    chunks: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        inicio = m.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto_claude_md)
        corpo = texto_claude_md[inicio:fim].strip()

        chunks.append({
            "bug_id": m.group(2),
            "data": m.group(1),
            "titulo": m.group(3).strip(),
            "corpo": corpo,
        })
    return chunks


def _hash_texto(texto: str) -> str:
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════
# SQLITE — schema + operações
# ═══════════════════════════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bugs (
    bug_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    titulo TEXT NOT NULL,
    corpo TEXT NOT NULL,
    hash TEXT NOT NULL,
    indexed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bugs_hash ON bugs(hash);
"""


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    caminho = db_path or _DEFAULT_DB
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho)
    conn.executescript(_SCHEMA_SQL)
    return conn


def indexar_claude_md(
    caminho_md: Optional[str] = None,
    db_path: Optional[str] = None,
) -> dict[str, int]:
    """Lê CLAUDE.md, extrai bugs, salva no SQLite (incremental).

    Só atualiza chunk se hash mudou. Rápido: ~50-100 bugs = <500ms.

    Returns:
        dict com {inseridos, atualizados, sem_mudanca, total_bugs}
    """
    if not _ativado():
        return {"toggle_off": 1}

    md_path = caminho_md or _CLAUDE_MD
    try:
        with open(md_path, encoding="utf-8") as f:
            texto = f.read()
    except FileNotFoundError:
        log.warning("CLAUDE.md não encontrado em %s", md_path)
        return {"erro": 1}

    chunks = extrair_chunks_bugs(texto)
    if not chunks:
        return {"total_bugs": 0}

    conn = _get_conn(db_path)
    try:
        import time
        agora = time.time()
        n_ins, n_upd, n_same = 0, 0, 0

        for chunk in chunks:
            corpo = chunk["corpo"]
            novo_hash = _hash_texto(corpo)

            cur = conn.execute(
                "SELECT hash FROM bugs WHERE bug_id = ?",
                (chunk["bug_id"],),
            )
            row = cur.fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO bugs VALUES (?, ?, ?, ?, ?, ?)",
                    (chunk["bug_id"], chunk["data"], chunk["titulo"],
                     corpo, novo_hash, agora),
                )
                n_ins += 1
            elif row[0] != novo_hash:
                conn.execute(
                    "UPDATE bugs SET data=?, titulo=?, corpo=?, "
                    "hash=?, indexed_at=? WHERE bug_id=?",
                    (chunk["data"], chunk["titulo"], corpo,
                     novo_hash, agora, chunk["bug_id"]),
                )
                n_upd += 1
            else:
                n_same += 1

        conn.commit()
        return {
            "inseridos": n_ins,
            "atualizados": n_upd,
            "sem_mudanca": n_same,
            "total_bugs": len(chunks),
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# BUSCA — TF-IDF + cosseno
# ═══════════════════════════════════════════════════════════════════════

# Cache do vetorizador+matriz (lazy, invalidado quando índice muda)
_CACHE: dict[str, Any] = {"vectorizer": None, "matrix": None, "bugs": None}


def _rebuild_cache(db_path: Optional[str] = None) -> None:
    """Rebuilda o cache TF-IDF a partir do SQLite."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            "SELECT bug_id, data, titulo, corpo FROM bugs ORDER BY bug_id",
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        _CACHE["vectorizer"] = None
        _CACHE["matrix"] = None
        _CACHE["bugs"] = []
        return

    corpos = [r[3] for r in rows]

    vec = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        stop_words=None,
        lowercase=True,
    )
    matrix = vec.fit_transform(corpos)

    _CACHE["vectorizer"] = vec
    _CACHE["matrix"] = matrix
    _CACHE["bugs"] = [
        {"bug_id": r[0], "data": r[1], "titulo": r[2], "corpo": r[3]}
        for r in rows
    ]


def buscar_bug_similar(
    descricao: str,
    top_k: int = 3,
    db_path: Optional[str] = None,
    threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """Busca semântica dos bugs mais similares à descrição.

    Args:
        descricao: texto livre (ex: "Lia mentiu agenda fora do ar")
        top_k: número de resultados (default 3)
        threshold: score mínimo (0-1) pra retornar (default 0.05)

    Returns:
        list[dict] com {bug_id, data, titulo, score, trecho}
    """
    if not _ativado():
        return []
    if not descricao or not descricao.strip():
        return []

    # Rebuild cache se vazio
    if _CACHE["vectorizer"] is None:
        _rebuild_cache(db_path)

    if not _CACHE["bugs"]:
        return []

    from sklearn.metrics.pairwise import cosine_similarity

    vec = _CACHE["vectorizer"]
    matrix = _CACHE["matrix"]
    bugs = _CACHE["bugs"]

    q_vec = vec.transform([descricao])
    scores = cosine_similarity(q_vec, matrix).flatten()

    # Top K
    ordem = scores.argsort()[::-1][:top_k]
    resultados: list[dict[str, Any]] = []
    for idx in ordem:
        score = float(scores[idx])
        if score < threshold:
            continue
        bug = bugs[idx]
        # Trecho = 400 chars da parte mais relevante
        trecho = bug["corpo"][:400] + ("..." if len(bug["corpo"]) > 400 else "")
        resultados.append({
            "bug_id": bug["bug_id"],
            "data": bug["data"],
            "titulo": bug["titulo"],
            "score": round(score, 4),
            "trecho": trecho,
        })
    return resultados


def invalidar_cache() -> None:
    """Chama depois de indexar_claude_md pra forçar re-cache."""
    _CACHE["vectorizer"] = None
    _CACHE["matrix"] = None
    _CACHE["bugs"] = None


def contar_bugs_indexados(db_path: Optional[str] = None) -> int:
    """Diagnóstico rápido."""
    conn = _get_conn(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM bugs").fetchone()[0]
    finally:
        conn.close()
