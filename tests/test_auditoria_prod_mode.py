"""Task #82 — modo prod da auditoria (transforms puros, sem rede).

Cobre:
- kommo.ler_cf_valor — leitura de custom_fields_values.
- procedimentos.codigos_por_label_kommo — reverso N.EXAMES → códigos.
- auditoria.montar_snapshot_pacientes — JSON do lead → PacienteAuditoria.
- auditoria.montar_fila_auditoria — leads → fila por status/unidade/médico.
"""
from __future__ import annotations

import pytest

from voice_agent import auditoria as A
from voice_agent import kommo as K
from voice_agent import procedimentos as P


# ---------------------------------------------------------------------------
# ler_cf_valor
# ---------------------------------------------------------------------------
def _cf(field_id, value):
    return {"field_id": field_id, "values": [{"value": value}]}


class TestLerCfValor:
    def test_le_valor_texto(self):
        lead = {"custom_fields_values": [_cf(123, "Maria Silva")]}
        assert K.ler_cf_valor(lead, 123) == "Maria Silva"

    def test_ausente_devolve_none(self):
        lead = {"custom_fields_values": [_cf(123, "x")]}
        assert K.ler_cf_valor(lead, 999) is None

    def test_vazio_devolve_none(self):
        lead = {"custom_fields_values": [_cf(123, "")]}
        assert K.ler_cf_valor(lead, 123) is None

    def test_lead_sem_cfs(self):
        assert K.ler_cf_valor({}, 123) is None
        assert K.ler_cf_valor(None, 123) is None


# ---------------------------------------------------------------------------
# codigos_por_label_kommo (reverso)
# ---------------------------------------------------------------------------
class TestCodigosPorLabel:
    def test_roundtrip_dos_4_agrupadores(self):
        for nome in P.AGRUPADOR_KOMMO_LABEL:
            label = P.agrupador_label_kommo(nome)
            nome2, codigos = P.codigos_por_label_kommo(label)
            assert nome2 == nome
            assert codigos == P.AGRUPADOR_NOME_CODIGOS[nome]

    def test_personalizado_ou_desconhecido(self):
        assert P.codigos_por_label_kommo(P.AGRUPADOR_KOMMO_PERSONALIZADO) == ("", [])
        assert P.codigos_por_label_kommo("xpto") == ("", [])
        assert P.codigos_por_label_kommo(None) == ("", [])


# ---------------------------------------------------------------------------
# montar_snapshot_pacientes
# ---------------------------------------------------------------------------
def _lead_um_paciente(label_exames, cod_agend="555"):
    """Lead com paciente 1 preenchido + médico/unidade/convênio + cod agend."""
    cfs = [
        _cf(K.FIELD_MEDICOS[0], "Dra. Karla Delalíbera"),
        _cf(K.FIELD_UNIDADE[0], "Asa Norte"),
        _cf(K.FIELD_CONVENIO[0], "Saúde Caixa"),
        _cf(K.FIELD_NOME_PACIENTES[1], "Maria Silva"),
        _cf(K.FIELD_EXAMES_PACIENTES[1][0], label_exames),
        _cf(K.FIELD_COD_AGENDAMENTO, cod_agend),
    ]
    return {"id": 24048691, "name": "Maria", "custom_fields_values": cfs}


class TestMontarSnapshot:
    def test_le_planejado_e_dados_do_lead(self):
        lead = _lead_um_paciente("Agrupa1-Adulto Rotina (9 exames)")
        pac = A.montar_snapshot_pacientes(lead, realizado_por_idx={1: [10, 20]})
        assert len(pac) == 1
        p = pac[0]
        assert p.idx == 1
        assert p.nome == "Maria Silva"
        assert p.medico_nome == "Dra. Karla Delalíbera"
        assert p.unidade == "Asa Norte"
        assert p.convenio == "Saúde Caixa"
        assert p.agrupador_planejado == "AGRUPADOR_1_ADULTO_ROTINA"
        assert p.planejado_codigos == P.AGRUPADOR_NOME_CODIGOS["AGRUPADOR_1_ADULTO_ROTINA"]
        assert p.realizado_codigos == [10, 20]

    def test_ignora_paciente_sem_exames(self):
        lead = {"id": 1, "name": "x", "custom_fields_values": [
            _cf(K.FIELD_NOME_PACIENTES[1], "Sem agrupador"),
        ]}
        assert A.montar_snapshot_pacientes(lead) == []

    def test_usa_fetcher_quando_sem_realizado_injetado(self):
        lead = _lead_um_paciente("Agrupa1-Adulto Rotina (9 exames)", cod_agend="777")
        chamado = {}

        def fake_fetcher(cod):
            chamado["cod"] = cod
            return [99, 1]

        pac = A.montar_snapshot_pacientes(lead, realizado_fetcher=fake_fetcher)
        assert chamado["cod"] == 777
        assert pac[0].realizado_codigos == [99, 1]

    def test_fetcher_chamado_uma_vez_para_lead(self):
        # dois pacientes, mesmo cod_agendamento → fetcher só 1x (cache)
        cfs = [
            _cf(K.FIELD_MEDICOS[0], "Dra. Karla Delalíbera"),
            _cf(K.FIELD_UNIDADE[0], "Asa Norte"),
            _cf(K.FIELD_NOME_PACIENTES[1], "Mãe"),
            _cf(K.FIELD_EXAMES_PACIENTES[1][0], "Agrupa1-Adulto Rotina (9 exames)"),
            _cf(K.FIELD_NOME_PACIENTES[2], "Filho"),
            _cf(K.FIELD_EXAMES_PACIENTES[2][0], "Agrupa3-Criança Rotina (6 exames)"),
            _cf(K.FIELD_COD_AGENDAMENTO, "888"),
        ]
        lead = {"id": 2, "name": "Família", "custom_fields_values": cfs}
        contador = {"n": 0}

        def fake_fetcher(cod):
            contador["n"] += 1
            return [5]

        pac = A.montar_snapshot_pacientes(lead, realizado_fetcher=fake_fetcher)
        assert len(pac) == 2
        assert contador["n"] == 1  # cache por lead


# ---------------------------------------------------------------------------
# montar_fila_auditoria
# ---------------------------------------------------------------------------
def _lead_status(lead_id, unidade, medico, status_por_idx):
    cfs = [
        _cf(K.FIELD_UNIDADE[0], unidade),
        _cf(K.FIELD_MEDICOS[0], medico),
    ]
    for idx, status in status_por_idx.items():
        cfs.append(_cf(A.kommo_field_id(idx, "status"), status))
        cfs.append(_cf(K.FIELD_NOME_PACIENTES[idx], f"Paciente {idx}"))
    return {"id": lead_id, "name": f"Lead {lead_id}", "custom_fields_values": cfs}


class TestMontarFila:
    def test_fila_secretaria_coleta_aguardando(self):
        leads = [
            _lead_status(1, "Asa Norte", "Dra. Karla Delalíbera",
                         {1: "aguardando_secretaria"}),
            _lead_status(2, "Águas Claras", "Dr. Fabrício Freitas",
                         {1: "fechada"}),
        ]
        fila = A.montar_fila_auditoria(leads, status_alvo="aguardando_secretaria")
        assert len(fila) == 1
        assert fila[0]["lead_id"] == 1
        assert fila[0]["pendentes"][0]["paciente_idx"] == 1

    def test_filtro_por_unidade(self):
        leads = [
            _lead_status(1, "Asa Norte", "Karla", {1: "aguardando_secretaria"}),
            _lead_status(2, "Águas Claras", "Fabrício", {1: "aguardando_secretaria"}),
        ]
        fila = A.montar_fila_auditoria(
            leads, status_alvo="aguardando_secretaria", unidade="aguas-claras",
        )
        assert len(fila) == 1
        assert fila[0]["lead_id"] == 2

    def test_filtro_por_medico(self):
        leads = [
            _lead_status(1, "Asa Norte", "Dra. Karla Delalíbera",
                         {1: "aguardando_medico"}),
            _lead_status(2, "Asa Norte", "Dr. Fabrício Freitas",
                         {1: "aguardando_medico"}),
        ]
        fila = A.montar_fila_auditoria(
            leads, status_alvo="aguardando_medico", medico="fabricio",
        )
        assert len(fila) == 1
        assert fila[0]["lead_id"] == 2

    def test_lead_sem_pendencia_fora(self):
        leads = [_lead_status(1, "Asa Norte", "Karla", {1: "fechada", 2: "divergencia"})]
        assert A.montar_fila_auditoria(leads, status_alvo="aguardando_secretaria") == []
