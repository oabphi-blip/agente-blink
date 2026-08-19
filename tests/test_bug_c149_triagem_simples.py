"""Pytest C-149 — Triagem Simples (19/08/2026)"""
import os
import pytest

os.environ.setdefault("TRIAGEM_SIMPLES_ATIVADA", "1")

from voice_agent.triagem_simples import processar, _proxima_pergunta, _extrair_do_inbound, _montar_resumo


def _ctx(known=None):
    return {"known": known or {}}


# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

def test_toggle_off():
    os.environ["TRIAGEM_SIMPLES_ATIVADA"] = "0"
    r = processar(1, "oi", _ctx())
    assert r.get("ativo") is False
    os.environ["TRIAGEM_SIMPLES_ATIVADA"] = "1"


def test_toggle_on():
    r = processar(1, "oi", _ctx())
    assert r.get("ativo") is True


# ---------------------------------------------------------------------------
# Sequência de perguntas
# ---------------------------------------------------------------------------

def test_primeira_pergunta_quantidade():
    r = processar(1, "oi", _ctx())
    assert "quantas" in r["resposta"].lower() or "pessoa" in r["resposta"].lower()
    assert r["transferir"] is False


def test_segunda_pergunta_convenio():
    known = {"quantidade_agendamentos": "1"}
    r = processar(2, "só eu", _ctx(known))
    assert "conv" in r["resposta"].lower() or "plano" in r["resposta"].lower()


def test_terceira_pergunta_nome():
    known = {"quantidade_agendamentos": "1", "convenio": "Bacen"}
    r = processar(3, "bacen", _ctx(known))
    assert "nome" in r["resposta"].lower()


def test_quarta_pergunta_data_nasc():
    known = {"quantidade_agendamentos": "1", "convenio": "Bacen", "nome_paciente": "Maria Silva"}
    r = processar(4, "Maria Silva", _ctx(known))
    assert "nascimento" in r["resposta"].lower() or "nasc" in r["resposta"].lower()


def test_quinta_pergunta_motivo():
    known = {
        "quantidade_agendamentos": "1",
        "convenio": "Bacen",
        "nome_paciente": "Maria Silva",
        "data_nasc": "10/05/1990",
    }
    r = processar(5, "10/05/1990", _ctx(known))
    assert "motivo" in r["resposta"].lower()


# ---------------------------------------------------------------------------
# Transferência ao completar
# ---------------------------------------------------------------------------

def test_transfere_quando_completo():
    known = {
        "quantidade_agendamentos": "1",
        "convenio": "Bacen",
        "nome_paciente": "Maria Silva",
        "data_nasc": "10/05/1990",
        "motivo_consulta": "rotina",
    }
    r = processar(6, "rotina", _ctx(known))
    assert r["transferir"] is True
    assert r["ativo"] is True
    assert "Maria Silva" in r["resposta"]
    assert "equipe" in r["resposta"].lower()


# ---------------------------------------------------------------------------
# Extração de dados do inbound
# ---------------------------------------------------------------------------

def test_extrai_quantidade_numerica():
    achados = _extrair_do_inbound("2", _ctx())
    assert achados.get("quantidade_agendamentos") == "2"


def test_extrai_quantidade_por_extenso():
    achados = _extrair_do_inbound("dois", _ctx())
    assert achados.get("quantidade_agendamentos") == "2"


def test_extrai_sem_convenio():
    achados = _extrair_do_inbound("não tenho convênio", _ctx())
    assert achados.get("sem_convenio") is True


def test_extrai_data_nasc():
    achados = _extrair_do_inbound("15/03/1985", _ctx())
    assert achados.get("data_nasc") == "15/03/1985"


def test_extrai_nome_duas_palavras():
    achados = _extrair_do_inbound("João Silva", _ctx())
    assert achados.get("nome_paciente") == "João Silva"


# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------

def test_resumo_contem_todos_campos():
    known = {
        "quantidade_agendamentos": "1",
        "convenio": "Saúde Caixa",
        "nome_paciente": "Ana Souza",
        "data_nasc": "20/08/2000",
        "motivo_consulta": "retorno",
    }
    resumo = _montar_resumo(known)
    assert "Ana Souza" in resumo
    assert "20/08/2000" in resumo
    assert "Saúde Caixa" in resumo
    assert "retorno" in resumo


def test_resumo_sem_convenio():
    known = {
        "quantidade_agendamentos": "1",
        "sem_convenio": True,
        "convenio": "Sem convênio",
        "nome_paciente": "Pedro Lima",
        "data_nasc": "01/01/1980",
        "motivo_consulta": "catarata",
    }
    resumo = _montar_resumo(known)
    assert "Sem convênio" in resumo


# ---------------------------------------------------------------------------
# Redis já concluído → não interferir
# ---------------------------------------------------------------------------

def test_ja_concluido_redis_nao_interfere():
    class FakeRedis:
        def get(self, key):
            if "triagem_concluida" in key:
                return b"1"
            return None
        def setex(self, *a, **kw):
            pass

    known = {
        "quantidade_agendamentos": "1",
        "convenio": "Bacen",
        "nome_paciente": "Maria Silva",
        "data_nasc": "10/05/1990",
        "motivo_consulta": "rotina",
    }
    r = processar(99, "qualquer coisa", _ctx(known), redis_client=FakeRedis())
    assert r.get("ativo") is False
