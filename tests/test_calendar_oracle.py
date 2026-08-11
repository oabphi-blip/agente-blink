"""Pytest blindando calendar_oracle.py — anti-regressão Bug C-35.

Roda: pytest tests/test_calendar_oracle.py -v
"""
from datetime import date

import pytest

from voice_agent.calendar_oracle import (
    DIAS_PT,
    dia_semana,
    gerar_oferta_2_slots,
    proximas_datas_validas,
    unidade_medico_em,
    validar,
)


class TestDiaSemana:
    """Bug C-35 — Claude inventou que 18/06/2026 era quarta. Era quinta."""

    def test_18_06_2026_eh_quinta(self):
        assert dia_semana(date(2026, 6, 18)) == "Quinta-feira"

    def test_20_06_2026_eh_sabado(self):
        assert dia_semana(date(2026, 6, 20)) == "Sábado"

    def test_22_07_2026_eh_quarta(self):
        # Eu havia dito "Terça 22/07" — era quarta
        assert dia_semana(date(2026, 7, 22)) == "Quarta-feira"

    def test_24_07_2026_eh_sexta(self):
        # Eu havia dito "Quinta 24/07" — era sexta
        assert dia_semana(date(2026, 7, 24)) == "Sexta-feira"

    def test_30_06_2026_eh_terca(self):
        # Eu havia dito "Segunda 30/06" — era terça
        assert dia_semana(date(2026, 6, 30)) == "Terça-feira"


class TestUnidadeKarla:
    """Karla: seg/qua/sex Asa Norte · ter/qui Águas Claras · sáb/dom não atende."""

    def test_segunda_22_06_asa_norte(self):
        assert unidade_medico_em(date(2026, 6, 22), "karla") == "Asa Norte"

    def test_terca_23_06_aguas_claras(self):
        assert unidade_medico_em(date(2026, 6, 23), "karla") == "Águas Claras"

    def test_quarta_24_06_asa_norte(self):
        assert unidade_medico_em(date(2026, 6, 24), "karla") == "Asa Norte"

    def test_quinta_18_06_aguas_claras(self):
        # CASO C-35 Warley: eu falei Asa Norte. Era Águas Claras.
        assert unidade_medico_em(date(2026, 6, 18), "karla") == "Águas Claras"

    def test_sexta_19_06_asa_norte(self):
        assert unidade_medico_em(date(2026, 6, 19), "karla") == "Asa Norte"

    def test_sabado_20_06_nao_atende(self):
        assert unidade_medico_em(date(2026, 6, 20), "karla") is None

    def test_domingo_21_06_nao_atende(self):
        assert unidade_medico_em(date(2026, 6, 21), "karla") is None


class TestValidar:
    """Validação de oferta de slot."""

    def test_caso_warley_18_06_asa_norte_invalido(self):
        info = validar(date(2026, 6, 18), "karla", "Asa Norte")
        assert info.valido_para_oferta is False
        assert "Águas Claras" in info.unidade_atende
        assert "NÃO Asa Norte" in info.texto_pronto

    def test_caso_warley_19_06_asa_norte_valido(self):
        info = validar(date(2026, 6, 19), "karla", "Asa Norte")
        assert info.valido_para_oferta is True
        assert info.unidade_atende == "Asa Norte"
        assert "Sexta-feira" in info.texto_pronto

    def test_sabado_20_06_invalido(self):
        info = validar(date(2026, 6, 20), "karla", "Asa Norte")
        assert info.valido_para_oferta is False
        assert info.motivo_invalido is not None

    def test_aceita_acento_aguas_claras(self):
        # Bug encontrado durante implementação: comparação sem normalizar acento.
        info = validar(date(2026, 6, 18), "karla", "aguas claras")
        assert info.valido_para_oferta is True


class TestProximasDatasValidas:
    """Listagem das próximas datas disponíveis."""

    def test_4_proximas_karla_asa_norte_a_partir_17_06(self):
        datas = proximas_datas_validas("Asa Norte", "karla", qtde=4,
                                       a_partir_de=date(2026, 6, 17))
        assert len(datas) == 4
        # Sequência esperada: qua 17/06, sex 19/06, seg 22/06, qua 24/06
        assert datas[0].data_iso == "2026-06-17"
        assert datas[1].data_iso == "2026-06-19"
        assert datas[2].data_iso == "2026-06-22"
        assert datas[3].data_iso == "2026-06-24"

    def test_4_proximas_karla_aguas_claras_a_partir_17_06(self):
        # CASO C-35 Lucineia: eu queria semana 21-25/07 Águas Claras.
        # Correto = ter 21/07 + qui 23/07.
        datas = proximas_datas_validas("Águas Claras", "karla", qtde=4,
                                       a_partir_de=date(2026, 7, 21))
        assert len(datas) == 4
        assert datas[0].data_iso == "2026-07-21"  # terça
        assert datas[1].data_iso == "2026-07-23"  # quinta
        assert datas[2].data_iso == "2026-07-28"  # próxima terça
        assert datas[3].data_iso == "2026-07-30"  # próxima quinta


class TestGerarOferta:
    """Texto pronto pra colar no WhatsApp."""

    def test_warley_asa_norte_09_30_14_30(self):
        # Hoje fixo 17/06 (quarta) — próximo Asa Norte é 17/06 mesmo (hoje), depois 19/06
        txt = gerar_oferta_2_slots("karla", "Asa Norte", ["09:30", "14:30"],
                                   a_partir_de=date(2026, 6, 17))
        assert "1️⃣" in txt
        assert "2️⃣" in txt
        # Garantir que NÃO aparece dia-da-semana errado
        assert "Sábado" not in txt
        assert "Domingo" not in txt

    def test_aguas_claras_18_06(self):
        # Lucineia — começando 18/06 (quinta Águas Claras)
        txt = gerar_oferta_2_slots("karla", "aguas claras", ["14:30", "15:00"],
                                   a_partir_de=date(2026, 6, 18))
        assert "Quinta-feira (18/06)" in txt
        assert "Terça-feira (23/06)" in txt


class TestRegressaoBugC35:
    """Cenários EXATOS do bug C-35 que devem TODOS ser pegos."""

    EXEMPLOS = [
        # (data, dia_correto, unidade_karla_correta)
        (date(2026, 6, 18), "Quinta-feira", "Águas Claras"),  # Warley/Anna Júlia/Theo
        (date(2026, 6, 19), "Sexta-feira", "Asa Norte"),       # Sem nome/Alaine/Pedro Miguel
        (date(2026, 6, 20), "Sábado", None),                   # Warley/Anna Júlia/Sem nome
        (date(2026, 6, 21), "Domingo", None),                  # Laura Ellie/Sem nome/Alaine/Luciana
        (date(2026, 6, 23), "Terça-feira", "Águas Claras"),    # Val (eu falei "segunda")
        (date(2026, 6, 24), "Quarta-feira", "Asa Norte"),      # Theo/Yuri (eu falei "terça" Águas Claras)
        (date(2026, 6, 26), "Sexta-feira", "Asa Norte"),       # Pedro Miguel (eu falei "quinta")
        (date(2026, 6, 28), "Domingo", None),                  # Luciana (eu falei "sábado")
        (date(2026, 6, 30), "Terça-feira", "Águas Claras"),    # Val (eu falei "segunda")
        (date(2026, 7, 3), "Sexta-feira", "Asa Norte"),        # Pedro Miguel/Ceará (eu falei "quinta")
        (date(2026, 7, 22), "Quarta-feira", "Asa Norte"),      # Lucineia (eu falei "terça Águas Claras")
        (date(2026, 7, 24), "Sexta-feira", "Asa Norte"),       # Lucineia (eu falei "quinta Águas Claras")
    ]

    @pytest.mark.parametrize("d, dia_esperado, unidade_esperada", EXEMPLOS)
    def test_caso_real_c35(self, d, dia_esperado, unidade_esperada):
        assert dia_semana(d) == dia_esperado, \
            f"Bug C-35: {d} é {dia_esperado}, não {dia_semana(d)}"
        assert unidade_medico_em(d, "karla") == unidade_esperada, \
            f"Bug C-35: {d} Karla atende {unidade_esperada}"
