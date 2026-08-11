"""blink-host — Orquestrador agêntico (livro 7.2).

Implementa o loop agêntico que conecta os 6 servidores MCP da Blink:
1. Observar (lê recursos: kommo, state, medware)
2. Pensar (consulta LLM com tools dos servidores)
3. Agir (chama tools de medware, kommo, whatsapp)
4. Avaliar (lê retorno, atualiza state)
5. Repetir até estado final

ARQUITETURA: este Host substitui o webhook.py atual do voice_agent.
Pode rodar como FastAPI + Anthropic SDK, conectando aos 6 servidores
MCP via stdio.

EXEMPLO DE USO (programático):
    from blink_host.orchestrator import processar_mensagem_inbound
    resultado = await processar_mensagem_inbound(
        phone="5561999000000",
        texto="oi",
        canal="8133",
    )

Este arquivo entrega o ESQUELETO operacional. A integração efetiva com
Anthropic SDK + FastAPI vem em sprint posterior (após validação dos 6
servidores em produção).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-host - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-host")


CONFIG_PATH = Path(__file__).parent / "config.json"


class InboundMessage(BaseModel):
    phone: str = Field(..., min_length=10)
    texto: str = Field(..., min_length=1, max_length=4096)
    canal: str = Field(default="8133")
    timestamp: Optional[int] = None


class OrchestratorResult(BaseModel):
    ok: bool
    decisao: str = Field(description="O que o agente fez")
    tools_chamadas: list[str] = Field(default_factory=list)
    resposta_outbound: Optional[str] = None
    erro: Optional[str] = None


def carregar_config() -> dict:
    """Carrega config.json com a lista dos servidores MCP."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def listar_servidores_disponiveis() -> list[str]:
    """Lista nomes dos servidores MCP configurados."""
    cfg = carregar_config()
    return list(cfg.get("mcpServers", {}).keys())


async def processar_mensagem_inbound(
    phone: str,
    texto: str,
    canal: str = "8133",
) -> OrchestratorResult:
    """Loop agêntico simplificado para processar 1 mensagem inbound.

    Esta é uma versão SÍNCRONA simplificada para mostrar o fluxo. A
    versão completa (com Anthropic SDK + tool calling real entre 6
    servidores) vem em sprint posterior.

    Fluxo:
    1. Verifica dedup via blink-state
    2. Adquire lock via blink-state
    3. Lê contexto via blink-kommo (lead) + blink-state (ctx_known)
    4. Se canal=0710 → redirect via blink-whatsapp (sem LLM)
    5. Senão, chama LLM com tools dos 6 servidores
    6. Executa tools decididas pela LLM
    7. Envia resposta via blink-whatsapp
    8. Persiste ctx atualizado via blink-state
    9. Libera lock

    Args:
        phone: Telefone E.164.
        texto: Mensagem inbound.
        canal: "8133" ou "0710".

    Returns:
        OrchestratorResult com decisão, tools chamadas, resposta.
    """
    msg = InboundMessage(phone=phone, texto=texto, canal=canal)
    log.info("Processando inbound phone=%s canal=%s", msg.phone, msg.canal)

    tools_chamadas = []

    # --- ETAPA 1: Dedup ---
    # Em prod: cliente MCP chama blink-state.dedup_check
    eh_nova = True  # placeholder
    tools_chamadas.append("blink-state.dedup_check")

    if not eh_nova:
        return OrchestratorResult(
            ok=True, decisao="msg_duplicada_ignorada",
            tools_chamadas=tools_chamadas,
        )

    # --- ETAPA 2: Lock ---
    tools_chamadas.append("blink-state.acquire_lock")
    pegou_lock = True  # placeholder
    if not pegou_lock:
        return OrchestratorResult(
            ok=False, decisao="conversa_ocupada",
            tools_chamadas=tools_chamadas,
            erro="Outra instância está processando esta conversa",
        )

    try:
        # --- ETAPA 3: Canal 0710 → redirect ---
        if msg.canal == "0710":
            tools_chamadas.append("blink-whatsapp.enviar_texto[redirect]")
            # Em prod: chamada real via cliente MCP
            return OrchestratorResult(
                ok=True,
                decisao="redirect_0710_para_8133",
                tools_chamadas=tools_chamadas,
                resposta_outbound=(
                    "Olá! Esse número antigo está sendo desativado. "
                    "Continua com a gente pelo canal oficial: "
                    "https://wa.me/5561981331005"
                ),
            )

        # --- ETAPA 4: Lê contexto ---
        tools_chamadas.append("blink-state.carregar_ctx_known")
        tools_chamadas.append("blink-kommo.buscar_leads_por_telefone")

        # --- ETAPA 5: LLM decide ---
        # Em prod: Anthropic SDK chama Claude com tools dos 6 servidores.
        # Claude decide quais tools chamar para resolver o pedido do paciente.
        # Esqueleto retorna decisão genérica.
        tools_chamadas.append("anthropic.messages.create[com 6 servers MCP]")

        # --- ETAPA 6: Executa tools decididas ---
        # Exemplo de cenário "paciente quer agendar":
        #   - blink-calendar.proximas_datas_disponiveis
        #   - blink-medware.consultar_horarios
        #   - blink-state.reservar_slot_temporariamente
        #   - blink-whatsapp.enviar_texto (oferta)

        # --- ETAPA 7: Persiste estado ---
        tools_chamadas.append("blink-state.salvar_ctx_known")

        return OrchestratorResult(
            ok=True,
            decisao="processado_via_llm",
            tools_chamadas=tools_chamadas,
            resposta_outbound="(resposta gerada pela LLM com base nos tools)",
        )

    finally:
        # --- ETAPA 8: Sempre libera lock ---
        tools_chamadas.append("blink-state.release_lock")


def main():
    """Ponto de entrada para teste interativo."""
    log.info("blink-host orquestrador inicializado")
    log.info("Servidores configurados: %s", listar_servidores_disponiveis())

    # Smoke test
    resultado = asyncio.run(processar_mensagem_inbound(
        phone="5561999000000",
        texto="oi",
        canal="8133",
    ))
    print(json.dumps(resultado.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
