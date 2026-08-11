"""blink-whatsapp — Sprint 6.

Servidor MCP para dispatch de mensagens WhatsApp em dois canais:
- 8133-1005 (Meta WhatsApp Cloud — oficial)
- 0710 (Evolution legado — apenas para redirect)

Quando outros servidores MCP pedem envio para o 0710, este servidor
detecta automaticamente e responde com mensagem de redirect ao 8133
em vez de tentar atendimento clínico no canal antigo.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-whatsapp - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-whatsapp")


# ─── Configuração ───────────────────────────────────────────────────
WA_CLOUD_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
WA_BUSINESS_ACCOUNT_ID = os.getenv("META_WABA_ID", "")
EVOLUTION_BASE = os.getenv("EVOLUTION_BASE_URL", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
EVOLUTION_TOKEN = os.getenv("EVOLUTION_TOKEN", "")

# Número oficial novo para onde redirecionar
NUMERO_OFICIAL = "5561981331005"
LINK_REDIRECT = (
    f"https://wa.me/{NUMERO_OFICIAL}"
    "?text=Ol%C3%A1%21%20Vim%20do%20WhatsApp%20antigo%20%28-0710%29."
)

# Identificador de canal — quando phone do remetente bate com 0710,
# todas as respostas vão pelo Evolution (não pela Cloud).
PHONE_0710_PREFIXO = "5561996630710"  # número antigo da Blink

_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=15.0)
    return _http_client


def _set_client(c: httpx.Client) -> None:
    """Para testes."""
    global _http_client
    _http_client = c


mcp = FastMCP("blink-whatsapp")


# ─── Pydantic models ────────────────────────────────────────────────

class EnviarTextoInput(BaseModel):
    phone_to: str = Field(..., min_length=10, description="Telefone destinatário E.164")
    texto: str = Field(..., min_length=1, max_length=4096)
    canal: Literal["8133", "0710", "auto"] = Field(default="auto")


class EnviarTemplateInput(BaseModel):
    phone_to: str = Field(..., min_length=10)
    template_name: str = Field(..., min_length=1)
    body_params: list[str] = Field(default_factory=list)
    language_code: str = Field(default="pt_BR")


# ─── TOOLS ──────────────────────────────────────────────────────────

@mcp.tool()
def enviar_texto(
    phone_to: str,
    texto: str,
    canal: str = "auto",
    veio_do_0710: bool = False,
) -> dict:
    """Envia mensagem de texto via WhatsApp.

    Roteamento de canal:
    - Se veio_do_0710=True → envia via Evolution AUTOMATICAMENTE substituindo
      o texto pela mensagem padrão de redirect ao 8133. Não envia conteúdo
      clínico no canal antigo.
    - Senão, usa o canal especificado (default 8133).

    Args:
        phone_to: Telefone E.164 do destinatário.
        texto: Texto a enviar (até 4096 chars).
        canal: "8133" (Meta Cloud), "0710" (Evolution), "auto" (default 8133).
        veio_do_0710: True se a mensagem inbound original veio do 0710.

    Returns:
        Dict com {ok, message_id, canal_usado, foi_redirect}.
    """
    inp = EnviarTextoInput(phone_to=phone_to, texto=texto, canal=canal)

    if veio_do_0710:
        return _enviar_redirect_0710(inp.phone_to)

    if inp.canal == "0710":
        return _enviar_evolution(inp.phone_to, inp.texto)

    return _enviar_meta_cloud(inp.phone_to, inp.texto)


@mcp.tool()
def enviar_template_meta(
    phone_to: str,
    template_name: str,
    body_params: list[str] = None,
    language_code: str = "pt_BR",
) -> dict:
    """Envia template Meta WhatsApp aprovado.

    Use para iniciar conversa fora da janela 24h ou para mensagens
    transacionais (confirmação, lembrete, NPS).
    """
    inp = EnviarTemplateInput(
        phone_to=phone_to, template_name=template_name,
        body_params=body_params or [], language_code=language_code,
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": inp.phone_to,
        "type": "template",
        "template": {
            "name": inp.template_name,
            "language": {"code": inp.language_code},
        },
    }
    if inp.body_params:
        payload["template"]["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in inp.body_params],
        }]

    c = _get_client()
    url = f"https://graph.facebook.com/v22.0/{WA_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_CLOUD_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        r = c.post(url, json=payload, headers=headers)
        if r.status_code in (200, 201):
            data = r.json()
            mid = (data.get("messages") or [{}])[0].get("id")
            log.info("Template %s enviado para %s wamid=%s",
                     inp.template_name, inp.phone_to, mid)
            return {"ok": True, "message_id": mid, "canal_usado": "8133"}
        return {"ok": False, "erro": f"HTTP {r.status_code}", "detail": r.text[:300]}
    except Exception as e:
        log.exception("Erro enviar template")
        return {"ok": False, "erro": "exception", "detail": str(e)}


# ─── Helpers internos ───────────────────────────────────────────────

def _enviar_meta_cloud(phone_to: str, texto: str) -> dict:
    """Envia texto via Meta WhatsApp Cloud (8133)."""
    c = _get_client()
    url = f"https://graph.facebook.com/v22.0/{WA_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_to,
        "type": "text",
        "text": {"body": texto},
    }
    headers = {
        "Authorization": f"Bearer {WA_CLOUD_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        r = c.post(url, json=payload, headers=headers)
        if r.status_code in (200, 201):
            data = r.json()
            mid = (data.get("messages") or [{}])[0].get("id")
            log.info("[8133] msg enviada para %s wamid=%s", phone_to, mid)
            return {"ok": True, "message_id": mid, "canal_usado": "8133", "foi_redirect": False}
        return {"ok": False, "erro": f"HTTP {r.status_code}", "canal_usado": "8133"}
    except Exception as e:
        log.exception("Erro Meta Cloud")
        return {"ok": False, "erro": "exception", "detail": str(e), "canal_usado": "8133"}


def _enviar_evolution(phone_to: str, texto: str) -> dict:
    """Envia texto via Evolution (0710)."""
    if not EVOLUTION_BASE or not EVOLUTION_INSTANCE:
        return {"ok": False, "erro": "evolution_nao_configurado"}

    c = _get_client()
    url = f"{EVOLUTION_BASE}/message/sendText/{EVOLUTION_INSTANCE}"
    payload = {"number": phone_to, "text": texto}
    headers = {"apikey": EVOLUTION_TOKEN, "Content-Type": "application/json"}
    try:
        r = c.post(url, json=payload, headers=headers)
        if r.status_code in (200, 201):
            log.info("[0710] msg enviada para %s", phone_to)
            return {"ok": True, "canal_usado": "0710", "foi_redirect": False}
        return {"ok": False, "erro": f"HTTP {r.status_code}", "canal_usado": "0710"}
    except Exception as e:
        log.exception("Erro Evolution")
        return {"ok": False, "erro": "exception", "detail": str(e), "canal_usado": "0710"}


def _enviar_redirect_0710(phone_to: str) -> dict:
    """Envia mensagem padrão de redirect ao 8133 via Evolution.

    Mensagem fixa, sem LLM, sem risco de alucinação clínica.
    """
    texto = (
        "Olá! Esse número antigo está sendo desativado. "
        "Para continuar seu atendimento, fala com a gente pelo canal oficial:\n\n"
        f"{LINK_REDIRECT}\n\n"
        "Toca no link e seguimos por lá. Obrigada!"
    )
    out = _enviar_evolution(phone_to, texto)
    out["foi_redirect"] = True
    return out


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("whatsapp://canais")
def resource_canais() -> str:
    return (
        "CANAIS WHATSAPP BLINK\n\n"
        f"  8133-1005 (oficial Meta Cloud) — número {NUMERO_OFICIAL}\n"
        f"  0710 (Evolution legado) — apenas redirect\n\n"
        f"  Link de migração: {LINK_REDIRECT}"
    )


if __name__ == "__main__":
    log.info(
        "Iniciando blink-whatsapp. 8133 cloud=%s 0710 evolution=%s",
        bool(WA_CLOUD_TOKEN), bool(EVOLUTION_TOKEN),
    )
    mcp.run()
