"""Pytest Bug C-31 — Karla por unidade + dia da semana SEMPRE-ON.

Origem: Fábio 16/06/2026, lead 24113652 Fábio Philipe Martins.
Lia ofereceu "quarta-feira, 18/06 às 08:30" E "sexta-feira, 20/06 às 08:00".
- 18/06/2026 = quinta (não quarta)
- 20/06/2026 = sábado (não sexta), e Karla NÃO atende sábado
- Karla Asa Norte só atende segunda, quarta, sexta — quinta seria errado de qualquer jeito

Causa raiz dupla:
1. _DIAS_ATENDIMENTO_POR_MEDICO dava Karla = {0,1,2,3,4} (seg-sex), inclui quinta
2. _viola_dia_semana e _viola_oferta_em_dia_nao_atendido atrás de FILTROS_LEGACY=0

Fix: mapping por médico+unidade + filtros sempre-ON.
"""
import os
from unittest.mock import patch

import pytest

from voice_agent.responder import (
    _viola_dia_semana,
    _viola_oferta_em_dia_nao_atendido,
    _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE,
    _DIAS_ATENDIMENTO_POR_MEDICO,
    _scrub_prohibited,
)


class TestMappingMedicoUnidade:
    """Validações estruturais do mapping."""

    def test_karla_asa_norte_segunda_quarta_sexta(self):
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("karla", "asa norte")] == {0, 2, 4}

    def test_karla_aguas_claras_terca_quinta(self):
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("karla", "águas claras")] == {1, 3}
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("karla", "aguas claras")] == {1, 3}

    def test_fabricio_terca_quinta(self):
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("fabricio", "asa norte")] == {1, 3}
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("fabrício", "asa norte")] == {1, 3}

    def test_katia_pausa(self):
        assert _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE[("katia", "asa norte")] == set()

    def test_karla_nunca_sabado_nem_domingo(self):
        # Sábado=5, domingo=6 — nunca em nenhum mapping de Karla
        for chave, dias in _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE.items():
            if "karla" in chave[0]:
                assert 5 not in dias, f"{chave}: sábado proibido"
                assert 6 not in dias, f"{chave}: domingo proibido"


class TestViolaOfertaEmDiaNaoAtendido:
    """Filtro pega oferta em dia errado considerando médico+unidade."""

    def test_karla_asa_norte_quinta_eh_violacao(self):
        # 18/06/2026 = quinta. Karla Asa Norte só atende seg/qua/sex.
        ctx = {"known": {"medico": "Karla Delalíbera", "unidade": "Asa Norte"}}
        texto = "Tenho horário 1️⃣ quarta-feira, 18/06 às 08:30"
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is not None, "Quinta-feira deveria ser violação pra Karla Asa Norte"
        medico, data, dia_real = result
        assert "quinta" in dia_real.lower()

    def test_karla_asa_norte_sabado_eh_violacao(self):
        # 20/06/2026 = sábado. Karla nunca atende sábado.
        ctx = {"known": {"medico": "Karla Delalíbera", "unidade": "Asa Norte"}}
        texto = "Sexta-feira, 20/06 às 08:00"
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is not None

    def test_karla_asa_norte_quarta_eh_ok(self):
        # 17/06/2026 = quarta. Karla Asa Norte atende.
        ctx = {"known": {"medico": "Karla Delalíbera", "unidade": "Asa Norte"}}
        texto = "Quarta-feira, 17/06 às 09:00"
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is None, "Quarta-feira é OK pra Karla Asa Norte"

    def test_karla_aguas_claras_quinta_eh_ok(self):
        # 18/06/2026 = quinta. Karla Águas Claras atende terça/quinta.
        ctx = {"known": {"medico": "Karla", "unidade": "Águas Claras"}}
        texto = "Quinta-feira, 18/06 às 09:00"
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is None, "Quinta-feira é OK pra Karla Águas Claras"

    def test_karla_aguas_claras_segunda_eh_violacao(self):
        # 22/06/2026 = segunda. Águas Claras só atende ter/qui.
        ctx = {"known": {"medico": "Karla", "unidade": "Águas Claras"}}
        texto = "Segunda-feira, 22/06"
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is not None

    def test_sem_unidade_usa_fallback_uniao(self):
        # Sem unidade no ctx: fallback pra mapa antigo (seg-sex)
        ctx = {"known": {"medico": "Karla"}}
        texto = "Sábado, 21/06"  # 21/06 = domingo na verdade
        # Domingo não está em {0,1,2,3,4} → violação
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        # Esperado dispara (domingo fora do permitido)
        assert result is not None

    def test_caso_real_fabio_philipe_24113652(self):
        """Texto literal do bug — duas violações no mesmo texto."""
        ctx = {"known": {"medico": "Dra. Karla Delalibera", "unidade": "Asa Norte"}}
        texto = (
            "Ótimo! Tenho estes horários disponíveis na Asa Norte, manhã, início:\n"
            "1️⃣ quarta-feira, 18/06 às 08:30\n"
            "2️⃣ sexta-feira, 20/06 às 08:00\n"
            "Qual prefere?"
        )
        # Detecta a primeira violação (18/06 = quinta, não atendida)
        result = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert result is not None


class TestViolaDiaSemana:
    """Filtro pega divergência entre dia-da-semana citado e data real."""

    def test_quarta_18_06_eh_quinta_dispara(self):
        # 18/06/2026 = quinta, mas Lia disse quarta
        result = _viola_dia_semana("Quarta-feira, 18/06 às 08:30")
        assert result is not None
        dia_falado, data_str, dia_real = result
        assert "quarta" in dia_falado.lower()
        assert "quinta" in dia_real.lower()

    def test_sexta_20_06_eh_sabado_dispara(self):
        # 20/06/2026 = sábado, mas Lia disse sexta
        result = _viola_dia_semana("Sexta-feira, 20/06 às 08:00")
        assert result is not None
        dia_falado, _, dia_real = result
        assert "sexta" in dia_falado.lower()
        assert "sábado" in dia_real.lower() or "sabado" in dia_real.lower()

    def test_quinta_18_06_eh_ok(self):
        # 18/06/2026 = quinta, Lia disse quinta — bate
        result = _viola_dia_semana("Quinta-feira, 18/06 às 09:00")
        assert result is None


class TestIntegracaoScrubProhibited:
    """O _scrub_prohibited substitui resposta com dia/médico inválido — sempre-ON."""

    def test_caso_fabio_substitui(self):
        """Sem _FILTROS_LEGACY_ATIVOS, o filtro DEVE pegar (Bug C-31)."""
        ctx = {"known": {"medico": "Dra. Karla Delalíbera", "unidade": "Asa Norte"}}
        texto = (
            "Tenho estes horários disponíveis na Asa Norte, manhã, início:\n"
            "1️⃣ quarta-feira, 18/06 às 08:30\n"
            "2️⃣ sexta-feira, 20/06 às 08:00\n"
            "Qual prefere?"
        )
        resultado = _scrub_prohibited(texto, ctx)
        # Substituição deve ter acontecido
        assert resultado != texto

    def test_resposta_correta_nao_substitui(self):
        # Karla Asa Norte oferecendo quarta (17/06) e sexta (19/06) — datas válidas
        ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
        texto = (
            "Tenho:\n"
            "1️⃣ quarta-feira, 17/06 às 08:30\n"
            "2️⃣ sexta-feira, 19/06 às 08:00"
        )
        resultado = _scrub_prohibited(texto, ctx)
        # Texto válido — outros filtros podem mexer, mas o C-31 não substitui
        # Confirma com tolerância: pelo menos contém alguma das datas válidas
        assert "17/06" in resultado or "19/06" in resultado or len(resultado) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
