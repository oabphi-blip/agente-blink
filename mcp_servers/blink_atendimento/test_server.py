"""Pytest do blink_atendimento MCP server.

Mocka HTTP client pra não bater no Kommo real. Valida:
    - _limpar_custom_fields traduz field_ids em nomes humanos
    - _resumir_estado extrai último inbound / outbound corretamente
    - ler_chat_completo_lead retorna estrutura esperada
    - desativar_ia_lead usa enum_id 927035
"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from blink_atendimento import server


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    monkeypatch.setenv("KOMMO_TOKEN", "fake-token")
    monkeypatch.setenv("KOMMO_BASE_URL", "https://univeja.kommo.com/api/v4")


@pytest.fixture
def mock_lead_theo_tiago() -> dict:
    """Payload real-like do lead 21759911 (Theo/Tiago)."""
    return {
        "id": 21759911,
        "name": "CAPTAÇÃO ATIVA_ ativado 16:30",
        "status_id": 102560495,
        "pipeline_id": 8601819,
        "custom_fields_values": [
            {"field_id": 1256257, "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_id": 1245125, "values": [{"value": "Asa Norte"}]},
            {"field_id": 853206,  "values": [{"value": "Care Plus"}]},
            {"field_id": 1255757, "values": [{"value": "Theo Bonfada dos Santos"}]},
            {"field_id": 1255761, "values": [{"value": "Tiago Fetter dos santos"}]},
            {"field_id": 1259118, "values": [{"value": "1"}]},
            {"field_id": 1260817, "values": [{"value": "Ativado"}]},
            {"field_id": 1259130, "values": [{"value": "Oftalmopediatria"}]},
            {"field_id": 1259984, "values": [{"value": 1639537200}]},
            {"field_id": 1255723, "values": [{"value": 1754395200}]},  # 1.DIA_CONSULTA
        ],
        "_embedded": {"contacts": [{"id": 999999}]},
    }


class FakeResp:
    def __init__(self, status_code: int, body: dict | list):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


# ─── Tests: _limpar_custom_fields ───────────────────────────────────

class TestLimparCustomFields:
    def test_traduz_field_ids_conhecidos(self, mock_lead_theo_tiago):
        cf = mock_lead_theo_tiago["custom_fields_values"]
        out = server._limpar_custom_fields(cf)
        assert out["MEDICOS"] == "Dra. Karla Delalibera"
        assert out["UNIDADE"] == "Asa Norte"
        assert out["CONVENIO"] == "Care Plus"
        assert out["1.NOME_PACIENTE"] == "Theo Bonfada dos Santos"
        assert out["2.NOME_PACIENTE"] == "Tiago Fetter dos santos"
        assert out["ATIVADO_IA"] == "Ativado"
        assert out["1.DIA_CONSULTA"] == 1754395200

    def test_ignora_field_ids_desconhecidos(self):
        cf = [{"field_id": 999999, "values": [{"value": "lixo"}]}]
        out = server._limpar_custom_fields(cf)
        assert out == {}

    def test_multiselect_vira_lista(self):
        cf = [{
            "field_id": 1256257,
            "values": [
                {"value": "Dra. Karla Delalibera"},
                {"value": "Dr. Fabrício Freitas"},
            ],
        }]
        out = server._limpar_custom_fields(cf)
        assert isinstance(out["MEDICOS"], list)
        assert len(out["MEDICOS"]) == 2


# ─── Tests: _resumir_estado ──────────────────────────────────────────

class TestResumirEstado:
    def test_extrai_ultimo_inbound_e_outbound(self):
        fields = {
            "ATIVADO_IA": "Ativado",
            "1.DIA_CONSULTA": 1754395200,
            "MEDICOS": "Dra. Karla Delalibera",
            "UNIDADE": "Asa Norte",
            "CONVENIO": "Care Plus",
            "ULTIMA_MSG_OUTBOUND": "Última msg da Lia",
        }
        notas = [
            {"texto": "Lia (WhatsApp):\nOlá, tudo bem?",
             "created_at": 100, "created_by": 0},
            {"texto": "Sim, quero agendar pro Theo",
             "created_at": 200, "created_by": 0},
            {"texto": "Lia (WhatsApp):\nOfereço 07/08 10h",
             "created_at": 300, "created_by": 0},
            {"texto": "Confirmo opção 2",
             "created_at": 400, "created_by": 0},
        ]
        resumo = server._resumir_estado(fields, notas)
        assert resumo["ja_agendado"] is True
        assert resumo["ativado_ia"] == "Ativado"
        assert resumo["medico"] == "Dra. Karla Delalibera"
        # Última msg paciente = "Confirmo opção 2"
        assert "opção 2" in (resumo["ultimo_msg_paciente"] or {}).get("texto", "")
        # Última msg Lia = "Ofereço 07/08 10h"
        assert "07/08" in (resumo["ultimo_msg_lia_notas"] or {}).get("texto", "")

    def test_pacientes_populados(self):
        fields = {
            "N_PACIENTES": "1",
            "1.NOME_PACIENTE": "Theo Bonfada dos Santos",
            "2.NOME_PACIENTE": "Tiago Fetter dos santos",
        }
        resumo = server._resumir_estado(fields, [])
        assert resumo["pacientes"]["n"] == "1"
        assert resumo["pacientes"]["1_nome"] == "Theo Bonfada dos Santos"
        assert resumo["pacientes"]["2_nome"] == "Tiago Fetter dos santos"


# ─── Tests: ler_chat_completo_lead (integração com mock HTTP) ────────

class TestLerChatCompletoLead:
    def test_lead_theo_tiago_retorna_estrutura_esperada(
        self, mock_lead_theo_tiago
    ):
        mock_client = MagicMock(spec=httpx.Client)

        def _get(url, **kwargs):
            if "leads/21759911" in url and "notes" not in url:
                return FakeResp(200, mock_lead_theo_tiago)
            if "leads/21759911/notes" in url:
                return FakeResp(200, {
                    "_embedded": {"notes": [
                        {"id": 1, "created_at": 100, "created_by": 0,
                         "note_type": "common",
                         "params": {"text": "Lia (WhatsApp):\nOlá"}},
                        {"id": 2, "created_at": 200, "created_by": 0,
                         "note_type": "common",
                         "params": {"text": "Quero agendar pro Theo"}},
                    ]},
                })
            if "contacts/999999" in url:
                return FakeResp(200, {
                    "custom_fields_values": [{
                        "field_code": "PHONE",
                        "values": [{"value": "+55 61 93222-018"}],
                    }],
                })
            return FakeResp(404, {})

        mock_client.get.side_effect = _get
        server._set_client(mock_client)

        out = server.ler_chat_completo_lead(21759911)

        assert out["erro"] is None
        assert out["lead_id"] == 21759911
        assert out["telefone_contato"] == "556193222018"
        assert out["custom_fields"]["MEDICOS"] == "Dra. Karla Delalibera"
        assert out["custom_fields"]["UNIDADE"] == "Asa Norte"
        assert len(out["notas"]) == 2
        assert out["resumo"]["ja_agendado"] is True
        assert out["resumo"]["medico"] == "Dra. Karla Delalibera"

    def test_lead_inexistente_retorna_erro(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = FakeResp(404, {})
        server._set_client(mock_client)

        out = server.ler_chat_completo_lead(99999999)
        assert "não encontrado" in (out.get("erro") or "")


# ─── Tests: desativar_ia_lead ───────────────────────────────────────

class TestDesativarIA:
    def test_envia_patch_com_enum_desativado(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.patch.return_value = FakeResp(200, {})
        mock_client.post.return_value = FakeResp(200, {})
        server._set_client(mock_client)

        out = server.desativar_ia_lead(12345, motivo="teste")

        assert out["ok"] is True
        assert out["ativado_ia"] == "Desativado"
        # Confirma que enum_id correto foi enviado
        call_args = mock_client.patch.call_args
        payload = call_args.kwargs["json"]
        cfv = payload["custom_fields_values"][0]
        assert cfv["field_id"] == 1260817
        assert cfv["values"][0]["enum_id"] == 927035
