"""Bug C-73 — Anti-repetição de pergunta de perfil (Fábio 14/08/2026).

Regra INVIOLÁVEL:
    Se o paciente JÁ disse categoria de perfil (bebê / criança /
    adolescente / adulto) OU ctx.known.perfil_paciente já existe,
    NUNCA repetir a pergunta de perfil. Refina direto pra idade / nome.

Origem: Fábio 14/08/2026 P0. Lead 24456676:
    Paciente: "Olá, vim do site e gostaria de agendar uma consulta."
    Lia: "pode me contar se a consulta é para um bebê, criança,
          adolescente ou adulto?"
    Paciente: "Criança"
    Lia: "Para eu te direcionar certo, pode me contar: é para um bebê,
          criança pequena, escolar ou adolescente?"   ← BURRICE.

Fix:
    Filtro pós-geração detecta padrão "bebê.*criança.*adolescente.*adulto"
    OU "bebê.*criança pequena.*escolar.*adolescente" no outbound.
    Se ctx.known ou user_text já indicam categoria → substitui pela
    pergunta correta de refinamento (idade / nome / motivo).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional


log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Detecta OUTBOUND repetindo pergunta de perfil
# ═════════════════════════════════════════════════════════════════════════

# Padrão 1: "bebê, criança, adolescente ou adulto"
_RE_OUTBOUND_PERGUNTA_PERFIL_v1 = re.compile(
    r"beb[eê].{0,50}crian[cç]a.{0,50}(?:adolescente|adulto)",
    re.IGNORECASE | re.DOTALL,
)

# Padrão 2: "bebê, criança pequena, escolar ou adolescente" (a variante burra)
_RE_OUTBOUND_PERGUNTA_PERFIL_v2 = re.compile(
    r"beb[eê].{0,50}crian[cç]a\s+pequena.{0,50}(?:escolar|adolescente)",
    re.IGNORECASE | re.DOTALL,
)


def _outbound_repete_pergunta_perfil(text: str) -> bool:
    """True se o texto contém uma pergunta de perfil (bebê/criança/etc)."""
    if not text:
        return False
    return bool(
        _RE_OUTBOUND_PERGUNTA_PERFIL_v1.search(text)
        or _RE_OUTBOUND_PERGUNTA_PERFIL_v2.search(text)
    )


# ═════════════════════════════════════════════════════════════════════════
# Detecta INBOUND com categoria de perfil
# ═════════════════════════════════════════════════════════════════════════

_RE_INBOUND_BEBE = re.compile(
    r"\b(?:beb[eê]|rec[eé]m[- ]?nascid[oa]|neonato|lactente|"
    r"\d+\s*(?:mes(?:es)?|m[eê]s))\b",
    re.IGNORECASE,
)
_RE_INBOUND_CRIANCA = re.compile(
    r"\b(?:crian[cç]a|menin[oa]|filh[oa]|meu\s+filho|minha\s+filha)\b",
    re.IGNORECASE,
)
_RE_INBOUND_ADOLESCENTE = re.compile(
    r"\b(?:adolescente|teen)\b",
    re.IGNORECASE,
)
_RE_INBOUND_ADULTO = re.compile(
    r"\b(?:adulto|adulta|mim|para\s+mim|pra\s+mim|sou\s+eu|"
    r"minha\s+m[aã]e|meu\s+pai|idos[oa])\b",
    re.IGNORECASE,
)


def _classificar_inbound(user_text: str) -> Optional[str]:
    """Retorna 'bebe' | 'crianca' | 'adolescente' | 'adulto' | None."""
    if not user_text:
        return None
    if _RE_INBOUND_BEBE.search(user_text):
        return "bebe"
    if _RE_INBOUND_CRIANCA.search(user_text):
        return "crianca"
    if _RE_INBOUND_ADOLESCENTE.search(user_text):
        return "adolescente"
    if _RE_INBOUND_ADULTO.search(user_text):
        return "adulto"
    return None


def _perfil_do_ctx(ctx: Any) -> Optional[str]:
    """Retorna categoria já registrada no ctx.known."""
    if ctx is None:
        return None
    known = None
    if isinstance(ctx, dict):
        known = ctx.get("known") or {}
    else:
        known = getattr(ctx, "known", None) or {}

    perfil = (known.get("perfil_paciente") or "").lower()
    if not perfil:
        return None
    if "beb" in perfil:
        return "bebe"
    if "crian" in perfil:
        return "crianca"
    if "adolesc" in perfil:
        return "adolescente"
    if "adult" in perfil or "idos" in perfil:
        return "adulto"
    return None


# ═════════════════════════════════════════════════════════════════════════
# Refinamento correto por categoria
# ═════════════════════════════════════════════════════════════════════════

def _refinamento_por_categoria(categoria: str, nome: str = "") -> str:
    """Retorna a pergunta canônica de refinamento pra próxima etapa."""
    saud = f"{nome}, " if nome else ""

    if categoria == "bebe":
        return (
            f"Perfeito! {saud}quantos meses o bebê tem? "
            "Assim consigo indicar o médico e horários certos."
        )
    if categoria == "crianca":
        return (
            f"Ótimo! {saud}qual a idade da criança? "
            "Assim consigo indicar o médico e horários certos."
        )
    if categoria == "adolescente":
        return (
            f"Perfeito! {saud}qual a idade do adolescente? "
            "Assim consigo direcionar o atendimento."
        )
    if categoria == "adulto":
        return (
            f"Perfeito! {saud}pode me passar seu nome completo pra eu "
            "montar o atendimento?"
        )
    # Fallback (nunca deveria chegar aqui)
    return f"{saud}pode me passar a idade do paciente?"


# ═════════════════════════════════════════════════════════════════════════
# Filtro principal
# ═════════════════════════════════════════════════════════════════════════

def _ativado() -> bool:
    return (os.environ.get("ANTI_REPETICAO_PERFIL_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off", ""
    )


def _extrair_nome(ctx: Any) -> str:
    if ctx is None:
        return ""
    known = None
    if isinstance(ctx, dict):
        known = ctx.get("known") or {}
    else:
        known = getattr(ctx, "known", None) or {}
    nome = (known.get("nome_contato") or known.get("nome_paciente") or "").strip()
    return nome.split()[0] if nome else ""


def _extrair_user_text(ctx: Any) -> str:
    if ctx is None:
        return ""
    if isinstance(ctx, dict):
        return str(ctx.get("user_text") or "")
    return str(getattr(ctx, "user_text", "") or "")


def validar_nao_repetir_pergunta_perfil(
    text: str,
    ctx: Any,
) -> tuple[str, bool]:
    """Retorna (texto_final, foi_substituido).

    Se `text` contém pergunta de perfil E a categoria JÁ é conhecida
    (via ctx ou via user_text atual), substitui `text` pela pergunta
    correta de refinamento.
    """
    if not _ativado() or not text:
        return text, False

    if not _outbound_repete_pergunta_perfil(text):
        return text, False  # não é pergunta de perfil — deixa passar

    # Prioridade: user_text > ctx.known
    user_text = _extrair_user_text(ctx)
    categoria = _classificar_inbound(user_text) or _perfil_do_ctx(ctx)

    if not categoria:
        return text, False  # categoria desconhecida — pergunta é legítima

    nome = _extrair_nome(ctx)
    resposta_correta = _refinamento_por_categoria(categoria, nome)

    log.error(
        "[C-73] REPETIÇÃO DE PERGUNTA DE PERFIL BLOQUEADA "
        "categoria=%s user_text=%r text=%r",
        categoria,
        user_text[:60],
        text[:120],
    )

    return resposta_correta, True
