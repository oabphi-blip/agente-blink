"""
Bug C-116 (11/08/2026) — Detecção de comprovante Pix pós-C-114 reserva.
========================================================================
Quando paciente escolhe opção "reserva" em C-114 ("poltrona de avião"),
pipeline grava flag Redis blink:c114_aguardando_comprovante:{lead_id} (TTL 7d).

Quando o paciente envia uma IMAGEM no WhatsApp, o webhook converte para
texto sintético:
  - Evolution: "[O paciente acabou de enviar uma imagem/foto pelo WhatsApp..."
  - WA Cloud:  "[O paciente enviou uma imagem pelo WhatsApp..."

Este módulo detecta:
  1. user_text é texto sintético de imagem
  2. flag blink:c114_aguardando_comprovante:{lead_id} ativo no Redis

Se ambos verdade → responde confirmação de recebimento + grava flag
blink:c116_comprovante_detectado:{lead_id} (TTL 2h) para pipeline
fazer side effects Kommo (nota + limpeza de flags).

Fail-open: qualquer erro → None → LLM trata normalmente.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Toggle (default ON)
# ─────────────────────────────────────────────────────────────────────────────
_ATIVADO = os.environ.get("COMPROVANTE_PIX_ATIVADO", "1").strip().lower() not in (
    "0", "false", "no", "off", ""
)

# ─────────────────────────────────────────────────────────────────────────────
# Redis keys
# ─────────────────────────────────────────────────────────────────────────────
REDIS_KEY_AGUARDANDO = "blink:c114_aguardando_comprovante:{lead_id}"   # set pelo C-114 loop
REDIS_KEY_DETECTADO = "blink:c116_comprovante_detectado:{lead_id}"    # set por este módulo
TTL_AGUARDANDO = 7 * 24 * 3600   # 7 dias — paciente pode demorar pra pagar
TTL_DETECTADO = 2 * 3600         # 2h — pipeline tem janela curta pra fazer side effects

# ─────────────────────────────────────────────────────────────────────────────
# Detecção de texto sintético de imagem
# ─────────────────────────────────────────────────────────────────────────────
_RE_IMAGEM_SINTETICA = re.compile(
    r"""
    # Evolution: "O paciente acabou de enviar uma imagem/foto pelo WhatsApp"
    O\s+paciente\s+acabou\s+de\s+enviar\s+(?:uma?\s+)?(?:imagem|foto|documento|arquivo)
    |
    # WA Cloud: "O paciente enviou uma imagem pelo WhatsApp"
    O\s+paciente\s+enviou\s+(?:uma?\s+)?(?:imagem|foto|documento|arquivo|sticker|video)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _texto_e_imagem_sintetica(user_text: str) -> bool:
    """Retorna True se user_text é o texto sintético gerado pelo webhook para imagem."""
    if not user_text:
        return False
    return bool(_RE_IMAGEM_SINTETICA.search(user_text))


# ─────────────────────────────────────────────────────────────────────────────
# Chave Pix por unidade (allowlist canônica — regra CLAUDE.md seção 6)
# ─────────────────────────────────────────────────────────────────────────────
_PIX_UNIDADE = {
    "asa norte": "karladelaliberaoftalmo@gmail.com",
    "águas claras": "52.303.729/0001-30",
    "aguas claras": "52.303.729/0001-30",
}

_PIX_DEFAULT = "karladelaliberaoftalmo@gmail.com"  # fallback Asa Norte


def _chave_pix(ctx: dict) -> str:
    """Retorna chave Pix baseada na unidade do ctx.known."""
    known = ctx.get("known") or {}
    unidade = str(known.get("unidade") or "").lower()
    for k, v in _PIX_UNIDADE.items():
        if k in unidade:
            return v
    return _PIX_DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# Resposta de confirmação
# ─────────────────────────────────────────────────────────────────────────────
def _montar_resposta_confirmacao(ctx: dict) -> str:
    """Monta mensagem de confirmação de recebimento do comprovante."""
    known = ctx.get("known") or {}

    nome = str(known.get("nome_paciente") or known.get("nome") or "").strip()
    primeiro = nome.split()[0] if nome else ""
    saudacao = f"{primeiro}, " if primeiro else ""

    unidade = str(known.get("unidade") or "").strip()

    partes = [
        f"✅ {saudacao}comprovante recebido!",
        "\nVou encaminhar para a equipe conferir o pagamento.",
        "Assim que confirmarmos, seu horário estará **garantido**. 🗓️",
    ]

    if unidade:
        partes.append(f"\nQualquer dúvida sobre a consulta na **{unidade}** é só chamar aqui!")
    else:
        partes.append("\nQualquer dúvida é só chamar aqui!")

    return " ".join(partes)


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────
def deve_confirmar_comprovante_pix(
    ctx: Optional[dict],
    user_text: str,
) -> Optional[str]:
    """
    Retorna texto de confirmação de comprovante Pix se:
      1. Toggle COMPROVANTE_PIX_ATIVADO ativo
      2. user_text é texto sintético de imagem
      3. ctx tem lead_id
      4. Redis tem flag blink:c114_aguardando_comprovante:{lead_id}

    Ao retornar texto (não-None):
      - Grava blink:c116_comprovante_detectado:{lead_id} (TTL 2h) para pipeline
        fazer nota Kommo + limpeza de flags.

    Fail-open: qualquer exceção → None.
    """
    if not _ATIVADO:
        return None

    try:
        if not user_text or not isinstance(user_text, str):
            return None

        if not _texto_e_imagem_sintetica(user_text):
            return None

        if not ctx or not isinstance(ctx, dict):
            return None

        lead_id = ctx.get("lead_id")
        if not lead_id:
            return None

        # Verifica flag Redis
        try:
            from voice_agent.redis_client import get_redis as _get_redis
            redis = _get_redis()
        except ImportError:
            redis = None

        if redis is None:
            # Sem Redis em testes — fail-open (não dispara)
            return None

        flag_key = REDIS_KEY_AGUARDANDO.format(lead_id=lead_id)
        if not redis.get(flag_key):
            # Paciente não escolheu "reserva" antes → imagem é carteirinha normal
            return None

        # Flag ativo → é um comprovante Pix!
        # Grava flag para pipeline fazer side effects
        detectado_key = REDIS_KEY_DETECTADO.format(lead_id=lead_id)
        try:
            redis.setex(detectado_key, TTL_DETECTADO, "1")
        except Exception as _e_set:
            log.warning("[C-116] setex detectado falhou: %s", _e_set)

        return _montar_resposta_confirmacao(ctx)

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-116] deve_confirmar_comprovante_pix falhou (fail-open): %s", exc)
        return None
