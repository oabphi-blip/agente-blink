"""
voice_agent/fallback_humano.py — Bug C-142 (14/08/2026)

REGRA FÁBIO (14/08/2026):
  "somente mensagem determinística. Se o agente não souber, tem que transferir
   para atendimento humano e desativar IA. Para que o agente não fique inventando
   resposta e prejudicando o atendimento."

PROBLEMA:
  Lia repetiu "pode me contar se a consulta é para um bebê, criança, adolescente
  ou adulto?" às 9:35 e às 9:36 (lead 24452256 Sinara). A anti-repetição C-127
  depende de `ultima_msg_outbound` no ctx — campo que estava vazio porque
  TODA CONVERSA (C-133) não estava gravando. Resultado: anti-repetição cega →
  Lia entra em loop → equipe humana gasta tempo corrigindo.

SOLUÇÃO (camada de última linha):
  Se o pipeline gera uma resposta que já foi enviada ao paciente (overlap ≥70%
  com `ultima_msg_outbound`), em vez de enviar a repetição:
  1. Envia mensagem de handoff ao paciente
  2. Grava flag Redis blink:c142_fallback_humano:{lead_id} (TTL 24h)
  3. Pipeline lê o flag → move pra 1-ATENDIMENTO HUMANO + desativa IA

Isso garante que NUNCA enviaremos 2x a mesma pergunta ao paciente.

Toggle: FALLBACK_HUMANO_ATIVADO (default ON).
Redis flag: blink:c142_fallback_humano:{lead_id} TTL 86400s (24h).
Rollback: FALLBACK_HUMANO_ATIVADO=0 em Easypanel → Implantar.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# Threshold de overlap léxico para detectar repetição (mesmo do C-127)
_OVERLAP_THRESHOLD = 0.70

# Mínimo de palavras relevantes para comparar (evita falso positivo em mensagens curtas)
_MIN_PALAVRAS = 6

# Stopwords PT-BR que não contribuem para detecção de repetição
_STOPWORDS = frozenset({
    "a", "o", "e", "de", "do", "da", "em", "um", "uma", "para", "com",
    "se", "que", "por", "mais", "como", "mas", "ou", "ao", "dos", "das",
    "nos", "nas", "seu", "sua", "isso", "este", "esta", "esse", "essa",
    "me", "te", "nos", "lhe", "já", "não", "sim", "ok", "né", "tá",
    "então", "aqui", "ali", "isso", "isto", "aquilo", "pode", "vai",
})


def _ativado() -> bool:
    return os.getenv("FALLBACK_HUMANO_ATIVADO", "1").lower() not in (
        "0", "false", "no", "off"
    )


def _palavras_relevantes(texto: str) -> set[str]:
    """Extrai palavras relevantes (sem stopwords) em lowercase."""
    palavras = re.findall(r"[a-záàâãéèêíìîóòôõúùûçñ]{3,}", texto.lower())
    return {p for p in palavras if p not in _STOPWORDS}


def _overlap(texto_a: str, texto_b: str) -> float:
    """Calcula overlap léxico entre dois textos. Retorna 0.0 a 1.0."""
    pals_a = _palavras_relevantes(texto_a)
    pals_b = _palavras_relevantes(texto_b)
    if not pals_a or not pals_b:
        return 0.0
    intersecao = pals_a & pals_b
    return len(intersecao) / min(len(pals_a), len(pals_b))


def _e_pergunta_repetida(candidata: str, ultima_outbound: str) -> bool:
    """Detecta se a resposta candidata é repetição da última outbound."""
    if not candidata or not ultima_outbound:
        return False
    pals_cand = _palavras_relevantes(candidata)
    if len(pals_cand) < _MIN_PALAVRAS:
        return False  # Muito curta — pode ser resposta legítima diferente
    ratio = _overlap(candidata, ultima_outbound)
    return ratio >= _OVERLAP_THRESHOLD


def _montar_handoff_c142(nome: str | None) -> str:
    """Mensagem de handoff enviada ao paciente quando detecta repetição."""
    saud = f"{nome}, " if nome else ""
    return (
        f"{saud}vou conectar você agora com nossa equipe para um atendimento "
        f"mais personalizado. Um momento! 🤝"
    )


def verificar_e_tratar_repeticao(
    ctx: dict,
    candidata: str,
    redis_client=None,
) -> Optional[str]:
    """
    Verifica se `candidata` repete `ultima_msg_outbound`. Se sim:
    - Grava flag Redis blink:c142_fallback_humano:{lead_id}
    - Retorna mensagem de handoff (que o pipeline deve enviar em vez da candidata)

    Se não repete → retorna None (candidata pode ser enviada normalmente).

    Assinatura compatível com fail-open: se ctx=None ou exceção → None.
    """
    if not _ativado():
        return None
    try:
        if not ctx or not candidata:
            return None

        known = (ctx.get("known") or {}) if isinstance(ctx, dict) else {}
        ultima_outbound = (
            known.get("ultima_msg_outbound") or ""
        ).strip()

        if not ultima_outbound:
            # Sem histórico de outbound → não há como detectar repetição
            return None

        if not _e_pergunta_repetida(candidata, ultima_outbound):
            return None

        # Repetição detectada
        lead_id = ctx.get("lead_id") if isinstance(ctx, dict) else None
        nome = known.get("nome_contato") or known.get("nome")

        log.warning(
            "[C-142] REPETIÇÃO DETECTADA lead=%s — candidata='%s...' vs ultima='%s...'",
            lead_id,
            candidata[:80],
            ultima_outbound[:80],
        )

        # Grava flag Redis para pipeline mover pra ATENDIMENTO HUMANO
        if redis_client and lead_id:
            try:
                redis_client.setex(
                    f"blink:c142_fallback_humano:{lead_id}",
                    86400,  # 24h
                    "1",
                )
            except Exception as exc_r:  # noqa: BLE001
                log.warning("[C-142] Redis setex falhou: %s", exc_r)

        return _montar_handoff_c142(nome)

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-142] verificar_e_tratar_repeticao falhou: %s", exc)
        return None
