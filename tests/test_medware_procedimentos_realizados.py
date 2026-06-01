"""Task #82 — medware.listar_procedimentos_realizados + extractor.

Cobre a normalização de formatos de resposta e o fallback multi-endpoint.
NOTA: o endpoint real do Medware ainda precisa ser confirmado em produção;
estes testes congelam o CONTRATO de parsing (offline, com _get mockado).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent.medware import (
    MedwareClient, _extrair_codigos_procedimento,
)


class TestExtrairCodigos:

    def test_lista_de_dicts(self):
        data = [{"codProcedimento": 10}, {"codProcedimento": 20}]
        assert _extrair_codigos_procedimento(data) == [10, 20]

    def test_dict_com_colecao(self):
        data = {"procedimentos": [{"codigo": 3}, {"cod": 1}]}
        assert _extrair_codigos_procedimento(data) == [1, 3]

    def test_dict_unico(self):
        assert _extrair_codigos_procedimento({"codProcedimento": 5}) == [5]

    def test_lista_de_ints(self):
        assert _extrair_codigos_procedimento([7, 7, 2]) == [2, 7]

    def test_dedup_e_ordena(self):
        data = [{"codProcedimento": 9}, {"codProcedimento": 9}, {"codProcedimento": 1}]
        assert _extrair_codigos_procedimento(data) == [1, 9]

    def test_vazio_e_lixo(self):
        assert _extrair_codigos_procedimento(None) == []
        assert _extrair_codigos_procedimento([]) == []
        assert _extrair_codigos_procedimento({}) == []
        assert _extrair_codigos_procedimento([{"semCodigo": 1}]) == []

    def test_valores_nao_numericos_ignorados(self):
        data = [{"codProcedimento": "abc"}, {"codProcedimento": 4}]
        assert _extrair_codigos_procedimento(data) == [4]


@pytest.fixture
def client():
    return MedwareClient(
        identificacao="test", senha="test",
        base_url="http://medware-fake/api",
    )


class TestListarProcedimentosRealizados:

    def test_agendamento_zero_devolve_vazio(self, client):
        client._get = MagicMock()
        assert client.listar_procedimentos_realizados(0) == []
        client._get.assert_not_called()

    def test_primeiro_endpoint_responde(self, client):
        client._get = MagicMock(return_value=[{"codProcedimento": 100}, {"codProcedimento": 200}])
        assert client.listar_procedimentos_realizados(999) == [100, 200]
        # parou no primeiro candidato
        assert client._get.call_count == 1

    def test_fallback_para_segundo_endpoint(self, client):
        # primeiro devolve vazio, segundo devolve dados
        client._get = MagicMock(side_effect=[None, {"procedimentos": [{"cod": 5}]}, None])
        assert client.listar_procedimentos_realizados(999) == [5]
        assert client._get.call_count == 2

    def test_todos_falham_devolve_vazio(self, client):
        client._get = MagicMock(return_value=None)
        assert client.listar_procedimentos_realizados(999) == []
        assert client._get.call_count == 3
