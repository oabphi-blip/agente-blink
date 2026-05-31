"""Mensagens automáticas de manutenção do atendimento — janela 24h WhatsApp.

O WhatsApp Cloud API (número 8133-1005) só permite enviar mensagens "livres"
nas primeiras 24h após o último turno do paciente. Depois disso, só template
aprovado. Para evitar que o paciente caia na regra de template, a Lia avisa
ANTES de expirar — pedindo um "oi" pra renovar a janela.

Esta mensagem é DISPARADA pelo pipeline, NÃO faz parte do fluxo conversacional
da Lia. É um "ping cordial de manutenção".

Regras de voz (validadas pelo pytest):
  - Tom Blink: cordial, profissional, sereno.
  - Concisão: 3-4 linhas.
  - Sem vocabulário vetado (regra 1.4 do MASTER_INSTRUCTION).
  - Sem "particular" — substituir por "sem convênio" (regra 1.4.1).
  - 1 emoji acolhedor permitido (👋 ou ✨).
  - Usa primeiro nome do contato — nunca "paciente" genérico.
  - Sempre oferece a opção "outro momento" pra não pressionar.

Como integrar no pipeline (task #87.2):
  1. Cron interno varre Redis: leads em status ATIVO sem mensagem
     do paciente há > 22h.
  2. Chama `render_mensagem_renovar_janela(nome_contato)` e dispara
     via WhatsApp Cloud ANTES de fechar 24h.
  3. Marca no Redis `blink:janela:ultima_renovacao:<lead>` pra evitar
     duplicar dentro da mesma janela.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# Vocabulário PROIBIDO no atendimento Blink (regra 1.4 do prompt mestre).
# Lista mantida em sincronia com responder._PROHIBITED_REPLACEMENTS.
_PALAVRAS_VETADAS = {
    "direitinho", "certinho", "rapidinho", "bonitinho", "obrigadinho",
    "fofo", "fofa", "queridinho", "queridinha", "filhinho", "filhinha",
    "consultinha", "infelizmente", "show", "particular",
}

# =============================================================================
# ELEGIBILIDADE — task #88
# =============================================================================
# Regra do Fábio (31/05/2026): só renovar janela 24h se:
#   1. Lead está em etapa ANTES de "AGENDADO" (101507507) e
#   2. Paciente já teve ALGUMA interação (ultima_msg_paciente_ts != None) e
#   3. Janela ainda válida (delta < JANELA_24H) — depois disso só template e
#   4. Janela perto de expirar (delta > LIMIAR_DISPARO).
#
# Após AGENDADO, o paciente recebe Salesbot D-1 e D-0 — não há motivo pra
# manter janela aberta com a Lia "ativa".

# Status do pipeline ATENDE (8601819) que ainda PRECISAM de janela 24h aberta
# pra a Lia conversar livre. Fonte: CLAUDE.md seção 4.
STATUS_IDS_ANTES_AGENDADO = frozenset({
    96441724,    # 0-ETAPA ENTRADA
    101508307,   # 1.LEADS FRIO
    102560495,   # 2-AGENDAR
    106184631,   # 3.REAGENDAR
    106184983,   # 5.1-NO-SHOW (precisa reagendar → conta como pré-agendado)
})

# Limites de tempo em segundos.
JANELA_24H_SEGUNDOS = 24 * 60 * 60          # depois disso = janela morta
LIMIAR_DISPARO_SEGUNDOS = 22 * 60 * 60      # disparo a partir desse delta

# Razões pra NÃO renovar — usadas pelo cron pra log + métrica.
RAZAO_STATUS_POS_AGENDAMENTO = "status_pos_agendado"
RAZAO_SEM_INTERACAO = "paciente_nunca_falou"
RAZAO_JANELA_MORTA = "janela_expirou_so_template"
RAZAO_AINDA_CEDO = "ainda_dentro_da_janela_confortavel"


def _primeiro_nome(nome_contato: str | None) -> str:
    """Extrai o primeiro nome, capitalizado.

    Aceita "marcela", "MARCELA SOUZA", "Marcela de Souza" → "Marcela".
    Devolve "" pra entrada vazia/None.
    """
    if not nome_contato:
        return ""
    nome = re.sub(r"\s+", " ", nome_contato.strip())
    if not nome:
        return ""
    primeiro = nome.split(" ", 1)[0]
    # Capitaliza preservando acentos
    return primeiro[:1].upper() + primeiro[1:].lower()


def render_mensagem_renovar_janela(nome_contato: str | None) -> str:
    """Mensagem curta de renovação de janela 24h.

    Personaliza com primeiro nome do contato. Se sem nome, usa saudação
    neutra ("Olá!").
    """
    primeiro = _primeiro_nome(nome_contato)
    saudacao = f"Olá, {primeiro}!" if primeiro else "Olá!"

    return (
        f"{saudacao} Aqui é a Lia, da Blink Oftalmologia 👋\n\n"
        f"Sua conversa por aqui está há quase 24 horas em pausa. "
        f"Pra eu continuar te ajudando sem interrupção, "
        f"me envia um \"oi\" — qualquer mensagem reabre nosso atendimento "
        f"por mais 24h, e seguimos assim até concluirmos seu agendamento.\n\n"
        f"Se preferir retomar em outro momento, é só me avisar — fico "
        f"disponível pra continuar quando você quiser."
    )


def _to_epoch(ts) -> float | None:
    """Aceita int, float ou datetime; devolve epoch UTC.

    None ou inválido → None.
    """
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts) if ts > 0 else None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.timestamp()
    return None


def elegivel_renovar_janela(
    status_id: int | None,
    ultima_msg_paciente_ts: int | float | datetime | None,
    agora: int | float | datetime | None = None,
    *,
    status_validos: frozenset[int] = STATUS_IDS_ANTES_AGENDADO,
    janela_total_seg: int = JANELA_24H_SEGUNDOS,
    limiar_disparo_seg: int = LIMIAR_DISPARO_SEGUNDOS,
) -> dict:
    """Decide se o lead deve receber o ping de renovação.

    Retorna sempre um dict (não levanta) com:
      {"elegivel": bool, "razao": str|None, "delta_seg": int|None}
    """
    if status_id not in status_validos:
        return {
            "elegivel": False,
            "razao": RAZAO_STATUS_POS_AGENDAMENTO,
            "delta_seg": None,
        }

    ultima = _to_epoch(ultima_msg_paciente_ts)
    if ultima is None:
        return {
            "elegivel": False,
            "razao": RAZAO_SEM_INTERACAO,
            "delta_seg": None,
        }

    agora_epoch = _to_epoch(agora)
    if agora_epoch is None:
        agora_epoch = datetime.now(timezone.utc).timestamp()

    delta = int(agora_epoch - ultima)

    if delta >= janela_total_seg:
        # Já passou de 24h — não adianta mais mandar texto livre.
        # Esse lead precisa de TEMPLATE aprovado, não de ping.
        return {
            "elegivel": False,
            "razao": RAZAO_JANELA_MORTA,
            "delta_seg": delta,
        }

    if delta < limiar_disparo_seg:
        # Ainda cedo — não vale gastar a oportunidade agora.
        return {
            "elegivel": False,
            "razao": RAZAO_AINDA_CEDO,
            "delta_seg": delta,
        }

    return {"elegivel": True, "razao": None, "delta_seg": delta}


def validar_mensagem_renovacao(texto: str) -> dict:
    """Verifica se a mensagem está em conformidade com as regras Blink.

    Devolve {"ok": bool, "violacoes": [str]}.
    """
    violacoes: list[str] = []
    baixo = texto.lower()
    for palavra in _PALAVRAS_VETADAS:
        # Match em palavra inteira (evita falso positivo "fofocar"→"fofo").
        if re.search(rf"\b{re.escape(palavra)}\b", baixo):
            violacoes.append(f"vocabulário vetado: {palavra!r}")
    # Tamanho razoável. Limite ampliado pra acomodar D-1 do ciclo
    # (endereço + Maps + orientação + lembrete docs).
    if len(texto) > 900:
        violacoes.append(f"mensagem longa demais ({len(texto)} chars)")
    if "oi" not in baixo:
        violacoes.append("não menciona 'oi' como forma de renovar")
    if "outro momento" not in baixo and "quando você quiser" not in baixo:
        violacoes.append("não oferece opção de retomar depois")
    return {"ok": not violacoes, "violacoes": violacoes}
