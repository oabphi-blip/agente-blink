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


# ID do status "0-ETAPA ENTRADA" no funil ATENDE. Leads que chegam por um
# canal Kommo não vinculado nascem AQUI sem histórico e sem custom_fields
# preenchidos — é o sinal que usamos pra reconhecer "canal desconhecido/novo"
# no bug C-38.
STATUS_ID_ETAPA_ENTRADA = 96441724


def lead_candidato_migracao_canal_novo(
    status_id: Optional[int],
    custom_fields: Optional[list],
    notes_count: int,
) -> bool:
    """Bug C-38: heurística de "lead fantasma em canal desconhecido".

    Um lead que aparece em 0-ETAPA ENTRADA (status_id=96441724) com
    custom_fields VAZIO E zero notas é candidato certo — nenhum outro fluxo
    (Salesbot, humano, batch) tocou nele. É esse padrão que aparece nos
    chats 38855/38919/38920 relatados.

    Args:
        status_id: status_id do lead no Kommo (int ou None).
        custom_fields: lista de custom_fields_values (pode ser None ou []).
        notes_count: quantas notas o lead já tem.

    Returns:
        True quando é o padrão exato do C-38. False em qualquer outro caso
        (lead com nota humana, com campos preenchidos, ou em outra etapa).
    """
    if status_id is None:
        return False
    try:
        status_id_int = int(status_id)
    except (TypeError, ValueError):
        return False
    if status_id_int != STATUS_ID_ETAPA_ENTRADA:
        return False
    if custom_fields:
        # Qualquer entrada em custom_fields_values significa que algo já foi
        # preenchido — evita disparar em lead legítimo em triagem.
        return False
    if notes_count > 0:
        return False
    return True


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


# ------------------------------------------------------------------------
# Bug C-38 — orquestrador plugado no /kommo (webhook.py)
# ------------------------------------------------------------------------

REDIS_DEDUP_KEY_FMT = "blink:migracao_canal:{lead_id}"
REDIS_DEDUP_TTL_SEG = 7 * 24 * 60 * 60  # 7 dias


def _redis_ja_disparou(redis_client, lead_id: str | int) -> bool:
    if redis_client is None:
        return False
    try:
        return bool(redis_client.exists(REDIS_DEDUP_KEY_FMT.format(lead_id=lead_id)))
    except Exception:  # noqa: BLE001
        return False


def _redis_marcar_disparado(redis_client, lead_id: str | int, wamid: str) -> None:
    if redis_client is None:
        return
    try:
        redis_client.setex(
            REDIS_DEDUP_KEY_FMT.format(lead_id=lead_id),
            REDIS_DEDUP_TTL_SEG,
            wamid or "1",
        )
    except Exception:  # noqa: BLE001
        pass


def talvez_disparar_migracao_canal(
    lead_id: str | int,
    kommo_client,
    wa_client,
    redis_client=None,
) -> dict:
    """Ponto único de entrada Bug C-38.

    Fluxo:
        1. Toggle LIA_MIGRACAO_CANAL_ENABLED (default ON via _or "1").
        2. Dedup Redis 7 dias por lead_id (não repete).
        3. Busca lead completo (custom_fields + status_id) e conta notas.
        4. Se NÃO é padrão C-38 (lead vazio + 0-ENTRADA + zero notas) → skip.
        5. Busca telefone do contato principal. Sem telefone → skip.
        6. Envia mensagem_migracao_8133() via wa_client.send_text().
        7. Grava nota Kommo com wamid + desativa IA pra não fazer loop.

    Retorna dict {"acao": ..., "motivo": ...} pra facilitar log/test.
    Nunca levanta exceção — falha silenciosamente com "acao=erro".
    """
    resultado = {"acao": "pulado", "motivo": "", "lead_id": str(lead_id)}

    if not migracao_habilitada():
        resultado["motivo"] = "toggle_desligado"
        return resultado

    if _redis_ja_disparou(redis_client, lead_id):
        resultado["acao"] = "dedup"
        resultado["motivo"] = "ja_disparou_7d"
        return resultado

    if kommo_client is None or wa_client is None:
        resultado["motivo"] = "cliente_ausente"
        return resultado

    # Passo 3: puxa lead + notas.
    try:
        lead = kommo_client.get_lead(lead_id)
    except Exception as e:  # noqa: BLE001
        resultado["acao"] = "erro"
        resultado["motivo"] = f"get_lead_falhou: {e!r}"[:200]
        return resultado
    if not lead:
        resultado["motivo"] = "lead_nao_encontrado"
        return resultado

    status_id = lead.get("status_id")
    custom_fields = lead.get("custom_fields_values") or []

    try:
        notas = kommo_client.get_lead_notes(lead_id, limit=5) or []
    except Exception as e:  # noqa: BLE001
        resultado["acao"] = "erro"
        resultado["motivo"] = f"get_lead_notes_falhou: {e!r}"[:200]
        return resultado
    notes_count = len(notas)

    # Passo 4: heurística C-38.
    if not lead_candidato_migracao_canal_novo(
        status_id=status_id,
        custom_fields=custom_fields,
        notes_count=notes_count,
    ):
        resultado["motivo"] = (
            f"nao_candidato status_id={status_id} "
            f"cf_len={len(custom_fields)} notes={notes_count}"
        )
        return resultado

    # Passo 5: pega telefone.
    telefone = None
    try:
        telefone = kommo_client.get_lead_main_phone(lead_id)
    except Exception as e:  # noqa: BLE001
        resultado["acao"] = "erro"
        resultado["motivo"] = f"get_lead_main_phone_falhou: {e!r}"[:200]
        return resultado
    if not telefone:
        resultado["motivo"] = "sem_telefone"
        return resultado

    # Passo 6: envia texto de migração. Sem nome (canal cru).
    texto = mensagem_migracao_8133(nome="", motivo=None)
    wamid = ""
    try:
        resp = wa_client.send_text(telefone, texto)
        if isinstance(resp, dict):
            msgs = resp.get("messages") or []
            if msgs and isinstance(msgs[0], dict):
                wamid = str(msgs[0].get("id") or "")
    except Exception as e:  # noqa: BLE001
        resultado["acao"] = "erro"
        resultado["motivo"] = f"send_text_falhou: {e!r}"[:200]
        return resultado

    # Passo 7: nota + desativa IA (não bloqueia sucesso se qualquer um falhar).
    try:
        kommo_client.add_note(
            int(lead_id),
            f"Migração de canal — Bug C-38 wired. wamid={wamid or 'sem_wamid'}",
        )
    except Exception as e:  # noqa: BLE001
        log_msg = f"add_note_falhou: {e!r}"[:150]
        resultado["nota_erro"] = log_msg
    try:
        kommo_client.update_lead_fields(
            int(lead_id), {"ativado_ia": "Desativado"},
        )
    except Exception as e:  # noqa: BLE001
        resultado["update_fields_erro"] = f"{e!r}"[:150]

    _redis_marcar_disparado(redis_client, lead_id, wamid)

    resultado["acao"] = "disparado"
    resultado["motivo"] = "ok"
    resultado["wamid"] = wamid
    resultado["telefone"] = telefone
    return resultado
