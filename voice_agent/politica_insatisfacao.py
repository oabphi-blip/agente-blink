"""Bug C-135 (13/08/2026) — Política de insatisfação do paciente.

Fábio (13/08/2026):
"Se ocorrer alguma insatisfação do paciente, orientar que o atendimento está
sendo feito com agente IA com supervisamento humano. Não se preocupe — qualquer
oscilação, instabilidade, repetições será observado e corrigido em tempo.
Pode pedir para transferir para atendimento humano. Se não for atendido,
o atendimento concluirá seu atendimento. Ter esta política para não deixar
os pacientes furiosos com possíveis erros. Pedir auxílio ao paciente se
possível registrar o erro, para servir de aprendizagem."

Objetivo: defuse anger ANTES de virar desistência (C-108) ou pedido de atendente (C-84).
Ativado UMA VEZ por conversa (Redis TTL 12h) para não soar repetitivo.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões de detecção de insatisfação (mais suave que desistência C-108)
# ---------------------------------------------------------------------------

_RE_INSATISFACAO = re.compile(
    r"\b(?:"
    # Frustração com repetição / bug
    r"repetindo|repete|mesma coisa|de novo|j[aá] falei|n[aã]o entende|n[aã]o ouviu"
    r"|bugou|bugado|travou|travado|n[aã]o funciona"
    # Qualidade do atendimento
    r"|p[eé]ssimo|horrível|horroroso|ridículo|absurdo|vergonha"
    r"|que atendimento|que servi[cç]o|que sistema"
    # Robô / IA
    r"|rob[ôo]|automatizado|m[aá]quina|bot\b"
    # Raiva
    r"|que raiva|t[oô] com raiva|perdi a paci[eê]ncia|n[aã]o aguento mais"
    r"|inacredit[aá]vel|impossível|que isso"
    # Dificuldade genérica
    r"|n[aã]o consigo|n[aã]o estou conseguindo|muito dif[íi]cil"
    r")\b",
    re.IGNORECASE,
)

_RE_NAO_INSATISFACAO = re.compile(
    r"\b(?:n[aã]o repete|sem repetir|n[aã]o bugou|tudo bem|tudo certo|ok|okay)\b",
    re.IGNORECASE,
)

_REDIS_KEY_INSATISFACAO = "blink:c135_insatisfacao_respondida:{lead_id}"
_TTL_12H = 43200  # 12 horas


def _ativado() -> bool:
    return os.environ.get("POLITICA_INSATISFACAO_ATIVADA", "1").lower() not in (
        "0", "false", "no", "off"
    )


def _dedup_redis(lead_id: Optional[str | int]) -> bool:
    """True se já respondemos a insatisfação nesta janela (12h). Grava o flag."""
    if not lead_id:
        return False
    try:
        from voice_agent.redis_client import get_redis
        r = get_redis()
        if not r:
            return False
        key = _REDIS_KEY_INSATISFACAO.format(lead_id=lead_id)
        if r.get(key):
            return True
        r.setex(key, _TTL_12H, "1")
        return False
    except Exception:
        return False


def _lead_id_from_ctx(ctx: Optional[dict]) -> Optional[str]:
    if not ctx:
        return None
    known = ctx.get("known") or {}
    return (
        str(known.get("lead_id") or "")
        or str(ctx.get("lead_id") or "")
        or str((ctx.get("lead") or {}).get("id") or "")
        or None
    )


def _nome_contato(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_contato") or known.get("nome_paciente") or ""
    return nome.split()[0] if nome else ""


def montar_resposta_insatisfacao(ctx: Optional[dict]) -> str:
    """Monta a mensagem canônica de política de insatisfação."""
    nome = _nome_contato(ctx)
    saud = f"{nome}, " if nome else ""

    return (
        f"{saud}peço desculpas pela experiência. 🙏\n\n"
        "Estou aqui como Lia, assistente IA da Blink Oftalmologia, com supervisão "
        "da nossa equipe humana em tempo real.\n\n"
        "Qualquer oscilação, instabilidade ou repetição é monitorada e corrigida — "
        "pedimos paciência e compreensão.\n\n"
        "Se preferir falar diretamente com nossa equipe, é só dizer "
        "\"Atendente\" que faço a transferência agora. "
        "Caso não seja atendido imediatamente, nossa equipe concluirá seu "
        "atendimento em breve.\n\n"
        "Se puder descrever o que aconteceu de errado, nos ajuda muito a melhorar "
        "o atendimento para você e outros pacientes. 😊"
    )


def deve_responder_insatisfacao(
    ctx: Optional[dict], user_text: str
) -> Optional[str]:
    """C-135: detecta insatisfação e entrega política de transparência.

    Retorna mensagem canônica ou None (fail-open).
    Suprimido por: C-108 (desistência), C-84 (pediu atendente) — esses
    têm prioridade e devem vir ANTES na chain.
    """
    if not _ativado():
        return None
    if not user_text or not user_text.strip():
        return None

    # Desistência ou pedido de atendente → C-108/C-84 cuida, não duplicar
    known = (ctx or {}).get("known") or {}
    if known.get("desistencia_explicita"):
        return None

    ut = user_text.strip()

    # Falso positivo: "não repete tudo isso" sendo negação
    if _RE_NAO_INSATISFACAO.search(ut):
        return None

    if not _RE_INSATISFACAO.search(ut):
        return None

    lead_id = _lead_id_from_ctx(ctx)
    if _dedup_redis(lead_id):
        log.debug("[C-135] insatisfação já respondida nesta janela — skip")
        return None

    log.info("[C-135] insatisfação detectada lead=%s user_text=%r", lead_id, ut[:60])
    return montar_resposta_insatisfacao(ctx)
