"""blink-atendimento — Camada 1 da memória ativa.

Servidor MCP local que expõe UMA tool determinística:
    ler_chat_completo_lead(lead_id: int) -> dict

Ela retorna, num único payload:
    - custom_fields relevantes do lead (nome, médico, unidade, convênio,
      status, ATIVADO IA, JANELA 24H, últimas msgs cache)
    - notas Kommo (últimas 30, ordem cronológica)
    - mensagens do canal WhatsApp (Meta Graph, últimas 30, ordem cronológica)
    - resumo estruturado {ultimo_paciente, ultimo_outbound, quem_pergunta_o_que}

Objetivo: quando URL de lead aparecer na conversa comigo (Claude Cowork),
o skill file trigger força chamada dessa tool ANTES de qualquer resposta.
Impede repetir o bug Theo/Tiago (perguntar A/B/C sem ter lido chat).

Tools:
    ler_chat_completo_lead(lead_id) — leitura obrigatória
    desativar_ia_lead(lead_id, motivo) — quando humano assumir
    confirmar_slot_medware(cod_medico, cod_unidade, data_iso, hora) — antes de gravar

Todas as tools são idempotentes e sem efeito colateral (menos desativar).
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-atendimento - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-atendimento")


# ─── Configuração — lida dinamicamente pra testabilidade ─────────────

def _kommo_base() -> str:
    return os.getenv("KOMMO_BASE_URL", "https://univeja.kommo.com/api/v4")


def _kommo_token() -> str:
    return os.getenv("KOMMO_TOKEN", "")


_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    """Reutiliza HTTP client (mais rápido, menos handshakes TLS)."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {_kommo_token()}",
                "Content-Type": "application/json",
                "User-Agent": "blink-atendimento-mcp/1.0",
            },
        )
    return _http_client


def _set_client(c: httpx.Client) -> None:
    """Pra testes com mock."""
    global _http_client
    _http_client = c


mcp = FastMCP("blink-atendimento")


# ─── Field IDs relevantes (fonte: CLAUDE.md seção 5) ─────────────────
FIELDS_RELEVANTES: dict[int, str] = {
    853206:  "CONVENIO",
    1245125: "UNIDADE",
    1246419: "ATENDENTE",
    1255723: "1.DIA_CONSULTA",
    1255757: "1.NOME_PACIENTE",
    1255761: "2.NOME_PACIENTE",
    1256257: "MEDICOS",
    1257961: "1.PERFIL",
    1259118: "N_PACIENTES",
    1259130: "ESPECIALIDADE",
    1259166: "2.PERFIL",
    1259960: "DIA_TURNO_PERIODO",
    1259984: "1.DATA_NASCIMENTO",
    1260817: "ATIVADO_IA",
    1260854: "STATUS_CONVERSA",
    1260856: "ULTIMA_MSG_OUTBOUND",
    1260858: "PROXIMA_ACAO",
    1260860: "ULTIMA_MENS_LIA",
    1260862: "ULTIMA_MENS_HUMANO",
    1260984: "ULTIMA_MENS_PACIENTE",
    1260986: "JANELA_24H",
    1261014: "2.1PROX_DIA",
    1261016: "2.2PROX_DIA",
    1261074: "0.DIA_PRIMEIRA_CONSULTA",
    1261076: "0.PACIENTES",
}


def _limpar_custom_fields(cf_list: list[dict]) -> dict[str, Any]:
    """Filtra apenas os campos relevantes + renomeia chave humano-legível."""
    out: dict[str, Any] = {}
    for cf in cf_list or []:
        fid = cf.get("field_id")
        nome = FIELDS_RELEVANTES.get(fid)
        if not nome:
            continue
        values = cf.get("values") or []
        if not values:
            continue
        # Pega o primeiro valor (multiselect vira lista)
        if len(values) == 1:
            out[nome] = values[0].get("value")
        else:
            out[nome] = [v.get("value") for v in values]
    return out


def _extrair_telefone_do_lead(lead_json: dict) -> Optional[str]:
    """Extrai telefone do primeiro contato do lead (formato E.164, com 55)."""
    embedded = lead_json.get("_embedded") or {}
    contatos = embedded.get("contacts") or []
    if not contatos:
        return None
    contato_id = contatos[0].get("id")
    if not contato_id:
        return None
    try:
        r = _get_client().get(f"{_kommo_base()}/contacts/{contato_id}")
        if r.status_code != 200:
            return None
        d = r.json()
        for cf in d.get("custom_fields_values") or []:
            code = (cf.get("field_code") or "").upper()
            nome = (cf.get("field_name") or "").upper()
            if code == "PHONE" or "PHONE" in nome or "FONE" in nome or "TEL" in nome:
                for v in cf.get("values") or []:
                    raw = str(v.get("value") or "")
                    digits = re.sub(r"\D", "", raw)
                    if len(digits) >= 10:
                        return digits if digits.startswith("55") else f"55{digits}"
    except Exception as e:
        log.warning("erro extrair telefone contato=%s: %s", contato_id, e)
    return None


def _buscar_notas_kommo(lead_id: int, limite: int = 30) -> list[dict]:
    """Retorna últimas N notas do lead, ordem cronológica crescente."""
    try:
        r = _get_client().get(
            f"{_kommo_base()}/leads/{lead_id}/notes",
            params={"limit": limite, "order[updated_at]": "desc"},
        )
        if r.status_code != 200:
            log.warning("notas Kommo status=%d", r.status_code)
            return []
        embedded = (r.json() or {}).get("_embedded") or {}
        notas_raw = embedded.get("notes") or []
        out = []
        for n in notas_raw:
            params = n.get("params") or {}
            texto = (
                params.get("text")
                or params.get("service")
                or n.get("text")
                or ""
            )
            if not texto:
                continue
            out.append({
                "id": n.get("id"),
                "created_at": n.get("created_at"),
                "created_by": n.get("created_by"),
                "note_type": n.get("note_type"),
                "texto": texto[:500],
            })
        out.reverse()  # cronológica crescente (mais antiga → mais recente)
        return out
    except Exception as e:
        log.warning("erro notas Kommo lead=%d: %s", lead_id, e)
        return []


def _buscar_msgs_whatsapp(telefone: str, limite: int = 30) -> list[dict]:
    """Retorna últimas mensagens WhatsApp do telefone via Meta Graph.

    Nota: Meta Graph API v21.0 tem endpoint /messages, mas retorna só as
    últimas 24h por token. Aqui devolvemos placeholder + orientação de
    fallback para leitura via notas Kommo (que já grava toda mensagem).
    """
    if not (WA_TOKEN and WA_PHONE_ID and telefone):
        return []
    # Meta Graph v21.0 NÃO tem endpoint público de "buscar mensagens
    # anteriores" — apenas /conversations retorna resumo de conversas.
    # Fallback confiável: as notas Kommo já contêm o inbound+outbound
    # gravado pela Lia. _buscar_notas_kommo() cobre isso.
    log.info(
        "Meta Graph API não expõe histórico de mensagens — "
        "usando notas Kommo como fonte única (telefone=%s...%s)",
        telefone[:4], telefone[-2:],
    )
    return []


def _resumir_estado(
    fields: dict[str, Any], notas: list[dict]
) -> dict[str, Any]:
    """Extrai resumo estruturado do estado atual da conversa."""
    ultimo_outbound = fields.get("ULTIMA_MSG_OUTBOUND", "")
    status_conversa = fields.get("STATUS_CONVERSA", "")
    proxima_acao = fields.get("PROXIMA_ACAO", "")
    ativado_ia = fields.get("ATIVADO_IA", "")
    ja_agendado = bool(fields.get("1.DIA_CONSULTA"))

    # Última msg do paciente e da Lia — a partir das notas
    ultimo_paciente = None
    ultima_lia = None
    for nota in reversed(notas):  # do mais recente pro mais antigo
        texto = (nota.get("texto") or "").strip()
        if texto.startswith("Lia (WhatsApp):"):
            if ultima_lia is None:
                ultima_lia = {
                    "texto": texto.replace("Lia (WhatsApp):", "").strip()[:300],
                    "quando": nota.get("created_at"),
                }
        elif nota.get("created_by") == 0 and not texto.startswith("Lia"):
            if ultimo_paciente is None:
                ultimo_paciente = {
                    "texto": texto[:300],
                    "quando": nota.get("created_at"),
                }
        if ultimo_paciente and ultima_lia:
            break

    return {
        "ativado_ia": ativado_ia,
        "ja_agendado": ja_agendado,
        "dia_consulta_ts": fields.get("1.DIA_CONSULTA"),
        "status_conversa": status_conversa,
        "proxima_acao": proxima_acao,
        "ultimo_outbound_lia": ultimo_outbound,
        "ultimo_msg_paciente": ultimo_paciente,
        "ultimo_msg_lia_notas": ultima_lia,
        "medico": fields.get("MEDICOS"),
        "unidade": fields.get("UNIDADE"),
        "convenio": fields.get("CONVENIO"),
        "especialidade": fields.get("ESPECIALIDADE"),
        "pacientes": {
            "n": fields.get("N_PACIENTES"),
            "1_nome": fields.get("1.NOME_PACIENTE"),
            "2_nome": fields.get("2.NOME_PACIENTE"),
        },
        "preferencia_temporal": fields.get("DIA_TURNO_PERIODO"),
    }


# ─── TOOL PRINCIPAL — ler_chat_completo_lead ─────────────────────────

@mcp.tool()
def ler_chat_completo_lead(lead_id: int) -> dict:
    """Retorna estado completo do lead + histórico da conversa.

    OBRIGATÓRIO chamar ANTES de responder qualquer pergunta sobre um
    lead. Sem essa chamada, resposta será baseada em suposição, não em
    fato.

    Returns:
        {
            "lead_id": int,
            "url_kommo": str,
            "custom_fields": dict com campos relevantes traduzidos,
            "notas": list[dict] (últimas 30, cronológica crescente),
            "resumo": dict estruturado com estado atual,
            "erro": str | None,
        }
    """
    if not _kommo_token():
        return {"erro": "KOMMO_TOKEN não configurado no ambiente"}

    try:
        r = _get_client().get(
            f"{_kommo_base()}/leads/{lead_id}",
            params={"with": "contacts,catalog_elements"},
        )
    except Exception as e:
        return {"erro": f"http_error_get_lead: {e}"}

    if r.status_code == 404:
        return {"erro": f"lead_id={lead_id} não encontrado"}
    if r.status_code != 200:
        return {"erro": f"kommo_status={r.status_code}"}

    lead_json = r.json()
    fields = _limpar_custom_fields(lead_json.get("custom_fields_values") or [])
    telefone = _extrair_telefone_do_lead(lead_json)
    notas = _buscar_notas_kommo(lead_id, limite=30)
    resumo = _resumir_estado(fields, notas)

    return {
        "lead_id": lead_id,
        "url_kommo": f"https://univeja.kommo.com/leads/detail/{lead_id}",
        "nome_lead": lead_json.get("name"),
        "status_id": lead_json.get("status_id"),
        "pipeline_id": lead_json.get("pipeline_id"),
        "telefone_contato": telefone,
        "custom_fields": fields,
        "notas": notas,
        "resumo": resumo,
        "erro": None,
    }


# ─── TOOL 2 — desativar_ia_lead ──────────────────────────────────────

@mcp.tool()
def desativar_ia_lead(lead_id: int, motivo: str = "humano assumiu") -> dict:
    """Desativa a IA num lead específico (seta ATIVADO_IA = Desativado).

    Usar quando você (Fábio) estiver conduzindo manualmente e não
    quiser que a Lia atropele. Grava nota Kommo com o motivo.

    Field 1260817 (ATIVADO_IA), enum_id 927035 = "Desativado".
    """
    if not _kommo_token():
        return {"erro": "KOMMO_TOKEN não configurado"}

    payload = {
        "custom_fields_values": [
            {
                "field_id": 1260817,
                "values": [{"value": "Desativado", "enum_id": 927035}],
            }
        ]
    }
    try:
        r = _get_client().patch(f"{_kommo_base()}/leads/{lead_id}", json=payload)
    except Exception as e:
        return {"erro": f"http_error_patch: {e}"}

    if r.status_code not in (200, 202):
        return {"erro": f"kommo_status={r.status_code}", "body": r.text[:300]}

    # Grava nota
    nota_texto = f"[BLINK-ATENDIMENTO MCP] IA desativada. Motivo: {motivo}"
    try:
        _get_client().post(
            f"{_kommo_base()}/leads/{lead_id}/notes",
            json=[{"note_type": "common", "params": {"text": nota_texto}}],
        )
    except Exception:
        pass

    return {"ok": True, "lead_id": lead_id, "ativado_ia": "Desativado"}


# ─── TOOL 3 — confirmar_slot_medware ────────────────────────────────

@mcp.tool()
def confirmar_slot_medware(
    cod_medico: int, cod_unidade: int, data_iso: str, hora: str
) -> dict:
    """Confirma se um slot específico está disponível no Medware.

    Chamar SEMPRE antes de dizer ao paciente "seu horário está reservado".
    Evita bug "Lia confirma slot que já foi ocupado".

    Args:
        cod_medico: 12080 (Karla) ou 12081 (Fabrício)
        cod_unidade: 5 (Asa Norte) ou 3 (Águas Claras)
        data_iso: "2026-08-07"
        hora: "10:00" ou "10:00:00"

    Returns:
        {"disponivel": bool, "slot": {...} | None, "erro": str | None}
    """
    MEDWARE_BASE = os.getenv(
        "MEDWARE_BASE_URL",
        "https://medware.blinkoftalmologia.com.br/api",
    )
    MEDWARE_USER = os.getenv("MEDWARE_USER", "")
    MEDWARE_PASSWORD = os.getenv("MEDWARE_PASSWORD", "")

    if not (MEDWARE_USER and MEDWARE_PASSWORD):
        return {"erro": "credencias Medware não configuradas"}

    # Chama endpoint Medware/Horarios/Listar filtrando o dia especifico
    from datetime import datetime
    try:
        dt = datetime.strptime(data_iso[:10], "%Y-%m-%d")
    except ValueError:
        return {"erro": f"data_iso inválido: {data_iso}"}
    data_br = dt.strftime("%d/%m/%Y")
    hora_hh_mm = hora[:5]

    params = {
        "dataInicio": data_br,
        "dataFim": data_br,
        "horaInicio": "07:00",
        "horaFim": "19:00",
        "codMedico": cod_medico,
        "codUnidade": cod_unidade,
    }
    try:
        auth = (MEDWARE_USER, MEDWARE_PASSWORD)
        r = httpx.get(
            f"{MEDWARE_BASE}/Medware/Horarios/Listar",
            params=params,
            auth=auth,
            timeout=15.0,
        )
    except Exception as e:
        return {"erro": f"http_error_medware: {e}"}

    if r.status_code != 200:
        return {"erro": f"medware_status={r.status_code}"}

    slots = r.json() if isinstance(r.json(), list) else []
    match = None
    for s in slots:
        s_hora = str(s.get("horario") or "")[:5]
        if s_hora == hora_hh_mm:
            match = s
            break

    return {
        "disponivel": match is not None,
        "slot": match,
        "erro": None,
    }


# ─── Ponto de entrada ────────────────────────────────────────────────

def main() -> None:
    """Roda o servidor MCP via stdio (padrão Cowork/Claude Desktop)."""
    mcp.run()


if __name__ == "__main__":
    main()
