"""Blink Bridge MCP — servidor MCP local que roda no Mac do Fábio.

Por quê: o sandbox do Cowork bloqueia `*.easypanel.host` no proxy HTTP,
então o Claude rodando no sandbox NÃO consegue chamar endpoints
admin do `blink-agent.6prkfn.easypanel.host` diretamente.

Como funciona:
  Claude (sandbox)
    ↓ MCP protocol (stdio)
  blink-bridge (este servidor, no Mac do Fábio)
    ↓ HTTP normal (acesso de rede do Mac)
  blink-agent.6prkfn.easypanel.host (produção)

Resultado: Claude executa qualquer endpoint admin de forma autônoma,
sem o Fábio precisar rodar curl/terminal.

Setup:
  1. `bash install.sh` (cria venv, instala dependências, valida)
  2. Adiciona o snippet de config no Claude Desktop
  3. Reinicia Claude Desktop
  4. Tudo funciona

Ferramentas expostas (7):
  - health()
  - reactivation_status()
  - disparar_lead(lead_id)
  - disparar_batch(lead_ids, dry_run)
  - disparar_categoria(categoria, unidade, medico, max_leads, dry_run)
  - disparar_template(lead_id, template, body_params, dry_run)
  - setup_campos_acompanhamento()
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Carrega .env.mcp do mesmo diretório do script
try:
    from dotenv import load_dotenv
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(SCRIPT_DIR, ".env.mcp"))
except ImportError:
    pass

BLINK_BASE_URL = os.environ.get(
    "BLINK_BASE_URL", "https://blink-agent.6prkfn.easypanel.host"
).rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
TIMEOUT_SECONDS = float(os.environ.get("BLINK_BRIDGE_TIMEOUT", "30"))

if not WEBHOOK_SECRET:
    print(
        "[blink-bridge] AVISO: WEBHOOK_SECRET não setado. "
        "Configure em .env.mcp ou via variável de ambiente.",
        file=sys.stderr,
    )

mcp = FastMCP("blink-bridge")


def _url(path: str) -> str:
    """Monta URL completa com path do app."""
    if not path.startswith("/"):
        path = "/" + path
    return f"{BLINK_BASE_URL}{path}"


def _add_secret(params: dict[str, Any]) -> dict[str, Any]:
    """Adiciona secret aos query params se setado."""
    if WEBHOOK_SECRET and "secret" not in params:
        params["secret"] = WEBHOOK_SECRET
    return params


def _safe_json(resp: httpx.Response) -> dict:
    """Tenta JSON, fallback pra dict com text."""
    try:
        return resp.json()
    except Exception:
        return {
            "ok": False,
            "status_code": resp.status_code,
            "text": resp.text[:2000],
        }


@mcp.tool()
def health() -> dict:
    """Verifica saúde do app blink-agent em produção.

    Retorna o JSON do endpoint /health (status, version, integrations).
    Útil pra confirmar que app está rodando antes de outras operações.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.get(_url("/health"))
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def reactivation_status() -> dict:
    """Status do motor de reativação 24h.

    Retorna config atual (enabled, dry_run, cap, template, etc) +
    contadores do dia.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.get(_url("/reactivation/status"))
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def disparar_lead(lead_id: int) -> dict:
    """Dispara template padrão (1089) pra UM lead específico.

    Pega telefone+nome via Kommo automaticamente, envia template
    aprovado, grava nota Kommo automática.

    Args:
        lead_id: ID do lead no Kommo (ex: 22982854)

    Retorna {ok, lead_id, telefone, nome, wamid, dispatch_result}.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.post(
                _url(f"/admin/disparar-lead/{lead_id}"),
                params=_add_secret({}),
            )
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "lead_id": lead_id, "error": str(e)}


@mcp.tool()
def disparar_batch(
    lead_ids: list[int],
    dry_run: bool = False,
) -> dict:
    """Dispara template aprovado pra N leads de uma vez.

    Args:
        lead_ids: lista de IDs (ex: [22982854, 21710873])
        dry_run: se True, valida sem enviar de verdade

    Retorna {total, ok, falhas, detalhes:[{lead_id, ok, wamid}]}.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.post(
                _url("/admin/disparar-batch"),
                params=_add_secret({}),
                json={
                    "lead_ids": lead_ids,
                    "dry_run": dry_run,
                },
            )
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "error": str(e), "lead_ids": lead_ids}


@mcp.tool()
def disparar_categoria(
    categoria: str,
    unidade: str = "",
    medico: str = "",
    max_leads: int = 30,
    dry_run: bool = False,
) -> dict:
    """Filtra leads por categoria + médico + unidade e dispara em batch.

    Args:
        categoria: 'R' (reagendar), 'E' (com convênio), 'C' (particular)
        unidade: 'Asa Norte' ou 'Águas Claras' (opcional)
        medico: 'Karla' ou 'Fabricio' (opcional)
        max_leads: default 30, máximo 200
        dry_run: se True, simula sem enviar

    Retorna {candidatos_encontrados, disparados_ok, detalhes}.
    """
    params: dict[str, Any] = {
        "categoria": categoria,
        "max": max_leads,
    }
    if unidade:
        params["unidade"] = unidade
    if medico:
        params["medico"] = medico
    if dry_run:
        params["dry_run"] = "true"
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.get(
                _url("/admin/disparar-categoria"),
                params=_add_secret(params),
            )
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "error": str(e), "categoria": categoria}


@mcp.tool()
def disparar_template(
    lead_id: int,
    template: str,
    body_params: list[str],
    dry_run: bool = False,
) -> dict:
    """Dispara template Meta CUSTOM pra 1 lead com body_params dinâmicos.

    Pra templates com múltiplas variáveis tipo captar_paciente.

    Args:
        lead_id: ID do lead
        template: nome exato do template Meta (case-sensitive)
        body_params: lista de strings pras variáveis {{1}}, {{2}}, ...
        dry_run: se True, simula sem enviar

    Retorna {ok, lead_id, telefone, nome, primeiro_nome, template, wamid}.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.post(
                _url(f"/admin/disparar-template/{lead_id}"),
                params=_add_secret({}),
                json={
                    "template": template,
                    "body_params": body_params,
                    "dry_run": dry_run,
                },
            )
        return _safe_json(r)
    except Exception as e:
        return {
            "ok": False, "lead_id": lead_id,
            "template": template, "error": str(e),
        }


@mcp.tool()
def setup_campos_acompanhamento() -> dict:
    """Cria os 3 campos de acompanhamento no Kommo.

    Idempotente: se já existirem, retorna ID atual.
    Campos: STATUS CONVERSA, ULTIMA MSG OUTBOUND, PROXIMA ACAO.
    """
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as c:
            r = c.post(
                _url("/admin/setup-campos-acompanhamento"),
                params=_add_secret({}),
            )
        return _safe_json(r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run()
