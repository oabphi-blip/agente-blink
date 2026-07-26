"""
Task #413 (14-15/07/2026) — Handoff humano preserva contexto.
Bug C-72 Etapa 1 (26/07/2026) — recuperação de contexto via campo MENS HUMANO.

Bug reincidente: quando Ariany/Stephany manda mensagem no meio da
conversa e depois Lia é reativada, Lia perde o contexto e trata paciente
como novo. Casos:
  - Emmy 24300272 (14/07)
  - Melissa 10934653 (14/07)
  - Ana Luiza 24290902 (12/07)
  - vários leads antes

Fix (Task #413): quando ctx tem notas humanas RECENTES (últimas 6h) + notas da Lia,
carrega até 20 notas cronológicas e injeta como bloco CONVERSA_ATUAL no
system prompt. Lia lê e continua do ponto onde humano parou.

Dois mecanismos de contexto humano:

1. montar_bloco_conversa_atual() [Task #413]
   Le ultimas N notas Kommo (6h window) e reconstroi thread intercalado.
   Cobre: humano reativa Lia no meio de conversa ativa.
   Limitacao: janela 6h. Nao cobre campanhas antigas.

2. montar_bloco_campo_mens_humano() [Bug C-72]
   Le campo MENS HUMANO (1261148) do lead -- sem janela de tempo.
   Cobre: paciente responde dias depois a template/mensagem humana.
   Limitacao: so o texto do ultimo outbound humano (nao thread completo).
   O campo e gravado pelo webhook /admin/kommo-trigger-msg-humano quando
   o humano envia mensagem pelo Kommo. Campanhas via Meta Graph usam
   C-72 Etapa 2 (Chats API) para cobertura completa.
"""

from __future__ import annotations

import re
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


def extrair_chat_id_da_url(url: str) -> Optional[int]:
    """Bug C-72 Etapa 2: extrai chat_id de URL do Kommo.

    Formatos reconhecidos:
      https://univeja.kommo.com/chats/42318/leads/detail/15321519  → 42318
      /chats/42318/leads/detail/15321519                           → 42318
    Se a URL não contém /chats/{id}, retorna None.
    """
    if not url:
        return None
    m = re.search(r"/chats/(\d+)", url)
    if m:
        return int(m.group(1))
    return None


def montar_bloco_historico_chat(messages: list, max_msgs: int = 30) -> str:
    """Bug C-72 Etapa 2: monta bloco de contexto a partir da Chats API Kommo.

    Cada mensagem retornada pela API tem estrutura:
      - content: {type: "text", text: "..."}  (ou content.text direto)
      - created_at: timestamp UNIX
      - direction: "in" (paciente→blink) | "out" (blink→paciente)
      - author: {type: "contact"|"user"|"bot", ...}

    Diferente de montar_bloco_conversa_atual():
    - Não tem janela de tempo — mostra o histórico completo
    - Cobre paciente respondendo dias/semanas depois a campanha
    - Usa API /chats/{chat_id}/messages, não notas Kommo

    Retorna bloco de texto pronto ou string vazia se lista vazia.
    """
    if not messages:
        return ""

    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        brt = ZoneInfo("America/Sao_Paulo")
    except ImportError:
        brt = None  # Python < 3.9 fallback

    linhas = []
    for msg in messages[-max_msgs:]:
        ts = msg.get("created_at") or 0
        try:
            if brt:
                hora = datetime.fromtimestamp(float(ts), tz=brt).strftime("%H:%M %d/%m")
            else:
                hora = datetime.utcfromtimestamp(float(ts)).strftime("%H:%M %d/%m")
        except Exception:
            hora = "??:??"

        direction = str(msg.get("direction") or "").lower()
        # Kommo Chats API retorna content como objeto ou como string direta
        content = msg.get("content") or {}
        if isinstance(content, dict):
            texto = content.get("text") or ""
        else:
            texto = str(content)
        # Fallback: campo "text" na raiz (versões antigas da API)
        if not texto:
            texto = str(msg.get("text") or "").strip()
        if not texto:
            continue

        # direction "in"/"incoming"/"0" = paciente; "out"/"outgoing"/"1" = atendente
        if direction in ("out", "outgoing", "1"):
            autor = "ATENDENTE"
        elif direction in ("in", "incoming", "0"):
            autor = "PACIENTE"
        else:
            # Tenta inferir pelo author.type
            author = msg.get("author") or {}
            atype = str(author.get("type") or "").lower()
            if atype in ("user", "bot"):
                autor = "ATENDENTE"
            elif atype == "contact":
                autor = "PACIENTE"
            else:
                autor = "SISTEMA"

        linhas.append(f"[{autor} {hora}] {texto}")

    if not linhas:
        return ""

    return (
        "\n\n================================================================"
        "\nHISTÓRICO COMPLETO DA CONVERSA (Chats API Kommo — C-72 Etapa 2)"
        "\n================================================================"
        "\n" + "\n".join(linhas) +
        "\n================================================================"
        "\nREGRA C-72: O paciente está respondendo à conversa acima."
        "\nVocê é a Lia. Continue de forma COERENTE com o histórico."
        "\nNÃO reinicie a triagem. Identifique o que já foi tratado."
        "\nSe o ATENDENTE ofertou slots, confirme o que o paciente escolheu."
        "\n================================================================"
    )


def montar_bloco_campo_mens_humano(ctx: dict) -> str:
    """Bug C-72 Etapa 1: injeta bloco de contexto quando MENS HUMANO (1261148)
    está preenchido no lead.

    Diferente de montar_bloco_conversa_atual():
    - Sem janela de tempo (campo persiste indefinidamente)
    - Lê do ctx.known["mens_humano"] (já vem grátis no GET /leads/{id})
    - Cobre paciente respondendo DIAS depois a mensagem humana
    - Não substitui montar_bloco_conversa_atual() — são complementares

    Retorna bloco de texto pronto ou string vazia se campo ausente.
    """
    if not isinstance(ctx, dict):
        return ""
    known = ctx.get("known") or {}
    mens_humano = str(known.get("mens_humano") or "").strip()
    if not mens_humano:
        return ""
    return (
        "\n\n================================================================"
        "\nCONTEXTO: ÚLTIMA MENSAGEM DO ATENDENTE HUMANO"
        "\n================================================================"
        f"\n{mens_humano}"
        "\n================================================================"
        "\nREGRA C-72: O paciente está respondendo à mensagem acima."
        "\nVocê é a Lia. Entenda o que o atendente ofereceu/perguntou e"
        "\ncontinue a conversa de forma coerente com essa mensagem."
        "\nNÃO reinicie a triagem se a mensagem já coletou informações."
        "\n================================================================"
    )


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
