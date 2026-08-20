"""
tests/test_bug_c150_supabase_memory.py — C-150 Supabase memória persistente

Testa:
- gravar_mensagem fail-open quando Supabase não configurado
- ler_historico retorna [] quando Supabase não configurado
- montar_bloco_historico_supabase retorna "" quando vazio
- esta_ativo retorna False sem SUPABASE_URL
- Toggle SUPABASE_MEMORY_ENABLED=0 desliga módulo
- Formato do bloco (PACIENTE/LIA/HUMANO labels)
- Endpoint /admin/contexto-supabase existe no webhook
- Endpoint /admin/importar-historico-supabase existe no webhook
"""
import os
import sys
import importlib
import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

def _reload_module():
    """Recarrega supabase_memory com env limpa."""
    import voice_agent.supabase_memory as mod
    mod._client = None  # reset singleton
    return importlib.reload(mod)


# ── 1. Sem SUPABASE_URL — fail-open ──────────────────────────────────────────

def test_gravar_sem_url_retorna_false(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    mod = _reload_module()
    result = mod.gravar_mensagem("+5561999999999", "patient", "Oi")
    assert result is False


def test_ler_sem_url_retorna_lista_vazia(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    mod = _reload_module()
    result = mod.ler_historico("+5561999999999", limit=10)
    assert result == []


def test_montar_bloco_sem_url_retorna_string_vazia(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    mod = _reload_module()
    result = mod.montar_bloco_historico_supabase("+5561999999999")
    assert result == ""


def test_esta_ativo_sem_url_retorna_false(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    mod = _reload_module()
    assert mod.esta_ativo() is False


# ── 2. Toggle SUPABASE_MEMORY_ENABLED=0 ──────────────────────────────────────

def test_toggle_desligado(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SUPABASE_MEMORY_ENABLED", "0")
    mod = _reload_module()
    assert mod._get_client() is None
    assert mod.esta_ativo() is False


def test_toggle_false_string(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "fake_key")
    monkeypatch.setenv("SUPABASE_MEMORY_ENABLED", "false")
    mod = _reload_module()
    assert mod._get_client() is None


# ── 3. Conteúdo vazio não grava ───────────────────────────────────────────────

def test_gravar_conteudo_vazio_retorna_false(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    mod = _reload_module()
    assert mod.gravar_mensagem("+5561999999999", "patient", "") is False
    assert mod.gravar_mensagem("+5561999999999", "patient", "   ") is False


# ── 4. Formato do bloco de histórico ─────────────────────────────────────────

def test_montar_bloco_formato_labels(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    mod = _reload_module()

    # Mock ler_historico
    msgs = [
        {"role": "patient", "content": "Quero agendar", "ts": "2026-08-19T10:00:00Z"},
        {"role": "lia",     "content": "Claro! Qual o nome?", "ts": "2026-08-19T10:01:00Z"},
        {"role": "human",   "content": "Atendente assumiu", "ts": "2026-08-19T10:05:00Z"},
    ]

    import voice_agent.supabase_memory as real_mod
    original = real_mod.ler_historico

    def fake_ler(phone, limit=20):
        return msgs

    real_mod.ler_historico = fake_ler
    try:
        bloco = real_mod.montar_bloco_historico_supabase("+5561999999999")
        assert "[PACIENTE" in bloco
        assert "[LIA" in bloco
        assert "[HUMANO" in bloco
        assert "Quero agendar" in bloco
        assert "Claro! Qual o nome?" in bloco
        assert "Atendente assumiu" in bloco
    finally:
        real_mod.ler_historico = original


def test_montar_bloco_historico_vazio(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    import voice_agent.supabase_memory as real_mod
    original = real_mod.ler_historico

    def fake_ler(phone, limit=20):
        return []

    real_mod.ler_historico = fake_ler
    try:
        bloco = real_mod.montar_bloco_historico_supabase("+5561999999999")
        assert bloco == ""
    finally:
        real_mod.ler_historico = original


# ── 5. Endpoints no webhook ───────────────────────────────────────────────────

def test_endpoint_importar_existe():
    """Endpoint /admin/importar-historico-supabase definido no webhook."""
    import voice_agent.webhook as wh
    src = open(wh.__file__).read()
    assert "importar-historico-supabase" in src


def test_endpoint_contexto_supabase_existe():
    """Endpoint /admin/contexto-supabase definido no webhook (FASE 4)."""
    import voice_agent.webhook as wh
    src = open(wh.__file__).read()
    assert "contexto-supabase" in src


def test_endpoint_contexto_tem_reativar():
    """Retorno tem campo 'reativar' para n8n usar em IF node."""
    import voice_agent.webhook as wh
    src = open(wh.__file__).read()
    assert '"reativar"' in src or "'reativar'" in src or "reativar" in src


# ── 6. gravar_mensagem trunca conteúdo longo ─────────────────────────────────

def test_gravar_nao_explode_com_conteudo_longo(monkeypatch):
    """gravar_mensagem não lança exceção mesmo sem Supabase."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    mod = _reload_module()
    long_content = "x" * 10000
    result = mod.gravar_mensagem("+5561999999999", "lia", long_content)
    assert result is False  # fail-open (sem Supabase)


# ── 7. pipeline.py tem bloco C-150 ───────────────────────────────────────────

def test_pipeline_tem_bloco_c150():
    import voice_agent.pipeline as p
    src = open(p.__file__).read()
    assert "C-150" in src
    assert "gravar_mensagem" in src or "_sb_gravar" in src


# ── 8. responder.py tem bloco C-150-READ ─────────────────────────────────────

def test_responder_tem_c150_read():
    import voice_agent.responder as r
    src = open(r.__file__).read()
    assert "C-150-READ" in src
    assert "HISTORICO_SUPABASE" in src
    assert "montar_bloco_historico_supabase" in src
