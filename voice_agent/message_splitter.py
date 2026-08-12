"""
voice_agent/message_splitter.py
Bug C-127 Fix 1 (12/08/2026) — Tom conversacional: quebrar mensagens longas em chunks.

Problema: Python bypasses geram 1 string longa → pipeline manda tudo de uma vez.
WhatsApp mostra como um "bloco de texto" → parece robô.

Solução: dividir em 2-3 partes em pontos naturais (fim de frase, emoji de separação,
nova pergunta) e enviar com delay de 1-1.5s entre cada parte.

Regras:
- Mensagem curta (≤ 120 chars ou ≤ 1 frase) → não divide, manda direto
- Mensagem média (2-3 frases ou tem pergunta + contexto) → divide em 2
- Mensagem longa (> 3 frases, múltiplos emojis de opção 1️⃣/2️⃣) → divide em 3 máx
- NUNCA quebrar dentro de uma opção 1️⃣/2️⃣ (menu de escolha deve ficar junto)
- NUNCA quebrar nome do médico no meio
- Toggle: MESSAGE_SPLIT_ENABLED (default ON)
"""

from __future__ import annotations

import logging
import os
import re
import time

log = logging.getLogger(__name__)

# Toggle — setar MESSAGE_SPLIT_ENABLED=0 no Easypanel para desligar
_ENABLED = os.environ.get("MESSAGE_SPLIT_ENABLED", "1").strip().lower() not in (
    "0", "false", "no", "off"
)

# Delay entre partes (segundos). Simulam "digitação".
DELAY_ENTRE_PARTES: float = float(os.environ.get("MESSAGE_SPLIT_DELAY", "1.2"))

# Limite de chars abaixo do qual NÃO divide (mensagem curta)
LIMITE_CURTA: int = 130

# Padrão: bloco de opções 1️⃣/2️⃣ — não quebrar por dentro desse bloco
_RE_OPCOES = re.compile(r"1️⃣.*?(?=\n\n|\Z)", re.DOTALL)

# Pontos naturais de quebra (em ordem de preferência)
# Quebramos APÓS: ponto final + espaço antes de maiúscula, emoji de separação,
# linha em branco antes de pergunta
_RE_QUEBRA_NATURAL = re.compile(
    r"(?<=[.!])\s{1,2}(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\U0001F300-\U0001FFFF])|"  # . / ! → nova frase capitalizada
    r"\n{2,}(?=[^\n])|"  # linha em branco
    r"(?<=\?)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\U0001F300-\U0001FFFF])",  # ? → nova frase
    re.UNICODE,
)


def _tem_menu_opcoes(texto: str) -> bool:
    """Verifica se o texto contém menu 1️⃣/2️⃣ (não deve ser quebrado no meio)."""
    return bool(re.search(r"1️⃣|2️⃣|[12][)\.]\s", texto))


def _contar_frases(texto: str) -> int:
    """Estimativa rápida de número de frases."""
    return len(re.findall(r"[.!?]+", texto))


def _encontrar_ponto_quebra(texto: str, limite_chars: int) -> int:
    """
    Encontra o melhor ponto de quebra até `limite_chars`.
    Retorna o índice onde quebrar (exclusive do espaço/newline).
    Retorna -1 se não encontrar bom ponto.
    """
    # Procura quebras naturais até limite_chars
    melhor = -1
    for m in _RE_QUEBRA_NATURAL.finditer(texto[:limite_chars + 50]):
        if m.start() <= limite_chars:
            melhor = m.start()
    return melhor


def split_message(texto: str) -> list[str]:
    """
    Divide o texto em 2-3 partes conversacionais.

    Retorna lista de 1, 2 ou 3 strings.
    Cada parte é stripped de espaços/newlines extras.
    """
    if not _ENABLED:
        return [texto]

    texto = texto.strip()
    if not texto:
        return [texto]

    # Mensagem curta → não divide
    if len(texto) <= LIMITE_CURTA:
        return [texto]

    # Se tem menu 1️⃣/2️⃣ — identificar onde começa o menu
    # A parte ANTES do menu pode ir em chunk 1, o menu fica junto no chunk 2
    if _tem_menu_opcoes(texto):
        # Achar onde começa o bloco de opções
        m_opcao = re.search(r"\n*1️⃣", texto)
        if m_opcao and m_opcao.start() > 30:
            parte1 = texto[:m_opcao.start()].strip()
            parte2 = texto[m_opcao.start():].strip()
            if parte1 and parte2:
                return [parte1, parte2]
        # Se não achou bom ponto, manda tudo junto (melhor que quebrar menu)
        return [texto]

    n_frases = _contar_frases(texto)

    # 1 frase → não divide
    if n_frases <= 1:
        return [texto]

    # 2 frases → divide ao meio (no ponto natural)
    if n_frases == 2:
        meio = len(texto) // 2
        ponto = _encontrar_ponto_quebra(texto, meio + 40)
        if ponto > 20:
            return [texto[:ponto].strip(), texto[ponto:].strip()]
        return [texto]

    # 3+ frases → divide em 2 ou 3
    # Primeira quebra por volta de 40-50% do texto
    ponto1 = _encontrar_ponto_quebra(texto, int(len(texto) * 0.45) + 30)
    if ponto1 < 20:
        return [texto]

    parte1 = texto[:ponto1].strip()
    resto = texto[ponto1:].strip()

    # Segunda quebra se o resto ainda é longo (> 120 chars e tem 2+ frases)
    if len(resto) > 150 and _contar_frases(resto) >= 2 and not _tem_menu_opcoes(resto):
        ponto2 = _encontrar_ponto_quebra(resto, int(len(resto) * 0.55) + 20)
        if ponto2 > 20:
            return [parte1, resto[:ponto2].strip(), resto[ponto2:].strip()]

    return [parte1, resto]


def send_split(
    send_fn,          # callable(text: str) → qualquer coisa
    texto: str,
    delay: float | None = None,
) -> None:
    """
    Chama `send_fn` para cada chunk do texto dividido,
    com delay entre partes.

    Uso em pipeline.py:
        from voice_agent.message_splitter import send_split
        send_split(
            lambda t: self.evolution.send_text(number=..., text=t),
            answer,
        )
    """
    partes = split_message(texto)
    _delay = delay if delay is not None else DELAY_ENTRE_PARTES

    for i, parte in enumerate(partes):
        if not parte:
            continue
        if i > 0 and _delay > 0:
            time.sleep(_delay)
        try:
            send_fn(parte)
        except Exception as e:
            log.error("[MESSAGE_SPLIT] falha ao enviar parte %d/%d: %s", i + 1, len(partes), e)
            raise
