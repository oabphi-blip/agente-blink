"""Detector de pedido de atendimento humano (Bug C-61 parte 2 / 20-07-2026).

Origem: Fábio 20/07 — lead 24325544 (Patrícia).
Lia disse "vou te conectar com nossa equipe" mas CONTINUOU respondendo
mais 8 mensagens. Handoff fake — IA nunca desativou.

Solução: detector + processamento REAL do handoff.
    1. detectar_pedido_humano(user_text) → bool
    2. processar_handoff(kommo_client, lead_id) → move pra 1-ATENDIMENTO
       HUMANO (106563343) + desativa IA (ATIVADO IA=Desativado)
    3. resposta_canonica_handoff() → mensagem curta pro paciente
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# PADRÕES — paciente pedindo humano
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# C-66 — Padrões de remarcação/cancelamento/desmarcação (SEMPRE humano)
# ═══════════════════════════════════════════════════════════════════════

_PADROES_REMARCACAO_CANCELAMENTO = re.compile(
    r"("
    # Cancelamento
    r"(?:quero|vou|posso|preciso|pretendo)\s+cancel(?:ar|amento)"
    r"|cancel(?:ar|amento)\s+(?:a\s+)?consulta"
    # Desmarcação
    r"|(?:quero|vou|posso|preciso)\s+desmarc(?:ar|amento)"
    r"|desmarc(?:ar|amento)\s+(?:a\s+)?consulta"
    # Remarcação
    r"|(?:quero|vou|posso|preciso|pretendo)\s+remarc(?:ar|amento)"
    r"|remarc(?:ar|amento)\s+(?:a\s+)?consulta"
    r"|posso\s+remarcar"
    # Não pode/vai (ampliado)
    r"|n[aã]o\s+(?:vou|posso|dá|d[aá]|conseguir[eé]|consigo)\s+(?:poder\s+)?(?:ir|comparecer|dar)"
    r"|n[aã]o\s+(?:vou|posso|d[aá])\s+mais"
    r"|n[aã]o\s+vai\s+dar"
    r"|imposs[íi]vel\s+(?:ir|comparecer)"
    # Mudar/trocar data/dia/horário (ampliado — aceita 'o' ou 'a' antes)
    r"|(?:quero|posso|preciso)\s+(?:mudar|trocar|alterar)\s+(?:[oa]\s+)?(?:data|dia|hor[áa]rio)"
    r"|(?:mudar|trocar|alterar)\s+(?:[oa]\s+)?(?:data|dia|hor[áa]rio)\s+(?:da\s+)?consulta"
    # Faltar / adiar
    r"|vou\s+faltar"
    r"|(?:quero|preciso|posso)\s+adiar"
    r"|adiar\s+(?:a\s+)?consulta"
    r")",
    re.IGNORECASE,
)


def _ativado_remarcacao() -> bool:
    return (os.getenv("HANDOFF_REMARCACAO_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off",
    )


def detectar_pedido_remarcacao_ou_cancelamento(user_text: str) -> bool:
    """C-66: detecta se paciente pediu remarcar/desmarcar/cancelar/faltar.

    QUALQUER match → transferir pra humano IMEDIATAMENTE.
    Fábio 21/07/2026: 'remarcação tem particularidades que a IA não resolve'.
    """
    if not _ativado_remarcacao():
        return False
    if not user_text or not user_text.strip():
        return False
    return bool(_PADROES_REMARCACAO_CANCELAMENTO.search(user_text))


def resposta_canonica_remarcacao(nome_paciente: Optional[str] = None) -> str:
    """Resposta canônica ÚNICA quando paciente pediu remarcação/cancelamento."""
    saudacao = f"{nome_paciente.split()[0]}, " if nome_paciente else ""
    return (
        f"{saudacao}entendi! Vou passar seu atendimento pra nossa equipe "
        "humana agora. Remarcação/cancelamento tem particularidades que só "
        "nossa equipe consegue resolver com você. Em instantes uma pessoa "
        "da Blink responde por aqui. 🤝"
    )


_PADROES_PEDIDO_HUMANO = re.compile(
    r"("
    # Direto — quero/prefiro/preciso com humano/atendente/pessoa/alguém
    r"(?:quero|prefiro|preciso|posso)\s+(?:falar|conversar|atendimento|um|uma)?\s*"
    r"(?:com\s+)?(?:um\s+|uma\s+)?(?:humano|atendente|pessoa(?:\s+real)?|gente\s+de\s+verdade|algu[eé]m)"
    r"|prefiro\s+humano"
    r"|prefiro\s+atendente"
    r"|prefiro\s+pessoa"
    r"|(?:falar|conversar)\s+com\s+(?:um\s+)?atendente"
    r"|atendimento\s+humano"
    # Rejeição direta ao bot
    r"|(?:n[aã]o|nao)\s+(?:quero|gosto|aguento|tolero)\s+(?:falar\s+com\s+)?(?:rob[ôo]|bot|m[aá]quina|ia)"
    r"|(?:me\s+)?passa\s+(?:pra|para)\s+(?:um\s+|uma\s+)?(?:atendente|humano|pessoa|algu[eé]m)"
    r"|(?:me\s+)?transfere\s+(?:pra|para)\s+(?:algu[eé]m|humano|atendente|pessoa)"
    r"|(?:posso|pode)\s+(?:me\s+)?(?:transferir|passar)\s+(?:pra|para)\s+(?:algu[eé]m|humano|atendente|pessoa)"
    r"|(?:tem|h[aá])\s+(?:algu[eé]m|humano|atendente|pessoa)\s+(?:pra|para)\s+(?:falar|atender)"
    r"|(?:t[oô]|estou)\s+falando\s+com\s+rob[ôo]"
    r"|isso\s+[eé]\s+rob[ôo]"
    # Frases de frustração alta
    r"|(?:cansei|chega)\s+de\s+(?:falar\s+com\s+)?(?:rob[ôo]|ia|bot|m[aá]quina)"
    r")",
    re.IGNORECASE,
)


def _ativado() -> bool:
    return (os.getenv("HANDOFF_HUMANO_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off",
    )


def detectar_pedido_humano(user_text: str) -> bool:
    """Detecta se paciente pediu atendimento humano.

    Casos:
        "quero falar com humano" → True
        "prefiro atendente" → True
        "me passa pra alguém" → True
        "cansei de robô" → True
        "isso é robô?" → True
        "quero agendar" → False
    """
    if not _ativado():
        return False
    if not user_text or not user_text.strip():
        return False
    return bool(_PADROES_PEDIDO_HUMANO.search(user_text))


# ═══════════════════════════════════════════════════════════════════════
# STATUS IDs — do CLAUDE.md seção 4
# ═══════════════════════════════════════════════════════════════════════

STATUS_ATENDIMENTO_HUMANO = 106563343  # "1-ATENDIMENTO HUMANO"
FIELD_ATIVADO_IA = 1260817
ENUM_ATIVADO_IA_DESATIVADO = 927035


# ═══════════════════════════════════════════════════════════════════════
# PROCESSAMENTO REAL DO HANDOFF
# ═══════════════════════════════════════════════════════════════════════

def processar_handoff(
    kommo_client: Any,
    lead_id: int | str,
    motivo: str = "paciente_pediu_humano",
) -> dict:
    """Executa handoff REAL (Bug C-61 parte 2):
        1. Move lead pra 1-ATENDIMENTO HUMANO (status 106563343)
        2. Desativa IA (ATIVADO IA = Desativado)
        3. Grava nota indicando o motivo
        4. Retorna dict com resultado

    Fail-open: erro em qualquer etapa → retorna erro no dict mas
    NÃO estoura exceção pra não travar o pipeline.
    """
    resultado = {
        "ok": False,
        "moveu_status": False,
        "desativou_ia": False,
        "gravou_nota": False,
        "erro": None,
    }

    if not _ativado():
        resultado["erro"] = "toggle_off"
        return resultado

    try:
        # 1. Move status + desativa IA — mesma call
        update_fields = {
            "convenio": None,  # não mexe em campos existentes
        }
        # Prefere método específico se existir
        if hasattr(kommo_client, "atualizar_status_lead"):
            try:
                kommo_client.atualizar_status_lead(
                    lead_id, STATUS_ATENDIMENTO_HUMANO,
                )
                resultado["moveu_status"] = True
            except Exception as e:  # noqa: BLE001
                log.warning("Falha mover status: %s", e)

        # 2. Desativa IA via update_lead_fields
        if hasattr(kommo_client, "update_lead_fields"):
            try:
                kommo_client.update_lead_fields(
                    lead_id,
                    {"ATIVADO IA?": "Desativado"},
                )
                resultado["desativou_ia"] = True
            except Exception as e:  # noqa: BLE001
                log.warning("Falha desativar IA: %s", e)

        # 3. Grava nota com motivo
        if hasattr(kommo_client, "add_note"):
            try:
                kommo_client.add_note(
                    lead_id,
                    f"[SISTEMA] Handoff automático — motivo: {motivo}. "
                    "Lead movido pra 1-ATENDIMENTO HUMANO + IA desativada. "
                    "Aguarda atendente responder.",
                )
                resultado["gravou_nota"] = True
            except Exception as e:  # noqa: BLE001
                log.warning("Falha gravar nota: %s", e)

        resultado["ok"] = (
            resultado["moveu_status"]
            or resultado["desativou_ia"]
        )
    except Exception as e:  # noqa: BLE001
        resultado["erro"] = str(e)
        log.exception("Handoff falhou lead=%s", lead_id)

    return resultado


def resposta_canonica_handoff(nome_paciente: Optional[str] = None) -> str:
    """Mensagem curta enviada ao paciente logo antes do handoff real."""
    saudacao = f"{nome_paciente.split()[0]}, " if nome_paciente else ""
    return (
        f"{saudacao}vou passar seu atendimento pra nossa equipe agora. "
        "Em instantes uma pessoa da Blink responde por aqui. 🤝"
    )
