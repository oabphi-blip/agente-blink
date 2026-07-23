"""Kill-switch AGENDA_SUSPENSA (Fábio 22/07/2026).

Enquanto AGENDA_SUSPENSA=1, a Lia não apresenta disponibilidade de agenda
(estava com muitos erros): no momento de agendar, faz handoff pra equipe
humana confirmar o horário (desativa IA + move pra 1-ATENDIMENTO HUMANO).
"""
from voice_agent.pipeline import (
    _agenda_suspensa_ativa,
    _texto_pede_agendamento,
)


def test_flag_desligada_por_default(monkeypatch):
    monkeypatch.delenv("AGENDA_SUSPENSA", raising=False)
    assert _agenda_suspensa_ativa() is False


def test_flag_ligada_varios_valores(monkeypatch):
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("AGENDA_SUSPENSA", v)
        assert _agenda_suspensa_ativa() is True


def test_flag_valor_invalido_fica_off(monkeypatch):
    monkeypatch.setenv("AGENDA_SUSPENSA", "0")
    assert _agenda_suspensa_ativa() is False
    monkeypatch.setenv("AGENDA_SUSPENSA", "nao")
    assert _agenda_suspensa_ativa() is False


def test_pede_agendamento_detecta():
    assert _texto_pede_agendamento("queria ver os horários")
    assert _texto_pede_agendamento("tem vaga essa semana?")
    assert _texto_pede_agendamento("quero agendar")
    assert _texto_pede_agendamento("qual a disponibilidade?")
    assert _texto_pede_agendamento("pode marcar pra mim")


def test_pede_agendamento_negativo():
    assert not _texto_pede_agendamento("bom dia")
    assert not _texto_pede_agendamento("obrigada!")
    assert not _texto_pede_agendamento("")
    assert not _texto_pede_agendamento(None)
