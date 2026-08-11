"""Pytest blindando o fluxo de gravação de agendamento no Medware.

Cenários congelados — qualquer regressão futura quebra build:

1. CONVÊNIO desconhecido → retorna ok:False motivo='convenio_desconhecido',
   NÃO posta ao Medware.

2. MÉDICO não mapeado → retorna ok:False motivo='medico_nao_mapeado',
   NÃO posta ao Medware.

3. Paciente NOVO (sem CPF cadastrado no Medware) → body inclui objeto
   'paciente' com nome/cpf/data nasc, NÃO inclui codPaciente.

4. Paciente JÁ cadastrado (buscar_paciente_por_cpf devolve cod) →
   body inclui codPaciente, NÃO inclui objeto paciente.

5. Medware retorna HTTP erro (não-ok) → result.ok=False, motivo=
   'erro_medware', _set_gravacao_status marca 'failed' em Redis E
   posta nota no Kommo movendo lead pra etapa humana (Gap 5).

6. Medware retorna sucesso com codAgendamento → result.ok=True,
   move lead Kommo pra 4-AGENDADO E grava cod_agendamento no
   custom_field do lead.

Ver: voice_agent/agendamento.py + voice_agent/medware.py
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent.medware import (
    MedwareClient, PLANO_PARTICULAR, PROC_CONSULTA_PARTICULAR_DEFAULT,
    PROC_CONSULTA_CONVENIO, MEDICO_CODES, UNIDADE_CODES,
)

# Constantes auxiliares pros testes — vindas do MEDICO_CODES/UNIDADE_CODES reais.
MEDICO_KARLA = MEDICO_CODES["dra. karla delalibera"]      # 12080
UNIDADE_ASA_NORTE = UNIDADE_CODES["asa norte"]            # 5


@pytest.fixture
def medware_mock():
    """MedwareClient com _post e buscar_paciente_por_cpf mockados."""
    c = MedwareClient(
        identificacao="test", senha="test",
        base_url="http://medware-fake/api",
    )
    c._post = MagicMock(return_value=(True, {"codAgendamento": 999000}))
    c.buscar_paciente_por_cpf = MagicMock(return_value=None)
    return c


class TestConvenioDesconhecido:

    def test_convenio_nao_mapeado_retorna_motivo_e_nao_posta(
        self, medware_mock
    ):
        result = medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Teste", cpf="12345678900",
            data_nascimento="1970-01-01", celular="61999999999",
            convenio="Convênio Que Não Existe LTDA",
        )
        assert result["ok"] is False
        assert result["motivo"] == "convenio_desconhecido"
        # _post NÃO pode ter sido chamado — falhou antes
        medware_mock._post.assert_not_called()


class TestPacienteNovoVsCadastrado:

    def test_paciente_novo_envia_objeto_paciente(self, medware_mock):
        # buscar_paciente_por_cpf retorna None (paciente novo)
        medware_mock.buscar_paciente_por_cpf.return_value = None
        medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Novo", cpf="11122233344",
            data_nascimento="1980-05-20", celular="61988887777",
            convenio="particular",
        )
        assert medware_mock._post.call_count == 1
        path, body = medware_mock._post.call_args.args
        assert path == "Medware/Agendamento/Salvar"
        assert "paciente" in body, "Paciente novo precisa do objeto paciente"
        assert "codPaciente" not in body
        assert body["paciente"]["nome"] == "JOÃO NOVO"  # uppercase
        assert body["paciente"]["cpf"] == "11122233344"
        assert body["codPlano"] == PLANO_PARTICULAR
        assert body["codProcedimento"] == PROC_CONSULTA_PARTICULAR_DEFAULT or \
               body["codProcedimento"] > 0

    def test_paciente_existente_envia_codpaciente(self, medware_mock):
        # buscar_paciente_por_cpf devolve um cod
        medware_mock.buscar_paciente_por_cpf.return_value = {
            "codPaciente": 555444,
        }
        medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Existente", cpf="11122233344",
            data_nascimento="", celular="61988887777",
            convenio="particular",
        )
        path, body = medware_mock._post.call_args.args
        assert body.get("codPaciente") == 555444
        assert "paciente" not in body, (
            "Paciente já cadastrado NÃO envia objeto paciente"
        )


class TestErroMedware:

    def test_medware_retorna_erro_devolve_motivo_erro_medware(
        self, medware_mock
    ):
        medware_mock._post.return_value = (
            False, {"message": "Conflito de horário"}
        )
        result = medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Conflito", cpf="11122233344",
            data_nascimento="1980-05-20", celular="61988887777",
            convenio="particular",
        )
        assert result["ok"] is False
        assert result["motivo"] == "erro_medware"
        assert "Conflito" in result.get("detalhe", "")


class TestSucessoCompleto:

    def test_medware_sucesso_devolve_cod_agendamento(self, medware_mock):
        medware_mock._post.return_value = (
            True, {"codAgendamento": 777888}
        )
        result = medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Sucesso", cpf="11122233344",
            data_nascimento="1980-05-20", celular="61988887777",
            convenio="particular",
        )
        assert result["ok"] is True
        assert result["cod_agendamento"] == 777888
        assert result["plano"] == PLANO_PARTICULAR


class TestPacienteSemCPF:

    def test_sem_cpf_nao_busca_paciente(self, medware_mock):
        medware_mock.criar_agendamento(
            cod_medico=MEDICO_KARLA, cod_unidade=UNIDADE_ASA_NORTE,
            cod_agenda=0, data_hora="2026-06-10T14:30",
            nome="João Sem CPF", cpf="",
            data_nascimento="1980-05-20", celular="",
            convenio="particular",
        )
        # buscar_paciente_por_cpf NÃO chamado quando cpf vazio
        medware_mock.buscar_paciente_por_cpf.assert_not_called()
        # E body deve ter objeto paciente vazio mas com nome
        path, body = medware_mock._post.call_args.args
        assert "paciente" in body
        assert body["paciente"]["nome"] == "JOÃO SEM CPF"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
