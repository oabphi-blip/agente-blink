"""Memória de bugs por embedding — defesa pré-envio via similaridade.

Origem: discussão Fábio 01/06/2026 noite. Os 13 filtros regex em
`responder.py` pegam padrões antigos; o juiz Haiku 4.5 pega semântica
nova. Esta camada adiciona uma TERCEIRA defesa: cada bug histórico
(Aurora, Juliene, Adelia, Diones, Esther) tem a frase exata que a Lia
DEU registrada como embedding. Antes de enviar resposta nova, calcula
cosine vs todos os bugs registrados. Se similaridade >= LIMIAR
(default 0.85), bloqueia e substitui pelo fallback seguro.

Vantagem sobre regex: generaliza sem precisar nomear cada padrão.
Vantagem sobre o juiz Haiku: deterministico, instantâneo (~10ms),
sem chamada de API.

Custo: ~$0.0001/turno (text-embedding-3-small = $0.02 / 1M tokens,
turno típico ~200 tokens).

Persistência: catálogo de bugs fica em Redis hash
`blink:memoria_bugs:catalogo` (chave=bug_id, valor=JSON com
{texto_lia, embedding_b64, ctx_resumo, motivo}). Reidrata na boot do
módulo. Bugs novos podem ser inseridos via endpoint
/admin/memoria-bugs/registrar.

Liga via env `MEMORIA_BUGS_ENABLED=1` (default off — rollout gradual).
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


LIMIAR_DEFAULT = 0.85
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Chave Redis do catálogo de bugs (hash)
REDIS_KEY_CATALOGO = "blink:memoria_bugs:catalogo"

# Fallback genérico quando bate similaridade com bug antigo
FALLBACK_SIMILAR_BUG = (
    "Anotei aqui! Em instantes confirmo com a equipe e te respondo. "
    "Se preferir, me diga sua dúvida específica que eu agilizo."
)


# Catálogo SEMENTE — bugs históricos canônicos. Sobe pra Redis na
# primeira ativação. Pode ser editado/incrementado depois.
SEMENTE_BUGS: list[dict[str, str]] = [
    {
        "bug_id": "aurora_retrocesso_ja_agendado",
        "texto_lia": (
            "Quer agendar uma consulta? Que dia da semana é melhor "
            "pra você? Temos terça, quarta e sexta com a Dra. Karla."
        ),
        "ctx_resumo": "ja_agendado:True",
        "motivo": (
            "Lead já AGENDADO mas Lia oferece slot novo (bug Aurora "
            "23907418, maio/26)"
        ),
    },
    {
        "bug_id": "juliene_promete_retorno_humano",
        "texto_lia": (
            "Vou registrar sua preferência para a equipe finalizar — "
            "retorno em horário comercial, segunda a sexta de 8h às 18h."
        ),
        "ctx_resumo": "agenda_vazia:True etapa:AGENDAR",
        "motivo": (
            "Lia alucina handoff humano quando Medware vem vazio "
            "(bug Juliene 24053159, 31/05/26)"
        ),
    },
    {
        "bug_id": "adelia_exemplo_aprovado_literal",
        "texto_lia": (
            "Exemplo aprovado: terça 03/06 às 10h ou quarta 04/06 "
            "às 14h. Qual prefere?"
        ),
        "ctx_resumo": "agenda_vazia:True medware:vazio",
        "motivo": (
            "Lia copia frase 'Exemplo aprovado' do prompt quando "
            "Medware vem vazio (bug Adelia 24056883, 01/06/26)"
        ),
    },
    {
        "bug_id": "diones_medico_trocado",
        "texto_lia": (
            "Tenho essas opções com o Dr. Fabrício Freitas:\n"
            "1️⃣ segunda 08/06 às 13:30\n"
            "2️⃣ terça 09/06 às 14:00"
        ),
        "ctx_resumo": "medico_ctx:Karla",
        "motivo": (
            "Lia oferece slot com médico DIFERENTE do ctx do lead "
            "(bug Diones 23742328, 01/06/26)"
        ),
    },
    {
        "bug_id": "esther_oferta_pos_agendado_imagem",
        "texto_lia": (
            "Recebi, obrigado! Nossa equipe vai conferir os documentos. "
            "Enquanto isso, deixa eu trazer os horários disponíveis "
            "para a Esther com a Dra. Karla em Águas Claras no "
            "início da noite. Me dá só mais um instante! ⏳"
        ),
        "ctx_resumo": "ja_agendado:True imagem_inbound:True",
        "motivo": (
            "Lia volta a oferecer slot após paciente enviar imagem da "
            "carteirinha em lead AGENDADO (bug Esther 24060221, 01/06/26)"
        ),
    },
]


# --- utilitários numéricos (sem numpy) ---------------------------------

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine(a: list[float], b: list[float]) -> float:
    """Similaridade cosine ∈ [-1, 1]. Aceita listas mesmo tamanho."""
    if not a or not b or len(a) != len(b):
        return 0.0
    na = _norm(a)
    nb = _norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return _dot(a, b) / (na * nb)


def _b64_encode_embedding(vec: list[float]) -> str:
    """Compacta embedding em base64 pra persistir em Redis (mais barato
    que JSON serializado)."""
    import struct
    raw = struct.pack(f"{len(vec)}f", *vec)
    return base64.b64encode(raw).decode("ascii")


def _b64_decode_embedding(s: str) -> list[float]:
    import struct
    raw = base64.b64decode(s)
    n = len(raw) // 4
    return list(struct.unpack(f"{n}f", raw))


# --- dataclass ---------------------------------------------------------

@dataclass
class BugRegistrado:
    bug_id: str
    texto_lia: str
    ctx_resumo: str
    motivo: str
    embedding: list[float] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "bug_id": self.bug_id,
            "texto_lia": self.texto_lia,
            "ctx_resumo": self.ctx_resumo,
            "motivo": self.motivo,
            "embedding_b64": _b64_encode_embedding(self.embedding),
        }

    @classmethod
    def from_json_dict(cls, d: dict) -> "BugRegistrado":
        emb_b64 = d.get("embedding_b64") or ""
        emb = _b64_decode_embedding(emb_b64) if emb_b64 else []
        return cls(
            bug_id=d["bug_id"],
            texto_lia=d["texto_lia"],
            ctx_resumo=d.get("ctx_resumo", ""),
            motivo=d.get("motivo", ""),
            embedding=emb,
        )


@dataclass
class MatchResultado:
    """Resultado de um match contra o catálogo de bugs."""
    bug_id: str = ""
    similaridade: float = 0.0
    motivo: str = ""
    deve_substituir: bool = False


# --- núcleo da memória -------------------------------------------------

class MemoriaBugs:
    """Catálogo de bugs registrados + checagem por similaridade.

    Uso:
        mem = MemoriaBugs.from_env(redis_client)
        if mem:
            res = mem.checar(lia_text="...", ctx={...})
            if res.deve_substituir:
                resposta = FALLBACK_SIMILAR_BUG
    """

    def __init__(
        self,
        openai_api_key: str,
        redis_client: Any,
        limiar: float = LIMIAR_DEFAULT,
        modelo: str = EMBEDDING_MODEL,
        timeout: float = 8.0,
    ):
        from openai import OpenAI
        self._client = OpenAI(api_key=openai_api_key, timeout=timeout)
        self._redis = redis_client
        self.limiar = limiar
        self.modelo = modelo
        # Catálogo em memória (lazy-loaded de Redis)
        self._catalogo: list[BugRegistrado] = []
        self._carregado = False

    # -------- factory ---------------------------------------------------

    @classmethod
    def from_env(cls, redis_client: Any) -> Optional["MemoriaBugs"]:
        if os.getenv("MEMORIA_BUGS_ENABLED", "0") != "1":
            return None
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            log.warning(
                "[MEMORIA_BUGS] MEMORIA_BUGS_ENABLED=1 mas sem "
                "OPENAI_API_KEY"
            )
            return None
        try:
            limiar = float(os.getenv("MEMORIA_BUGS_LIMIAR", str(LIMIAR_DEFAULT)))
        except (TypeError, ValueError):
            limiar = LIMIAR_DEFAULT
        return cls(openai_api_key=key, redis_client=redis_client, limiar=limiar)

    # -------- embedding -------------------------------------------------

    def _embed(self, texto: str) -> list[float]:
        """Gera embedding via OpenAI. Trunca texto pra 8k chars."""
        if not texto:
            return []
        t = texto.strip()
        if len(t) > 8000:
            t = t[:8000]
        try:
            resp = self._client.embeddings.create(
                model=self.modelo,
                input=t,
            )
            data = resp.data[0]
            return list(data.embedding or [])
        except Exception as e:  # noqa: BLE001
            log.warning("[MEMORIA_BUGS] erro embedding: %s", e)
            return []

    # -------- catálogo --------------------------------------------------

    def _carregar_redis(self) -> None:
        """Lê o catálogo do Redis (lazy)."""
        if self._carregado:
            return
        self._carregado = True
        if not self._redis:
            return
        try:
            raw_dict = self._redis.hgetall(REDIS_KEY_CATALOGO) or {}
            for k, v in raw_dict.items():
                try:
                    if isinstance(v, bytes):
                        v = v.decode("utf-8")
                    d = json.loads(v)
                    self._catalogo.append(BugRegistrado.from_json_dict(d))
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "[MEMORIA_BUGS] entrada inválida (key=%s): %s", k, e,
                    )
        except Exception as e:  # noqa: BLE001
            log.warning("[MEMORIA_BUGS] erro ao carregar Redis: %s", e)

    def carregar_semente_se_vazio(self) -> int:
        """Se Redis está vazio, popula com o catálogo SEMENTE.
        Devolve quantos foram registrados."""
        self._carregar_redis()
        if self._catalogo:
            return 0
        n = 0
        for s in SEMENTE_BUGS:
            ok = self.registrar(
                bug_id=s["bug_id"],
                texto_lia=s["texto_lia"],
                ctx_resumo=s.get("ctx_resumo", ""),
                motivo=s.get("motivo", ""),
            )
            if ok:
                n += 1
        log.info("[MEMORIA_BUGS] semente carregada: %d bugs", n)
        return n

    def registrar(
        self,
        bug_id: str,
        texto_lia: str,
        ctx_resumo: str = "",
        motivo: str = "",
    ) -> bool:
        """Adiciona bug novo ao catálogo. Gera embedding + persiste."""
        if not bug_id or not texto_lia:
            return False
        emb = self._embed(texto_lia)
        if not emb:
            return False
        bug = BugRegistrado(
            bug_id=bug_id,
            texto_lia=texto_lia,
            ctx_resumo=ctx_resumo,
            motivo=motivo,
            embedding=emb,
        )
        # Persiste em Redis
        if self._redis:
            try:
                self._redis.hset(
                    REDIS_KEY_CATALOGO,
                    bug_id,
                    json.dumps(bug.to_json_dict()),
                )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[MEMORIA_BUGS] erro ao persistir %s: %s", bug_id, e,
                )
        # Atualiza cache em memória
        # Remove versão antiga do mesmo bug_id se existir
        self._catalogo = [
            x for x in self._catalogo if x.bug_id != bug_id
        ]
        self._catalogo.append(bug)
        return True

    # -------- checagem --------------------------------------------------

    def checar(
        self,
        lia_text: str,
        ctx: Optional[dict] = None,
    ) -> MatchResultado:
        """Compara lia_text vs todos os bugs do catálogo.

        Devolve o melhor match (maior similaridade). `deve_substituir`
        fica True se similaridade >= limiar.
        """
        if not lia_text or not lia_text.strip():
            return MatchResultado()
        self._carregar_redis()
        if not self._catalogo:
            return MatchResultado()
        emb_atual = self._embed(lia_text)
        if not emb_atual:
            return MatchResultado()
        melhor = MatchResultado(similaridade=-2.0)  # < -1 = sentinela
        for bug in self._catalogo:
            if not bug.embedding:
                continue
            sim = cosine(emb_atual, bug.embedding)
            if sim > melhor.similaridade:
                melhor.bug_id = bug.bug_id
                melhor.similaridade = sim
                melhor.motivo = bug.motivo
        # Normaliza sentinela pra 0 se ninguém bateu
        if melhor.similaridade < -1.0:
            melhor.similaridade = 0.0
        melhor.deve_substituir = melhor.similaridade >= self.limiar
        return melhor

    def listar(self) -> list[dict]:
        """Devolve catálogo sem o embedding (pra endpoint admin)."""
        self._carregar_redis()
        return [
            {
                "bug_id": b.bug_id,
                "texto_lia_preview": b.texto_lia[:200],
                "ctx_resumo": b.ctx_resumo,
                "motivo": b.motivo,
                "embedding_dims": len(b.embedding),
            }
            for b in self._catalogo
        ]
