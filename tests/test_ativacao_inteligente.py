"""
Testes da saudação personalizada com prova de escuta.

Origem: Fábio 12/06/2026 — ativação inteligente.
"""

from datetime import datetime, timezone, timedelta
import pytest

from voice_agent.ativacao_inteligente import gerar_saudacao_personalizada


def _ts_dias_atras(dias: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=dias)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def test_lead_vazio_gera_saudacao_generica():
    lead = {"id": 1, "custom_fields": []}
    r = gerar_saudacao_personalizada(lead)
    assert r["tipo"] == "generica"
    assert "com quem estou falando" in r["saudacao"].lower()
    assert r["campos_usados"] == []


def test_lead_com_nome_paciente_cita_primeiro_nome():
    lead = {
        "id": 2,
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Maria Silva Santos"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert r["tipo"] == "personalizada"
    assert "Maria" in r["saudacao"]
    assert "Maria Silva Santos" not in r["saudacao"]  # só primeiro nome
    assert "nome_paciente" in r["campos_usados"]


def test_lead_com_medico_karla_recapitula():
    lead = {
        "id": 3,
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "João Pedro"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert "João" in r["saudacao"]
    assert "Dra. Karla" in r["saudacao"]
    assert "vamos seguir de onde paramos" in r["saudacao"].lower()
    assert "medico" in r["campos_usados"]


def test_lead_com_convenio_aceito_cita_convenio():
    lead = {
        "id": 4,
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Carmen Pla"}]},
            {"field_name": "CONVENIO",
             "values": [{"value": "Plan Assiste - MPF (MPU)"}]},
            {"field_name": "UNIDADE",
             "values": [{"value": "Asa Norte"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert "Carmen" in r["saudacao"]
    assert "Plan Assiste" in r["saudacao"]
    assert "Asa Norte" in r["saudacao"]
    assert "convenio" in r["campos_usados"]
    assert "unidade" in r["campos_usados"]


def test_lead_lacuna_longa_180_dias_reconhece_gap():
    lead = {
        "id": 5,
        "updated_at": _ts_dias_atras(220),
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Patricia"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert r["tipo"] == "lacuna_longa"
    assert "meses" in r["saudacao"]
    assert "Patricia" in r["saudacao"]


def test_convenio_nao_se_aplica_nao_cita():
    lead = {
        "id": 6,
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Bruno Santos"}]},
            {"field_name": "CONVENIO",
             "values": [{"value": "Não se aplica"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert "Não se aplica" not in r["saudacao"]
    assert "Bruno" in r["saudacao"]
    assert "Dra. Karla" in r["saudacao"]


def test_saudacao_max_2_paragrafos():
    """Não despeja histórico — máx 2 'parágrafos' separados por \\n\\n."""
    lead = {
        "id": 7,
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Aline"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_name": "CONVENIO",
             "values": [{"value": "TJDFT Pró-Saúde"}]},
            {"field_name": "UNIDADE",
             "values": [{"value": "Águas Claras"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    # Quebra por \n\n e considera paragrafos
    paragrafos = [p for p in r["saudacao"].split("\n\n") if p.strip()]
    assert len(paragrafos) <= 2


def test_pergunta_aberta_sempre_no_fim():
    leads_dict = [
        {"id": 8, "custom_fields": []},
        {"id": 9, "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Teste"}]},
        ]},
    ]
    for lead in leads_dict:
        r = gerar_saudacao_personalizada(lead)
        last_char = r["saudacao"].rstrip()[-1]
        assert last_char == "?", f"Saudação deve terminar com ?: {r['saudacao']}"


def test_caso_real_carmen_24142996():
    """Caso real de hoje 12/06: Carmen Pla Pujades Magalhães.
    Lead que entrou em loop Bug C-26. Versão correta da saudação inicial."""
    lead = {
        "id": 24142996,
        "name": "AGENDAR_ Duas filhas",
        "custom_fields": [
            {"field_name": "1.NOME PACIENTE",
             "values": [{"value": "Carmen Pla Pujades Magalhães"}]},
            {"field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_name": "CONVENIO",
             "values": [{"value": "Plan Assiste - MPF (MPU)"}]},
            {"field_name": "UNIDADE",
             "values": [{"value": "Asa Norte"}]},
        ],
    }
    r = gerar_saudacao_personalizada(lead)
    assert "Carmen" in r["saudacao"]
    assert "Dra. Karla" in r["saudacao"]
    assert "Plan Assiste" in r["saudacao"]
    assert "deixa eu reconsultar" not in r["saudacao"].lower()
    assert r["tipo"] == "personalizada"
