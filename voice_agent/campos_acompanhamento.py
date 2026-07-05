"""Mapeia estado da Lia → campos Kommo visíveis na lista do funil.

Origem: Fábio 05/06/2026 — adicionou 3 colunas custom na lista ATENDE
(STATUS CONVERSA, ULTIMA MSG OUTBOUND, PROXIMA ACAO) e quer que a Lia
preencha automaticamente a cada turno. Equipe humana enxerga pela lista
quem está esperando resposta, qual a próxima ação operacional e qual
foi a última mensagem outbound — sem precisar abrir cada lead.

Field IDs (criados em task #216):
- 1260854 STATUS CONVERSA  (select, 15 enums)
- 1260856 ULTIMA MSG OUTBOUND  (textarea)
- 1260858 PROXIMA ACAO  (select, 12 enums)

Enums confirmados via API Kommo em 05/06/2026.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Field IDs + enums (Kommo)
# ---------------------------------------------------------------------------

FIELD_STATUS_CONVERSA = (1260854, {
    "aguardando_paciente_responder": 927048,
    "aguardando_humano_intervir": 927050,
    "coletando_dados": 927052,
    "validando_convenio": 927054,
    "agenda_oferecida": 927056,
    "confirmando_horario": 927058,
    "gravando_medware": 927060,
    "aguardando_sinal_pix": 927062,
    "agendado_aguarda_consulta": 927064,
    "consulta_realizada_aguarda_pos": 927066,
    "faltou_consulta": 927068,
    "parado_sem_acao_7d": 927070,
    "parado_sem_acao_30d": 927072,
    "convenio_nao_aceito": 927074,
    "desistiu_explicito": 927076,
})

FIELD_ULTIMA_MSG_OUTBOUND = 1260856  # textarea

# ÚLTIMA MENS LIA + ULTIMA MENS HUMANO — datetime, criados por Fábio
# 05/06/2026. Separados pra equipe enxergar QUEM enviou por último:
# - LIA preenche FIELD_TS_ULTIMA_MSG_LIA em cada turno do agente
# - Webhook Kommo Automation preenche FIELD_TS_ULTIMA_MSG_HUMANO quando
#   atendente humano envia mensagem manual
# Override via env BLINK_FIELD_TS_LIA / BLINK_FIELD_TS_HUMANO pra teste.
import os as _os
try:
    FIELD_TS_ULTIMA_MSG_LIA = int(
        _os.getenv("BLINK_FIELD_TS_LIA") or "1260860"
    )
except ValueError:
    FIELD_TS_ULTIMA_MSG_LIA = 1260860
try:
    FIELD_TS_ULTIMA_MSG_HUMANO = int(
        _os.getenv("BLINK_FIELD_TS_HUMANO") or "1260862"
    )
except ValueError:
    FIELD_TS_ULTIMA_MSG_HUMANO = 1260862

# Alias mantido pra compat com código antigo
FIELD_TS_ULTIMA_MSG_ENVIADA = FIELD_TS_ULTIMA_MSG_LIA

FIELD_PROXIMA_ACAO = (1260858, {
    "aguardar_resposta_paciente": 927078,
    "disparar_template_reativacao": 927080,
    "oferecer_agenda": 927082,
    "coletar_dados_minimos": 927084,
    "validar_convenio": 927086,
    "cobrar_sinal_pix": 927088,
    "confirmar_horario_d-1": 927090,
    "confirmar_chegada_d-0": 927092,
    "escalar_humano": 927094,
    "desativar_lead": 927096,
    "pos_consulta_avaliacao": 927098,
    "agendar_proxima_consulta": 927100,
})

# ---------------------------------------------------------------------------
# JANELA 24H — observabilidade do prazo pra fechar a janela do WhatsApp
# ---------------------------------------------------------------------------
# Origem: Fábio 05/07/2026 — pediu campo pra "observar o tempo restante para
# fechar a janela de 24h" na lista ATENDE. A janela do WhatsApp conta a partir
# do ÚLTIMO INBOUND do paciente; depois de 24h só template aprovado passa.
#
# 2 campos criados no Kommo (funil ATENDE):
#   - ÚLTIMA MENS PACIENTE (date_time) → timestamp do último inbound.
#   - JANELA 24H (select) → status derivado (aberta / expirando / fechada),
#     recalculado periodicamente pelo cron pra transicionar durante o silêncio
#     do paciente (é aí que a janela vai fechando, sem turno rodando).
#
# Field IDs + enum IDs criados via API Kommo em 05/07/2026:
#   ÚLTIMA MENS PACIENTE (date_time) = 1260984
#   JANELA 24H (select) = 1260986 → Aberta 927302 / Expirando 927304 /
#                                    Fechada 927306
# (Emoji nos labels foi removido pelo Kommo — labels em texto puro.)
# Override por env pra teste/rollout.
try:
    FIELD_TS_ULTIMA_MSG_PACIENTE = int(
        _os.getenv("BLINK_FIELD_TS_PACIENTE") or "1260984"
    )
except ValueError:
    FIELD_TS_ULTIMA_MSG_PACIENTE = 1260984

# (field_id, {valor_semantico: enum_id})
try:
    _FIELD_JANELA_24H_ID = int(
        _os.getenv("BLINK_FIELD_JANELA_24H") or "1260986"
    )
except ValueError:
    _FIELD_JANELA_24H_ID = 1260986
FIELD_JANELA_24H = (_FIELD_JANELA_24H_ID, {
    "aberta": 927302,
    "expirando": 927304,
    "fechada": 927306,
})

# Limiares (segundos). Reutiliza a mesma régua do motor de renovação:
#   < 22h   → aberta   (🟢) — tem folga
#   22h-24h → expirando (🟠) — < 2h pra fechar, hora de renovar
#   >= 24h  → fechada  (🔴) — só template aprovado agora
_JANELA_TOTAL_SEG = 24 * 60 * 60
_JANELA_EXPIRANDO_SEG = 22 * 60 * 60

JANELA_ABERTA = "aberta"
JANELA_EXPIRANDO = "expirando"
JANELA_FECHADA = "fechada"


def classificar_janela_24h(
    ultima_msg_paciente_ts: int | float | datetime | None,
    agora: int | float | datetime | None = None,
    *,
    total_seg: int = _JANELA_TOTAL_SEG,
    expirando_seg: int = _JANELA_EXPIRANDO_SEG,
) -> str | None:
    """Classifica o estado da janela de 24h a partir do último inbound.

    Retorna "aberta" / "expirando" / "fechada", ou None se não há
    timestamp de inbound (paciente nunca falou → janela não se aplica).
    """
    ultima = _epoch(ultima_msg_paciente_ts)
    if ultima is None:
        return None
    agora_epoch = _epoch(agora)
    if agora_epoch is None:
        agora_epoch = datetime.now(timezone.utc).timestamp()
    delta = agora_epoch - ultima
    if delta < 0:
        delta = 0
    if delta >= total_seg:
        return JANELA_FECHADA
    if delta >= expirando_seg:
        return JANELA_EXPIRANDO
    return JANELA_ABERTA


def segundos_restantes_janela(
    ultima_msg_paciente_ts: int | float | datetime | None,
    agora: int | float | datetime | None = None,
    *,
    total_seg: int = _JANELA_TOTAL_SEG,
) -> int | None:
    """Segundos que faltam pra fechar a janela (0 se já fechou, None se n/a)."""
    ultima = _epoch(ultima_msg_paciente_ts)
    if ultima is None:
        return None
    agora_epoch = _epoch(agora)
    if agora_epoch is None:
        agora_epoch = datetime.now(timezone.utc).timestamp()
    restante = int(total_seg - (agora_epoch - ultima))
    return max(restante, 0)


def campos_janela_24h(
    ultima_msg_paciente_ts: int | float | datetime | None,
    agora: int | float | datetime | None = None,
) -> dict[str, object]:
    """Monta as chaves pra `update_lead_fields()` referentes à janela.

    Devolve dict (vazio se sem inbound):
      - ts_ultima_msg_paciente: int (epoch) — carimba o campo date_time
      - janela_24h: str ("aberta"/"expirando"/"fechada") — status derivado
    """
    ts = _epoch(ultima_msg_paciente_ts)
    if ts is None:
        return {}
    status = classificar_janela_24h(ultima_msg_paciente_ts, agora)
    out: dict[str, object] = {"ts_ultima_msg_paciente": int(ts)}
    if status:
        out["janela_24h"] = status
    return out


def _epoch(ts: int | float | datetime | None) -> float | None:
    """Converte int/float/datetime → epoch (segundos). None se inválido."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.timestamp()
    try:
        return float(ts)
    except (TypeError, ValueError):
        return None


# Fuso horário Brasília (UTC-3)
_TZ_BR = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Mapeamento estado FSM → enums
# ---------------------------------------------------------------------------

# Caminho feliz: FSM → (status, proxima)
_MAPA_FSM_PADRAO: dict[str, tuple[str, str]] = {
    "TRIAGEM": ("coletando_dados", "coletar_dados_minimos"),
    "DADOS": ("coletando_dados", "coletar_dados_minimos"),
    "CONVENIO": ("validando_convenio", "validar_convenio"),
    "AGENDA": ("agenda_oferecida", "aguardar_resposta_paciente"),
    "CONFIRMACAO": ("confirmando_horario", "aguardar_resposta_paciente"),
    "GRAVACAO": ("gravando_medware", "aguardar_resposta_paciente"),
    "POS_GRAVACAO": (
        "agendado_aguarda_consulta", "confirmar_horario_d-1",
    ),
}


def mapear_status_e_proxima(
    estado_fsm: str | None,
    *,
    ja_agendado: bool = False,
    convenio_nao_aceito: bool = False,
    cobrar_sinal: bool = False,
    paciente_desistiu: bool = False,
) -> tuple[str | None, str | None]:
    """Resolve (status_conversa, proxima_acao) a partir do estado.

    Prioridades (vencem o padrão FSM):
      1. paciente_desistiu → desistiu_explicito + desativar_lead
      2. convenio_nao_aceito → convenio_nao_aceito + escalar_humano
      3. ja_agendado → agendado_aguarda_consulta + confirmar_horario_d-1
      4. cobrar_sinal (após oferta confirmada) → aguardando_sinal_pix +
         cobrar_sinal_pix
      5. caminho normal FSM via _MAPA_FSM_PADRAO

    Retorna (None, None) se estado desconhecido — chamador decide se
    grava ou pula.
    """
    if paciente_desistiu:
        return ("desistiu_explicito", "desativar_lead")
    if convenio_nao_aceito:
        return ("convenio_nao_aceito", "escalar_humano")
    if ja_agendado:
        return ("agendado_aguarda_consulta", "confirmar_horario_d-1")
    if cobrar_sinal:
        return ("aguardando_sinal_pix", "cobrar_sinal_pix")

    if not estado_fsm:
        return (None, None)
    estado_upper = str(estado_fsm).upper().strip()
    par = _MAPA_FSM_PADRAO.get(estado_upper)
    if not par:
        return (None, None)
    return par


# ---------------------------------------------------------------------------
# Formatadores
# ---------------------------------------------------------------------------

def formatar_ultima_msg_outbound(
    texto: str,
    *,
    autor: str = "LIA",
    ts_unix: int | None = None,
    max_chars: int = 500,
) -> str:
    """Devolve string pronta pra gravar no campo ULTIMA MSG OUTBOUND.

    Formato:  `[LIA 14:35 05/06] {texto truncado}`

    autor pode ser "LIA" (default) ou "HUMANO" — sufixo pra equipe ver
    quem mandou a última mensagem.
    """
    if not texto:
        return ""
    if ts_unix is None:
        ts_unix = int(time.time())
    dt = datetime.fromtimestamp(int(ts_unix), tz=_TZ_BR)
    prefix = f"[{autor.upper()} {dt:%H:%M %d/%m}]"
    limpo = " ".join(str(texto).split())  # collapse whitespace
    sobra = max_chars - len(prefix) - 1
    if sobra < 20:
        sobra = 20
    if len(limpo) > sobra:
        limpo = limpo[: sobra - 1].rstrip() + "…"
    return f"{prefix} {limpo}"


def montar_dict_campos(
    *,
    answer: str,
    estado_fsm: str | None = None,
    autor: str = "LIA",
    ts_unix: int | None = None,
    ja_agendado: bool = False,
    convenio_nao_aceito: bool = False,
    cobrar_sinal: bool = False,
    paciente_desistiu: bool = False,
) -> dict[str, str]:
    """Monta dict pronto pra `update_lead_fields()`.

    Chaves geradas (só inclui quando há valor real):
      - ultima_msg_outbound: str
      - status_conversa: str (valor do enum, ex: "agenda_oferecida")
      - proxima_acao: str (valor do enum)

    O `update_lead_fields` traduz isso pra payload Kommo.
    """
    out: dict[str, str] = {}
    msg = formatar_ultima_msg_outbound(answer, autor=autor, ts_unix=ts_unix)
    if msg:
        out["ultima_msg_outbound"] = msg
    status, proxima = mapear_status_e_proxima(
        estado_fsm,
        ja_agendado=ja_agendado,
        convenio_nao_aceito=convenio_nao_aceito,
        cobrar_sinal=cobrar_sinal,
        paciente_desistiu=paciente_desistiu,
    )
    if status:
        out["status_conversa"] = status
    if proxima:
        out["proxima_acao"] = proxima
    return out
