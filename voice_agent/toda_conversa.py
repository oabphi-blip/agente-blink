"""
C-133 (13/08/2026) — Campo TODA CONVERSA (field_id 1261206)

Fonte de verdade única e persistente para histórico de cada conversa.

PROBLEMA RESOLVIDO:
  Paciente responde "27/12/2024" → LLM processa → dado fica em memória do turno atual.
  Na próxima mensagem, ctx é reconstruído do zero → dado some → Lia pergunta de novo.
  Loop infinito, paciente frustrado.

SOLUÇÃO:
  1. Todo turno começa lendo TODA CONVERSA → extrai o que o paciente já disse
  2. Injeta em ctx.known ANTES do checklist → checklist vê os dados → não pergunta de novo
  3. No fim do turno, appenda [P HH:MM] + [L HH:MM] ao campo → próximo turno lê de lá

FIELD: TODA CONVERSA · field_id 1261206 · type textarea · pipeline 8601819

Toggle: TODA_CONVERSA_ATIVADO (default ON). Fail-open em tudo.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger(__name__)

FIELD_ID_TODA_CONVERSA = 1261206
BRT = timezone(timedelta(hours=-3))
_MAX_CHARS = 8000  # limite seguro para textarea Kommo


def _ativado() -> bool:
    return os.getenv("TODA_CONVERSA_ATIVADO", "1").lower() not in ("0", "false", "no", "off")


# ─── Extração de dados do histórico ───────────────────────────────────────────

# Reutiliza as mesmas funções do C-131 para consistência
def _extrair_data_nascimento(texto: str) -> Optional[str]:
    """
    Extrai data de nascimento de texto livre.
    Cobre: DD/MM/YYYY, DD/MMM/YYYY (typo 3 dígitos), escrito por extenso.
    Retorna string no formato DD/MM/YYYY ou None.
    """
    # Corrige typo de 3 dígitos no mês: "27/012/2024" → "27/12/2024"
    texto = re.sub(r"\b(\d{1,2})/0(\d{2})/(\d{4})\b", r"\1/\2/\3", texto)

    # DD/MM/YYYY ou D/M/YYYY
    m = re.search(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b", texto)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        if 1 <= int(d) <= 31 and 1 <= int(mo) <= 12 and 1900 <= int(y) <= 2026:
            return f"{int(d):02d}/{int(mo):02d}/{y}"

    # Meses por extenso
    _MESES = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
        "abril": "04", "maio": "05", "junho": "06", "julho": "07",
        "agosto": "08", "setembro": "09", "outubro": "10",
        "novembro": "11", "dezembro": "12",
    }
    m2 = re.search(
        r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[çc]o|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b",
        texto, re.IGNORECASE,
    )
    if m2:
        d = int(m2.group(1))
        mo = _MESES.get(m2.group(2).lower().replace("ç", "c").replace("ã", "a"))
        y = m2.group(3)
        if mo and 1 <= d <= 31:
            return f"{d:02d}/{mo}/{y}"

    return None


def _extrair_cpf(texto: str) -> Optional[str]:
    """Extrai CPF com ou sem máscara."""
    m = re.search(r"\b(\d{3})[.\-\s]?(\d{3})[.\-\s]?(\d{3})[.\-\s]?(\d{2})\b", texto)
    if m:
        cpf = "".join(m.groups())
        if len(cpf) == 11 and len(set(cpf)) > 1:
            return cpf
    return None


def _extrair_nome(texto: str) -> Optional[str]:
    """Extrai nome completo de resposta do paciente."""
    # Remove prefixos comuns
    t = re.sub(
        r"(?i)^(meu\s+nome\s+[eéè]\s+|me\s+chamo\s+|sou\s+(?:a\s+|o\s+)?|"
        r"eu\s+sou\s+|meu\s+nome\s+é\s+)",
        "", texto.strip(),
    )
    # Deve ter pelo menos 2 palavras alfabéticas
    palavras = [p for p in t.split() if re.match(r"^[A-Za-zÀ-ú]{2,}$", p)]
    if len(palavras) >= 2:
        # Não pode ser resposta de sim/não/data
        _REJEITAR = {"sim", "nao", "não", "ok", "ola", "olá", "bom", "boa", "dia", "tarde", "noite"}
        if palavras[0].lower() not in _REJEITAR:
            return " ".join(p.capitalize() for p in palavras[:4])
    return None


def extrair_dados_de_notas(notas_historico: list) -> dict:
    """
    Varre notas do lead (notas_historico do ctx) e extrai dados que o paciente
    informou em mensagens anteriores. Usa as mesmas extrações do C-131.

    Retorna dict com chaves: data_nasc, cpf, nome (apenas os que encontrar).
    """
    if not _ativado():
        return {}

    resultado: dict = {}

    for nota in (notas_historico or []):
        texto = nota.get("text", "") if isinstance(nota, dict) else str(nota)
        # Processar apenas mensagens do paciente
        if not (texto.startswith("Paciente (WhatsApp):") or "[PACIENTE" in texto or "[P " in texto):
            continue

        # Extrair a parte da mensagem do paciente
        msg = (
            texto
            .replace("Paciente (WhatsApp):", "")
            .strip()
        )
        # Remove prefixo de timestamp se houver: "[P 14:05 12/08] msg"
        msg = re.sub(r"^\[P\s+\d{2}:\d{2}[^\]]*\]\s*", "", msg).strip()

        if not msg:
            continue

        if not resultado.get("data_nasc"):
            data = _extrair_data_nascimento(msg)
            if data:
                resultado["data_nasc"] = data
                log.debug("[C-133] data_nasc extraída de nota: %s", data)

        if not resultado.get("cpf"):
            cpf = _extrair_cpf(msg)
            if cpf:
                resultado["cpf"] = cpf
                log.debug("[C-133] CPF extraído de nota: %s", cpf[:3] + "***")

        if not resultado.get("nome") and not resultado.get("nome_paciente"):
            nome = _extrair_nome(msg)
            if nome:
                resultado["nome"] = nome
                log.debug("[C-133] nome extraído de nota: %s", nome)

    return resultado


def extrair_dados_de_toda_conversa(texto: str) -> dict:
    """
    Varre o texto do campo TODA CONVERSA e extrai dados do paciente.
    Formato das linhas: [P HH:MM DD/MM] mensagem
    """
    if not _ativado() or not texto:
        return {}

    resultado: dict = {}
    # Extrair todas as linhas do paciente
    for linha in texto.splitlines():
        m = re.match(r"^\[P\s+[\d:/\s]+\]\s*(.+)$", linha)
        if not m:
            continue
        msg = m.group(1).strip()

        if not resultado.get("data_nasc"):
            data = _extrair_data_nascimento(msg)
            if data:
                resultado["data_nasc"] = data

        if not resultado.get("cpf"):
            cpf = _extrair_cpf(msg)
            if cpf:
                resultado["cpf"] = cpf

        if not resultado.get("nome"):
            nome = _extrair_nome(msg)
            if nome:
                resultado["nome"] = nome

    return resultado


# ─── Leitura e escrita do campo TODA CONVERSA ─────────────────────────────────

def ler_toda_conversa_de_ctx(ctx: dict) -> str:
    """
    Lê o campo TODA CONVERSA do ctx (já carregado do Kommo).
    O kommo.py::get_caller_context_by_lead popula ctx['toda_conversa'].
    """
    return ctx.get("toda_conversa") or ""


def appender_turno(
    texto_atual: str,
    user_text: str,
    resposta_lia: str,
) -> str:
    """
    Monta o novo texto com o turno atual adicionado.
    Formato: [P HH:MM DD/MM] msg\n[L HH:MM DD/MM] resposta\n
    Trunca para _MAX_CHARS mantendo os mais recentes.
    """
    ts = datetime.now(BRT).strftime("%H:%M %d/%m")
    # Trunca mensagens individuais para não estourar
    p_curto = (user_text or "")[:300].replace("\n", " ")
    l_curto = (resposta_lia or "")[:400].replace("\n", " ")
    novo_bloco = f"[P {ts}] {p_curto}\n[L {ts}] {l_curto}\n"
    novo_texto = (texto_atual or "") + novo_bloco
    if len(novo_texto) > _MAX_CHARS:
        # Mantém os mais recentes
        novo_texto = novo_texto[-_MAX_CHARS:]
        # Garante início limpo (não corta no meio de uma linha)
        idx = novo_texto.find("\n")
        if idx > 0:
            novo_texto = novo_texto[idx + 1:]
    return novo_texto


def gravar_toda_conversa(kommo_client, lead_id: int, novo_texto: str) -> bool:
    """
    Grava o campo TODA CONVERSA via patch_textarea_field (sem validação GET).

    Bug C-133 (14/08/2026): patch_custom_fields_raw usava GET pós-PATCH para validar
    que o campo foi gravado. Campos textarea Kommo às vezes não aparecem no GET
    imediatamente após escrita (indexação assíncrona), fazendo a validação retornar
    C-12 mesmo com PATCH bem-sucedido. Resultado: campo ficava vazio.

    Fix: usar patch_textarea_field que confia no HTTP 2xx sem GET de validação.
    """
    if not _ativado():
        return False
    if not lead_id or not novo_texto:
        log.warning("[C-133] gravar_toda_conversa: lead_id=%s ou texto vazio", lead_id)
        return False
    try:
        # Usa método específico para textarea — sem validação GET pós-PATCH
        if hasattr(kommo_client, "patch_textarea_field"):
            ok = kommo_client.patch_textarea_field(
                lead_id, FIELD_ID_TODA_CONVERSA, novo_texto
            )
        else:
            # Fallback para versões antigas do KommoClient (compatibilidade)
            ok, detalhes = kommo_client.patch_custom_fields_raw(
                lead_id,
                [{"field_id": FIELD_ID_TODA_CONVERSA, "values": [{"value": novo_texto}]}],
            )
            if not ok:
                log.warning("[C-133] gravar_toda_conversa (fallback) falhou: %s", detalhes)
        if ok:
            log.info("[C-133] TODA CONVERSA gravada lead=%s (%d chars)", lead_id, len(novo_texto))
        else:
            log.warning("[C-133] gravar_toda_conversa falhou lead=%s", lead_id)
        return ok
    except Exception as exc:
        log.warning("[C-133] gravar_toda_conversa exception lead=%s: %s", lead_id, exc)
        return False


def injetar_dados_em_ctx(ctx: dict, dados: dict) -> None:
    """
    Injeta dados extraídos em ctx['known'], respeitando valores já existentes.
    """
    known = ctx.setdefault("known", {})
    for chave, valor in dados.items():
        if valor and not known.get(chave):
            known[chave] = valor
            log.info("[C-133] injetado ctx.known[%s] = %s", chave, valor)
