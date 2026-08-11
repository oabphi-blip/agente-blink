"""Blindagem do bug Priscila lead 24055629 — 01/06/2026 12:30.

Lia escreveu "9h de sexta-feira (06/06)" — 06/06/2026 é SÁBADO.
Paciente questionou: "Dia 5, sexta ou 6, sábado?".

Dois filtros precisam pegar:

  1. `_viola_dia_semana` — divergência DIA-SEMANA × DATA. O regex original
     não pegava "sexta-feira (06/06)" porque a classe de separadores
     entre o dia e a data NÃO incluía '('. Agora inclui.

  2. `_viola_oferta_em_dia_nao_atendido` — Dra. Karla Delalibera não
     atende sábado. Mesmo que o regex de cima tivesse falhado, esse
     filtro pega a oferta de sábado pra Karla.

Origem: Fábio 03/06/2026.
"""
from voice_agent.responder import (
    _viola_dia_semana,
    _viola_oferta_em_dia_nao_atendido,
)


# ---------------------------------------------------------------------------
# Caso real Priscila (regressão direta)
# ---------------------------------------------------------------------------

def test_priscila_sexta_feira_06_06_2026_eh_sabado():
    """06/06/2026 é sábado. Lia escreveu 'sexta-feira (06/06)' — viola."""
    txt = (
        "Ótimo! Você prefere 9h de amanhã (terça-feira, 02/06) ou "
        "9h de sexta-feira (06/06)?"
    )
    res = _viola_dia_semana(txt)
    assert res is not None
    dia_falado, data_str, dia_real = res
    # A primeira divergência detectada deve ser 06/06 (sexta vs sábado)
    assert "sexta" in dia_falado
    assert "sábado" in dia_real
    assert "06/06" in data_str


def test_priscila_terca_02_06_2026_eh_terca_real():
    """Sanity: 02/06/2026 é mesmo terça. Não deve violar isoladamente."""
    txt = "9h de amanhã (terça-feira, 02/06/2026)"
    res = _viola_dia_semana(txt)
    assert res is None


def test_priscila_sabado_oferta_para_karla_eh_violacao():
    """Dra. Karla não atende sábado. 06/06/2026 é sábado."""
    txt = "Posso te encaixar em 9h de sábado, 06/06/2026"
    ctx = {"medico": "Dra. Karla Delalibera"}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is not None
    medico_norm, data_str, dia_real = res
    assert medico_norm == "karla"
    assert "sábado" in dia_real
    assert "06/06/2026" in data_str


def test_priscila_domingo_oferta_para_karla_eh_violacao():
    """07/06/2026 é domingo. Karla não atende domingo."""
    txt = "Tenho domingo, 07/06/2026 às 10h"
    ctx = {"medico": "Dra. Karla Delalibera"}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is not None


def test_quarta_feira_para_karla_NAO_eh_violacao():
    """Karla atende quarta. 03/06/2026 é quarta."""
    txt = "Tenho quarta-feira 03/06/2026 às 9h"
    ctx = {"medico": "Dra. Karla Delalibera"}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is None


# ---------------------------------------------------------------------------
# Variantes de formato que o regex original NÃO pegava
# ---------------------------------------------------------------------------

def test_formato_parenteses_sem_ano_eh_detectado():
    """'(06/06)' sem ano — assume ano corrente."""
    txt = "sexta-feira (06/06)"
    res = _viola_dia_semana(txt)
    assert res is not None


def test_formato_parenteses_com_ano_2_digitos():
    """'(06/06/26)' — 26 expande pra 2026."""
    txt = "sexta-feira (06/06/26)"
    res = _viola_dia_semana(txt)
    assert res is not None  # 06/06/2026 é sábado


def test_formato_colchetes_eh_detectado():
    """Variante com colchetes [DD/MM]."""
    txt = "sexta [06/06]"
    res = _viola_dia_semana(txt)
    assert res is not None


def test_formato_classico_virgula_continua_funcionando():
    """Regressão do regex original — 'terça-feira, 03/06' (formato Aurora)."""
    # 03/06/2026 é quarta — então "terça-feira, 03/06" viola
    txt = "Tenho terça-feira, 03/06 às 9h"
    res = _viola_dia_semana(txt)
    assert res is not None


# ---------------------------------------------------------------------------
# Edge cases — datas inválidas
# ---------------------------------------------------------------------------

def test_data_invalida_31_02_eh_violacao():
    """31/02 não existe — conta como violação."""
    txt = "terça (31/02)"
    res = _viola_dia_semana(txt)
    assert res is not None


def test_medico_desconhecido_nao_bloqueia():
    """Se ctx.medico vier vazio ou desconhecido, não bloqueia (evita FP)."""
    txt = "sábado, 06/06/2026"
    ctx = {"medico": ""}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is None
    ctx2 = {"medico": "Dr. X Y Z"}
    res2 = _viola_oferta_em_dia_nao_atendido(txt, ctx2)
    assert res2 is None


# ---------------------------------------------------------------------------
# Fabrício atende ter+qui — outros dias violam
# ---------------------------------------------------------------------------

def test_fabricio_segunda_eh_violacao():
    """Fabrício atende ter+qui. 01/06/2026 é segunda → viola."""
    txt = "Posso ofertar segunda-feira 01/06/2026 às 14h"
    ctx = {"medico": "Dr. Fabrício Freitas"}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is not None


def test_fabricio_terca_NAO_eh_violacao():
    """Fabrício atende terça. 02/06/2026 é terça → OK."""
    txt = "Tenho terça-feira 02/06/2026 às 14h"
    ctx = {"medico": "Dr. Fabrício Freitas"}
    res = _viola_oferta_em_dia_nao_atendido(txt, ctx)
    assert res is None
