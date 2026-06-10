"""Pytest do Validador Factual.

Cobre os 3 casos reais (Tatiana data×dia, Maria Inas, preços R$).
"""
from __future__ import annotations

from datetime import date

import pytest

from voice_agent.validador_factual import (
    validar_texto_lia, todas_consistentes, inconsistencias,
    extrair_afirmacoes,
)


HOJE = date(2026, 6, 9)  # terça-feira


class TestPreco:
    def test_preco_correto_karla_611(self):
        r = validar_texto_lia("Consulta R$ 611,00 com a Dra. Karla", ctx={})
        assert todas_consistentes(r)

    def test_preco_correto_sinal_305(self):
        r = validar_texto_lia("Sinal R$ 305,50 via Pix", ctx={})
        assert todas_consistentes(r)

    def test_preco_inventado_R_500_falha(self):
        r = validar_texto_lia("Consulta R$ 500,00", ctx={})
        incons = inconsistencias(r)
        assert len(incons) == 1
        assert "não bate com tabela" in incons[0].motivo_inconsistencia


class TestDataDiaSemana:
    def test_quarta_10_06_bate(self):
        r = validar_texto_lia(
            "Quarta-feira, 10/06 às 14:00", ctx={"hoje": HOJE},
        )
        assert todas_consistentes(r)

    def test_quarta_11_06_NAO_bate_caso_tatiana(self):
        """Caso real Tatiana 24125064 — 11/06 é QUINTA, não QUARTA."""
        r = validar_texto_lia(
            "Quarta-feira, 11/06 às 14:00", ctx={"hoje": HOJE},
        )
        incons = inconsistencias(r)
        assert len(incons) == 1
        assert "11/06 é quinta" in incons[0].motivo_inconsistencia.lower(), incons[0].motivo_inconsistencia
        # Validador propõe correção (dia certo pra mesma data — conservador)
        assert incons[0].valor_correto and "quinta" in incons[0].valor_correto.lower()

    def test_sexta_13_06_NAO_bate_caso_tatiana(self):
        """13/06/2026 é SÁBADO, não sexta."""
        r = validar_texto_lia(
            "Sexta-feira, 13/06 às 15:30", ctx={"hoje": HOJE},
        )
        assert not todas_consistentes(r)


class TestConvenioAtende:
    def test_atende_sis_senado_OK(self):
        """SIS Senado está em KB 17 — afirmar atende é correto."""
        r = validar_texto_lia(
            "Sim, atendemos o SIS Senado", ctx={},
        )
        assert todas_consistentes(r)

    def test_atende_inas_NAO_caso_maria_agostini(self):
        """Caso Maria 24117314 — INAS está em KB 18 (não aceito)."""
        r = validar_texto_lia(
            "Perfeito! Atendemos o INAS GDF", ctx={},
        )
        incons = inconsistencias(r)
        assert len(incons) >= 1
        motivos = [i.motivo_inconsistencia.lower() for i in incons]
        assert any("inas" in m and "não aceito" in m for m in motivos)

    def test_negacao_nao_dispara(self):
        r = validar_texto_lia("Infelizmente não atendemos INAS GDF", ctx={})
        assert todas_consistentes(r)

    def test_atende_bradesco_falha(self):
        r = validar_texto_lia("Sim, atendemos Bradesco", ctx={})
        assert not todas_consistentes(r)


class TestIntegracaoMultiplaAfirmacao:
    def test_texto_com_multiplas_afirmacoes_pega_todas(self):
        """Texto da Lia com 3 afirmações simultâneas."""
        texto = (
            "Olá Maria! Atendemos INAS GDF sim. "
            "Sua consulta R$ 611,00 ficaria quarta-feira, 11/06 às 14h."
        )
        r = validar_texto_lia(texto, ctx={"hoje": HOJE})
        incons = inconsistencias(r)
        # Espera detectar INAS errado + data errada (R$ 611 é correto)
        assert len(incons) >= 2

    def test_texto_correto_passa(self):
        texto = (
            "Maria, atendemos Saúde Caixa. "
            "Consulta R$ 611,00. Tenho quarta-feira 10/06 às 14h disponível."
        )
        r = validar_texto_lia(texto, ctx={"hoje": HOJE})
        assert todas_consistentes(r)
