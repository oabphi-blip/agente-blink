"""
Bug C-57 (14/07/2026) — Melissa Vargas Nakatani (lead 10934653).

Dra. Karla escreveu em 15/08/2025 (nota 27722655):
    "DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE, JÁ DESMARCOU ALGUMAS
    VEZES EM CIMA DA HORA E NA ULTIMA VEZ NÃO COMPARECEU E NÃO AVISOU"

Stephany reforçou em 15/06/2026 (nota 28986672):
    "Caso a paciente não compareça no dia agendado, não agendar mais com
    a Dra. Karla a pedido da mesma."

Mesmo assim Lia conversou com paciente em 27/05, 07-08/06, 15/06 e 14/07.

Fix: `voice_agent/bloqueio_clinico.py::detectar_bloqueio_clinico(notas)`
faz regex nas notas humanas. Plugado em `kommo.py::agent_paused_for_lead`
como Regra 3 (permanente, não decai como regra 2 de 30min).
"""

from __future__ import annotations

from voice_agent.bloqueio_clinico import (
    _eh_nota_humana,
    _texto_da_nota,
    detectar_bloqueio_clinico,
    paciente_bloqueado,
)


# ---------- Helpers de teste ----------

def _nota_humana(texto: str, created_by: int = 11132911) -> dict:
    return {"text": texto, "created_by": created_by}


def _nota_bot(texto: str) -> dict:
    """Nota de robô/serviço Kommo — created_by=0."""
    return {"text": texto, "created_by": 0}


# ---------- Caso Melissa REAL ----------

def test_c57_melissa_dra_karla_nao_agendar_mais_essa_paciente():
    """Texto EXATO da nota 27722655 da Dra. Karla em 15/08/2025."""
    notas = [
        _nota_humana(
            "DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE, JÁ DESMARCOU "
            "ALGUMAS VEZES EM CIMA DA HORA E NA ULTIMA VEZ NÃO COMPARECEU "
            "E NÃO AVISOU"
        )
    ]
    resultado = detectar_bloqueio_clinico(notas)
    assert resultado is not None
    assert "não agendar" in resultado.lower() or "nao agendar" in resultado.lower()


def test_c57_melissa_stephany_nao_agendar_mais_com_karla():
    """Texto EXATO da nota 28986672 da Stephany em 15/06/2026."""
    notas = [
        _nota_humana(
            "Caso a paciente não compareça no dia agendado, não agendar "
            "mais com a Dra. Karla a pedido da mesma."
        )
    ]
    resultado = detectar_bloqueio_clinico(notas)
    assert resultado is not None


def test_c57_paciente_bloqueado_wrapper_true():
    notas = [_nota_humana("DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE")]
    assert paciente_bloqueado(notas) is True


# ---------- Variantes que devem BLOQUEAR ----------

def test_c57_variante_paciente_bloqueada():
    notas = [_nota_humana("Paciente bloqueada — agenda somente com autorização")]
    assert paciente_bloqueado(notas) is True


def test_c57_variante_proibido_reagendar():
    notas = [_nota_humana("Proibido reagendar essa paciente")]
    assert paciente_bloqueado(notas) is True


def test_c57_variante_nao_agendar_mais_com_fabricio():
    notas = [_nota_humana("Não agendar mais com Dr. Fabrício por 90 dias")]
    assert paciente_bloqueado(notas) is True


def test_c57_variante_a_pedido_da_medica():
    notas = [
        _nota_humana(
            "A pedido da própria médica, não agendar novos horários."
        )
    ]
    assert paciente_bloqueado(notas) is True


def test_c57_variante_bloquear_agendamento():
    notas = [_nota_humana("bloquear agendamento até rever com Dra. Karla")]
    assert paciente_bloqueado(notas) is True


# ---------- Casos que NÃO devem bloquear ----------

def test_c57_nota_bot_nao_bloqueia():
    """Nota de robô (created_by=0) com texto de bloqueio NÃO bloqueia.
    Evita falso positivo se Lia repetir a frase."""
    notas = [_nota_bot("Vou anotar 'não agendar mais' pra você")]
    assert paciente_bloqueado(notas) is False


def test_c57_paciente_disse_nao_confirmou_nao_bloqueia():
    """Frase branda sem ordem de bloqueio permanente."""
    notas = [_nota_humana("Paciente não confirmou o horário de hoje")]
    assert paciente_bloqueado(notas) is False


def test_c57_paciente_faltou_uma_vez_nao_bloqueia():
    """Faltar 1x não é bloqueio médico."""
    notas = [_nota_humana("Paciente faltou hoje sem avisar")]
    assert paciente_bloqueado(notas) is False


def test_c57_notas_vazias_nao_bloqueia():
    assert paciente_bloqueado([]) is False
    assert paciente_bloqueado(None) is False


def test_c57_nota_sem_texto_nao_bloqueia():
    notas = [{"created_by": 11132911, "text": ""}]
    assert paciente_bloqueado(notas) is False


# ---------- Múltiplas notas ----------

def test_c57_encontra_bloqueio_no_meio_de_muitas_notas():
    """Nota de bloqueio pode estar em meio a várias outras."""
    notas = [
        _nota_bot("Lia (WhatsApp): Olá, bom dia!"),
        _nota_humana("Paciente chegou 15 minutos atrasada"),
        _nota_humana("DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE"),
        _nota_humana("Contato via SMS realizado"),
    ]
    assert paciente_bloqueado(notas) is True


def test_c57_bloqueio_antigo_ainda_vale():
    """Bloqueio de 15/08/2025 ainda deve bloquear em 14/07/2026.
    Regra: não tem decay temporal — vale até desbloqueio manual."""
    notas_recentes = [
        _nota_bot("Lia (WhatsApp): tudo certo pra amanhã?"),
        _nota_bot("Lia (WhatsApp): confirmação recebida"),
    ]
    notas_antigas = [
        _nota_humana("DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE"),
    ]
    # Ordem: antigas primeiro (como vem do Kommo)
    todas = notas_antigas + notas_recentes
    assert paciente_bloqueado(todas) is True


# ---------- Helpers internos ----------

def test_eh_nota_humana():
    assert _eh_nota_humana({"created_by": 11132911}) is True
    assert _eh_nota_humana({"created_by": 0}) is False
    assert _eh_nota_humana({}) is False
    assert _eh_nota_humana("string") is False  # type: ignore


def test_texto_da_nota():
    assert _texto_da_nota({"text": "abc"}) == "abc"
    assert _texto_da_nota({}) == ""
    assert _texto_da_nota({"text": None}) == ""


# ---------- Integração — plug em agent_paused_for_lead ----------

def test_c57_plug_agent_paused_for_lead_pega_bloqueio():
    """Confirma que kommo.py::agent_paused_for_lead usa
    detectar_bloqueio_clinico como Regra 3."""
    from pathlib import Path
    kommo_py = (
        Path(__file__).resolve().parent.parent / "voice_agent" / "kommo.py"
    ).read_text(encoding="utf-8")
    # Deve importar e chamar detectar_bloqueio_clinico
    assert "detectar_bloqueio_clinico" in kommo_py, (
        "kommo.py deve importar/chamar detectar_bloqueio_clinico"
    )
    assert '"bloqueio-clinico"' in kommo_py or "'bloqueio-clinico'" in kommo_py, (
        "Regra 3 deve retornar 'bloqueio-clinico' como motivo"
    )
