"""Pytest blindando que kommo.update_lead_fields NÃO grava nome
incompleto (task 31/05/2026 — pedido Fábio).

Testa a função pública `kommo.nome_paciente_pode_ser_gravado` que é
chamada antes de gravar `N.NOME PACIENTE` no Kommo. Origem do bug:
lead 24048691 — Marcela gravada como nome completo sendo só o primeiro.
"""
from __future__ import annotations

import pytest

from voice_agent.kommo import nome_paciente_pode_ser_gravado


class TestNomeCompletoGrava:

    def test_3_tokens_completos(self):
        ok, _ = nome_paciente_pode_ser_gravado("Marcela Almeida Souza")
        assert ok is True

    def test_4_tokens_completos(self):
        ok, _ = nome_paciente_pode_ser_gravado(
            "Renata Cristina Barbosa Coelho"
        )
        assert ok is True

    def test_nome_com_conectivos_e_completo(self):
        ok, _ = nome_paciente_pode_ser_gravado("Maria de Souza e Silva")
        assert ok is True


class TestNomeIncompletoBloqueado:

    def test_so_primeiro_nome_bloqueado(self):
        """Caso real lead 24048691."""
        ok, status = nome_paciente_pode_ser_gravado("Marcela")
        assert ok is False
        assert status == "so_primeiro_nome"

    def test_2_tokens_bloqueado(self):
        ok, status = nome_paciente_pode_ser_gravado("João Silva")
        assert ok is False
        assert status == "so_sobrenome_faltando"

    def test_iniciais_no_meio_bloqueado(self):
        ok, status = nome_paciente_pode_ser_gravado("Renata C B M Coelho")
        assert ok is False
        assert status == "incompleto_com_iniciais"


class TestCasosBorda:

    def test_none_bloqueado(self):
        ok, status = nome_paciente_pode_ser_gravado(None)
        assert ok is False
        assert status == "vazio"

    def test_vazio_bloqueado(self):
        ok, status = nome_paciente_pode_ser_gravado("")
        assert ok is False
        assert status == "vazio"

    def test_so_espaco_bloqueado(self):
        ok, status = nome_paciente_pode_ser_gravado("   ")
        assert ok is False
        assert status == "vazio"


class TestImportaEUsa:
    """Garante que o módulo nomes.avaliar_nome_paciente é o backend real
    (não falsificar nem cair em fallback silencioso)."""

    def test_status_strings_batem_com_enum(self):
        # Os 4 status que esperamos do validador
        from voice_agent.nomes import NomeStatus
        for raw, esperado in [
            ("Marcela", NomeStatus.SO_PRIMEIRO_NOME),
            ("João Silva", NomeStatus.SO_SOBRENOME_FALTANDO),
            ("Renata C B M Coelho", NomeStatus.INCOMPLETO_COM_INICIAIS),
        ]:
            ok, status = nome_paciente_pode_ser_gravado(raw)
            assert ok is False
            assert status == esperado.value
