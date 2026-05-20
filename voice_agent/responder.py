"""Responder com Claude Sonnet/Haiku — especialista em atendimento e conversão.

Arquitetura:
- INSTRUÇÃO MESTRA oficial Blink como system prompt (autoridade máxima).
- RAG por keywords dos 40 artigos da knowledge_base.
- Roteador inteligente Sonnet vs Haiku por complexidade da mensagem.
- Histórico curto por contato (sliding window).
- Cache de resposta de 30s para evitar duplicata de webhook.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque

from anthropic import Anthropic

from .knowledge import KB_DIR, KnowledgeBase

log = logging.getLogger(__name__)


def _load_master_instruction() -> str:
    path = KB_DIR / "_MASTER_INSTRUCTION.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "Você é a assistente virtual da Blink Oftalmologia."


# Palavras/contextos que exigem Sonnet (mais inteligente, mais caro)
# Para tudo o resto, Haiku (rápido, barato).
SONNET_TRIGGERS = {
    # Urgência e segurança
    "urgência", "urgencia", "emergência", "emergencia", "socorro",
    "trauma", "perdi a visão", "perdi visao", "respingo", "dor forte",
    "dor intensa", "flashes", "secreção", "secrecao", "vermelho extremo",
    # Catarata e venda complexa
    "catarata", "cirurgia", "lente intraocular", "lio", "multifocal",
    "premium", "dr fabricio", "dr fabrício", "fabricio freitas",
    # SDP / Estrabismo / Prisma
    "sdp", "síndrome postural", "sindrome postural", "estrabismo",
    "prisma", "tontura", "deficiência postural", "deficiencia postural",
    # Objeções e situações sensíveis
    "está caro", "esta caro", "muito caro", "vou pensar",
    "cancelar", "reembolso", "remarcar",
    "humano", "atendente", "pessoa de verdade",
    "reclamar", "reclamação", "reclamacao",
    # Pediatria (criança = sensível)
    "filho", "filha", "criança", "crianca", "bebê", "bebe", "filhinho", "filhinha",
}


@dataclass
class _ConversationStore:
    """Histórico em memória com TTL e janela limitada por contato."""
    max_turns: int = 12
    ttl_seconds: int = 60 * 60 * 6  # 6h
    _store: dict[str, Deque[dict]] = field(default_factory=lambda: defaultdict(deque))
    _last_seen: dict[str, float] = field(default_factory=dict)

    def get(self, key: str) -> list[dict]:
        self._gc()
        return list(self._store.get(key, []))

    def append(self, key: str, role: str, content: str) -> None:
        dq = self._store.setdefault(key, deque())
        dq.append({"role": role, "content": content})
        while len(dq) > self.max_turns * 2:
            dq.popleft()
        self._last_seen[key] = time.time()

    def reset(self, key: str) -> None:
        self._store.pop(key, None)
        self._last_seen.pop(key, None)

    def _gc(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for k in [k for k, t in self._last_seen.items() if t < cutoff]:
            self.reset(k)


def _route_model(user_text: str, history_len: int, sonnet: str, haiku: str) -> str:
    """Roteador Sonnet vs Haiku por complexidade.

    Regras:
    - Sonnet se mensagem contém gatilho sensível (urgência, catarata, SDP, objeção, criança).
    - Sonnet se for primeira interação (history vazia) — abre conversa bem.
    - Sonnet em conversas longas (>10 turnos) — manter qualidade.
    - Haiku para confirmações/agradecimentos simples no meio da conversa.
    """
    text_lower = (user_text or "").lower()

    # Primeira interação merece o melhor (cria boa primeira impressão)
    if history_len == 0:
        return sonnet

    # Conversa já bem desenvolvida — manter qualidade
    if history_len > 20:
        return sonnet

    # Triggers sensíveis
    for trig in SONNET_TRIGGERS:
        if trig in text_lower:
            return sonnet

    # Default: Haiku (rápido e barato)
    return haiku


class Responder:
    """Especialista em atendimento e conversão da Blink Oftalmologia."""

    def __init__(
        self,
        api_key: str,
        sonnet_model: str = "claude-sonnet-4-5",
        haiku_model: str = "claude-haiku-4-5-20251001",
        system_prompt: str | None = None,
        max_response_chars: int = 1200,
        knowledge_base: KnowledgeBase | None = None,
    ):
        self._client = Anthropic(api_key=api_key)
        self._sonnet = sonnet_model
        self._haiku = haiku_model
        # System prompt oficial = INSTRUÇÃO MESTRA + artigos por contexto
        self._base_system_prompt = system_prompt or _load_master_instruction()
        self._max_chars = max_response_chars
        self._convos = _ConversationStore()
        self._kb = knowledge_base or KnowledgeBase()

    def reply(self, conversation_key: str, user_text: str) -> dict:
        """Gera resposta para o paciente.

        Returns:
            {"answer": str, "model_used": str, "articles_used": list[str]}
        """
        # 1. Seleciona artigos relevantes da KB
        relevant = self._kb.select_relevant(user_text, max_articles=3, max_chars=12000)

        # 1b. SEMPRE injetar as listas oficiais de convênios (artigos 17 e 18) —
        # são pequenas (~10KB juntas) e críticas: o agente NUNCA pode afirmar
        # "não aceitamos X" sem o catálogo completo na frente. Isso elimina o
        # bug onde "Tribunal" / "STJ" eram negados erradamente.
        mandatory_filenames = [
            "17_convenios_aceitos_lista_oficial.md",
            "18_convenios_NAO_aceitos_lista_oficial.md",
        ]
        existing_filenames = {a.filename for a in relevant}
        mandatory_articles = []
        for fn in mandatory_filenames:
            if fn in existing_filenames:
                continue
            art = self._kb._articles.get(fn)
            if art is not None:
                mandatory_articles.append(art)
        # Listas oficiais primeiro, depois os artigos por RAG
        combined = mandatory_articles + list(relevant)

        kb_block = self._kb.format_for_prompt(combined) if combined else ""

        # 2. Monta system prompt = INSTRUÇÃO MESTRA + KB contextual
        system_prompt = self._base_system_prompt
        if kb_block:
            system_prompt += (
                "\n\n================================================================"
                "\nCONHECIMENTO BLINK RELEVANTE PARA ESTA CONVERSA"
                "\n================================================================"
                f"\n{kb_block}"
                "\n\n================================================================"
                "\nFIM DO CONHECIMENTO. APLIQUE COM AS REGRAS DA INSTRUÇÃO MESTRA ACIMA."
                "\n================================================================"
            )

        # 3. Monta histórico no formato Anthropic (sem system, só user/assistant)
        history = self._convos.get(conversation_key)
        messages = history + [{"role": "user", "content": user_text}]

        # 4. Decide modelo
        model = _route_model(user_text, len(history), self._sonnet, self._haiku)

        # 5. Chama Claude
        response = self._client.messages.create(
            model=model,
            max_tokens=600,
            system=system_prompt,
            messages=messages,
            temperature=0.3,  # baixa pra seguir as regras estritas da Blink
        )

        # Extrai texto da resposta
        answer_parts = [block.text for block in response.content if block.type == "text"]
        answer = "\n".join(answer_parts).strip()

        if len(answer) > self._max_chars:
            answer = answer[: self._max_chars - 1].rstrip() + "…"

        # 6. Persiste no histórico
        self._convos.append(conversation_key, "user", user_text)
        self._convos.append(conversation_key, "assistant", answer)

        log.info(
            "Claude %s respondeu (%d chars, hist=%d, kb=%d artigos)",
            model, len(answer), len(history), len(combined),
        )

        return {
            "answer": answer,
            "model_used": model,
            "articles_used": [a.filename for a in combined],
        }

    def reset(self, conversation_key: str) -> None:
        self._convos.reset(conversation_key)
