"""blink-kommo — Sprint 5.

Servidor MCP para Kommo CRM. Resolve nativamente o Bug C-12 (MCP
kommo_update_lead mente em custom_fields): toda atualização passa por
GET de validação imediato. Se o campo não confirmou, retorna erro
estruturado em vez de sucesso falso.

Também resolve Bug C-27 (duplicação) implementando busca por telefone
ANTES de criar lead novo.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-kommo - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-kommo")


# ─── Configuração ───────────────────────────────────────────────────
KOMMO_BASE = os.getenv("KOMMO_BASE_URL", "https://univeja.kommo.com/api/v4")
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN", "")

_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=10.0,
            headers={
                "Authorization": f"Bearer {KOMMO_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    return _http_client


def _set_client(c: httpx.Client) -> None:
    """Para testes."""
    global _http_client
    _http_client = c


mcp = FastMCP("blink-kommo")


# Field IDs canônicos
FIELD_ATIVADO_IA = 1260817
FIELD_NOME_PACIENTE = 1255757
FIELD_MEDICO = 1256257
FIELD_UNIDADE = 1245125
FIELD_CONVENIO = 853206
FIELD_DIA_TURNO_PERIODO = 1259960
FIELD_DIA_CONSULTA = 1255723

PIPELINE_ATENDE = 8601819
STATUS_ATENDIMENTO_HUMANO = 106563343
STATUSES_INATIVAM_IA = {
    106563343,  # 1-ATENDIMENTO HUMANO
    106157139,  # CIRURGIAS
    106484343,  # LENTES
    106484347,  # FORNECEDORES
}


# ─── TOOLS ──────────────────────────────────────────────────────────

@mcp.tool()
def get_lead(lead_id: int) -> dict:
    """Busca lead Kommo completo (custom_fields, notes, contacts).

    Args:
        lead_id: ID numérico do lead.

    Returns:
        Dict completo do lead.
    """
    c = _get_client()
    r = c.get(
        f"{KOMMO_BASE}/leads/{lead_id}",
        params={"with": "custom_fields_values,contacts,notes"},
    )
    if r.status_code != 200:
        raise ValueError(f"Lead {lead_id} não encontrado (HTTP {r.status_code})")
    return r.json()


@mcp.tool()
def buscar_leads_por_telefone(phone: str) -> list[dict]:
    """Busca leads pelo telefone do contato. Resolve Bug C-27 (duplicação).

    Use ANTES de criar lead novo. Se já existe lead ativo para esse
    telefone, retorna em vez de criar duplicata.

    Args:
        phone: Telefone E.164 ou apenas dígitos.

    Returns:
        Lista de leads associados.
    """
    phone_clean = "".join(c for c in phone if c.isdigit())
    c = _get_client()
    r = c.get(f"{KOMMO_BASE}/leads", params={"query": phone_clean, "limit": 50})
    if r.status_code != 200:
        return []
    data = r.json()
    embedded = data.get("_embedded", {})
    return embedded.get("leads", []) if embedded else []


@mcp.tool()
def atualizar_custom_field(lead_id: int, field_id: int, valor) -> dict:
    """Atualiza custom_field e VALIDA via GET imediato. Resolve Bug C-12.

    O endpoint PATCH do Kommo às vezes retorna success mas NÃO grava
    custom_fields. Esta tool faz GET após PATCH e confirma que o valor
    realmente entrou no banco. Se não confirmou, retorna ok=False com
    detalhe — em vez de mascarar a falha.

    Args:
        lead_id: ID do lead.
        field_id: field_id numérico Kommo.
        valor: valor a gravar (string, número, ou enum_id).

    Returns:
        Dict com {ok, valor_gravado, valor_pedido}.
    """
    c = _get_client()

    payload = {
        "custom_fields_values": [
            {"field_id": field_id, "values": [{"value": valor}]}
        ]
    }

    # PATCH
    r = c.patch(f"{KOMMO_BASE}/leads/{lead_id}", json=payload)
    if r.status_code not in (200, 202):
        log.error("PATCH falhou HTTP %d: %s", r.status_code, r.text[:200])
        return {"ok": False, "erro": f"PATCH HTTP {r.status_code}", "detail": r.text[:300]}

    # GET de validação (Fix Bug C-12)
    rg = c.get(
        f"{KOMMO_BASE}/leads/{lead_id}",
        params={"with": "custom_fields_values"},
    )
    if rg.status_code != 200:
        return {"ok": False, "erro": "GET validacao falhou"}

    lead = rg.json()
    cfs = lead.get("custom_fields_values") or []
    valor_real = None
    for cf in cfs:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                valor_real = vals[0].get("value")
            break

    if valor_real != valor:
        # Pode ser enum (str vs int) — tenta comparação mais flexível
        if str(valor_real) != str(valor):
            log.warning(
                "[BUG-C-12] Campo %d não confirmou. pedido=%r gravado=%r",
                field_id, valor, valor_real,
            )
            return {
                "ok": False,
                "erro": "campo_nao_confirmou",
                "valor_pedido": valor,
                "valor_gravado": valor_real,
            }

    log.info("Custom field %d atualizado em lead %d", field_id, lead_id)
    return {"ok": True, "valor_gravado": valor_real, "valor_pedido": valor}


@mcp.tool()
def anexar_nota(lead_id: int, texto: str) -> dict:
    """Anexa nota visível à equipe humana no lead Kommo.

    Args:
        lead_id: ID do lead.
        texto: Conteúdo da nota.

    Returns:
        Dict com {ok, note_id}.
    """
    c = _get_client()
    payload = [{
        "entity_id": lead_id,
        "note_type": "common",
        "params": {"text": texto},
    }]
    r = c.post(f"{KOMMO_BASE}/leads/notes", json=payload)
    if r.status_code in (200, 201, 202):
        data = r.json()
        embedded = data.get("_embedded", {})
        notes = embedded.get("notes", [])
        note_id = notes[0].get("id") if notes else None
        return {"ok": True, "note_id": note_id}
    log.error("Falha anexar nota: HTTP %d", r.status_code)
    return {"ok": False, "erro": f"HTTP {r.status_code}"}


@mcp.tool()
def mover_etapa(lead_id: int, status_id: int) -> dict:
    """Move lead para outra etapa do funil.

    Quando move para uma das 4 etapas inativas (ATENDIMENTO HUMANO,
    CIRURGIAS, LENTES, FORNECEDORES), AUTOMATICAMENTE desativa a IA
    via campo ATIVADO IA? (Bug C-24a).
    """
    c = _get_client()
    r = c.patch(f"{KOMMO_BASE}/leads/{lead_id}", json={"status_id": status_id})
    if r.status_code not in (200, 202):
        return {"ok": False, "erro": f"HTTP {r.status_code}"}

    # Se mudou para etapa inativa, desativa IA via mesma interface
    if status_id in STATUSES_INATIVAM_IA:
        # enum_id 927035 = "Desativado"
        atualizar_custom_field(lead_id, FIELD_ATIVADO_IA, "Desativado")
        log.info("Lead %d movido para etapa inativa, IA desativada", lead_id)

    return {"ok": True, "status_id": status_id}


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("kommo://lead/{lead_id}")
def resource_lead(lead_id: str) -> str:
    """Leitura completa do lead como recurso passivo."""
    import json
    lead = get_lead(int(lead_id))
    return json.dumps(lead, ensure_ascii=False, indent=2)


@mcp.resource("kommo://etapas-inativam-ia")
def resource_etapas_inativas() -> str:
    """Lista das 4 etapas em que a IA fica automaticamente desativada."""
    linhas = ["ETAPAS QUE INATIVAM A IA (Bug C-24a)"]
    nomes = {
        106563343: "1-ATENDIMENTO HUMANO",
        106157139: "CIRURGIAS",
        106484343: "LENTES",
        106484347: "FORNECEDORES",
    }
    for sid, nome in nomes.items():
        linhas.append(f"  {sid} — {nome}")
    return "\n".join(linhas)


if __name__ == "__main__":
    log.info("Iniciando blink-kommo. base=%s", KOMMO_BASE)
    mcp.run()
