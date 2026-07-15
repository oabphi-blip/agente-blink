"""
Task #413 (14-15/07/2026) — Handoff humano preserva contexto.

Bug reincidente: quando Ariany/Stephany manda mensagem no meio da
conversa e depois Lia é reativada, Lia perde o contexto e trata paciente
como novo. Casos:
  - Emmy 24300272 (14/07)
  - Melissa 10934653 (14/07)
  - Ana Luiza 24290902 (12/07)
  - vários leads antes

Fábio: "Não está conseguindo conviver com o atendimento humano. Saltando
a mensagem, e silenciando."

Fix: quando ctx tem notas humanas RECENTES (últimas 6h) + notas da Lia,
carrega até 20 notas cronológicas e injeta como bloco CONVERSA_ATUAL no
system prompt. Lia lê e continua do ponto onde humano parou.
"""

from __future__ import annotations

import time as _time
from typing import Iterable, Optional


# Janela: só considera notas dos últimos 6h como "conversa atual".
# Notas mais antigas viram histórico/referência, não bloco vivo.
_JANELA_CONVERSA_ATUAL_SEG = 6 * 3600  # 6 horas

# Máximo de notas incluídas no bloco (evita estourar cache Anthropic).
_MAX_NOTAS_CONVERSA = 20


def _eh_nota_lia(nota: dict) -> bool:
    """Nota da Lia = created_by == 0 (bot) E texto começa com 'Lia (WhatsApp)'."""
    if not isinstance(nota, dict):
        return False
    if int(nota.get("created_by") or 0) != 0:
        return False
    texto = str(nota.get("text") or "")
    return texto.startswith("Lia (WhatsApp)") or texto.startswith("🤖 Lia")


def _eh_nota_humano_lendo_paciente(nota: dict) -> bool:
    """Nota humana de operador (Ariany, Stephany, etc) — created_by > 0
    E não é mensagem inbound do paciente."""
    if not isinstance(nota, dict):
        return False
    if int(nota.get("created_by") or 0) <= 0:
        return False
    return True


def _eh_nota_paciente(nota: dict) -> bool:
    """Nota do paciente (inbound WhatsApp) = created_by == 0 E texto começa
    com '💬 Paciente (WhatsApp)' (fix task #406)."""
    if not isinstance(nota, dict):
        return False
    if int(nota.get("created_by") or 0) != 0:
        return False
    texto = str(nota.get("text") or "")
    return texto.startswith("💬 Paciente") or texto.startswith("Paciente (WhatsApp)")


def _autor_da_nota(nota: dict) -> str:
    """Retorna label do autor pra exibir no bloco."""
    if _eh_nota_lia(nota):
        return "LIA"
    if _eh_nota_paciente(nota):
        return "PACIENTE"
    if _eh_nota_humano_lendo_paciente(nota):
        return "HUMANO"
    return "SISTEMA"


def _texto_limpo(nota: dict) -> str:
    """Remove prefixos ('Lia (WhatsApp):', '💬 Paciente (WhatsApp):') do texto."""
    t = str(nota.get("text") or "").strip()
    for prefixo in (
        "🤖 Lia (WhatsApp):",
        "Lia (WhatsApp):",
        "💬 Paciente (WhatsApp):",
        "Paciente (WhatsApp):",
    ):
        if t.startswith(prefixo):
            t = t[len(prefixo):].strip()
            break
    return t


def houve_handoff_humano_recente(
    notas: Optional[Iterable[dict]],
    janela_seg: int = _JANELA_CONVERSA_ATUAL_SEG,
) -> bool:
    """True se existe pelo menos 1 nota humana (operador) nas últimas Xh.
    Diferente de nota do paciente (que é created_by=0)."""
    if not notas:
        return False
    now = _time.time()
    for nota in notas:
        if not _eh_nota_humano_lendo_paciente(nota):
            continue
        ts_str = nota.get("created_at") or ""
        try:
            # created_at do Kommo é ISO 8601 UTC "2026-07-14T20:30:00.000Z"
            from datetime import datetime as _dt
            if isinstance(ts_str, (int, float)):
                ts = float(ts_str)
            elif isinstance(ts_str, str) and ts_str:
                ts = _dt.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            else:
                continue
            if now - ts < janela_seg:
                return True
        except (ValueError, TypeError):
            continue
    return False


def montar_bloco_conversa_atual(
    notas: Optional[Iterable[dict]],
    janela_seg: int = _JANELA_CONVERSA_ATUAL_SEG,
    max_notas: int = _MAX_NOTAS_CONVERSA,
) -> str:
    """Monta bloco de texto pronto pra injetar no system prompt.

    Formato:
        ================================================================
        CONVERSA ATUAL (histórico intercalado — Lia + Humano + Paciente)
        ================================================================
        [PACIENTE 12:30] Oi, quero marcar consulta
        [LIA 12:31] Olá! Pra qual médico?
        [HUMANO 12:33] Olá, aqui é a Ariany. Vou te ajudar.
        [PACIENTE 12:35] Obrigada
        ...
        ================================================================
        REGRA: Você é a Lia. Respeite TUDO que o HUMANO disse acima.
        NÃO repita perguntas. NÃO reinicie triagem. Continue do último
        turno do HUMANO ou do PACIENTE. Se o HUMANO já resolveu uma
        parte, você segue da parte SEGUINTE.
        ================================================================

    Retorna string vazia se não há notas relevantes ou se não houve
    handoff humano recente (nesse caso não precisa injetar).
    """
    if not notas:
        return ""
    if not houve_handoff_humano_recente(notas, janela_seg):
        return ""

    now = _time.time()
    entradas: list[tuple[float, str, str]] = []

    for nota in notas:
        autor = _autor_da_nota(nota)
        if autor == "SISTEMA":
            continue
        ts_str = nota.get("created_at") or ""
        try:
            from datetime import datetime as _dt
            if isinstance(ts_str, (int, float)):
                ts = float(ts_str)
            elif isinstance(ts_str, str) and ts_str:
                ts = _dt.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            else:
                continue
            if now - ts > janela_seg:
                continue
            texto = _texto_limpo(nota)
            if not texto:
                continue
            # Formato HH:MM no BRT
            from zoneinfo import ZoneInfo
            brt = ZoneInfo("America/Sao_Paulo")
            hora_str = _dt.fromtimestamp(ts, tz=brt).strftime("%H:%M")
            entradas.append((ts, hora_str, f"[{autor} {hora_str}] {texto}"))
        except (ValueError, TypeError, ImportError):
            continue

    if not entradas:
        return ""

    # Ordenar cronologicamente e limitar
    entradas.sort(key=lambda x: x[0])
    entradas = entradas[-max_notas:]  # últimas N

    linhas = [e[2] for e in entradas]
    return (
        "\n\n================================================================"
        "\nCONVERSA ATUAL (histórico intercalado — Lia + Humano + Paciente)"
        "\n================================================================"
        "\n" + "\n".join(linhas) +
        "\n================================================================"
        "\nREGRA DE OURO: Você é a Lia. RESPEITE tudo que o HUMANO disse"
        "\nacima. NÃO repita perguntas que ele já fez. NÃO reinicie triagem."
        "\nSe o HUMANO já resolveu parte da conversa, você continua da"
        "\nparte SEGUINTE. Se o PACIENTE respondeu ao HUMANO, considere"
        "\nque a informação foi passada — não pergunte de novo."
        "\n================================================================"
    )
