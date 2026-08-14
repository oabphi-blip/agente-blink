"""
Bug C-106 (11/08/2026) — Valor contextualizado antes do preço.

Regras de negócio:
  - Pergunta de valor → SEMPRE pressupõe sem convênio.
    Não perguntar "é convênio ou particular?" neste contexto.
  - Usar "sem convênio" (nunca "particular").
  - Apresentar VALOR (especialidade, ambiente, o que a consulta entrega)
    ANTES de apresentar o preço.
  - Contexto pediátrico (idade < 18): destacar expertise pediátrica da
    Dra. Karla + ambiente acolhedor para crianças.
  - NUNCA mostrar tabela com os dois médicos quando o médico já é conhecido.
  - NUNCA perguntar "Qual médico?" quando Python já derivou pelo contexto.

Toggle: VALOR_CONTEXTUALIZADO_ATIVADO (default ON)
Fail-open: qualquer exceção → retorna None (LLM continua normalmente)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("VALOR_CONTEXTUALIZADO_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# ─────────────────────────────────────────────────────────────────────────────
# Templates de valor por contexto
# ─────────────────────────────────────────────────────────────────────────────

def _valor_karla_pediatrico(nome: str, idade: Optional[int] = None) -> str:
    """Criança < 18 anos → Dra. Karla, ênfase em oftalmopediatria."""
    saudacao = f"{nome}, " if nome else ""
    faixa = ""
    if idade is not None:
        if idade <= 2:
            faixa = "bebês e crianças pequenas"
        elif idade <= 12:
            faixa = f"crianças (ela atende desde bebês até os {idade} anos do seu filho)"
        else:
            faixa = "crianças e adolescentes"
    else:
        faixa = "crianças desde bebês"

    return (
        f"{saudacao}a Dra. Karla Delalíbera é especialista em oftalmopediatria — "
        f"ela tem experiência no atendimento de {faixa}, "
        "com um jeito de examinar pensado para deixar os pequenos à vontade.\n\n"
        "A consulta inclui:\n"
        "👁️ Avaliação completa da visão (acuidade visual)\n"
        "🔍 Exame do alinhamento e coordenação dos olhos\n"
        "🩺 Fundo de olho e pressão ocular\n"
        "✅ Orientação sobre desenvolvimento visual da criança\n\n"
        "O valor da consulta sem convênio:\n"
        "💰 Pix: *R$ 611*\n"
        "💳 Cartão em 1x: *R$ 670*\n\n"
        "Gostaria de agendar?"
    )


def _valor_karla_apv(nome: str) -> str:
    """Avaliação do Processamento Visual (APV / SDP)."""
    saudacao = f"{nome}, " if nome else ""
    return (
        f"{saudacao}a Avaliação do Processamento Visual com a "
        "Dra. Karla Delalíbera, especialista Avaliação do Processamento Visual, "
        "é uma avaliação completa que investiga a relação entre a visão e sintomas "
        "como cefaleia, cansaço ao ler, tontura e dificuldade de concentração.\n\n"
        "A avaliação inclui:\n"
        "👁️ Exame refractivo completo\n"
        "🔍 Avaliação binocular e de convergência\n"
        "🩺 Teste de dominância ocular e processamento visual\n"
        "✅ Relatório para equipe multidisciplinar (quando necessário)\n\n"
        "Valor sem convênio:\n"
        "💰 Pix: *R$ 800*\n"
        "💳 Cartão em 1x: *R$ 870*\n\n"
        "Gostaria de agendar?"
    )


def _valor_karla_adulto(nome: str) -> str:
    """Dra. Karla, adulto, rotina/estrabismo/outros."""
    saudacao = f"{nome}, " if nome else ""
    return (
        f"{saudacao}a consulta com a Dra. Karla Delalíbera cobre avaliação completa "
        "da saúde ocular — visão, pressão ocular, fundo de olho e, quando indicado, "
        "avaliação de estrabismo e coordenação binocular.\n\n"
        "Incluso na consulta:\n"
        "👁️ Tonometria (pressão ocular)\n"
        "🔍 Avaliação do alinhamento dos olhos\n"
        "🩺 Mapeamento de retina\n"
        "🕶️ Voucher para óculos, se necessário\n\n"
        "Valor sem convênio:\n"
        "💰 Pix: *R$ 611*\n"
        "💳 Cartão em 1x: *R$ 670*\n\n"
        "Gostaria de agendar?"
    )


def _valor_fabricio_catarata(nome: str) -> str:
    """Dr. Fabrício, avaliação de catarata."""
    saudacao = f"{nome}, " if nome else ""
    return (
        f"{saudacao}o Dr. Fabrício Freitas é especialista em catarata e saúde ocular "
        "do adulto — a avaliação cobre diagnóstico completo e orientação sobre o "
        "melhor momento para cirurgia, se for indicada.\n\n"
        "A avaliação inclui:\n"
        "👁️ Biometria ocular\n"
        "🔍 Avaliação do cristalino e grau de opacificação\n"
        "🩺 Exame de fundo de olho\n"
        "✅ Orientação personalizada sobre o tratamento\n\n"
        "Valor sem convênio:\n"
        "💰 Pix: *R$ 445*\n"
        "💳 Cartão em 1x: *R$ 470*\n\n"
        "Gostaria de agendar?"
    )


def _valor_fabricio_geral(nome: str) -> str:
    """Dr. Fabrício, adulto 50+, saúde ocular geral / córnea."""
    saudacao = f"{nome}, " if nome else ""
    return (
        f"{saudacao}o Dr. Fabrício Freitas é especialista em saúde ocular do adulto 50+ "
        "e em doenças da córnea — a consulta inclui avaliação completa com foco nas "
        "condições mais comuns nessa faixa etária.\n\n"
        "Incluso na consulta:\n"
        "👁️ Tonometria e pressão ocular\n"
        "🔍 Avaliação da córnea e superfície ocular\n"
        "🩺 Mapeamento de retina\n"
        "✅ Orientação preventiva personalizada\n\n"
        "Valor sem convênio:\n"
        "💰 Pix: *R$ 611*\n"
        "💳 Cartão em 1x: *R$ 670*\n\n"
        "Gostaria de agendar?"
    )


def _tabela_sem_convenio(nome: str) -> str:
    """Tabela geral sem convênio — quando médico não é conhecido.

    Não pergunta "Qual médico?" — apresenta os dois e deixa o paciente escolher
    naturalmente, sem criar fricção de formulário.
    """
    saudacao = f"Olá, {nome}!\n\n" if nome else ""
    return (
        f"{saudacao}"
        "Nossos valores para consulta sem convênio:\n\n"
        "👩‍⚕️ *Dra. Karla Delalíbera* — Oftalmopediatria, estrabismo, rotina\n"
        "💰 Pix: *R$ 611* · 💳 Cartão 1x: *R$ 670*\n\n"
        "👨‍⚕️ *Dr. Fabrício Freitas* — Saúde ocular adulto 50+, catarata, córnea\n"
        "💰 Pix: *R$ 445* (catarata) · *R$ 611* (outros)\n"
        "💳 Cartão 1x: *R$ 470* (catarata) · *R$ 670* (outros)\n\n"
        "Com qual médico seria a consulta?"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────

def gerar_valor_contextualizado(
    ctx: Optional[dict],
    user_text: str = "",
) -> Optional[str]:
    """Retorna resposta contextualizada de valor, ou None se não aplicável.

    Lógica:
      1. Toggle OFF → None (LLM segue normalmente)
      2. Detecta médico via ctx.known + fallback user_text
      3. Detecta contexto pediátrico via ctx.known.contexto_pediatrico ou idade
      4. Seleciona template correto (pediátrico / APV / adulto / Fabrício)
      5. Sem médico identificado → tabela geral sem convênio

    SEMPRE usa "sem convênio" — nunca "particular".
    NUNCA pergunta "é convênio ou particular?" — pressupõe sem convênio.
    """
    if not _ATIVADO:
        return None
    if not ctx:
        return None

    try:
        known = ctx.get("known") or {}
        nome = _extrair_nome(ctx)

        medico_raw = (known.get("medico") or "").lower().strip()
        motivo = (known.get("motivo") or known.get("especialidade") or "").lower()
        idade = known.get("idade")
        pediatrico = known.get("contexto_pediatrico", False)

        # Se não tem médico, tenta inferir pela idade/palavras do user_text
        if not medico_raw:
            medico_raw = _inferir_medico_user_text(user_text, idade)

        if not medico_raw:
            # Bug C-141 (14/08/2026): contexto pediátrico sem médico explícito
            # → só Karla Delalíbera (Fabrício não atende crianças).
            # Não mostrar tabela com ambos os médicos quando a consulta é claramente
            # pediátrica (criança, bebê, filho, filho de X anos, adolescente).
            if pediatrico or (idade is not None and idade < 18):
                return _valor_karla_pediatrico(nome, idade)
            # Sem médico nem contexto pediátrico → tabela geral (ambos médicos)
            return _tabela_sem_convenio(nome)

        karla = "karla" in medico_raw
        fabricio = "fabr" in medico_raw

        if karla:
            # APV / SDP tem precedência
            if any(k in motivo for k in ("apv", "processamento visual", "sdp", "prisma")):
                return _valor_karla_apv(nome)

            # Pediátrico: ctx.known ou idade extraída
            if pediatrico or (idade is not None and idade < 18):
                return _valor_karla_pediatrico(nome, idade)

            # Adulto rotina
            return _valor_karla_adulto(nome)

        if fabricio:
            if "catarata" in motivo:
                return _valor_fabricio_catarata(nome)
            return _valor_fabricio_geral(nome)

        # Médico não reconhecido → tabela geral
        return _tabela_sem_convenio(nome)

    except Exception as exc:
        log.warning("[C-106] gerar_valor_contextualizado falhou: %s", exc)
        return None  # fail-open


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

import re

_RE_IDADE_USER = re.compile(
    r"(?:para|de|com|tem)\s+(\d{1,2})\s+anos?"
    r"|\b(\d{1,2})\s+anos?\s+de\s+(?:idade|vida)\b",
    re.IGNORECASE,
)
_RE_MESES = re.compile(r"\b\d{1,2}\s+meses?\b", re.IGNORECASE)
_RE_KEYWORDS_KID = re.compile(
    r"\b(?:beb[eê]|crian[çc]a|filho|filha|infantil|rec[eé]m[- ]?nascido)\b",
    re.IGNORECASE,
)


def _inferir_medico_user_text(user_text: str, idade_known: Optional[int] = None) -> str:
    """Infere 'karla' ou 'fabricio' pelo texto livre do paciente."""
    if not user_text:
        return ""
    # Idade conhecida tem prioridade
    if idade_known is not None:
        return "karla" if idade_known < 18 else ""
    # Extrai idade do user_text
    m = _RE_IDADE_USER.search(user_text)
    if m:
        age = int(m.group(1) or m.group(2))
        if age < 18:
            return "karla"
        return ""  # adulto → não forçar
    if _RE_MESES.search(user_text):
        return "karla"
    if _RE_KEYWORDS_KID.search(user_text):
        return "karla"
    return ""


def _extrair_nome(ctx: Optional[dict]) -> str:
    """Retorna primeiro nome do contato, ou string vazia."""
    if not ctx:
        return ""
    nome_completo = (ctx.get("name") or ctx.get("contact_name") or "").strip()
    if not nome_completo or nome_completo.lower() in ("você", "cliente", "lead"):
        return ""
    partes = nome_completo.split()
    return partes[0].capitalize() if partes else ""
