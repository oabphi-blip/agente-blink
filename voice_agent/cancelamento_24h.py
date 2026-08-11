"""
Bug C-117 (11/08/2026) — Cancelamento < 24h → política de sinal não devolvido.
================================================================================
Quando paciente cancela ou remarca com menos de 24h de antecedência e
ctx.known.dia_consulta_iso está preenchido, Python:

1. Calcula delta entre agora (BRT) e a consulta
2. Se delta_horas < 24h → entrega mensagem canônica informando a política
3. Se delta_horas >= 24h → retorna None → LLM trata (cancelamento normal)

Comportamento:
  - Mensagem informativa (NÃO coercitiva) — explica que sinal 50% não é devolvido
    para cancelamentos < 24h, conforme regra E6 da clínica
  - Inclui abertura para reagendamento (converte cancelamento em remarcação)
  - Fail-open: sem dia_consulta_iso, sem data válida, exceção → None

Exemplos de user_text detectados:
  - "quero cancelar"
  - "preciso desmarcar"
  - "vou ter que desmarcar"
  - "não vou poder ir"
  - "não posso comparecer"
  - "quero remarcar"
  - "preciso mudar o horário"

Toggle: CANCELAMENTO_24H_ATIVADO (default ON)
Rollback: CANCELAMENTO_24H_ATIVADO=0 em Easypanel → Implantar.
"""

from __future__ import annotations

import logging
import re
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Toggle (default ON)
# ─────────────────────────────────────────────────────────────────────────────
_ATIVADO = os.environ.get("CANCELAMENTO_24H_ATIVADO", "1").strip().lower() not in (
    "0", "false", "no", "off", ""
)

# ─────────────────────────────────────────────────────────────────────────────
# Fuso horário BRT (UTC-3)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _TZ_BR = _ZoneInfo("America/Sao_Paulo")
except ImportError:
    _TZ_BR = timezone(timedelta(hours=-3))  # type: ignore[assignment]

# ─────────────────────────────────────────────────────────────────────────────
# Threshold
# ─────────────────────────────────────────────────────────────────────────────
HORAS_LIMITE = 24  # < 24h → política se aplica

# ─────────────────────────────────────────────────────────────────────────────
# Padrões de detecção PT-BR — cancelamento / desistência de comparecer
# ─────────────────────────────────────────────────────────────────────────────
_RE_CANCELAR = re.compile(
    r"""
    # Cancelamento explícito
    (?:quero|preciso|gostaria\s+de|vou\s+ter\s+que|tenho\s+que)\s+
      (?:cancelar|desmarcar|desistir|remover|tirar)
    |
    # "vou cancelar", "vou desmarcar"
    vou\s+(?:cancelar|desmarcar|desistir)
    |
    # "não vou poder ir", "não posso comparecer", "não consigo ir"
    n[ãa]o\s+(?:vou\s+(?:poder|conseguir)\s+ir
                |(?:posso|consigo)\s+(?:ir|comparecer|aparecer)
                |vou\s+(?:ir|comparecer))
    |
    # "preciso remarcar", "quero mudar o horário", "trocar o horário"
    (?:preciso|quero|gostaria\s+de)\s+(?:remarcar|mudar|trocar|alterar)\s+(?:o\s+)?hor[aá]rio
    |
    # "infelizmente não vou poder"
    infelizmente\s+n[ãa]o\s+vou
    |
    # "não posso comparecer"
    n[ãa]o\s+posso\s+comparecer
    |
    # "cancelamento" standalone
    \bcancelamento\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Falsos positivos: remarcação afirmativa, confirmação
_RE_NAO_CANCELAR = re.compile(
    r"""
    n[ãa]o\s+(?:quero|preciso|vou)\s+cancelar
    |
    confirmar?\s+(?:consulta|agendamento|hor[aá]rio)
    |
    (?:sim|yes|ok)\s*[,.]?\s*confirmo
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _e_cancelamento(user_text: str) -> bool:
    """True se user_text detecta intenção de cancelar/não comparecer."""
    if _RE_NAO_CANCELAR.search(user_text):
        return False
    return bool(_RE_CANCELAR.search(user_text))


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de delta
# ─────────────────────────────────────────────────────────────────────────────
def _horas_ate_consulta(iso_str: str) -> Optional[float]:
    """
    Retorna horas entre agora e a consulta.
    Negativo se consulta já passou. None se não consegue parsear.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_BR)
        agora = datetime.now(tz=_TZ_BR)
        delta = (dt - agora).total_seconds() / 3600
        return delta
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Resposta canônica
# ─────────────────────────────────────────────────────────────────────────────
def _montar_resposta_cancelamento_24h(horas: float, ctx: dict) -> str:
    """
    Monta mensagem informando política de sinal para cancelamento < 24h.
    Tom: informativo, gentil, abre para remarcação.
    """
    known = ctx.get("known") or {}
    nome = str(known.get("nome_paciente") or known.get("nome") or "").strip()
    primeiro = nome.split()[0] if nome else ""
    saudacao = f"{primeiro}, " if primeiro else ""

    if horas <= 0:
        # Consulta já passou — cancelamento pós-consulta, mensagem diferente
        return (
            f"Entendido, {saudacao}obrigado por nos avisar. "
            "Se quiser agendar uma nova consulta no futuro, é só chamar aqui! 😊"
        )

    # Formata as horas que faltam
    if horas < 1:
        tempo_str = f"{int(horas * 60)} minutos"
    elif horas < 2:
        tempo_str = "menos de 2 horas"
    else:
        tempo_str = f"{int(horas):.0f} horas"

    return (
        f"Entendido, {saudacao}vou registrar o seu cancelamento. 📋\n\n"
        f"⚠️ Como faltam apenas ~{tempo_str} para a consulta, "
        "de acordo com nossa política, o sinal de 50% já pago "
        "**não é devolvido** para cancelamentos com menos de 24h de antecedência. "
        "Isso porque o horário fica bloqueado para outros pacientes.\n\n"
        "Gostaria de **remarcar** para outro dia? "
        "Tenho horários disponíveis e consigo verificar agora! 😊"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────
def deve_informar_politica_cancelamento_24h(
    ctx: Optional[dict],
    user_text: str,
) -> Optional[str]:
    """
    Retorna mensagem de política de sinal se:
      1. Toggle CANCELAMENTO_24H_ATIVADO ativo
      2. user_text detecta intenção de cancelar/não comparecer
      3. ctx.known.dia_consulta_iso está preenchido
      4. Tempo até consulta < 24h

    Retorna None (fail-open) se:
      - Toggle OFF
      - Não é cancelamento
      - Sem dia_consulta_iso
      - Tempo >= 24h (cancelamento normal — LLM trata sem política especial)
      - Consulta não tem sinal (sem flag no ctx)

    Nota: a política só faz sentido quando o paciente PAGOU sinal.
    Se ctx.known.sinal_pago não está True, retorna None (não ameaça sem razão).
    """
    if not _ATIVADO:
        return None

    try:
        if not user_text or not isinstance(user_text, str):
            return None

        if not _e_cancelamento(user_text):
            return None

        if not ctx or not isinstance(ctx, dict):
            return None

        known = ctx.get("known") or {}
        iso_str = known.get("dia_consulta_iso")
        if not iso_str:
            return None  # sem consulta marcada → LLM trata

        # Verifica sinal pago — só aplica política se houve sinal
        # (flag sinal_pago no known, setado pela politica_comparecimento quando paciente
        #  confirma comprovante Pix; ou ausente → não há sinal → política não se aplica)
        sinal_pago = bool(known.get("sinal_pago") or known.get("sinal_recebido"))
        if not sinal_pago:
            # Sem sinal — cancelamento sem custo financeiro
            # Ainda retornamos um aviso gentil para reagendamento mas sem "política"
            horas = _horas_ate_consulta(iso_str)
            if horas is None or horas <= 0 or horas >= HORAS_LIMITE:
                return None
            # Menos de 24h, sem sinal → mensagem simples (sem mencionar sinal)
            nome = str(known.get("nome_paciente") or known.get("nome") or "").strip()
            primeiro = nome.split()[0] if nome else ""
            saudacao = f"{primeiro}, " if primeiro else ""
            return (
                f"Entendido, {saudacao}anotei o cancelamento. "
                "Posso te oferecer outros horários disponíveis para remarcar! "
                "Gostaria de ver as opções? 😊"
            )

        horas = _horas_ate_consulta(iso_str)
        if horas is None:
            return None  # ISO inválido → fail-open

        if horas >= HORAS_LIMITE:
            return None  # >= 24h → cancelamento normal, sem custo

        return _montar_resposta_cancelamento_24h(horas, ctx)

    except Exception as exc:  # noqa: BLE001
        log.warning("[C-117] cancelamento_24h falhou (fail-open): %s", exc)
        return None
