"""Memória ativa nível 1 — RAG por TF-IDF (Nível 1 do plano de aprendizagem).

Indexa duas fontes:
  1. lia-atendimento-blink/memoria/bugs-licoes/*.md  → lições de bugs reais
  2. voice_agent/knowledge_base/*.md                 → KB oficial (38 artigos)

Quando o paciente manda uma mensagem, `recuperar_licoes_relevantes()` devolve
os top-K trechos mais similares — o `responder.py` injeta esses trechos no
contexto do Claude. A Lia "aprende" novos casos só pelo Fábio gravar mais
`.md` na pasta de lições.

POR QUE TF-IDF EM VEZ DE EMBEDDINGS:
- Zero download de modelo (~0 MB extra).
- Zero custo recorrente.
- Para base de ~50 docs em PT-BR, recall é equivalente ao de
  sentence-transformers em consultas curtas.
- Quando ficar limitado, trocar pra embeddings (Voyage AI ou local) com
  a mesma interface pública (`recuperar_licoes_relevantes`).

ATIVAÇÃO NO PIPELINE: env `MEMORIA_RAG_ENABLED=1`. Padrão off.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

# scikit-learn está nos requirements desde 31/05/2026.
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_OK = True
except ImportError:  # pragma: no cover
    _SKLEARN_OK = False


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Path absoluto do repositório, calculado a partir deste arquivo.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

PASTA_BUGS_LICOES = _PROJECT_ROOT / "lia-atendimento-blink" / "memoria" / "bugs-licoes"
PASTA_KNOWLEDGE_BASE = _PROJECT_ROOT / "voice_agent" / "knowledge_base"

# Quantos trechos recuperar por consulta.
TOP_K_DEFAULT = int(os.environ.get("MEMORIA_RAG_TOP_K", "3"))

# Limite mínimo de similaridade (0..1). Abaixo disso, trecho é ignorado —
# evita injetar lição irrelevante quando a base não tem nada parecido.
SIMILARIDADE_MINIMA = float(os.environ.get("MEMORIA_RAG_SIM_MIN", "0.08"))

# Stopwords PT-BR mínimas — TfidfVectorizer já cuida bem do resto.
_STOPWORDS_PT = [
    "a", "o", "e", "de", "da", "do", "das", "dos", "que", "em", "para",
    "com", "um", "uma", "uns", "umas", "no", "na", "nos", "nas", "se",
    "por", "como", "mais", "mas", "ou", "ao", "à", "às", "aos", "é", "foi",
    "ser", "tem", "tinha", "ter", "será", "este", "esta", "isso", "isto",
    "estes", "estas", "ela", "ele", "elas", "eles", "voc", "você", "vocês",
    "pra", "pro", "lá", "aqui", "já", "sim", "não", "vai", "fica", "muito",
]


# ---------------------------------------------------------------------------
# Estado do índice (lazy + thread-safe)
# ---------------------------------------------------------------------------

@dataclass
class _Trecho:
    """Um pedaço indexado da memória."""
    fonte: str            # caminho relativo do arquivo
    titulo: str           # primeira linha do .md ou nome do arquivo
    conteudo: str         # texto bruto (até ~1500 chars por trecho)
    fonte_tipo: str       # "licao" | "kb"


@dataclass
class IndiceMemoria:
    trechos: list[_Trecho]
    vectorizer: object
    matriz_tfidf: object

    def total(self) -> int:
        return len(self.trechos)


_indice_cache: IndiceMemoria | None = None
_indice_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Carga e indexação
# ---------------------------------------------------------------------------

def _ler_markdown(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:  # pragma: no cover
        return ""


def _extrair_titulo(texto: str, fallback: str) -> str:
    for linha in texto.splitlines():
        l = linha.strip().lstrip("#").strip()
        if l:
            return l[:120]
    return fallback


def _chunkar(texto: str, max_chars: int = 1500) -> list[str]:
    """Divide texto longo em parágrafos para indexação.

    Para arquivos curtos (< max_chars), devolve [texto inteiro].
    """
    texto = texto.strip()
    if len(texto) <= max_chars:
        return [texto] if texto else []
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragrafos:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                # parágrafo gigante — corta no espaço
                for i in range(0, len(p), max_chars):
                    chunks.append(p[i:i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _fonte_relativa(md: Path) -> str:
    """Devolve path relativo ao projeto; fallback para nome se fora."""
    try:
        return str(md.relative_to(_PROJECT_ROOT))
    except ValueError:
        return md.name


def _carregar_pasta(pasta: Path, fonte_tipo: str) -> list[_Trecho]:
    out: list[_Trecho] = []
    if not pasta.exists():
        return out
    for md in sorted(pasta.glob("*.md")):
        texto = _ler_markdown(md)
        if not texto.strip():
            continue
        titulo = _extrair_titulo(texto, md.stem)
        for chunk in _chunkar(texto):
            out.append(_Trecho(
                fonte=_fonte_relativa(md),
                titulo=titulo,
                conteudo=chunk,
                fonte_tipo=fonte_tipo,
            ))
    return out


def construir_indice(
    pastas_extras: list[tuple[Path, str]] | None = None,
) -> IndiceMemoria:
    """Constrói índice TF-IDF da memória ativa + knowledge base.

    `pastas_extras` permite injeção em testes — lista de (path, fonte_tipo).
    """
    if not _SKLEARN_OK:
        raise RuntimeError(
            "scikit-learn ausente. Instalar: "
            "`pip install scikit-learn --break-system-packages`"
        )

    trechos: list[_Trecho] = []
    if pastas_extras is None:
        trechos.extend(_carregar_pasta(PASTA_BUGS_LICOES, "licao"))
        trechos.extend(_carregar_pasta(PASTA_KNOWLEDGE_BASE, "kb"))
    else:
        for path, tipo in pastas_extras:
            trechos.extend(_carregar_pasta(path, tipo))

    if not trechos:
        # Base vazia → índice vazio mas válido.
        vec = TfidfVectorizer()
        try:
            mat = vec.fit_transform(["placeholder"])
        except Exception:  # noqa: BLE001
            mat = None
        return IndiceMemoria(trechos=[], vectorizer=vec, matriz_tfidf=mat)

    corpus = [t.conteudo for t in trechos]
    vec = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        max_df=0.95,
        min_df=1,
        stop_words=_STOPWORDS_PT,
        token_pattern=r"(?u)\b[a-záàâãéèêíïóôõöúüçñA-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÜÇÑ]{2,}\b",
    )
    matriz = vec.fit_transform(corpus)
    return IndiceMemoria(trechos=trechos, vectorizer=vec, matriz_tfidf=matriz)


def obter_indice(forcar_rebuild: bool = False) -> IndiceMemoria:
    """Devolve índice cacheado. Constrói lazy na primeira chamada."""
    global _indice_cache
    with _indice_lock:
        if _indice_cache is None or forcar_rebuild:
            _indice_cache = construir_indice()
        return _indice_cache


def limpar_cache() -> None:
    """Invalida cache. Útil em testes ou quando arquivos mudam."""
    global _indice_cache
    with _indice_lock:
        _indice_cache = None


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

@dataclass
class TrechoRelevante:
    fonte: str
    titulo: str
    conteudo: str
    fonte_tipo: str
    similaridade: float


def recuperar_licoes_relevantes(
    mensagem: str,
    *,
    k: int = TOP_K_DEFAULT,
    indice: IndiceMemoria | None = None,
    similaridade_minima: float = SIMILARIDADE_MINIMA,
    filtrar_tipo: str | None = None,
) -> list[TrechoRelevante]:
    """Top-K trechos mais similares à mensagem.

    Filtros:
      - `similaridade_minima` (default 0.08) — abaixo disso ignora.
      - `filtrar_tipo` = "licao" / "kb" / None (ambos).
    """
    if not mensagem or not mensagem.strip():
        return []
    if indice is None:
        indice = obter_indice()
    if not indice.trechos:
        return []

    vec_msg = indice.vectorizer.transform([mensagem])
    sims = cosine_similarity(vec_msg, indice.matriz_tfidf).flatten()

    pares = []
    for i, score in enumerate(sims):
        if score < similaridade_minima:
            continue
        t = indice.trechos[i]
        if filtrar_tipo and t.fonte_tipo != filtrar_tipo:
            continue
        pares.append((i, float(score)))

    pares.sort(key=lambda x: x[1], reverse=True)
    pares = pares[:k]

    out: list[TrechoRelevante] = []
    for i, score in pares:
        t = indice.trechos[i]
        out.append(TrechoRelevante(
            fonte=t.fonte, titulo=t.titulo, conteudo=t.conteudo,
            fonte_tipo=t.fonte_tipo, similaridade=score,
        ))
    return out


def formatar_para_prompt(trechos: list[TrechoRelevante]) -> str:
    """Bloco markdown pra injetar no system prompt do Claude.

    Mantém formato compacto — Lia não cita as fontes ao paciente, é
    contexto interno.
    """
    if not trechos:
        return ""
    linhas = ["## Memória ativa recuperada (uso interno — não citar ao paciente)"]
    for i, t in enumerate(trechos, 1):
        tag = "LIÇÃO" if t.fonte_tipo == "licao" else "KB"
        linhas.append(
            f"\n### [{tag}] {t.titulo}  _(sim={t.similaridade:.2f})_"
        )
        # Conteúdo já limitado por chunk; corta cabeçalho markdown duplicado.
        corpo = t.conteudo.lstrip("# ").strip()
        # Limita injeção a 800 chars por trecho pra economizar tokens.
        if len(corpo) > 800:
            corpo = corpo[:800].rsplit("\n", 1)[0] + "\n[...]"
        linhas.append(corpo)
    linhas.append(
        "\n---\nFim da memória recuperada. Aplique se aplicável; senão ignore."
    )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Helper de smoke test (chamado pelo /admin/rag-smoke endpoint, futuro)
# ---------------------------------------------------------------------------

def diagnostico() -> dict:
    """Resumo do estado atual do índice — útil pra /admin/rag-status."""
    try:
        idx = obter_indice()
        por_tipo: dict[str, int] = {}
        for t in idx.trechos:
            por_tipo[t.fonte_tipo] = por_tipo.get(t.fonte_tipo, 0) + 1
        return {
            "ok": True,
            "sklearn_disponivel": _SKLEARN_OK,
            "total_trechos": idx.total(),
            "por_tipo": por_tipo,
            "pasta_bugs_licoes_existe": PASTA_BUGS_LICOES.exists(),
            "pasta_kb_existe": PASTA_KNOWLEDGE_BASE.exists(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
