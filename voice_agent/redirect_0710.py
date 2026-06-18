# voice_agent/redirect_0710.py
"""Agente redirecionador 0710 → 8133 (Blink Oftalmologia).

Missão única: convencer pacientes que chegam pelo número legado (61 9 9663-0710)
a migrarem para o canal oficial (61 8133-1005).

Não cria leads no Kommo. Não conduz atendimento clínico.
Apenas redireciona com link clicável pré-preenchido.

Arquitetura:
  - handle_inbound_0710(): entrada principal
    - _lead_em_etapa_inativa(): P0 — silencia se lead em etapa crítica
      - _dedup_check(): evita flood (1 redirect completo / 7 dias)
        - _escolher_modelo_e_gerar(): Claude Haiku 4.5 com prompt reduzido
          - _filtrar_resposta(): validações pós-geração
            - _montar_nota_kommo(): nota de auditoria para o CRM
            """
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Etapas inativas — espelha exatamente _STATUS_INATIVOS_IA de reativacao_ia.py
_STATUS_INATIVOS_IA: frozenset[int] = frozenset({
    106563343,  # 1-ATENDIMENTO HUMANO
                                                  106157139,  # CIRURGIAS
                                                  106484343,  # LENTES
                                                  106484347,  # FORNECEDORES
})

# Link obrigatório (URL-encoded, texto pré-preenchido para o 8133)
_LINK_OFICIAL = (
    "https://wa.me/556181331005"
    "?text=Ol%C3%A1%21%20Vim%20do%20WhatsApp%20antigo%20%28-0710%29."
    "%20Quero%20continuar%20o%20atendimento%20por%20aqui."
)

# Fallback fixo usado quando modelo falha OU filtros recusam a resposta
_FALLBACK = (
    "Oi! Estou neste número antigo só pra te redirecionar. "
    "O atendimento da Blink agora é pelo canal oficial — toca aqui: "
    + _LINK_OFICIAL
)

# Prompt de sistema (carregado do arquivo .md em knowledge_base/)
_PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "knowledge_base"
    / "_PROMPT_REDIRECT_0710.md"
)

def _load_prompt() -> str:
    try:
          return _PROMPT_PATH.read_text(encoding="utf-8")
except Exception as e:  # noqa: BLE001
    log.warning("[REDIRECT-0710] prompt nao encontrado: %s", e)
    return (
            "Voce eh a Lia da Blink Oftalmologia no numero antigo 0710. "
            "Sua unica missao eh redirecionar o paciente para o canal oficial "
            "61 8133-1005 com o link: " + _LINK_OFICIAL
    )

_SYSTEM_PROMPT: str = _load_prompt()

# ---------------------------------------------------------------------------
# Helpers de telefone
# ---------------------------------------------------------------------------

def _normalizar_telefone(raw: str) -> str:
    """Converte qualquer formato para E.164 sem o '+' (55DDDNÚMERO)."""
    if not raw:
          return raw
        digits = re.sub(r"\D", "", raw)
  if not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits
      return digits

# ---------------------------------------------------------------------------
# P0: verificação de etapa inativa
# ---------------------------------------------------------------------------

def _lead_em_etapa_inativa(kommo_client, phone: str) -> tuple[bool, Optional[int], Optional[int]]:
    """Retorna (inativo, lead_id, status_id).

      Se inativo=True, handler termina sem responder.
        """
  if kommo_client is None:
        return False, None, None
      try:
            ctx = kommo_client.get_caller_context(phone)
            if not ctx or not ctx.get("found"):
                    return False, None, None
                  lead_id = ctx.get("lead_id")
    status_id = (ctx.get("known") or {}).get("status_id")
    # Tenta também via campo direto do contexto
    if status_id is None:
            status_id = ctx.get("status_id")
    if status_id and int(status_id) in _STATUS_INATIVOS_IA:
            return True, lead_id, int(status_id)
    return False, lead_id, status_id
except Exception as e:  # noqa: BLE001
    log.warning("[REDIRECT-0710] _lead_em_etapa_inativa erro: %s", e)
    return False, None, None

# ---------------------------------------------------------------------------
# Dedup e contadores Redis
# ---------------------------------------------------------------------------

def _dedup_check(redis_client, phone: str, ttl_dias: int = 7) -> bool:
    """Retorna True se dedup ativo (mensagem já enviada nos últimos ttl_dias dias)."""
  if redis_client is None:
        return False
  key = f"blink:redirect_0710:{phone}"
  try:
        return bool(redis_client.exists(key))
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] dedup_check erro: %s", e)
    return False

def _dedup_set(redis_client, phone: str, ttl_dias: int = 7) -> None:
    if redis_client is None:
          return
  key = f"blink:redirect_0710:{phone}"
  try:
        redis_client.set(key, "1", ex=ttl_dias * 86400)
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] dedup_set erro: %s", e)

def _escalacao_ativa(redis_client, phone: str) -> bool:
    """Retorna True se paciente já atingiu 3 turnos hoje (escalado para humano)."""
  if redis_client is None:
        return False
  key = f"blink:redirect_0710:escalou:{phone}"
  try:
        return bool(redis_client.exists(key))
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] escalacao_ativa erro: %s", e)
    return False

def _incrementar_turnos_dia(redis_client, phone: str, max_turnos: int = 3) -> int:
    """Incrementa contador de turnos do dia. Retorna novo valor."""
  if redis_client is None:
        return 1
  hoje = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
  key = f"blink:redirect_0710:turnos_dia:{phone}:{hoje}"
  try:
        val = redis_client.incr(key)
        redis_client.expire(key, 86400)
        return int(val)
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] incrementar_turnos_dia erro: %s", e)
    return 1

def _marcar_escalacao(redis_client, phone: str) -> None:
    """Marca que este paciente foi escalado para equipe humana hoje."""
  if redis_client is None:
        return
      key = f"blink:redirect_0710:escalou:{phone}"
  try:
        redis_client.set(key, "1", ex=86400)
        log.info("[REDIRECT-0710] ESCALACAO phone=%s — 3 turnos atingidos", phone)
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] marcar_escalacao erro: %s", e)

def _incrementar_reforco(redis_client, phone: str) -> None:
    if redis_client is None:
          return
        hoje = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
  key = f"blink:redirect_0710:reforco:{phone}:{hoje}"
  try:
        redis_client.incr(key)
        redis_client.expire(key, 86400)
except Exception:  # noqa: BLE001
    pass

# ---------------------------------------------------------------------------
# Geração via modelo
# ---------------------------------------------------------------------------

def _escolher_modelo_e_gerar(
    anthropic_client,
    texto_paciente: str,
    modelo: str = "claude-haiku-4-5-20251001",
) -> str:
    """Chama Claude Haiku com o prompt de sistema reduzido. Retorna a resposta."""
  try:
        resp = anthropic_client.messages.create(
                model=modelo,
                max_tokens=300,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": texto_paciente}],
        )
        return resp.content[0].text.strip() if resp.content else ""
except Exception as e:  # noqa: BLE001
    log.warning("[REDIRECT-0710] anthropic falhou: %s", e)
    return ""

# ---------------------------------------------------------------------------
# Filtros pós-geração
# ---------------------------------------------------------------------------

# Padrões bloqueados
_FILTROS_BLOQUEAR = [
    r"chave\s*pix",
    r"R\$\s*\d",
    r"\d{1,2}h\d{0,2}\b",        # hora específica: "14h", "14h30"
    r"\b(segunda|terça|quarta|quinta|sexta|sábado|domingo)\s+às?\s+\d",  # "quinta às 14"
    r"\b(cirurgia|mapeamento|refração|lasik|catarata|pterígio|vitrectomia)\b",
]

_RE_FILTROS = [re.compile(p, re.IGNORECASE) for p in _FILTROS_BLOQUEAR]
_RE_MARKDOWN = re.compile(r"^#{1,6}\s|^---+$|\*{2,}|_{2,}", re.MULTILINE)
_RE_CAPS = re.compile(r"[A-ZÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙ]{5,}")

def _contar_palavras(texto: str) -> int:
    return len(texto.split())

def _filtrar_resposta(resposta: str) -> tuple[str, bool]:
    """Aplica filtros pós-geração.

      Retorna (texto_filtrado, ok).
        Se ok=False, usar fallback.
          """
  if not resposta:
        return resposta, False

  violacoes = 0

  # 1. Verifica padrões bloqueados
  for regex in _RE_FILTROS:
        if regex.search(resposta):
                log.warning("[REDIRECT-0710] filtro bloqueou: %s", regex.pattern[:40])
                violacoes += 1

      # 2. Se 2+ violações, descarta
      if violacoes >= 2:
            return resposta, False

  # 3. Se 1 violação, descarta também (segurança extra para escopo fechado)
  if violacoes >= 1:
        return resposta, False

  # 4. Remove markdown estruturado
  resposta = _RE_MARKDOWN.sub("", resposta).strip()

  # 5. Força link se ausente
  if "wa.me/556181331005" not in resposta:
        log.warning("[REDIRECT-0710] link ausente — forcando inclusao")
        resposta = resposta.rstrip(".!?") + " " + _LINK_OFICIAL

  # 6. Corta para 60 palavras (preservando o link)
  palavras = resposta.split()
  if len(palavras) > 60:
        # Tenta preservar o link
        sem_link = resposta.replace(_LINK_OFICIAL, "").strip()
        palavras_sem_link = sem_link.split()
        if len(palavras_sem_link) > 55:
                palavras_sem_link = palavras_sem_link[:55]
              resposta = " ".join(palavras_sem_link) + " " + _LINK_OFICIAL

  # 7. Remove CAPS excessivos (mantém siglas curtas como "Blink")
  # Apenas avisa em log, não bloqueia
  if _RE_CAPS.search(resposta):
        log.warning("[REDIRECT-0710] CAPS detectado — resposta passa mas logada")

  return resposta, True

# ---------------------------------------------------------------------------
# Nota Kommo
# ---------------------------------------------------------------------------

def _montar_nota_kommo(
    texto_inbound: str,
    angulo: str,
    resposta_enviada: str,
    reforco: bool,
) -> str:
    agora = datetime.now(tz=timezone.utc)
  # Converte para BRT (UTC-3)
  hora_brt = agora.strftime("%d/%m/%Y %H:%M") + " BRT"
  return (
        f"[REDIRECT 0710 → 8133]\n"
        f"Hora: {hora_brt}\n"
        f'Texto inbound: "{texto_inbound[:200]}"\n'
        f"Ângulo escolhido: {angulo}\n"
        f'Resposta enviada: "{resposta_enviada[:300]}"\n'
        f"Reforço: {'sim' if reforco else 'não'}"
  )

# ---------------------------------------------------------------------------
# Métricas Redis
# ---------------------------------------------------------------------------

def _incrementar_metricas(
    redis_client,
    angulo: str,
    tem_lead: bool,
) -> None:
    if redis_client is None:
          return
        hoje = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
  try:
        pipe = redis_client.pipeline()
    pipe.incr(f"blink:redirect_0710:total_dia:{hoje}")
    pipe.expire(f"blink:redirect_0710:total_dia:{hoje}", 90 * 86400)
    if angulo:
            pipe.incr(f"blink:redirect_0710:angulo:{angulo}:{hoje}")
            pipe.expire(f"blink:redirect_0710:angulo:{angulo}:{hoje}", 90 * 86400)
          if not tem_lead:
                  pipe.incr(f"blink:redirect_0710:lead_sem_kommo:{hoje}")
                  pipe.expire(f"blink:redirect_0710:lead_sem_kommo:{hoje}", 90 * 86400)
                pipe.execute()
except Exception as e:  # noqa: BLE001
    log.debug("[REDIRECT-0710] metricas erro: %s", e)

# ---------------------------------------------------------------------------
# Handler principal
# ---------------------------------------------------------------------------

def handle_inbound_0710(
    phone: str,
    texto: str,
    redis_client=None,
    kommo_client=None,
    evolution_client=None,
    anthropic_client=None,
    max_turnos_dia: int = 3,
    dedup_ttl_dias: int = 7,
    modelo: str = "claude-haiku-4-5-20251001",
    enabled: bool = True,
) -> dict:
    """Handler principal para mensagens inbound no canal 0710.

      Retorna dict com:
          sent: bool
              motivo_silencio: str ou None
                  angulo: str ou None
                      reforco: bool
                        """
  result = {
        "sent": False,
        "motivo_silencio": None,
        "angulo": None,
        "reforco": False,
  }

  # Toggle global
  if not enabled:
        log.debug("[REDIRECT-0710] desabilitado via flag")
    result["motivo_silencio"] = "disabled"
    return result

  # Normaliza telefone
  phone = _normalizar_telefone(phone)
  if not phone:
        result["motivo_silencio"] = "telefone_invalido"
    return result

  # P0: verificação de etapa inativa (ANTES de qualquer outra coisa)
  inativo, lead_id, status_id = _lead_em_etapa_inativa(kommo_client, phone)
  if inativo:
        log.info(
          "[REDIRECT-0710 SILENCIOSO] motivo=lead_em_etapa_inativa "
          "status_id=%s lead_id=%s phone=%s",
          status_id, lead_id, phone,
  )
    result["motivo_silencio"] = "lead_em_etapa_inativa"
    return result

  # Verificação de escalação humana (paciente já atingiu 3 turnos)
  if _escalacao_ativa(redis_client, phone):
        log.info("[REDIRECT-0710 SILENCIOSO] motivo=escalacao_ativa phone=%s", phone)
    result["motivo_silencio"] = "escalacao_ativa"
    return result

  # Verificação de turnos do dia (antes do dedup, pois reforço também conta turno)
  turnos = _incrementar_turnos_dia(redis_client, phone, max_turnos_dia)
  if turnos > max_turnos_dia:
        _marcar_escalacao(redis_client, phone)
    result["motivo_silencio"] = "max_turnos_atingido"
    return result

  # Dedup: verifica se já enviamos redirect completo nos últimos dedup_ttl_dias
  dedup_ativo = _dedup_check(redis_client, phone, dedup_ttl_dias)

  resposta_final = ""
  angulo = "acolhimento"  # default
  reforco = False

  if dedup_ativo:
        # Resposta de reforço curta (sem chamar modelo)
        reforco = True
    resposta_final = (
            f"Estou te esperando no canal oficial 61 8133-1005. "
            f"Toca aqui: {_LINK_OFICIAL}"
    )
    _incrementar_reforco(redis_client, phone)
    log.info("[REDIRECT-0710] reforco enviado phone=%s", phone)
else:
    # Geração completa via modelo
      if anthropic_client is not None:
              raw = _escolher_modelo_e_gerar(anthropic_client, texto, modelo)
              resposta_filtrada, ok = _filtrar_resposta(raw)
              if ok and resposta_filtrada:
                        resposta_final = resposta_filtrada
                        # Extrai ângulo do log (best-effort — modelo menciona no texto)
                        for ang in ("acolhimento", "conveniência", "autoridade", "urgência", "segurança"):
                                    if ang in resposta_final.lower():
                                                  angulo = ang
                                                  break
                                              # Tenta identificar ângulo pelo conteúdo da resposta
                                              if "sendo desligado" in resposta_final or "perder o atendimento" in resposta_final:
                                                          angulo = "urgência"
              elif "dados" in resposta_final and "proteção" in resposta_final:
                          angulo = "segurança"
      elif "Dra." in resposta_final or "Dr." in resposta_final:
          angulo = "autoridade"
elif "segundos" in resposta_final or "rápido" in resposta_final:
          angulo = "conveniência"
else:
          angulo = "acolhimento"
else:
        log.warning("[REDIRECT-0710] filtro recusou — usando fallback phone=%s", phone)
        resposta_final = _FALLBACK
        angulo = "fallback"
else:
      resposta_final = _FALLBACK
      angulo = "fallback"

    # Grava dedup (7 dias)
    _dedup_set(redis_client, phone, dedup_ttl_dias)

  # Envio
  if evolution_client is not None and resposta_final:
        try:
                evolution_client.send_text(number=phone, text=resposta_final)
                result["sent"] = True
                log.info(
                  "[REDIRECT-0710] enviado phone=%s angulo=%s reforco=%s",
                  phone, angulo, reforco,
                )
except Exception as e:  # noqa: BLE001
      log.warning("[REDIRECT-0710] evolution.send_text falhou: %s", e)
      result["motivo_silencio"] = f"evolution_erro: {str(e)[:100]}"
      return result
else:
    result["sent"] = bool(resposta_final)  # para testes sem evolution_client

  result["angulo"] = angulo
  result["reforco"] = reforco

  # Métricas
  _incrementar_metricas(redis_client, angulo, lead_id is not None)

  # Nota Kommo (somente se lead foi encontrado)
  if lead_id and kommo_client is not None and result["sent"]:
        try:
                nota = _montar_nota_kommo(texto, angulo, resposta_final, reforco)
                kommo_client.add_note(int(lead_id), nota)
except Exception as e:  # noqa: BLE001
      log.warning("[REDIRECT-0710] add_note falhou: %s", e)

  return result
