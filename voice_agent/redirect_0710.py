# voice_agent/redirect_0710.py
"""Agente redirecionador 0710 -> 8133 (Blink Oftalmologia).

Missão única: convencer pacientes que chegam pelo número legado (61 9 9663-0710)
a migrarem para o canal oficial (61 8133-1005).

Não cria leads no Kommo. Não conduz atendimento clínico.
Apenas redireciona com link clicável pré-preenchido.

Bug C-40 (20/06/2026): re-escrito do zero — versão original tinha auto-formatter
quebrado e nunca compilou. Versão atual é mínima funcional sem LLM (usa fallback
fixo), pra reduzir custo Anthropic em mensagens de redirect.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Etapas Kommo que silenciam o redirect (lead em ATENDIMENTO HUMANO etc)
_STATUS_INATIVOS_IA: frozenset[int] = frozenset({
    106563343,  # 1-ATENDIMENTO HUMANO
    106157139,  # CIRURGIAS
    106484343,  # LENTES
    106484347,  # FORNECEDORES
})

# Link oficial — pode ser sobrescrito via env REDIRECT_0710_LINK_8133
_LINK_OFICIAL = (
    "https://wa.me/5561981331005"
    "?text=Ol%C3%A1%21%20Vim%20do%20WhatsApp%20antigo%20%28-0710%29."
    "%20Quero%20continuar%20o%20atendimento%20por%20aqui."
)

# Fallback fixo (usado quando não há LLM disponível)
_FALLBACK = (
    "Oi! 😊 Aqui é da Blink Oftalmologia. Este número antigo está sendo "
    "desativado. Pra continuar o atendimento com toda a atenção, toca aqui no "
    "nosso canal oficial: " + _LINK_OFICIAL
)


# ---------------------------------------------------------------------------
# Helpers de telefone
# ---------------------------------------------------------------------------

def _normalizar_telefone(raw: str) -> str:
    """Converte qualquer formato para E.164 sem o '+' (55DDDNÚMERO).

    Strip de sufixo "@s.whatsapp.net" / "@lid" tipico do WhatsApp.
    """
    if not raw:
        return ""
    # Remove sufixos WhatsApp
    base = raw.split("@", 1)[0]
    digits = re.sub(r"\D", "", base)
    if not digits:
        return ""
    if not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits
    return digits


# ---------------------------------------------------------------------------
# P0: verificação de etapa inativa
# ---------------------------------------------------------------------------

def _lead_em_etapa_inativa(
    kommo_client, phone: str
) -> tuple[bool, Optional[int], Optional[int]]:
    """Retorna (inativo, lead_id, status_id). Se inativo, handler silencia."""
    if kommo_client is None:
        return False, None, None
    try:
        ctx = kommo_client.get_caller_context(phone)
        if not ctx or not ctx.get("found"):
            return False, None, None
        lead_id = ctx.get("lead_id")
        status_id = (ctx.get("known") or {}).get("status_id")
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
    """Retorna True se já enviamos redirect completo nos últimos ttl_dias."""
    if redis_client is None:
        return False
    key = f"blink:redirect_0710:{phone}"
    try:
        return bool(redis_client.exists(key))
    except Exception as e:  # noqa: BLE001
        log.debug("[REDIRECT-0710] dedup_check erro: %s", e)
        return False


def _dedup_set(redis_client, phone: str, ttl_dias: int = 7) -> None:
    """Grava marcador de dedup com TTL em dias."""
    if redis_client is None:
        return
    key = f"blink:redirect_0710:{phone}"
    try:
        redis_client.set(key, "1", ex=ttl_dias * 86400)
    except Exception as e:  # noqa: BLE001
        log.debug("[REDIRECT-0710] dedup_set erro: %s", e)


def _incrementar_turnos_dia(
    redis_client, phone: str, max_turnos: int = 3
) -> int:
    """Incrementa contador de turnos do dia. Retorna valor atual."""
    if redis_client is None:
        return 1
    from datetime import datetime, timezone
    hoje = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"blink:redirect_0710:turnos:{hoje}:{phone}"
    try:
        atual = redis_client.incr(key)
        redis_client.expire(key, 86400)
        return int(atual)
    except Exception as e:  # noqa: BLE001
        log.debug("[REDIRECT-0710] incrementar_turnos erro: %s", e)
        return 1


def _escalacao_ativa(redis_client, phone: str) -> bool:
    """Retorna True se paciente já está em escalação humana."""
    if redis_client is None:
        return False
    key = f"blink:redirect_0710:escalado:{phone}"
    try:
        return bool(redis_client.exists(key))
    except Exception:  # noqa: BLE001
        return False


def _marcar_escalacao(redis_client, phone: str, ttl_dias: int = 30) -> None:
    """Marca paciente como escalado pra humano (sem mais redirect auto)."""
    if redis_client is None:
        return
    key = f"blink:redirect_0710:escalado:{phone}"
    try:
        redis_client.set(key, "1", ex=ttl_dias * 86400)
    except Exception:  # noqa: BLE001
        pass


def _incrementar_metricas(
    redis_client, angulo: Optional[str], com_lead: bool
) -> None:
    """Incrementa métricas básicas de envio."""
    if redis_client is None:
        return
    try:
        from datetime import datetime, timezone
        hoje = datetime.now(timezone.utc).strftime("%Y%m%d")
        pipe = redis_client.pipeline()
        pipe.incr(f"blink:redirect_0710:enviados:{hoje}")
        pipe.expire(f"blink:redirect_0710:enviados:{hoje}", 90 * 86400)
        if angulo:
            pipe.incr(f"blink:redirect_0710:angulo:{angulo}:{hoje}")
            pipe.expire(f"blink:redirect_0710:angulo:{angulo}:{hoje}", 90 * 86400)
        if not com_lead:
            pipe.incr(f"blink:redirect_0710:lead_sem_kommo:{hoje}")
            pipe.expire(f"blink:redirect_0710:lead_sem_kommo:{hoje}", 90 * 86400)
        pipe.execute()
    except Exception as e:  # noqa: BLE001
        log.debug("[REDIRECT-0710] metricas erro: %s", e)


def _incrementar_reforco(redis_client, phone: str) -> None:
    """Incrementa contador de reforços enviados pra este phone."""
    if redis_client is None:
        return
    try:
        key = f"blink:redirect_0710:reforcos:{phone}"
        redis_client.incr(key)
        redis_client.expire(key, 30 * 86400)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Nota Kommo (auditoria)
# ---------------------------------------------------------------------------

def _montar_nota_kommo(
    inbound_text: str,
    angulo: str,
    resposta_enviada: str,
    reforco: bool,
) -> str:
    """Monta texto pra nota Kommo (auditoria do redirect)."""
    from datetime import datetime, timezone
    tipo = "REFORCO" if reforco else "REDIRECT"
    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return (
        f"[REDIRECT-0710 {tipo} {ts}]\n"
        f"Inbound do paciente: \"{(inbound_text or '')[:200]}\"\n"
        f"Angulo: {angulo}\n"
        f"Resposta enviada: \"{resposta_enviada[:300]}\""
    )


# ---------------------------------------------------------------------------
# Handler principal
# ---------------------------------------------------------------------------

def handle_inbound_0710(
    phone: str,
    texto: str,
    redis_client=None,
    kommo_client=None,
    evolution_client=None,
    anthropic_client=None,  # mantido na assinatura mas não usado (MVP fixo)
    max_turnos_dia: int = 3,
    dedup_ttl_dias: int = 7,
    modelo: str = "claude-haiku-4-5-20251001",  # noqa: ARG001
    enabled: bool = True,
) -> dict:
    """Handler principal para mensagens inbound no canal 0710.

    Lógica simplificada (MVP sem LLM):
      1. Toggle enabled
      2. Normaliza telefone
      3. Verifica etapa inativa (silencia se ATENDIMENTO HUMANO etc)
      4. Verifica escalação ativa
      5. Verifica turnos do dia (max 3)
      6. Verifica dedup (já enviou nos últimos 7 dias?)
         - Sim → manda REFORÇO curto
         - Não → manda FALLBACK completo
      7. Grava dedup
      8. Envia via evolution_client
      9. Métricas + nota Kommo opcional
    """
    result = {
        "sent": False,
        "motivo_silencio": None,
        "angulo": None,
        "reforco": False,
    }

    if not enabled:
        log.debug("[REDIRECT-0710] desabilitado via flag enabled=False")
        result["motivo_silencio"] = "disabled"
        return result

    phone_norm = _normalizar_telefone(phone)
    if not phone_norm:
        result["motivo_silencio"] = "telefone_invalido"
        return result

    # P0 — etapa inativa
    inativo, lead_id, status_id = _lead_em_etapa_inativa(kommo_client, phone_norm)
    if inativo:
        log.info(
            "[REDIRECT-0710 SILENCIOSO] motivo=lead_em_etapa_inativa "
            "status_id=%s lead_id=%s phone=%s",
            status_id, lead_id, phone_norm,
        )
        result["motivo_silencio"] = "lead_em_etapa_inativa"
        return result

    # Escalação humana já ativa
    if _escalacao_ativa(redis_client, phone_norm):
        log.info(
            "[REDIRECT-0710 SILENCIOSO] motivo=escalacao_ativa phone=%s",
            phone_norm,
        )
        result["motivo_silencio"] = "escalacao_ativa"
        return result

    # Cap diário de turnos
    turnos = _incrementar_turnos_dia(redis_client, phone_norm, max_turnos_dia)
    if turnos > max_turnos_dia:
        _marcar_escalacao(redis_client, phone_norm)
        result["motivo_silencio"] = "max_turnos_atingido"
        return result

    # Dedup → reforço curto ou mensagem completa
    dedup_ativo = _dedup_check(redis_client, phone_norm, dedup_ttl_dias)
    reforco = False
    if dedup_ativo:
        reforco = True
        resposta_final = (
            f"Estou te esperando no canal oficial 61 8133-1005. "
            f"Toca aqui: {_LINK_OFICIAL}"
        )
        angulo = "reforco"
        _incrementar_reforco(redis_client, phone_norm)
        log.info("[REDIRECT-0710] reforco enviado phone=%s", phone_norm)
    else:
        resposta_final = _FALLBACK
        angulo = "fallback"
        _dedup_set(redis_client, phone_norm, dedup_ttl_dias)
        log.info("[REDIRECT-0710] primeira msg enviada phone=%s", phone_norm)

    # Envio via Evolution
    if evolution_client is not None and resposta_final:
        try:
            evolution_client.send_text(number=phone_norm, text=resposta_final)
            result["sent"] = True
            log.info(
                "[REDIRECT-0710] enviado phone=%s angulo=%s reforco=%s",
                phone_norm, angulo, reforco,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[REDIRECT-0710] evolution.send_text falhou: %s", e)
            result["motivo_silencio"] = f"evolution_erro: {str(e)[:100]}"
            return result
    else:
        # Modo teste (sem Evolution): considera sent=True se gerou texto
        result["sent"] = bool(resposta_final)

    result["angulo"] = angulo
    result["reforco"] = reforco

    # Métricas
    _incrementar_metricas(redis_client, angulo, lead_id is not None)

    # Nota Kommo (auditoria)
    if lead_id and kommo_client is not None and result["sent"]:
        try:
            nota = _montar_nota_kommo(texto, angulo, resposta_final, reforco)
            kommo_client.add_note(int(lead_id), nota)
        except Exception as e:  # noqa: BLE001
            log.warning("[REDIRECT-0710] add_note falhou: %s", e)

    return result
