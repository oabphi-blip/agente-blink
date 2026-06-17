"""Bug C-38 — Janela default Medware 90→21 dias (Fábio 17/06/2026).

Origem: diagnóstico LOG_DIAGNOSTICO_MEDWARE_CPU_17-06-2026.md.
Janela 7d responde ~5s, janela 90d estoura ReadTimeout na VM Light.
Lead 24113652 (Fábio Philipe testando): Lia caiu em filtro C-30A
('dificuldade técnica + encaminhar humano') porque ctx.agenda=[]
após Medware timeout na janela 90d.

Fix: voice_agent/medware.py::horarios_para_agente:
- dias default 90 → 21
- env MEDWARE_DIAS_DEFAULT override (1-90)
- janela_fonte agora reflete o número real (default_21d, etc.)
"""
import os
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def _limpar_env(monkeypatch):
    monkeypatch.delenv("MEDWARE_DIAS_DEFAULT", raising=False)
    yield


def _make_client(slots_retornados=None):
    """Cria MedwareClient mockado pra inspecionar params do request."""
    from voice_agent import medware as _m
    cli = _m.MedwareClient.__new__(_m.MedwareClient)
    cli.ultimo_req_horarios = {}
    cli.listar_horarios_livres = MagicMock(return_value=slots_retornados or [])
    return cli


def _params_chamada(cli):
    """Extrai (data_inicio, data_fim) do último listar_horarios_livres."""
    args, kwargs = cli.listar_horarios_livres.call_args
    return kwargs.get("data_inicio"), kwargs.get("data_fim")


def _delta_dias(ini_br: str, fim_br: str) -> int:
    """Conta dias entre 2 datas no formato dd/mm/YYYY."""
    from datetime import datetime
    ini = datetime.strptime(ini_br, "%d/%m/%Y")
    fim = datetime.strptime(fim_br, "%d/%m/%Y")
    return (fim - ini).days


# ─────────────────────────────────────────────────────────────────────────
# 1. Default é 21 dias, NÃO 90
# ─────────────────────────────────────────────────────────────────────────


def test_default_eh_21_dias_nao_90():
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    assert ini is not None and fim is not None
    delta = _delta_dias(ini, fim)
    # 21 dias (não 90). Pode variar 20-22 por causa do amanhã/hoje.
    assert 20 <= delta <= 22, f"Esperado ~21d, recebido {delta}d"


def test_janela_fonte_reflete_21d():
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    assert cli.ultimo_req_horarios.get("janela_fonte") == "default_21d"


# ─────────────────────────────────────────────────────────────────────────
# 2. Env MEDWARE_DIAS_DEFAULT override (rollback path)
# ─────────────────────────────────────────────────────────────────────────


def test_env_override_para_30_dias(monkeypatch):
    monkeypatch.setenv("MEDWARE_DIAS_DEFAULT", "30")
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 29 <= delta <= 31, f"Esperado ~30d com env, recebido {delta}d"


def test_env_override_volta_para_90_se_provedor_consertar(monkeypatch):
    monkeypatch.setenv("MEDWARE_DIAS_DEFAULT", "90")
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 89 <= delta <= 91, f"Esperado ~90d com env, recebido {delta}d"


def test_env_invalida_zero_cai_pro_default_21(monkeypatch):
    monkeypatch.setenv("MEDWARE_DIAS_DEFAULT", "0")
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 20 <= delta <= 22


def test_env_invalida_acima_90_cai_pro_default_21(monkeypatch):
    monkeypatch.setenv("MEDWARE_DIAS_DEFAULT", "120")
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 20 <= delta <= 22


def test_env_string_lixo_cai_pro_default_21(monkeypatch):
    monkeypatch.setenv("MEDWARE_DIAS_DEFAULT", "abc")
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente("Dra. Karla Delalibera", "Asa Norte")
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 20 <= delta <= 22


# ─────────────────────────────────────────────────────────────────────────
# 3. data_inicio/data_fim explícitos vencem o default (compat C-30)
# ─────────────────────────────────────────────────────────────────────────


def test_preferencia_paciente_vence_default():
    from datetime import date
    cli = _make_client([{"data": "2026-07-07", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente(
        "Dra. Karla Delalibera", "Asa Norte",
        data_inicio=date(2026, 7, 7), data_fim=date(2026, 7, 15),
    )
    ini, fim = _params_chamada(cli)
    assert ini == "07/07/2026"
    assert fim == "15/07/2026"
    assert cli.ultimo_req_horarios.get("janela_fonte") == "preferencia"


# ─────────────────────────────────────────────────────────────────────────
# 4. Param dias= explícito ainda funciona (compat retroativa)
# ─────────────────────────────────────────────────────────────────────────


def test_param_dias_explicito_ainda_funciona():
    cli = _make_client([{"data": "2026-06-18", "hora": "09:00",
                          "codAgenda": 1}])
    cli.horarios_para_agente(
        "Dra. Karla Delalibera", "Asa Norte", dias=14,
    )
    ini, fim = _params_chamada(cli)
    delta = _delta_dias(ini, fim)
    assert 13 <= delta <= 15, f"Esperado ~14d, recebido {delta}d"
