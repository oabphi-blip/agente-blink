"""FIX DEFINITIVO bug repetido — pytest que CRIA a app FastAPI.

Por que existe (06/06/2026, task #265):
Bug `_check_admin_secret` inexistente passou pytest local porque a função
nunca era invocada em pytest unitário. Em produção, no primeiro request,
NameError → 500. Esse pytest captura ESSE TIPO de bug ANTES do deploy.

Como funciona:
- Cria settings mínimo com envs dummy
- Chama `create_app(settings)` que registra TODAS as rotas
- Lista as rotas registradas — confirma que esperadas estão lá
- Se qualquer import/decorator/closure quebrar, falha aqui
- Roda em GitHub Actions (CI)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fake_envs(monkeypatch):
    """Envs mínimos pra Settings.load() não quebrar."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("EVOLUTION_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("EVOLUTION_API_KEY", "fake")
    monkeypatch.setenv("EVOLUTION_DEFAULT_INSTANCE", "test")
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("MEDWARE_ENABLED", "0")
    monkeypatch.setenv("WHATSAPP_CLOUD_ENABLED", "0")
    monkeypatch.setenv("KOMMO_ENABLED", "0")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("BLINK_CRON_ENABLED", "0")


class TestAppStartup:
    """Cria a app real. Detecta NameError / ImportError em IMPORT time."""

    def test_create_app_nao_quebra(self, fake_envs):
        """O coração: se algum endpoint usa nome inexistente, quebra aqui."""
        from voice_agent.webhook import create_app
        app = create_app()
        assert app is not None
        # Lista rotas registradas — sanity check
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_endpoints_novos_registrados(self, fake_envs):
        """Confirma que endpoints da task #260/#256 entraram na app."""
        from voice_agent.webhook import create_app
        app = create_app()
        routes = {r.path for r in app.routes}
        # Endpoints novos desta sessão
        esperados = [
            "/admin/funcionamento",
            "/admin/funcionamento/checar-alarmes",
            "/admin/leads-abandonados",
            "/admin/disparar-lead/{lead_id}",
            "/admin/reativar-ia-batch",
        ]
        ausentes = [e for e in esperados if e not in routes]
        assert not ausentes, f"Endpoints ausentes: {ausentes}"

    def test_endpoints_admin_chamaveis_no_test_client(self, fake_envs):
        """Smoke real: usa TestClient pra bater nos endpoints e
        confirmar que NÃO retornam 500 por erro de nome.

        Sem secret → espera 401. Erro de NameError viria como 500.
        """
        from fastapi.testclient import TestClient
        from voice_agent.webhook import create_app
        app = create_app()
        client = TestClient(app)
        # Pega todas rotas /admin/* GET registradas
        endpoints_a_testar = [
            "/admin/funcionamento",
            "/admin/leads-abandonados",
            "/admin/healthz-kommo",
        ]
        crashes = []
        for ep in endpoints_a_testar:
            try:
                r = client.get(ep, headers={})
                # 401 = secret faltando (esperado). 200/422/500 também ok pra
                # detectar — o que NÃO pode é 500 por NameError.
                if r.status_code == 500:
                    body_preview = r.text[:300]
                    crashes.append({
                        "endpoint": ep, "status": 500,
                        "body": body_preview,
                    })
            except Exception as e:  # noqa: BLE001
                crashes.append({"endpoint": ep, "exception": str(e)[:200]})
        assert not crashes, f"Endpoints com 500: {crashes}"

    def test_nenhum_endpoint_admin_duplicado(self, fake_envs):
        """Detecta @app.get + @app.post pra MESMO path com handlers
        diferentes (raro mas já aconteceu)."""
        from voice_agent.webhook import create_app
        from collections import Counter
        app = create_app()
        # Conta path+method
        sigs = []
        for r in app.routes:
            methods = getattr(r, "methods", None) or {"GET"}
            for m in methods:
                if "/admin/" in (r.path or ""):
                    sigs.append((m, r.path))
        contagem = Counter(sigs)
        dups = {k: v for k, v in contagem.items() if v > 1}
        assert not dups, f"Rotas admin duplicadas: {dups}"
