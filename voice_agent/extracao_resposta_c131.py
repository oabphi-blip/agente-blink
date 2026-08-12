"""Bug C-131 (12/08/2026) — Extração determinística de dados do paciente.

Causa raiz do loop infinito (leads 24448016 Lorena/Nicolas e 24448040 Patrícia):
- C-125 pergunta "Qual a data de nascimento de Nicolas?"
- Paciente responde "09/02/2025" (3 vezes! inclusive "9 de fevereiro de 2025")
- C-130 detecta que inbound é resposta → retorna None → LLM processa
- LLM responde "Anotado!" mas NÃO atualiza ctx.known["data_nasc"]
- Próximo turno: checklist vê data_nasc vazia → C-125 dispara novamente → LOOP

Fix arquitetural:
Python extrai o valor DETERMINISTICAMENTE do user_text quando a última pergunta
foi um campo específico do C-125, e grava em ctx.known ANTES do checklist.
Isso quebra o loop na raiz — campo preenchido = C-125 não dispara.

Rodado em enriquecimento_ctx.py step 19 (antes do checklist / bypass chain).
Toggle: EXTRACAO_RESPOSTA_ATIVADO (default ON). Fail-open.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Detectores: o que a última mensagem da Lia perguntou?
# ──────────────────────────────────────────────────────────────────────────────

_RE_ULTIMA_PERGUNTOU_NOME = re.compile(r"nome\s+completo", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_DATA = re.compile(r"data de nascimento", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_CPF  = re.compile(r"\bcpf\b", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_CONV = re.compile(
    r"conv[eê]nio\s+ou\s+sem|por\s+conv[eê]nio|\bconv[eê]nio\b.*\?",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Extrator de DATA (múltiplos formatos PT-BR)
# ──────────────────────────────────────────────────────────────────────────────

_MESES_PT = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10",
    "novembro": "11", "dezembro": "12",
}

_RE_DATA_NUMERICA = re.compile(
    r"\b(\d{1,2})[/\-\.](\d{1,4})[/\-\.](\d{2,4})\b"  # 09/02/2025 ou 27/012/2024
    r"|\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b",   # ISO: 2025-02-09
    re.IGNORECASE,
)

_RE_DATA_ESCRITA = re.compile(
    r"\b(\d{1,2})\s+de\s+(" + "|".join(_MESES_PT.keys()) + r")\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)

_RE_DATA_ESCRITA_SEM_DE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_MESES_PT.keys()) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)


def extrair_data_nascimento(user_text: str) -> Optional[str]:
    """Retorna data no formato DD/MM/YYYY se encontrar padrão no user_text, else None."""
    if not user_text:
        return None
    ut = user_text.strip()

    # Formato escrito: "9 de fevereiro de 2025"
    m = _RE_DATA_ESCRITA.search(ut) or _RE_DATA_ESCRITA_SEM_DE.search(ut)
    if m:
        dia, mes_nome, ano = m.group(1), m.group(2).lower(), m.group(3)
        mes = _MESES_PT.get(mes_nome)
        if mes:
            return f"{int(dia):02d}/{mes}/{ano.zfill(4)}"

    # Formato numérico: "09/02/2025", "27/012/2024" (typo mês), ISO "2025-02-09"
    m2 = _RE_DATA_NUMERICA.search(ut)
    if m2:
        if m2.group(4):  # ISO: YYYY-MM-DD
            ano, mes, dia = m2.group(4), m2.group(5), m2.group(6)
            return f"{int(dia):02d}/{int(mes):02d}/{ano}"
        else:  # DD/MM/YYYY (com possível typo no mês — normalizar)
            dia, mes, ano = m2.group(1), m2.group(2), m2.group(3)
            # Normaliza mês: "012" → "12", "2" → "02"
            mes_int = int(mes) % 100  # "012" % 100 = 12
            ano_int = int(ano)
            if ano_int < 100:  # 2 dígitos: "25" → 2025
                ano_int += 2000
            if 1 <= mes_int <= 12:
                return f"{int(dia):02d}/{mes_int:02d}/{ano_int:04d}"

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Extrator de NOME
# ──────────────────────────────────────────────────────────────────────────────

# Prefixos a remover antes de extrair nome
_RE_NOME_PREFIXO = re.compile(
    r"^(?:meu\s+nome\s+[eé]|me\s+chamo|me\s+chamam|eu\s+(?:sou|me\s+chamo)|"
    r"pode\s+(?:me\s+)?chamar\s+de|sou\s+(?:a|o)?)\s*",
    re.IGNORECASE,
)

# Palavras que indicam que não é um nome
_NOMES_INVALIDOS = {
    "sim", "não", "nao", "ok", "tudo", "bem", "certo", "claro", "pode",
    "obrigado", "obrigada", "oi", "olá", "ola", "bom", "boa", "tarde",
    "dia", "noite", "preciso", "quero", "gostaria", "agendar", "marcar",
    "consulta", "retorno", "atendimento", "horário", "horario",
}


def extrair_nome_completo(user_text: str) -> Optional[str]:
    """Retorna nome completo se user_text parecer um nome de pessoa, else None.

    Critérios:
    - Remove prefixos ("Meu nome é", "Me chamo", etc.)
    - Mínimo 2 palavras alfa com >= 2 letras cada
    - Sem algarismos (não é data ou CPF)
    - Sem palavras-chave comuns de contexto
    - Não termina com "?"
    """
    if not user_text:
        return None
    ut = user_text.strip()
    if "?" in ut or len(ut) > 120:
        return None

    # Remove prefixo
    limpo = _RE_NOME_PREFIXO.sub("", ut).strip()
    # Pega apenas a primeira linha (pacientes às vezes adicionam infos extras)
    limpo = limpo.split("\n")[0].split(",")[0].strip()

    # Verifica dígitos (não é nome se tem número)
    if re.search(r"\d", limpo):
        return None

    palavras = [p for p in re.split(r"[\s\-]+", limpo) if p.isalpha() and len(p) >= 2]
    if len(palavras) < 2:
        return None

    # Verifica se palavras são todas nomes (não palavras de contexto)
    palavras_lower = {p.lower() for p in palavras}
    if palavras_lower & _NOMES_INVALIDOS:
        return None

    # Retorna em title case
    return " ".join(p.capitalize() for p in palavras[:5])  # máximo 5 tokens


# ──────────────────────────────────────────────────────────────────────────────
# Extrator de CPF
# ──────────────────────────────────────────────────────────────────────────────

_RE_CPF_EXTRATOR = re.compile(
    r"\b(\d{3})[\.\- ]?(\d{3})[\.\- ]?(\d{3})[\.\- ]?(\d{2})\b|\b(\d{11})\b"
)


def extrair_cpf(user_text: str) -> Optional[str]:
    """Retorna CPF formatado (só dígitos, 11 chars) se encontrar no user_text."""
    if not user_text:
        return None
    m = _RE_CPF_EXTRATOR.search(user_text)
    if not m:
        return None
    if m.group(5):  # captura bruta de 11 dígitos
        return m.group(5)
    return m.group(1) + m.group(2) + m.group(3) + m.group(4)


# ──────────────────────────────────────────────────────────────────────────────
# Função principal: enriquecer ctx.known com dados extraídos do inbound
# ──────────────────────────────────────────────────────────────────────────────

def extrair_e_injetar_resposta_c131(ctx: Optional[dict], user_text: str) -> None:
    """Step 19 de enriquecimento_ctx.py — extrai dados do inbound ANTES do checklist.

    Quando a última mensagem da Lia perguntou nome/data/CPF e o paciente respondeu,
    Python extrai e grava em ctx.known IMEDIATAMENTE.

    Isso quebra o loop na raiz:
      ctx.known["data_nasc"] preenchido → checklist não pende → C-125 não dispara.

    Não sobrescreve campos já validados. Fail-open: qualquer exceção → silêncio.
    """
    try:
        import os
        if os.environ.get("EXTRACAO_RESPOSTA_ATIVADO", "1").lower() in ("0", "false", "no", "off"):
            return

        if not ctx or not user_text or not user_text.strip():
            return

        known: dict = ctx.get("known") or {}
        ultima: str = known.get("ultima_msg_outbound") or ctx.get("ultima_msg_outbound") or ""
        if not ultima:
            return

        ut = user_text.strip()

        # ── DATA DE NASCIMENTO ──────────────────────────────────────────────────
        if _RE_ULTIMA_PERGUNTOU_DATA.search(ultima) and not known.get("data_nasc"):
            data = extrair_data_nascimento(ut)
            if data:
                known["data_nasc"] = data
                log.info(
                    "[C-131] data_nasc extraída: %r → %r (lead=%s)",
                    ut[:40], data, known.get("lead_id"),
                )
                ctx["known"] = known

        # ── NOME COMPLETO ───────────────────────────────────────────────────────
        if _RE_ULTIMA_PERGUNTOU_NOME.search(ultima) and not known.get("nome"):
            nome = extrair_nome_completo(ut)
            if nome:
                known["nome"] = nome
                log.info(
                    "[C-131] nome extraído: %r → %r (lead=%s)",
                    ut[:40], nome, known.get("lead_id"),
                )
                ctx["known"] = known

        # ── CPF ────────────────────────────────────────────────────────────────
        if _RE_ULTIMA_PERGUNTOU_CPF.search(ultima) and not known.get("cpf_validado"):
            cpf = extrair_cpf(ut)
            if cpf:
                known["cpf_extraido_c131"] = cpf
                # Nota: validação matemática fica em C-110 (enriquecimento_ctx step 16)
                # Aqui só popula para que o checklist não repita a pergunta.
                # C-110 valida e atualiza "cpf_validado" ou "cpf_invalido_detectado".
                log.info(
                    "[C-131] cpf extraído para validação C-110: lead=%s",
                    known.get("lead_id"),
                )
                ctx["known"] = known

    except Exception as _exc:
        log.warning("[C-131] extração falhou (fail-open): %s", _exc)
