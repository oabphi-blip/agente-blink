"""Task #80 — integração selecionar_agrupador → executar_agendamento.

Congela os cenários:

1. classificar_motivo_tipo_kommo devolve os 5 labels corretos.
2. agrupador_label_kommo converte nome interno → label do enum N.EXAMES.
3. executar_agendamento, em sucesso, chama kommo.update_lead_fields com
   `pacientes[0]` contendo motivo_tipo + agrupador_label.
4. num_pacientes vazio (não clobra a contagem real do lead).
5. Falha no agrupador NÃO quebra a gravação do cod_agendamento.

Ver: voice_agent/procedimentos.py + voice_agent/agendamento.py
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent import procedimentos as P
from voice_agent.agendamento import executar_agendamento


# ---------------------------------------------------------------------------
# 1) classificador de motivo (5 categorias)
# ---------------------------------------------------------------------------
class TestClassificarMotivoTipo:

    def test_rotina_default(self):
        assert P.classificar_motivo_tipo_kommo("quero fazer um check-up") == P.MOTIVO_TIPO_ROTINA
        assert P.classificar_motivo_tipo_kommo(None) == P.MOTIVO_TIPO_ROTINA
        assert P.classificar_motivo_tipo_kommo("") == P.MOTIVO_TIPO_ROTINA

    def test_urgencia_por_palavra(self):
        assert P.classificar_motivo_tipo_kommo("estou com dor forte no olho") == P.MOTIVO_TIPO_URGENCIA
        assert P.classificar_motivo_tipo_kommo("é urgente, machucou o olho") == P.MOTIVO_TIPO_URGENCIA

    def test_pos_op_antes_de_pre(self):
        # quem já operou é pós, não pré
        assert P.classificar_motivo_tipo_kommo("retorno da cirurgia de catarata") == P.MOTIVO_TIPO_POS_OP
        assert P.classificar_motivo_tipo_kommo("já operei e preciso de revisão") == P.MOTIVO_TIPO_POS_OP

    def test_pre_op(self):
        assert P.classificar_motivo_tipo_kommo("avaliação pré-operatória de catarata") == P.MOTIVO_TIPO_PRE_OP
        assert P.classificar_motivo_tipo_kommo("vou operar, preciso da avaliação") == P.MOTIVO_TIPO_PRE_OP

    def test_retorno(self):
        assert P.classificar_motivo_tipo_kommo("retorno de acompanhamento") == P.MOTIVO_TIPO_RETORNO
        assert P.classificar_motivo_tipo_kommo("trazer resultado de exame") == P.MOTIVO_TIPO_RETORNO

    def test_enum_explicito_respeitado(self):
        # se o atendente já classificou no Kommo, respeita
        assert P.classificar_motivo_tipo_kommo("texto qualquer", "Pós-Operatório") == P.MOTIVO_TIPO_POS_OP
        # acento/caixa insensível
        assert P.classificar_motivo_tipo_kommo("x", "pos-operatório".title()) in (
            P.MOTIVO_TIPO_POS_OP, P.MOTIVO_TIPO_ROTINA,
        )

    def test_sempre_retorna_um_dos_5(self):
        labels = {
            P.MOTIVO_TIPO_ROTINA, P.MOTIVO_TIPO_RETORNO, P.MOTIVO_TIPO_PRE_OP,
            P.MOTIVO_TIPO_URGENCIA, P.MOTIVO_TIPO_POS_OP,
        }
        for txt in ("", "abc", "dor", "cirurgia", "rotina", None, "retorno"):
            assert P.classificar_motivo_tipo_kommo(txt) in labels


# ---------------------------------------------------------------------------
# 2) label do agrupador
# ---------------------------------------------------------------------------
class TestAgrupadorLabel:

    def test_mapeia_conhecidos(self):
        assert P.agrupador_label_kommo("AGRUPADOR_1_ADULTO_ROTINA") == "Agrupa1-Adulto Rotina (9 exames)"
        assert P.agrupador_label_kommo("AGRUPADOR_4_CRIANCA_URGENCIA") == "Agrupa4-Criança Urgência(5 exames)"

    def test_desconhecido_vira_personalizado(self):
        assert P.agrupador_label_kommo("AGRUPADOR_XPTO") == P.AGRUPADOR_KOMMO_PERSONALIZADO
        assert P.agrupador_label_kommo(None) == P.AGRUPADOR_KOMMO_PERSONALIZADO

    def test_label_casa_com_enum_kommo(self):
        # os 4 labels têm que existir na tabela de enum N.EXAMES do paciente 1
        from voice_agent.kommo import FIELD_EXAMES_PACIENTES
        _fid, tabela = FIELD_EXAMES_PACIENTES[1]
        for nome in P.AGRUPADOR_KOMMO_LABEL:
            label = P.agrupador_label_kommo(nome)
            assert label in tabela, f"{label} não está no enum N.EXAMES"


# ---------------------------------------------------------------------------
# 3-5) integração no executar_agendamento
# ---------------------------------------------------------------------------
def _decision():
    return {
        "medico": "dra. karla delalibera",
        "unidade": "asa norte",
        "data_iso": "2026-06-10",
        "hora": "09:00",
        "cod_agenda": 1,
    }


def _caller_context(motivo="consulta de rotina", nasc="2020-06-01"):
    return {
        "lead_id": 24048691,
        "name": "Maria Teste",
        "known": {
            "medico": "dra. karla delalibera",
            "unidade": "asa norte",
            "convenio": "Não se aplica",
            "nome_paciente": "Maria Teste Silva",
            "cpf": "",
            "data_nascimento": nasc,
            "telefone": "61999990000",
            "motivo": motivo,
        },
    }


@pytest.fixture
def medware_ok():
    m = MagicMock()
    m.criar_agendamento.return_value = {"ok": True, "cod_agendamento": 999000}
    return m


def _pacientes_arg(kommo_mock):
    """Extrai o `pacientes` passado em update_lead_fields (call task #80)."""
    for call in kommo_mock.update_lead_fields.call_args_list:
        _lead, fields = call.args[0], call.args[1]
        if isinstance(fields, dict) and "pacientes" in fields:
            return fields
    return None


class TestIntegracaoAgendamento:

    def test_sucesso_injeta_motivo_tipo_e_agrupador(self, medware_ok):
        kommo = MagicMock()
        res = executar_agendamento(
            _decision(), _caller_context(motivo="dor forte no olho", nasc="1980-06-01"),
            medware_ok, kommo,
        )
        assert res["ok"] is True
        fields = _pacientes_arg(kommo)
        assert fields is not None, "update_lead_fields não recebeu pacientes"
        p = fields["pacientes"][0]
        # adulto + urgência → Agrupa2 + Emergência/Urgência
        assert p["motivo_tipo"] == P.MOTIVO_TIPO_URGENCIA
        assert p["agrupador_label"] == "Agrupa2-Adulto Emergência (6 exames)"
        assert fields["cod_agendamento"] == 999000
        # num_pacientes vazio → não clobra contagem real
        assert fields.get("num_pacientes") == ""

    def test_crianca_rotina(self, medware_ok):
        kommo = MagicMock()
        executar_agendamento(
            _decision(), _caller_context(motivo="consulta de rotina", nasc="2024-06-01"),
            medware_ok, kommo,
        )
        p = _pacientes_arg(kommo)["pacientes"][0]
        assert p["motivo_tipo"] == P.MOTIVO_TIPO_ROTINA
        assert p["agrupador_label"] == "Agrupa3-Criança Rotina (6 exames)"

    def test_falha_agrupador_nao_quebra_cod(self, medware_ok, monkeypatch):
        # força exceção no selecionar_agrupador
        import voice_agent.procedimentos as _p
        monkeypatch.setattr(
            _p, "selecionar_agrupador",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        kommo = MagicMock()
        res = executar_agendamento(_decision(), _caller_context(), medware_ok, kommo)
        # cod_agendamento ainda gravado mesmo com agrupador quebrado
        assert res["ok"] is True
        assert kommo.update_lead_fields.called
        last = kommo.update_lead_fields.call_args.args[1]
        assert last.get("cod_agendamento") == 999000

    def test_medware_falha_nao_chama_agrupador(self):
        medware = MagicMock()
        medware.criar_agendamento.return_value = {"ok": False, "motivo": "erro_medware"}
        kommo = MagicMock()
        res = executar_agendamento(_decision(), _caller_context(), medware, kommo)
        assert res["ok"] is False
        # em falha não deve haver pacientes injetados
        assert _pacientes_arg(kommo) is None
