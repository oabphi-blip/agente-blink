"""Bug C-145 (14/08/2026) — Convênio verificado ANTES dos dados do paciente.

Fábio (14/08/2026), lead 24456884 (Beatriz/Amil):
"perdeu a logica de saber primeiro o convenio, para saber se atendemos.
No caso Amil nao atendemos e a conversa estendeu. Inserir como norma
deterministica antes de comecar perguntar os dados do paciente. Porque
a conversa pode ir para valor de consulta se nao tem convenio.
Inserir como norma deterministica."

Causa raiz: C-136 (pergunta_perfil) disparava ANTES de faq_convenio_aceito.
Quando a paciente Beatriz disse "Vocês aceitam o plano de saúde Amil?" na
1ª mensagem, C-136 disparou e retornou "bebê, criança, adolescente ou adulto?"
antes mesmo de informar que Amil não é aceito. 5 turnos desperdiçados.

Fix — 3 camadas:
1. Este módulo (C-145): quando convênio desconhecido E texto não menciona
   plano por nome (faq_convenio_aceito trataria), pergunta convênio primeiro.
2. Guard em pergunta_perfil.py (C-136): retorna None enquanto convênio
   desconhecido — delega a este módulo.
3. Reordenação em blindagens_deterministicas.py: escolha_convenio_c123 →
   faq_convenio_aceito → C-145 → C-136 (nova ordem).

Toggle: BLINDAGEM_CONVENIO_PRIMEIRO_C145_ATIVADO (default ON). Fail-open.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões que indicam que o texto já menciona convênio por nome ou pergunta
# sobre aceitação → faq_convenio_aceito ou classificador_convenio tratam.
# C-145 NÃO deve disparar nesses casos.
# ---------------------------------------------------------------------------

# Nomes de planos conhecidos (aceitos ou não aceitos)
_RE_NOME_PLANO_NO_TEXTO = re.compile(
    r"\b(?:"
    r"bacen|amil|unimed|bradesco|sul\s*am[eé]rica|inas|gdf"
    r"|cassi|hapvida|proas[ae]|saúde\s+caixa|saude\s+caixa"
    r"|petrobras?|conab|serpro|fascal|omint|care\s*plus|anafe"
    r"|plan\s*assist|stj|tjdft|trf|trt|tst|tre|stm|stf"
    r"|sis\s*senado|pro\s*sa[uú]de|c[aâ]mara|e-vida|luminar"
    r"|afeg[oa]|pf\s+sa[uú]de|policia\s+federal"
    r")\b",
    re.IGNORECASE,
)

# Padrões de FAQ de convênio genérico ("vocês aceitam?", "tem convênio?")
_RE_FAQ_CONVENIO_GENERICO = re.compile(
    r"\b(?:"
    r"voc[êe]s?\s+aceitam?"
    r"|aceitam?\s+(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r"|atendem?\s+(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r"|tem\s+conv[êe]nio"
    r"|aceita\s+conv[êe]nio"
    r"|atende\s+(?:pelo\s+)?conv[êe]nio"
    r"|qual(?:is)?\s+conv[êe]nios?\s+(?:aceitam?|atendem?)"
    r"|funciona\s+(?:com\s+)?(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r")\b",
    re.IGNORECASE,
)

# Paciente já disse "sem convênio" / "sem plano" / "particular" nesta mensagem
_RE_SEM_CONVENIO_NO_TEXTO = re.compile(
    r"\b(?:sem\s+conv[êe]nio|sem\s+plano|sem\s+pl[aã]o|pagar\s+(?:direto|do\s+bolso))\b",
    re.IGNORECASE,
)

# Anti-loop: última outbound já perguntou sobre convênio
_ANTI_LOOP_MARCAS = (
    "plano de saúde ou sem convênio",
    "pelo seu plano",
    "pelo convênio ou sem",
    "tem convênio",
    "tem plano de saúde",
)


def _ativado() -> bool:
    return os.environ.get(
        "BLINDAGEM_CONVENIO_PRIMEIRO_C145_ATIVADO", "1"
    ).lower() not in ("0", "false", "no", "off")


def _convenio_ja_resolvido(ctx: Optional[dict]) -> bool:
    """True se já sabemos o convênio OU se já foi recusado/aceito."""
    known = (ctx or {}).get("known") or {}
    # Convênio explicitamente definido (plano ou Não se aplica)
    if known.get("convenio"):
        return True
    # Aceito/recusado já derivado por C-103/enriquecimento_ctx
    if known.get("convenio_aceito") is not None:
        return True
    # Paciente escolheu "Seguir Sem Convênio" (C-123)
    if known.get("sem_convenio"):
        return True
    # Não se aplica explicitamente
    conv = (known.get("convenio") or "").lower()
    if "não se aplica" in conv or "nao se aplica" in conv or "particular" in conv:
        return True
    return False


def _nome_contato(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_contato") or known.get("nome_paciente") or ""
    return nome.split()[0] if nome else ""


def deve_perguntar_convenio_primeiro_c145(
    ctx: Optional[dict], user_text: str
) -> Optional[str]:
    """C-145 (14/08/2026): se convênio ainda desconhecido E texto não menciona
    plano ou FAQ de convênio, retorna pergunta canônica de convênio ANTES de
    qualquer dado do paciente.

    Objetivo: garantir que Lia saiba PRIMEIRO se o convênio é aceito antes de
    gastar turnos coletando dados — evita situação em que recusa de convênio
    vem DEPOIS de nome, data de nascimento e outros dados já coletados.

    Retorna None (fail-open) em caso de exceção.
    """
    if not _ativado():
        return None

    if ctx is None:
        return None  # fail-open: sem contexto, deixar LLM decidir

    try:
        # Convênio já resolvido → não perguntar
        if _convenio_ja_resolvido(ctx):
            return None

        known = (ctx or {}).get("known") or {}

        # Lead já agendado → não entrar no fluxo de triagem
        if known.get("ja_agendado"):
            return None

        ut = (user_text or "").strip()

        # Inbound sem conteúdo relevante → não perguntar ainda
        if not ut or len(ut) < 3:
            return None

        # Paciente mencionou nome de plano → faq_convenio_aceito/classificador trata
        if _RE_NOME_PLANO_NO_TEXTO.search(ut):
            return None

        # Paciente fez pergunta de FAQ sobre convênio → faq_convenio_aceito trata
        if _RE_FAQ_CONVENIO_GENERICO.search(ut):
            return None

        # Paciente já disse "sem convênio" nesta mensagem → convênio resolvido
        if _RE_SEM_CONVENIO_NO_TEXTO.search(ut):
            return None

        # Anti-loop: última outbound já perguntou sobre convênio → não repetir
        ultima = (known.get("ultima_msg_outbound") or "").lower()
        for marca in _ANTI_LOOP_MARCAS:
            if marca.lower() in ultima:
                return None

        nome = _nome_contato(ctx)
        saud = f"{nome}, " if nome else ""

        log.debug(
            "[C-145] convênio desconhecido → perguntando antes do perfil (lead=%s)",
            (ctx or {}).get("lead_id") or "?",
        )
        return (
            f"{saud}a consulta seria pelo seu plano de saúde ou sem convênio? 😊"
        )

    except Exception as exc:
        log.warning("[C-145] falha ao verificar convenio_primeiro: %s", exc)
        return None
