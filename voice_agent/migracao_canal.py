"""Detecta inbound em canal LEGADO (WhatsApp Lite / Evolution 0710) e dispara
mensagem automática de migração pro canal oficial 8133.

Origem: Fábio 07/06/2026 — "secretária CLT custa R$3.500/mês. Lia tem que fazer
sozinha." Lead Marcelo 23934832 voltou no canal Lite após Closed-lost; tive que
mandar manualmente. Agora a Lia detecta e migra sozinha.

Como funciona:
    1. Pipeline recebe inbound; detecta `is_canal_legado()` via chat_id ou
       nome do canal no Kommo contact.
    2. Se SIM E é PRIMEIRA msg do paciente nas últimas 24h nesse canal:
       chama `mensagem_migracao_8133(nome, motivo)`.
    3. Marca custom field `STATUS CONVERSA = aguardando_migracao_8133`.
    4. Conversa "morre" naquele canal — paciente migra pro 8133 e recomeça lá.

Toggle:
    LIA_MIGRACAO_CANAL_ENABLED=1   default ON
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

NUMERO_OFICIAL_8133 = "(61) 8133-1005"
NUMERO_OFICIAL_E164 = "556181331005"  # pra wa.me link

# Padrões de canais legados — qualquer um deles aciona migração.
# Adicionar novos canais aqui à medida que aparecerem.
CANAIS_LEGADOS_PATTERNS = (
    "whatsapp lite",
    "whatsapp_lite",
    "evolution",
    "0710",
    "wa-lite",
    "wa_lite",
)

CANAIS_OFICIAIS_PATTERNS = (
    "whatsapp business",
    "whatsapp_business",
    "whatsapp cloud",
    "whatsapp_cloud",
    "8133",
    "wa-cloud",
    "wa_cloud",
    "official",
)


def migracao_habilitada() -> bool:
    """Toggle. Default ON (1)."""
    return os.getenv("LIA_MIGRACAO_CANAL_ENABLED", "1").lower() in (
        "1", "true", "yes", "on",
    )


def is_canal_legado(canal_nome: Optional[str]) -> bool:
    """Decide se o canal por onde o inbound chegou é legado.

    Comparação case-insensitive contra `CANAIS_LEGADOS_PATTERNS`.
    """
    if not canal_nome:
        return False
    n = canal_nome.lower().strip()
    return any(p in n for p in CANAIS_LEGADOS_PATTERNS)


def is_canal_oficial(canal_nome: Optional[str]) -> bool:
    if not canal_nome:
        return False
    n = canal_nome.lower().strip()
    return any(p in n for p in CANAIS_OFICIAIS_PATTERNS)


def _primeiro_nome(nome_completo: Optional[str]) -> str:
    if not nome_completo:
        return ""
    partes = nome_completo.strip().split()
    return partes[0] if partes else ""


def _wa_link(nome: str, motivo: Optional[str] = None) -> str:
    """Gera link wa.me com texto pré-preenchido pra agilizar migração."""
    nome_curto = _primeiro_nome(nome) or "paciente"
    if motivo:
        texto = f"Oi, sou o(a) {nome_curto} e quero continuar o atendimento — {motivo}"
    else:
        texto = f"Oi, sou o(a) {nome_curto} e quero continuar o atendimento"
    return f"https://wa.me/{NUMERO_OFICIAL_E164}?text={quote(texto)}"


def mensagem_migracao_8133(
    nome: Optional[str] = None,
    motivo: Optional[str] = None,
    medico: Optional[str] = None,
) -> str:
    """Retorna a mensagem padrão de migração pro canal oficial.

    Args:
        nome: nome do paciente/contato (opcional, personaliza saudação).
        motivo: motivo da consulta — usado no texto do link wa.me.
        medico: ex. "Dra. Karla Delalíbera" — incluído no convite se passado.

    Returns:
        Texto pronto pra mandar no canal legado. Sem "slots", sem jargão técnico.
    """
    nome_curto = _primeiro_nome(nome)
    saudacao = f"Oi {nome_curto}! " if nome_curto else "Olá! "

    convite_medico = ""
    if medico:
        convite_medico = f" Vou te apresentar os horários e incentivos da consulta com {medico}."

    link = _wa_link(nome or "", motivo)

    return (
        f"{saudacao}Boa notícia 😊\n\n"
        f"Agora temos um número oficial da Blink Oftalmologia que vai te atender com "
        f"mais agilidade — incentivos, agendamento e lembretes, tudo num lugar só:\n\n"
        f"📲 {NUMERO_OFICIAL_8133}\n\n"
        f"Salva esse contato como \"Blink Oftalmologia\" e me chama no número novo.{convite_medico}\n\n"
        f"Pra facilitar é só clicar:\n"
        f"{link}\n\n"
        f"Esse número que você usou hoje vai sair de uso. Te espero no novo!"
    )


def deve_migrar_lead(
    canal_atual: Optional[str],
    status_conversa: Optional[str] = None,
    historico_msgs_neste_canal: int = 0,
) -> bool:
    """Regra completa: deve disparar mensagem de migração agora?

    Critérios:
        - migracao_habilitada() True
        - is_canal_legado(canal_atual) True
        - status_conversa NÃO indica que já tentamos migrar (evita loop)
        - historico_msgs_neste_canal <= 2 (só nas primeiras interações; depois
          deixa fluir pra não atrapalhar conversa em andamento)

    Args:
        canal_atual: nome do canal Kommo de onde veio o inbound.
        status_conversa: valor do campo Kommo STATUS CONVERSA (ex.
            "aguardando_migracao_8133" → não repete).
        historico_msgs_neste_canal: contador de mensagens já trocadas nesse canal.
    """
    if not migracao_habilitada():
        return False
    if not is_canal_legado(canal_atual):
        return False
    if status_conversa and "migracao" in (status_conversa or "").lower():
        return False
    if historico_msgs_neste_canal > 2:
        return False
    return True
