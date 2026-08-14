"""Bug C-136 (14/08/2026) — Pergunta de perfil do paciente.

Fábio (14/08/2026):
"Atualizar a primeira abordagem para inserir em Python.
Leia-se: 'Pode me contar se a consulta é para um bebê, criança,
adolescente ou adulto?'"

Motivo: a pergunta 'para você ou para outra pessoa?' é vaga — não
captura informação útil. A faixa etária é o dado crítico que Python
usa para derivar médico (Karla/Fabrício), protocolo de retorno e
agrupador de exames. Com a resposta, enriquecimento_ctx já deriva
tudo automaticamente sem pergunta extra.

Gatilho: primeiro turno da conversa sem perfil_paciente nem médico
definido no ctx.known, e user_text não contém pista de faixa etária.

Toggle: PERGUNTA_PERFIL_ATIVADA (default ON). Fail-open.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões que indicam faixa etária JÁ FORNECIDA pelo paciente
# ---------------------------------------------------------------------------

_RE_PERFIL_JA_DADO = re.compile(
    r"\b(?:"
    # Bebê / lactente  ("recém" cobre recém-nascido; .nasc falha no \b final)
    r"beb[eê]|rec[eé]m|infant|lactente|neonato"
    # Criança
    r"|crian[cç]a|menin[oa]|garot[oa]|filho|filha|filhos|filhas"
    # Adolescente
    r"|adolescente|teenage"
    # Adulto / idoso
    r"|adulto|adulta|idoso|idosa|senhor|senhora|minha\s+m[aã]e|meu\s+pai"
    # Pronomes de si mesmo
    r"|para\s+mim\b|[eé]\s+para\s+mim\b|sou\s+eu\b|é\s+pra\s+mim\b"
    # Idade explícita  "3 anos", "8 meses", "65 anos"
    r"|\d+\s*(?:anos?|meses?|m[eê]s)"
    r")\b",
    re.IGNORECASE,
)

# Padrões que indicam médico já especificado (não precisa perguntar perfil)
_RE_MEDICO_JA_DADO = re.compile(
    r"\b(?:karla|fabr[ií]cio|k[aá]tia|dra?\.|drª\.?)\b",
    re.IGNORECASE,
)

# Padrões de specialidade já dita (catarata → Fabrício, sem precisar perguntar)
_RE_ESPECIALIDADE_JA_DADA = re.compile(
    r"\b(?:catarata|estrabismo|retina|processamento\s+visual|apv|sdp|oft"
    r"|óculos|oculos|miopia|astigmatismo|hipermetropia|presbiopia)\b",
    re.IGNORECASE,
)


def _ativado() -> bool:
    return os.environ.get("PERGUNTA_PERFIL_ATIVADA", "1").lower() not in (
        "0", "false", "no", "off"
    )


def _perfil_ja_conhecido(ctx: Optional[dict]) -> bool:
    """True se ctx.known já tem perfil ou médico derivado."""
    known = (ctx or {}).get("known") or {}
    if known.get("perfil_paciente"):
        return True
    if known.get("medico"):
        return True
    if known.get("faixa_etaria"):
        return True
    # Idade derivada de data de nascimento
    if known.get("idade_paciente") is not None:
        return True
    return False


def _nome_contato(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_contato") or known.get("nome_paciente") or ""
    return nome.split()[0] if nome else ""


def _montar_pergunta(ctx: Optional[dict]) -> str:
    """Monta a pergunta canônica de perfil com saudação pelo nome."""
    nome = _nome_contato(ctx)
    saud = f"{nome}, " if nome else ""
    return (
        f"{saud}pode me contar se a consulta é para "
        "um bebê, criança, adolescente ou adulto? 😊"
    )


def deve_perguntar_perfil(
    ctx: Optional[dict], user_text: str
) -> Optional[str]:
    """C-136: quando não há perfil no ctx E o inbound não traz faixa etária,
    retorna a pergunta canônica de perfil.

    Gatilho: primeiro turno ou turno sem perfil conhecido, e paciente
    não mencionou faixa etária, médico ou especialidade.

    Retorna None (fail-open) em caso de exceção.
    """
    if not _ativado():
        return None

    try:
        # Perfil já conhecido no ctx → não perguntar
        if _perfil_ja_conhecido(ctx):
            return None

        ut = (user_text or "").strip()

        # Paciente já informou faixa etária no inbound → não perguntar
        if _RE_PERFIL_JA_DADO.search(ut):
            return None

        # Médico ou especialidade já citado → não perguntar
        if _RE_MEDICO_JA_DADO.search(ut):
            return None
        if _RE_ESPECIALIDADE_JA_DADA.search(ut):
            return None

        # Só perguntar quando inbound tem ALGUM conteúdo (não é saudação vazia)
        # mas não traz contexto suficiente para derivar perfil
        if not ut or len(ut) < 3:
            return None

        # C-145 (14/08/2026): convênio verificado ANTES do perfil.
        # Se convênio ainda desconhecido, C-145 pergunta primeiro.
        # C-136 só dispara quando convênio já resolvido (aceito OU sem convênio).
        known = (ctx or {}).get("known") or {}
        if not known.get("convenio") and known.get("convenio_aceito") is None and not known.get("sem_convenio"):
            return None  # C-145 pergunta convênio antes do perfil

        # Verificar se já perguntamos antes (última msg outbound contém "bebê, criança")
        ultima = known.get("ultima_msg_outbound") or ""
        if "bebê, criança" in ultima.lower() or "bebe, crianca" in ultima.lower():
            return None  # já perguntamos, não repetir

        log.debug("[C-136] perfil não identificado → pergunta de perfil")
        return _montar_pergunta(ctx)

    except Exception as exc:
        log.warning("[C-136] falha ao verificar perfil: %s", exc)
        return None
