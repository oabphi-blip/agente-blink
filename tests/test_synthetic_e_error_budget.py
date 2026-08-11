"""Pytest da sprint SRE 18/06 — synthetic_users (100 cenários) +
error_budget (alertas SLO).

12 cenários:
  1. GERAR_CENARIOS_100 retorna exatamente 100 cenários com chaves obrigatórias
  2. executar_cenario valida must_contain
  3. executar_cenario valida must_not_contain (frase Juliene = falha)
  4. executar_todos_cenarios_paralelo agrega corretamente
  5. error_budget detecta violação hallucination
  6. error_budget detecta violação synthetic_pass_rate
  7. gerar_alerta_slack formata mensagem com emoji e link
  8. disparar_alerta_se_necessario dedup por hora via Redis
  9. disparar_alerta_se_necessario toggle ERROR_BUDGET_ALERTS_ENABLED=0
 10. Worker synthetic respeita SYNTHETIC_USERS_ENABLED=0
 11. Alertas Slack SÓ disparados se houver violations
 12. usar_simulate_inbound_default mocka requests.get sem bater rede
"""
from __future__ import annotations

import os
import sys
from typing import Any
from unittest import mock

import pytest

# Garante import a partir do voice_agent local
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from voice_agent import error_budget as eb  # noqa: E402
from voice_agent import synthetic_users as su  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: agent_callable mockado (não bate na Anthropic nem na Easypanel)
# ---------------------------------------------------------------------------

class FakeAgent:
    """Agent fake — retorna respostas controladas por cenário.nome."""

    def __init__(self, mapeamento: dict[str, dict] | None = None,
                 default_answer: str = "Olá! Sou a Lia da Blink. Pode me dizer seu nome?",
                 default_tools: list[str] | None = None):
        self.mapeamento = mapeamento or {}
        self.default_answer = default_answer
        self.default_tools = default_tools or []
        self.chamadas: list[dict] = []

    def __call__(self, cenario: dict) -> dict:
        self.chamadas.append(cenario)
        nome = cenario.get("nome") or ""
        if nome in self.mapeamento:
            base = {
                "ok": True, "answer": self.default_answer,
                "tools_chamadas": self.default_tools,
            }
            base.update(self.mapeamento[nome])
            return base
        return {
            "ok": True,
            "answer": self.default_answer,
            "tools_chamadas": list(self.default_tools),
        }


class FakeRedis:
    def __init__(self):
        self.store: dict[str, Any] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.store[k] = v


# ---------------------------------------------------------------------------
# 1. GERAR_CENARIOS_100 — exatamente 100 com chaves obrigatórias
# ---------------------------------------------------------------------------

def test_gerar_cenarios_100_total_e_estrutura():
    cenarios = su.GERAR_CENARIOS_100()
    assert len(cenarios) == 100, f"esperava 100, deu {len(cenarios)}"

    chaves_obrig = {"nome", "persona", "inputs", "must_contain",
                    "must_not_contain", "must_chamar_tool"}
    nomes_vistos = set()
    for c in cenarios:
        faltam = chaves_obrig - set(c.keys())
        assert not faltam, f"cenário {c.get('nome')} sem chaves: {faltam}"
        assert isinstance(c["inputs"], list) and len(c["inputs"]) >= 1, \
            f"cenário {c['nome']} sem inputs"
        assert c["nome"] not in nomes_vistos, \
            f"nome duplicado: {c['nome']}"
        nomes_vistos.add(c["nome"])

    # Cobertura: cada categoria presente
    prefixos = {n.split("-", 1)[0] for n in nomes_vistos}
    assert "feliz" in prefixos
    assert "borda" in prefixos
    assert "adv" in prefixos
    assert "risco" in prefixos
    assert "hist" in prefixos


# ---------------------------------------------------------------------------
# 2. executar_cenario valida must_contain
# ---------------------------------------------------------------------------

def test_executar_cenario_must_contain_passa():
    cenario = {
        "nome": "teste-mc-ok",
        "persona": "smoke",
        "inputs": ["oi"],
        "must_contain": [r"\bblink\b"],
        "must_not_contain": [],
        "must_chamar_tool": None,
    }
    agent = FakeAgent(default_answer="Olá, aqui é a Lia da Blink Oftalmologia!")
    res = su.executar_cenario(cenario, agent_callable=agent)
    assert res["ok"] is True
    assert res["falhas"] == []


def test_executar_cenario_must_contain_falha():
    cenario = {
        "nome": "teste-mc-fail",
        "persona": "smoke",
        "inputs": ["oi"],
        "must_contain": [r"medware\s+slot\s+especifico"],
        "must_not_contain": [],
        "must_chamar_tool": None,
    }
    agent = FakeAgent(default_answer="Olá, sou a Lia.")
    res = su.executar_cenario(cenario, agent_callable=agent)
    assert res["ok"] is False
    assert any("must_contain MISS" in f for f in res["falhas"])


# ---------------------------------------------------------------------------
# 3. executar_cenario detecta must_not_contain (frase Juliene)
# ---------------------------------------------------------------------------

def test_executar_cenario_frase_juliene_bloqueada():
    cenario = {
        "nome": "teste-juliene",
        "persona": "regressão Juliene",
        "inputs": ["prefiro segunda manhã"],
        "must_contain": [],
        "must_not_contain": [
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
        ],
        "must_chamar_tool": None,
    }
    agent = FakeAgent(default_answer=(
        "Tudo bem! Vou registrar sua preferência aqui e nossa equipe finaliza."
    ))
    res = su.executar_cenario(cenario, agent_callable=agent)
    assert res["ok"] is False
    assert any("must_not_contain HIT" in f for f in res["falhas"])


# ---------------------------------------------------------------------------
# 4. executar_todos_cenarios_paralelo agrega corretamente
# ---------------------------------------------------------------------------

def test_executar_todos_paralelo_agrega():
    # Agent que sempre dá resposta neutra — passa nos 100 (não tem
    # must_contain em quase ninguém, e a resposta não contém proibidas)
    agent = FakeAgent(
        default_answer=(
            "Olá! Aqui é a Lia da Blink Oftalmologia. Como posso ajudar? "
            "Estamos em horário de urgência total se for emergência, "
            "podemos te atender hoje no pronto-socorro mais próximo."
        ),
    )
    rel = su.executar_todos_cenarios_paralelo(
        max_workers=8, agent_callable=agent,
    )
    assert rel["total"] == 100
    assert rel["ok"] + rel["falhou"] == 100
    assert 0.0 <= rel["taxa"] <= 1.0
    assert "duracao_ms" in rel
    assert isinstance(rel["falhas_detalhadas"], list)


# ---------------------------------------------------------------------------
# 5. error_budget detecta violação hallucination (menor é melhor)
# ---------------------------------------------------------------------------

def test_error_budget_hallucination_estoura():
    # alvo hallucination = 0.01. Se atual=0.05, burn = 5.0 → critical
    slos = {"hallucination_rate": 0.05}
    viols = eb.verificar_burn(slos)
    assert len(viols) == 1
    v = viols[0]
    assert v["metrica"] == "hallucination_rate"
    assert v["severidade"] == "critical"
    assert v["burn_rate"] >= 1.0


# ---------------------------------------------------------------------------
# 6. error_budget detecta violação synthetic_pass_rate (maior é melhor)
# ---------------------------------------------------------------------------

def test_error_budget_synthetic_estoura():
    # alvo 0.95. Atual=0.80 → budget=0.05, consumido=0.20, burn=4.0
    slos = {"synthetic_pass_rate": 0.80}
    viols = eb.verificar_burn(slos)
    assert len(viols) == 1
    v = viols[0]
    assert v["metrica"] == "synthetic_pass_rate"
    assert v["severidade"] == "critical"
    assert v["burn_rate"] >= 1.0


def test_error_budget_synthetic_ok_nao_violation():
    slos = {"synthetic_pass_rate": 0.99}
    assert eb.verificar_burn(slos) == []


# ---------------------------------------------------------------------------
# 7. gerar_alerta_slack formata com emoji + link
# ---------------------------------------------------------------------------

def test_gerar_alerta_slack_formata():
    violations = [
        {"metrica": "hallucination_rate", "alvo": 0.01, "atual": 0.05,
         "burn_rate": 5.0, "severidade": "critical"},
        {"metrica": "synthetic_pass_rate", "alvo": 0.95, "atual": 0.80,
         "burn_rate": 4.0, "severidade": "critical"},
    ]
    msg = eb.gerar_alerta_slack(violations)
    assert ":rotating_light:" in msg
    assert "Error Budget" in msg
    assert "hallucination_rate" in msg
    assert "synthetic_pass_rate" in msg
    assert "/admin/slo" in msg


def test_gerar_alerta_slack_vazio_se_sem_violations():
    assert eb.gerar_alerta_slack([]) == ""


# ---------------------------------------------------------------------------
# 8. dedup por hora via Redis
# ---------------------------------------------------------------------------

def test_dedup_redis_evita_spam():
    redis_fake = FakeRedis()
    slos = {"hallucination_rate": 0.10}

    with mock.patch.dict(os.environ, {
        "ERROR_BUDGET_ALERTS_ENABLED": "1",
        "SLACK_WEBHOOK_ALERTAS_URL": "https://hooks.slack.com/fake",
    }):
        http_calls = []

        class FakeClient:
            def post(self, url, json=None):
                http_calls.append({"url": url, "json": json})

        # Primeira chamada — posta
        res1 = eb.disparar_alerta_se_necessario(
            redis_client=redis_fake, slos_atuais=slos,
            http_client=FakeClient(),
        )
        assert res1["enviou"] is True
        assert len(http_calls) == 1

        # Segunda chamada na mesma hora — dedup hit
        res2 = eb.disparar_alerta_se_necessario(
            redis_client=redis_fake, slos_atuais=slos,
            http_client=FakeClient(),
        )
        assert res2["enviou"] is False
        assert res2["motivo"] == "dedup_hit"


# ---------------------------------------------------------------------------
# 9. Toggle ERROR_BUDGET_ALERTS_ENABLED=0 desliga
# ---------------------------------------------------------------------------

def test_toggle_alerts_desligado():
    with mock.patch.dict(os.environ, {
        "ERROR_BUDGET_ALERTS_ENABLED": "0",
        "SLACK_WEBHOOK_ALERTAS_URL": "https://hooks.slack.com/fake",
    }):
        res = eb.disparar_alerta_se_necessario(
            slos_atuais={"hallucination_rate": 0.99},
        )
        assert res["enviou"] is False
        assert res["motivo"] == "disabled"


# ---------------------------------------------------------------------------
# 10. Worker synthetic respeita toggle (lógica)
# ---------------------------------------------------------------------------

def test_synthetic_toggle_via_env():
    # Importa o helper do cron_interno via funcao privada
    from voice_agent import cron_interno as ci

    with mock.patch.dict(os.environ, {"SYNTHETIC_USERS_ENABLED": "1"}):
        assert ci._synthetic_users_enabled() is True

    with mock.patch.dict(os.environ, {"SYNTHETIC_USERS_ENABLED": "0"}):
        assert ci._synthetic_users_enabled() is False

    # Default = OFF
    novo_env = {k: v for k, v in os.environ.items()
                if k != "SYNTHETIC_USERS_ENABLED"}
    with mock.patch.dict(os.environ, novo_env, clear=True):
        assert ci._synthetic_users_enabled() is False


def test_error_budget_toggle_default_on():
    from voice_agent import cron_interno as ci
    novo_env = {k: v for k, v in os.environ.items()
                if k != "ERROR_BUDGET_ALERTS_ENABLED"}
    with mock.patch.dict(os.environ, novo_env, clear=True):
        assert ci._error_budget_alerts_enabled() is True


# ---------------------------------------------------------------------------
# 11. Alertas Slack só pra violations (no_violation → no_post)
# ---------------------------------------------------------------------------

def test_sem_violations_nao_posta():
    redis_fake = FakeRedis()
    with mock.patch.dict(os.environ, {
        "ERROR_BUDGET_ALERTS_ENABLED": "1",
        "SLACK_WEBHOOK_ALERTAS_URL": "https://hooks.slack.com/fake",
    }):
        slos = {
            "hallucination_rate": 0.001,
            "synthetic_pass_rate": 1.0,
            "agent_uptime": 1.0, "delivery_rate": 1.0,
        }
        http_calls = []

        class FakeClient:
            def post(self, url, json=None):
                http_calls.append({"url": url, "json": json})

        res = eb.disparar_alerta_se_necessario(
            redis_client=redis_fake, slos_atuais=slos,
            http_client=FakeClient(),
        )
        assert res["enviou"] is False
        assert res["motivo"] == "no_violation"
        assert http_calls == []


# ---------------------------------------------------------------------------
# 12. usar_simulate_inbound_default mocka HTTP sem bater rede
# ---------------------------------------------------------------------------

def test_usar_simulate_inbound_default_mockado():
    """Mocka httpx.get usado pelo wrapper default."""
    fake_resp = mock.MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "answer": "Olá! Sou a Lia. Posso te ajudar?",
        "ok": True,
    }
    with mock.patch.object(su.httpx, "get", return_value=fake_resp) as patched:
        agent = su.usar_simulate_inbound_default()
        cenario = {
            "nome": "smoke",
            "persona": "p",
            "phone": "5561988000999",
            "inputs": ["oi"],
            "must_contain": [], "must_not_contain": [],
        }
        out = agent(cenario)
        assert out["ok"] is True
        assert "Lia" in out["answer"]
        assert patched.call_count == 1
        call_args = patched.call_args
        assert "/admin/simulate-inbound" in call_args[0][0]


def test_usar_simulate_inbound_http_error_marca_falha():
    fake_resp = mock.MagicMock()
    fake_resp.status_code = 500
    fake_resp.text = "boom"
    with mock.patch.object(su.httpx, "get", return_value=fake_resp):
        agent = su.usar_simulate_inbound_default()
        cenario = {"nome": "x", "phone": "5561988000000",
                   "inputs": ["oi"], "must_contain": [],
                   "must_not_contain": []}
        out = agent(cenario)
        assert out["ok"] is False
        assert "HTTP 500" in (out.get("error") or "")
