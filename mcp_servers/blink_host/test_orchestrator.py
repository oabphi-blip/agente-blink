"""Pytest blink-host orquestrador."""
from __future__ import annotations
import asyncio
import pytest

from blink_host.orchestrator import (
    processar_mensagem_inbound,
    listar_servidores_disponiveis,
    carregar_config,
)


def test_carregar_config_ok():
    cfg = carregar_config()
    assert "mcpServers" in cfg


def test_listar_servidores_inclui_6_essenciais():
    srv = listar_servidores_disponiveis()
    assert "blink-calendar" in srv
    assert "blink-knowledge" in srv
    assert "blink-state" in srv
    assert "blink-medware" in srv
    assert "blink-kommo" in srv
    assert "blink-whatsapp" in srv


def test_processar_msg_8133_chama_loop_completo():
    out = asyncio.run(processar_mensagem_inbound(
        phone="5561999000000", texto="oi", canal="8133",
    ))
    assert out.ok is True
    assert "blink-state.dedup_check" in out.tools_chamadas
    assert "blink-state.acquire_lock" in out.tools_chamadas
    assert "blink-state.release_lock" in out.tools_chamadas


def test_processar_msg_0710_eh_redirect_sem_llm():
    out = asyncio.run(processar_mensagem_inbound(
        phone="5561999000000",
        texto="quero agendar consulta urgente",
        canal="0710",
    ))
    assert out.ok is True
    assert out.decisao == "redirect_0710_para_8133"
    # NÃO chamou Anthropic (zero custo de tokens)
    assert not any("anthropic" in t for t in out.tools_chamadas)
    # Mensagem de redirect contém link oficial
    assert "wa.me/5561981331005" in out.resposta_outbound


def test_phone_invalido_rejeita():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        asyncio.run(processar_mensagem_inbound(
            phone="123", texto="oi", canal="8133",
        ))


def test_texto_vazio_rejeita():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        asyncio.run(processar_mensagem_inbound(
            phone="5561999000000", texto="", canal="8133",
        ))
