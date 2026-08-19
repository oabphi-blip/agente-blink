"""Triagem Simples — C-149 (19/08/2026)

Coleta os 5 dados mínimos para agendamento e transfere para ATENDIMENTO HUMANO.
Sem LLM, sem slots Medware, sem convênio complexo — apenas 5 perguntas em sequência.

Dados coletados:
  1. Quantidade de agendamentos
  2. Convênio (nome ou "sem convênio")
  3. Nome completo do paciente
  4. Data de nascimento
  5. Motivo da consulta

Toggle: TRIAGEM_SIMPLES_ATIVADA=1 (default OFF até deploy consciente)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

def _ativada() -> bool:
    return os.environ.get("TRIAGEM_SIMPLES_ATIVADA", "0").lower() in ("1", "true", "yes", "on")

# ---------------------------------------------------------------------------
# Extração de respostas do paciente
# ---------------------------------------------------------------------------

_RE_QUANTIDADE = re.compile(
    r"\b(uma?|dois?|duas?|tr[eê]s?|quatro|cinco|[1-5])\b"
    r"|\b(s[oó]\s+(?:eu|um|uma))\b"
    r"|\b(minha?\s+(?:esposa|marido|filho[sa]?|m[aã]e|pai))\b",
    re.IGNORECASE,
)
_RE_QUANTIDADE_NUM = re.compile(r"\b([1-5])\b")

_RE_SEM_CONVENIO = re.compile(
    r"\b(sem\s+conv[eê]nio|particular|n[aã]o\s+tem?|n[aã]o\s+possuo|n[aã]o\s+tenho"
    r"|sem\s+plano|pago\s+(?:eu\s+mesmo|direto))\b",
    re.IGNORECASE,
)

_RE_DATA_NASC = re.compile(
    r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b"
    r"|\b(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)

_MESES = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10",
    "novembro": "11", "dezembro": "12",
}

# ---------------------------------------------------------------------------
# Chave Redis por lead
# ---------------------------------------------------------------------------

def _chave(lead_id) -> str:
    return f"blink:triagem:{lead_id}"

# ---------------------------------------------------------------------------
# Extração de contexto do inbound
# ---------------------------------------------------------------------------

def _extrair_do_inbound(user_text: str, ctx: dict) -> dict:
    """Extrai dados do inbound e retorna dict com novos achados."""
    achados: dict = {}
    ut = (user_text or "").strip()

    known = ctx.get("known") or {}

    # Quantidade
    if not known.get("quantidade_agendamentos"):
        m = _RE_QUANTIDADE_NUM.search(ut)
        if m:
            achados["quantidade_agendamentos"] = m.group(1)
        elif _RE_QUANTIDADE.search(ut):
            texto = _RE_QUANTIDADE.search(ut).group(0).lower()
            mapa = {"uma": "1", "um": "1", "dois": "2", "duas": "2",
                    "três": "3", "tres": "3", "quatro": "4", "cinco": "5"}
            for k, v in mapa.items():
                if k in texto:
                    achados["quantidade_agendamentos"] = v
                    break
            if not achados.get("quantidade_agendamentos"):
                achados["quantidade_agendamentos"] = "1"

    # Convênio
    if not known.get("convenio") and not known.get("sem_convenio"):
        if _RE_SEM_CONVENIO.search(ut):
            achados["sem_convenio"] = True
            achados["convenio"] = "Sem convênio"
        else:
            # só captura como convênio se for texto curto que NÃO seja motivo/rotina/etc.
            _NAO_CONVENIO = {
                "rotina", "retorno", "urgente", "urgencia", "urgência",
                "consulta", "exame", "cirurgia", "catarata", "estrabismo",
                "visao", "visão", "oculos", "óculos", "miopia", "astigmatismo",
                "glaucoma", "macula", "macula", "pterígio", "pterigio",
                "checkup", "check-up", "revisao", "revisão",
            }
            palavras = [w for w in ut.split() if len(w) > 2]
            if 1 <= len(palavras) <= 5:
                genericos = {"oi", "olá", "ola", "bom", "dia", "tarde", "noite",
                             "sim", "não", "nao", "ok", "certo", "tudo", "bem"}
                palavras_lower = {w.lower() for w in palavras}
                if (not all(w.lower() in genericos for w in palavras)
                        and not palavras_lower & _NAO_CONVENIO):
                    achados["convenio"] = ut.strip()

    # Nome completo (≥ 2 palavras, só letras)
    if not known.get("nome_paciente"):
        palavras = ut.strip().split()
        if (2 <= len(palavras) <= 6 and
                all(re.match(r"^[A-Za-zÀ-ú\-']+$", p) for p in palavras)):
            achados["nome_paciente"] = ut.strip().title()

    # Data de nascimento
    if not known.get("data_nasc"):
        m = _RE_DATA_NASC.search(ut)
        if m:
            if m.group(1):  # DD/MM/AAAA
                d, mo, a = m.group(1), m.group(2), m.group(3)
                if len(a) == 2:
                    a = "19" + a
                achados["data_nasc"] = f"{d.zfill(2)}/{mo.zfill(2)}/{a}"
            else:  # DD de mês de AAAA
                d, mes_str, a = m.group(4), m.group(5).lower(), m.group(6)
                mo = _MESES.get(mes_str, "??")
                achados["data_nasc"] = f"{d.zfill(2)}/{mo}/{a}"

    # Motivo (qualquer texto depois das outras perguntas — captura mais liberalmente)
    if not known.get("motivo_consulta"):
        if len(ut) >= 3:
            achados["motivo_consulta"] = ut.strip()

    return achados


# ---------------------------------------------------------------------------
# Próxima pergunta
# ---------------------------------------------------------------------------

def _proxima_pergunta(known: dict, nome_contato: str) -> Optional[str]:
    """Retorna a próxima pergunta a fazer, ou None se todos os dados foram coletados."""
    saud = f"{nome_contato.split()[0]}, " if nome_contato else ""

    if not known.get("quantidade_agendamentos"):
        return f"{saud}a consulta é para quantas pessoas? 😊"

    if not known.get("convenio") and not known.get("sem_convenio"):
        return "Tem plano de saúde? Se sim, qual o nome do convênio?"

    if not known.get("nome_paciente"):
        qtd = known.get("quantidade_agendamentos", "1")
        if qtd != "1":
            return "Qual o nome completo dos pacientes?"
        return "Qual o nome completo do paciente?"

    if not known.get("data_nasc"):
        nome = known.get("nome_paciente", "o paciente").split()[0]
        return f"Qual a data de nascimento de {nome}? (DD/MM/AAAA)"

    if not known.get("motivo_consulta"):
        return "Qual o motivo da consulta? (ex: rotina, retorno, dificuldade visual, catarata...)"

    return None  # tudo coletado


# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------

def _montar_resumo(known: dict) -> str:
    qtd = known.get("quantidade_agendamentos", "1")
    conv = known.get("convenio") or ("Sem convênio" if known.get("sem_convenio") else "—")
    nome = known.get("nome_paciente", "—")
    nasc = known.get("data_nasc", "—")
    motivo = known.get("motivo_consulta", "—")

    return (
        f"Perfeito! Vou passar as informações para nossa equipe:\n\n"
        f"👤 Paciente: {nome}\n"
        f"📅 Nascimento: {nasc}\n"
        f"🏥 Convênio: {conv}\n"
        f"📋 Motivo: {motivo}\n"
        f"👥 Nº de pessoas: {qtd}\n\n"
        f"Nossa equipe entrará em contato em breve para confirmar o horário. 😊"
    )


# ---------------------------------------------------------------------------
# Função principal — chamada pelo pipeline
# ---------------------------------------------------------------------------

def processar(
    lead_id,
    user_text: str,
    ctx: dict,
    redis_client=None,
) -> dict:
    """Processa um turno de triagem simples.

    Retorna:
        {"resposta": str, "transferir": False}  — envia resposta e continua
        {"resposta": str, "transferir": True}   — envia resumo e move para humano
        {"ativo": False}                         — triagem_simples não ativa
    """
    if not _ativada():
        return {"ativo": False}

    # Verificar se triagem já foi concluída para este lead
    if redis_client:
        try:
            if redis_client.get(f"blink:triagem_concluida:{lead_id}"):
                return {"ativo": False}  # já transferido → não interferir
        except Exception:
            pass

    known = ctx.get("known") or {}
    nome_contato = known.get("nome_contato") or known.get("nome_paciente") or ""

    # Extrair dados do inbound e mesclar no known
    novos = _extrair_do_inbound(user_text, ctx)

    # Não deixar extração de convenio/motivo/nome sobrescrever perguntas anteriores
    # quando o known ainda está incompleto — só aplica achado se faz sentido
    # na sequência atual
    if not known.get("quantidade_agendamentos") and novos.get("quantidade_agendamentos"):
        known["quantidade_agendamentos"] = novos["quantidade_agendamentos"]

    elif (not known.get("convenio") and not known.get("sem_convenio") and
          known.get("quantidade_agendamentos")):
        if novos.get("sem_convenio"):
            known["sem_convenio"] = True
            known["convenio"] = "Sem convênio"
        elif novos.get("convenio"):
            known["convenio"] = novos["convenio"]

    elif (not known.get("nome_paciente") and known.get("convenio") or known.get("sem_convenio")):
        if novos.get("nome_paciente"):
            known["nome_paciente"] = novos["nome_paciente"]

    elif not known.get("data_nasc") and known.get("nome_paciente"):
        if novos.get("data_nasc"):
            known["data_nasc"] = novos["data_nasc"]

    elif not known.get("motivo_consulta") and known.get("data_nasc"):
        if novos.get("motivo_consulta"):
            known["motivo_consulta"] = novos["motivo_consulta"]

    # Próxima pergunta ou transferência
    prox = _proxima_pergunta(known, nome_contato)

    if prox is None:
        # Todos os dados coletados → resumo + transferir
        resumo = _montar_resumo(known)
        if redis_client:
            try:
                redis_client.setex(f"blink:triagem_concluida:{lead_id}", 86400 * 7, "1")
            except Exception:
                pass
        log.info("[TRIAGEM-SIMPLES] lead=%s — dados completos, transferindo", lead_id)
        return {"ativo": True, "resposta": resumo, "transferir": True, "known": known}

    log.debug("[TRIAGEM-SIMPLES] lead=%s → %s", lead_id, prox[:60])
    return {"ativo": True, "resposta": prox, "transferir": False, "known": known}
