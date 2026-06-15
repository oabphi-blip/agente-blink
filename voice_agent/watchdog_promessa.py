"""Watchdog Promessa Não Cumprida — cron 2 min.

Origem: Fábio 14/06/2026, casos repetidos (Carolina 24145994, Cecília
21500693, Lílian 24146092, Fernanda 24145890, Maitê 24128026, Carmen
24142996). Padrão único: Lia escreveu "deixa eu consultar / um minutinho
/ já volto / vou buscar" e **nunca voltou**. Paciente fica esperando
horas. Bug C-28.

Causa raiz: em FSM=AGENDA, o modelo às vezes escreve TEXTO LIVRE em
vez de chamar a tool `oferecer_slot`. Fix #183 (tool_choice forçado)
elimina maior parte, mas brechas escapam.

Esse watchdog fecha a brecha SEM enviar mensagem automática (risco
alto). Em vez disso:

1. Detecta leads onde Lia prometeu voltar há > 3 min e < 2 h.
2. Move pra 1-ATENDIMENTO HUMANO (status_id 106563343).
3. Desativa IA (campo 1260817 → "Desativado").
4. Grava nota Kommo explicativa pra atendente humana agir.
5. Dedup Redis 30 min — não realerta o mesmo lead repetidamente.

Liga via env `WATCHDOG_PROMESSA_ENABLED=1`. Default OFF.

Pytest: tests/test_watchdog_promessa.py.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# Pipeline ATENDE + status onde Lia conversa (não fechado, não em humano já)
PIPELINE_ATENDE = 8601819

# Status onde Lia conversa ativamente — esses sim podem estar com promessa
# pendente. NÃO incluir 1-ATENDIMENTO HUMANO (106563343) — humano já assumiu.
STATUS_CONVERSAVEIS_LIA = [
    96441724,    # 0-ETAPA ENTRADA
    106919911,   # 0-a classificar
    101508307,   # 2.LEADS FRIO (Lia tenta reativar)
    102560495,   # 3-AGENDAR
    106184631,   # 4.REAGENDAR
    106184983,   # 7.1-NO-SHOW (ATIVAR)
]

# Status destino quando promessa não cumprida — força humano assumir
STATUS_ATENDIMENTO_HUMANO = 106563343

# Campos Kommo
FIELD_ATIVADO_IA = 1260817
ENUM_ATIVADO_IA_DESATIVADO = 927035  # value: "Desativado"
FIELD_ULTIMA_MSG_OUTBOUND = 1260856
FIELD_ULTIMA_MENS_LIA = 1260860       # date_time (UNIX seconds)
FIELD_STATUS_CONVERSA = 1260854

# Padrões de promessa não cumprida — detectados na ULTIMA MSG OUTBOUND
# Case-insensitive. Acentos opcionais (alguns clientes normalizam).
_PADROES_PROMESSA = [
    r"deixa\s+eu\s+(?:re)?consultar",
    r"deixa\s+eu\s+(?:re)?ver",
    r"deixa\s+eu\s+(?:re)?conferir",
    r"deixa\s+eu\s+(?:re)?checar",
    r"deixa\s+eu\s+buscar",
    r"deixa\s+eu\s+verificar",
    r"deixa\s+eu\s+finalizar",
    r"um\s+min[ui]?t?inho",
    r"um\s+minutinho",
    r"um\s+minuto\b",
    r"j[aá]\s+volto",
    r"volto\s+(?:com|j[aá]|em)",
    r"vou\s+(?:re)?consultar",
    r"vou\s+buscar",
    r"vou\s+(?:re)?ver(?:ificar)?",
    r"vou\s+(?:re)?conferir",
    r"vou\s+(?:re)?checar",
    r"aguarda\s+s[oó]\s+mais",
    r"ainda\s+estou\s+(?:buscando|consultando|procurando|verificando)",
    r"s[oó]\s+(?:um|mais)\s+(?:um\s+)?minutinho",
    r"j[aá]\s+(?:te\s+)?retorno",
    r"j[aá]\s+(?:te\s+)?passo\s+as?\s+(?:op[cç][oõ]es|hor[aá]rios)",
]

_PADROES_PROMESSA_RGX = re.compile(
    r"(?i)" + "|".join(_PADROES_PROMESSA),
    re.IGNORECASE,
)

# Padrões que CANCELAM a detecção — Lia já voltou com slot, não é promessa
# pendente. Ex: "1️⃣ Quarta 24/06" / "Tenho 2 horários disponíveis".
_PADROES_RESPOSTA_REAL = [
    r"1[️⃣]?\s*[—\-:]",          # "1️⃣ ..."
    r"2[️⃣]?\s*[—\-:]",
    r"tenho\s+\d+\s+hor[aá]rios?\s+dispon",
    r"hor[aá]rios?\s+dispon[ií]veis",
    r"agendamento\s+confirmado",
    r"\b\d{1,2}h\d{0,2}\b",                # "9h", "10h30"
    r"\b\d{1,2}:\d{2}\b",                   # "09:00"
]

_PADROES_RESPOSTA_REAL_RGX = re.compile(
    r"(?i)" + "|".join(_PADROES_RESPOSTA_REAL),
    re.IGNORECASE,
)

# Limites temporais (segundos)
SILENCIO_MIN_SEG_DEFAULT = 3 * 60       # 3 min — abaixo disso é normal
SILENCIO_MAX_SEG_DEFAULT = 2 * 60 * 60  # 2 h — acima disso o lead já está esquecido

# Dedup Redis
REDIS_DEDUP_PREFIX = "blink:watchdog_promessa:tratado:"
DEDUP_TTL = 30 * 60  # 30 min — se persistir, realerta


# ============================================================
# Detecção pura — testável sem rede
# ============================================================

def texto_contem_promessa(texto: str) -> bool:
    """True se o texto contém marcador de promessa não cumprida."""
    if not texto:
        return False
    return bool(_PADROES_PROMESSA_RGX.search(texto))


def texto_contem_resposta_real(texto: str) -> bool:
    """True se o texto tem slot / agendamento concreto — cancela detecção."""
    if not texto:
        return False
    return bool(_PADROES_RESPOSTA_REAL_RGX.search(texto))


def eh_promessa_nao_cumprida(
    ultima_msg_outbound: str,
    ts_ultima_msg_lia: int,
    agora_ts: Optional[int] = None,
    silencio_min_seg: int = SILENCIO_MIN_SEG_DEFAULT,
    silencio_max_seg: int = SILENCIO_MAX_SEG_DEFAULT,
) -> bool:
    """Coração da detecção. Puro — sem rede, sem Kommo, só lógica.

    Returns True se:
    - texto tem marcador de promessa
    - texto NÃO tem resposta real (slot concreto)
    - silêncio entre silencio_min e silencio_max segundos
    """
    if not ultima_msg_outbound or not ts_ultima_msg_lia:
        return False
    if not texto_contem_promessa(ultima_msg_outbound):
        return False
    if texto_contem_resposta_real(ultima_msg_outbound):
        return False
    if agora_ts is None:
        agora_ts = int(time.time())
    silencio = agora_ts - int(ts_ultima_msg_lia)
    if silencio < silencio_min_seg:
        return False
    if silencio > silencio_max_seg:
        return False
    return True


# ============================================================
# Extrator de campos do lead Kommo (defensivo)
# ============================================================

def _extrair_custom(lead: dict, field_id: int) -> Optional[Any]:
    cfs = lead.get("custom_fields") or lead.get("custom_fields_values") or []
    for cf in cfs:
        fid = cf.get("field_id") or cf.get("id")
        if fid != field_id:
            continue
        values = cf.get("values") or []
        if not values:
            return None
        return values[0].get("value")
    return None


def avaliar_lead(
    lead: dict,
    agora_ts: Optional[int] = None,
    silencio_min_seg: int = SILENCIO_MIN_SEG_DEFAULT,
    silencio_max_seg: int = SILENCIO_MAX_SEG_DEFAULT,
) -> dict:
    """Recebe lead JSON do Kommo, devolve veredicto estruturado."""
    if agora_ts is None:
        agora_ts = int(time.time())
    lead_id = lead.get("id")
    status_id = lead.get("status_id")
    ultima_msg = _extrair_custom(lead, FIELD_ULTIMA_MSG_OUTBOUND) or ""
    ts_lia = _extrair_custom(lead, FIELD_ULTIMA_MENS_LIA) or 0
    try:
        ts_lia = int(ts_lia)
    except (TypeError, ValueError):
        ts_lia = 0

    if status_id not in STATUS_CONVERSAVEIS_LIA:
        return {
            "lead_id": lead_id,
            "tratar": False,
            "motivo": f"status_id {status_id} fora dos conversáveis",
        }

    pendente = eh_promessa_nao_cumprida(
        ultima_msg_outbound=ultima_msg,
        ts_ultima_msg_lia=ts_lia,
        agora_ts=agora_ts,
        silencio_min_seg=silencio_min_seg,
        silencio_max_seg=silencio_max_seg,
    )
    if not pendente:
        return {
            "lead_id": lead_id,
            "tratar": False,
            "motivo": "sem promessa OU já respondeu OU fora da janela",
        }

    silencio_seg = agora_ts - ts_lia
    return {
        "lead_id": lead_id,
        "tratar": True,
        "status_id_atual": status_id,
        "ultima_msg_outbound": ultima_msg[:200],
        "ts_ultima_msg_lia": ts_lia,
        "silencio_seg": silencio_seg,
        "silencio_min": round(silencio_seg / 60, 1),
    }


# ============================================================
# Resultado do tick (acumulado)
# ============================================================

@dataclass
class TickResultado:
    varridos: int = 0
    candidatos: int = 0
    tratados: int = 0
    ja_dedup: int = 0
    erros: int = 0
    detalhes: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "varridos": self.varridos,
            "candidatos": self.candidatos,
            "tratados": self.tratados,
            "ja_dedup": self.ja_dedup,
            "erros": self.erros,
            "detalhes": self.detalhes,
        }


# ============================================================
# Ação — mover pra atendimento humano + desativar IA + nota
# ============================================================

def _dedup_chave(lead_id: int) -> str:
    return f"{REDIS_DEDUP_PREFIX}{lead_id}"


def ja_tratado_recente(redis_client, lead_id: int) -> bool:
    if redis_client is None:
        return False
    try:
        return bool(redis_client.exists(_dedup_chave(lead_id)))
    except Exception:  # noqa: BLE001
        return False


def marcar_tratado(redis_client, lead_id: int) -> None:
    if redis_client is None:
        return
    try:
        redis_client.setex(_dedup_chave(lead_id), DEDUP_TTL, "1")
    except Exception as e:  # noqa: BLE001
        log.warning("Redis dedup setex falhou lead=%s: %s", lead_id, e)


def tratar_lead(
    lead: dict,
    veredicto: dict,
    kommo_client,
    redis_client=None,
    dry_run: bool = True,
) -> dict:
    """Executa a ação corretiva: move pra ATENDIMENTO HUMANO + nota.

    Conservador — NÃO envia mensagem automática ao paciente. Equipe
    humana vê a nota e age.
    """
    lead_id = veredicto["lead_id"]
    silencio_min = veredicto.get("silencio_min", 0)
    ultima_msg = veredicto.get("ultima_msg_outbound", "")

    if dry_run:
        return {
            "lead_id": lead_id,
            "ok": True,
            "dry_run": True,
            "acao": "would_move_to_human",
            "silencio_min": silencio_min,
        }

    # Skip se já tratado recentemente
    if ja_tratado_recente(redis_client, lead_id):
        return {
            "lead_id": lead_id,
            "ok": True,
            "ja_dedup": True,
            "acao": "skip_dedup",
        }

    nota = (
        "[WATCHDOG PROMESSA · automático] Lia prometeu voltar e ainda não voltou.\n\n"
        f"Última mensagem da Lia (há {silencio_min:.0f} min):\n"
        f"  > {ultima_msg[:300]}\n\n"
        "Ação tomada pelo sistema:\n"
        "- Lead movido para 1-ATENDIMENTO HUMANO\n"
        "- IA desativada para evitar resposta tardia fora de contexto\n\n"
        "AÇÃO HUMANA NECESSÁRIA: entrar em contato com o paciente e cumprir "
        "a promessa (buscar agenda real no Medware e oferecer 2 slots).\n"
        f"Veredicto técnico: silêncio={veredicto.get('silencio_seg')}s "
        f"status_atual={veredicto.get('status_id_atual')}"
    )

    erros = []

    # 1. Move pra atendimento humano + desativa IA
    try:
        # Atualiza via update_lead_fields padrão do projeto (chave nome do campo)
        ok = kommo_client.update_lead_fields(
            lead_id=lead_id,
            status_id=STATUS_ATENDIMENTO_HUMANO,
            custom_fields={"ATIVADO IA?": "Desativado"},
        )
        moveu = bool(ok)
    except Exception as e:  # noqa: BLE001
        erros.append(f"update_lead_fields: {e}")
        moveu = False

    # 2. Grava nota explicativa
    note_id = None
    try:
        nota_result = kommo_client.add_note(lead_id=lead_id, text=nota)
        if isinstance(nota_result, dict):
            note_id = nota_result.get("id") or nota_result.get("note_id")
        else:
            note_id = nota_result
    except Exception as e:  # noqa: BLE001
        erros.append(f"add_note: {e}")

    marcar_tratado(redis_client, lead_id)

    log.warning(
        "[WATCHDOG-PROMESSA] tratado lead=%s silencio_min=%.1f moveu=%s nota=%s erros=%s",
        lead_id, silencio_min, moveu, note_id, erros,
    )

    return {
        "lead_id": lead_id,
        "ok": not erros,
        "acao": "moved_to_human",
        "silencio_min": silencio_min,
        "moveu_status": moveu,
        "nota_id": note_id,
        "erros": erros or None,
    }


# ============================================================
# Tick principal — varre + trata
# ============================================================

def tick(
    kommo_client,
    redis_client=None,
    dry_run: bool = True,
    max_leads: int = 30,
    silencio_min_seg: int = SILENCIO_MIN_SEG_DEFAULT,
    silencio_max_seg: int = SILENCIO_MAX_SEG_DEFAULT,
) -> TickResultado:
    """Varre status conversáveis + trata leads com promessa pendente."""
    res = TickResultado()
    agora_ts = int(time.time())

    leads_brutos: list[dict] = []
    for status_id in STATUS_CONVERSAVEIS_LIA:
        try:
            chunk = kommo_client.list_leads_by_status(
                status_id=status_id,
                pipeline_id=PIPELINE_ATENDE,
                limit=80,
            )
            if isinstance(chunk, list):
                leads_brutos.extend(chunk)
        except Exception as e:  # noqa: BLE001
            log.warning("list_leads_by_status %s erro: %s", status_id, e)
            res.erros += 1

    res.varridos = len(leads_brutos)
    candidatos: list[tuple[dict, dict]] = []

    for lead in leads_brutos:
        try:
            veredicto = avaliar_lead(
                lead=lead,
                agora_ts=agora_ts,
                silencio_min_seg=silencio_min_seg,
                silencio_max_seg=silencio_max_seg,
            )
            if veredicto.get("tratar"):
                candidatos.append((lead, veredicto))
        except Exception as e:  # noqa: BLE001
            log.warning("avaliar_lead erro id=%s: %s", lead.get("id"), e)
            res.erros += 1

    res.candidatos = len(candidatos)
    # Ordena por silêncio DESC (mais antigos primeiro)
    candidatos.sort(key=lambda x: x[1].get("silencio_seg", 0), reverse=True)

    for lead, veredicto in candidatos[:max_leads]:
        try:
            r = tratar_lead(
                lead=lead,
                veredicto=veredicto,
                kommo_client=kommo_client,
                redis_client=redis_client,
                dry_run=dry_run,
            )
            res.detalhes.append(r)
            if r.get("ja_dedup"):
                res.ja_dedup += 1
            elif r.get("ok"):
                res.tratados += 1
            else:
                res.erros += 1
        except Exception as e:  # noqa: BLE001
            log.warning(
                "tratar_lead erro id=%s: %s", veredicto.get("lead_id"), e,
            )
            res.erros += 1

    return res


def esta_habilitado() -> bool:
    return os.getenv("WATCHDOG_PROMESSA_ENABLED", "0") == "1"


def silencio_min_seg_env() -> int:
    try:
        return int(os.getenv("WATCHDOG_PROMESSA_MIN_SEG", str(SILENCIO_MIN_SEG_DEFAULT)))
    except (TypeError, ValueError):
        return SILENCIO_MIN_SEG_DEFAULT


def silencio_max_seg_env() -> int:
    try:
        return int(os.getenv("WATCHDOG_PROMESSA_MAX_SEG", str(SILENCIO_MAX_SEG_DEFAULT)))
    except (TypeError, ValueError):
        return SILENCIO_MAX_SEG_DEFAULT
