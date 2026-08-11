"""Testes do parser de janela de preferência (Bug C-30, lead Sofia 24158652).

Garante que a preferência textual do paciente vira uma janela de datas
específica para o request do Medware — e que entradas ambíguas caem em None
(default 90d), nunca regredindo.
"""
from datetime import date

import pytest

from voice_agent.janela_preferencia import parse_janela_preferencia

# "Hoje" fixo pra testes determinísticos (mesma data do bug Sofia).
HOJE = date(2026, 6, 16)


class TestCasoSofia:
    def test_entre_7_e_15_de_julho(self):
        di, df = parse_janela_preferencia("Entre 7 e 15 de julho", HOJE)
        assert di == date(2026, 7, 7)
        assert df == date(2026, 7, 15)

    def test_entre_7_e_15_de_julho_com_parentetico(self):
        di, df = parse_janela_preferencia(
            "Entre 7 e 15 de julho (aguardando disponibilidade)", HOJE
        )
        assert (di, df) == (date(2026, 7, 7), date(2026, 7, 15))


class TestRangesPorExtenso:
    def test_de_a_de_mes(self):
        assert parse_janela_preferencia("de 10 a 12 de agosto", HOJE) == (
            date(2026, 8, 10), date(2026, 8, 12),
        )

    def test_x_a_y_de_mes(self):
        assert parse_janela_preferencia("20 a 25 de setembro", HOJE) == (
            date(2026, 9, 20), date(2026, 9, 25),
        )

    def test_ordem_invertida_normaliza(self):
        # "15 a 7 de julho" — clamp ordena
        assert parse_janela_preferencia("15 a 7 de julho", HOJE) == (
            date(2026, 7, 7), date(2026, 7, 15),
        )

    def test_marco_sem_acento(self):
        assert parse_janela_preferencia("entre 3 e 5 de março", HOJE) == (
            date(2027, 3, 3), date(2027, 3, 5),
        )  # março já passou em 2026 → 2027


class TestRangesNumericos:
    def test_entre_datas_barra(self):
        assert parse_janela_preferencia("entre 07/07 e 15/07", HOJE) == (
            date(2026, 7, 7), date(2026, 7, 15),
        )

    def test_de_a_barra_com_ano(self):
        assert parse_janela_preferencia("de 07/07/2026 a 15/07/2026", HOJE) == (
            date(2026, 7, 7), date(2026, 7, 15),
        )


class TestSemana:
    def test_semana_de_data(self):
        assert parse_janela_preferencia("semana de 29/06", HOJE) == (
            date(2026, 6, 29), date(2026, 7, 5),
        )

    def test_semana_de_data_por_extenso(self):
        assert parse_janela_preferencia("semana de 7 de julho", HOJE) == (
            date(2026, 7, 7), date(2026, 7, 13),
        )


class TestDataUnica:
    def test_dia_barra(self):
        assert parse_janela_preferencia("dia 10/07", HOJE) == (
            date(2026, 7, 10), date(2026, 7, 10),
        )

    def test_data_por_extenso(self):
        assert parse_janela_preferencia("10 de julho", HOJE) == (
            date(2026, 7, 10), date(2026, 7, 10),
        )


class TestMesInteiro:
    def test_em_julho(self):
        assert parse_janela_preferencia("em julho", HOJE) == (
            date(2026, 7, 1), date(2026, 7, 31),
        )

    def test_mes_de_agosto(self):
        di, df = parse_janela_preferencia("no mes de agosto", HOJE)
        assert di == date(2026, 8, 1)
        assert df == date(2026, 8, 31)


class TestRelativas:
    def test_proxima_semana(self):
        di, df = parse_janela_preferencia("próxima semana", HOJE)
        # 16/06/2026 é terça → próxima segunda = 22/06
        assert di == date(2026, 6, 22)
        assert df == date(2026, 6, 28)

    def test_proximo_mes(self):
        assert parse_janela_preferencia("mês que vem", HOJE) == (
            date(2026, 7, 1), date(2026, 7, 31),
        )


class TestClampEInferencia:
    def test_inferencia_ano_mes_passado(self):
        # maio já passou em 16/06/2026 → assume 2027
        di, df = parse_janela_preferencia("10 de maio", HOJE)
        assert di.year == 2027

    def test_data_no_passado_proximo_ano_quando_unica(self):
        di, df = parse_janela_preferencia("dia 01/01", HOJE)
        assert di == date(2027, 1, 1)

    def test_clamp_inicio_nao_antes_de_amanha(self):
        # "semana de 16/06" começaria hoje; clamp puxa pra amanhã (17/06)
        di, df = parse_janela_preferencia("semana de 16/06", HOJE)
        assert di >= date(2026, 6, 17)


class TestFallbackNone:
    @pytest.mark.parametrize("txt", [
        "", "   ", "manhã", "tarde", "qualquer horário",
        "o quanto antes", "urgente", "sem preferência", "você escolhe",
    ])
    def test_inparseavel_retorna_none(self, txt):
        assert parse_janela_preferencia(txt, HOJE) is None

    def test_nao_levanta_excecao(self):
        # entradas estranhas não derrubam
        assert parse_janela_preferencia("32 a 99 de julho", HOJE) is None


class TestJanelaMaxima:
    def test_cap_120_dias(self):
        di, df = parse_janela_preferencia("de 20/06 a 31/12", HOJE)
        assert (df - di).days <= 120
