"""Pytest da ponte Slack → auditoria.

Cobre:
 - extração lead/paciente do texto
 - mapeamento user_id → Assinante via env
 - parser de payload Slack reaction_added
 - processador completo (com buscar_mensagem mockado)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.slack_auditoria import (  # noqa: E402
    Assinante,
    EventoReaction,
    ResultadoProcessamento,
    carregar_mapping_env,
    extrair_lead_paciente,
    parsear_reaction_event,
    processar_evento_slack,
)


# ----------------------------------------------------------------------
# Extração lead/paciente do texto
# ----------------------------------------------------------------------

class TestExtrairLeadPaciente:

    def test_formato_padrao(self):
        texto = (
            ":warning: *Auditoria pós-consulta — discrepância detectada*\n"
            "Lead: 24053159 · Paciente 1: Daniel Silva\n"
            "Médico: Dra Karla · Unidade: Águas Claras"
        )
        assert extrair_lead_paciente(texto) == (24053159, 1)

    def test_formato_compacto(self):
        assert extrair_lead_paciente("Lead 12345 Paciente 2") == (12345, 2)

    def test_paciente_3(self):
        assert extrair_lead_paciente("Lead: 99999 · Paciente 3: João") == (99999, 3)

    def test_case_insensitive(self):
        assert extrair_lead_paciente("LEAD: 1 PACIENTE: 1") == (1, 1)

    def test_sem_match_devolve_none(self):
        assert extrair_lead_paciente("texto sem lead nem paciente") is None
        assert extrair_lead_paciente("") is None
        assert extrair_lead_paciente("Lead: abc Paciente xyz") is None


# ----------------------------------------------------------------------
# Mapeamento env
# ----------------------------------------------------------------------

class TestCarregarMapping:

    def test_env_vazia_retorna_vazio(self, monkeypatch):
        monkeypatch.delenv("SLACK_AUDIT_MAPPING_JSON", raising=False)
        assert carregar_mapping_env() == {}

    def test_json_invalido_retorna_vazio(self, monkeypatch):
        monkeypatch.setenv("SLACK_AUDIT_MAPPING_JSON", "{nao é json")
        assert carregar_mapping_env() == {}

    def test_mapping_basico(self, monkeypatch):
        mapping = {
            "U01ABC": "sec:asa-norte:Maria Santos",
            "U02DEF": "med:karla:Dra Karla Delalíbera",
        }
        monkeypatch.setenv("SLACK_AUDIT_MAPPING_JSON", json.dumps(mapping))
        out = carregar_mapping_env()
        assert "U01ABC" in out
        assert out["U01ABC"].papel == "sec"
        assert out["U01ABC"].slug == "asa-norte"
        assert out["U01ABC"].nome == "Maria Santos"
        assert out["U02DEF"].papel == "med"

    def test_papel_invalido_ignora(self, monkeypatch):
        mapping = {
            "U_OK": "sec:asa-norte:Ana",
            "U_BAD": "ceo:tudo:Boss",
        }
        monkeypatch.setenv("SLACK_AUDIT_MAPPING_JSON", json.dumps(mapping))
        out = carregar_mapping_env()
        assert "U_OK" in out
        assert "U_BAD" not in out

    def test_formato_mal_formado_ignora(self, monkeypatch):
        mapping = {
            "U_OK": "sec:asa-norte:Ana",
            "U_BAD": "so-uma-string-sem-colon",
        }
        monkeypatch.setenv("SLACK_AUDIT_MAPPING_JSON", json.dumps(mapping))
        out = carregar_mapping_env()
        assert "U_OK" in out
        assert "U_BAD" not in out


class TestPapelCompleto:

    def test_secretaria(self):
        a = Assinante(papel="sec", slug="asa-norte", nome="X")
        assert a.papel_completo == "secretaria_asa_norte"

    def test_medico(self):
        a = Assinante(papel="med", slug="karla", nome="X")
        assert a.papel_completo == "medico_karla"


# ----------------------------------------------------------------------
# Parser de evento Slack
# ----------------------------------------------------------------------

class TestParsearEvento:

    def _payload_valido(self, **overrides):
        base = {
            "type": "event_callback",
            "event": {
                "type": "reaction_added",
                "user": "U01ABC",
                "reaction": "white_check_mark",
                "item": {"type": "message", "channel": "C123", "ts": "1.0"},
            },
        }
        base.update(overrides)
        return base

    def test_payload_valido(self):
        out = parsear_reaction_event(self._payload_valido())
        assert out is not None
        assert out.user_id == "U01ABC"
        assert out.reaction == "white_check_mark"
        assert out.channel_id == "C123"

    def test_tipo_errado_none(self):
        assert parsear_reaction_event({"type": "url_verification"}) is None
        assert parsear_reaction_event({}) is None
        assert parsear_reaction_event(None) is None

    def test_evento_nao_reaction_none(self):
        p = self._payload_valido()
        p["event"]["type"] = "message"
        assert parsear_reaction_event(p) is None

    def test_item_nao_message_ignora(self):
        p = self._payload_valido()
        p["event"]["item"]["type"] = "file"
        assert parsear_reaction_event(p) is None

    def test_user_vazio_ignora(self):
        p = self._payload_valido()
        p["event"]["user"] = ""
        assert parsear_reaction_event(p) is None


# ----------------------------------------------------------------------
# Processamento end-to-end
# ----------------------------------------------------------------------

class TestProcessarEvento:

    def _mapping(self):
        return {
            "U_SEC_AN": Assinante(papel="sec", slug="asa-norte", nome="Maria"),
            "U_SEC_AC": Assinante(papel="sec", slug="aguas-claras", nome="Joana"),
            "U_MED_KAR": Assinante(papel="med", slug="karla", nome="Dra Karla"),
        }

    def _payload(self, user, reaction="white_check_mark", channel="C_AUD"):
        return {
            "type": "event_callback",
            "event": {
                "type": "reaction_added",
                "user": user,
                "reaction": reaction,
                "item": {"type": "message", "channel": channel, "ts": "X"},
            },
        }

    def _mensagem_padrao(self):
        return "Lead: 24053159 · Paciente 1: Daniel"

    def test_assinatura_secretaria_ok(self):
        def buscar(ch, ts):
            return self._mensagem_padrao()
        r = processar_evento_slack(
            self._payload("U_SEC_AN"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
        )
        assert r.acao == "assinar"
        assert r.lead_id == 24053159
        assert r.paciente_idx == 1
        assert r.papel == "secretaria_asa_norte"
        assert r.autor == "Maria"

    def test_user_fora_do_mapping_ignora(self):
        def buscar(ch, ts):
            return self._mensagem_padrao()
        r = processar_evento_slack(
            self._payload("U_DESCONHECIDO"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
        )
        assert r.acao == "ignorar"
        assert "fora do mapping" in r.motivo

    def test_reaction_errada_ignora(self):
        def buscar(ch, ts):
            return self._mensagem_padrao()
        r = processar_evento_slack(
            self._payload("U_SEC_AN", reaction="thumbsdown"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
        )
        assert r.acao == "ignorar"

    def test_canal_errado_ignora(self):
        def buscar(ch, ts):
            return self._mensagem_padrao()
        r = processar_evento_slack(
            self._payload("U_SEC_AN", channel="C_OUTRO"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
            canal_esperado="C_AUD",
        )
        assert r.acao == "ignorar"

    def test_mensagem_sem_lead_da_erro(self):
        def buscar(ch, ts):
            return "mensagem sem identificação"
        r = processar_evento_slack(
            self._payload("U_SEC_AN"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
        )
        assert r.acao == "erro"

    def test_buscar_mensagem_none_eh_erro(self):
        r = processar_evento_slack(
            self._payload("U_SEC_AN"),
            mapping=self._mapping(),
            buscar_mensagem=None,
        )
        assert r.acao == "erro"

    def test_medico_karla_assina(self):
        def buscar(ch, ts):
            return "Lead: 99 · Paciente 2: x"
        r = processar_evento_slack(
            self._payload("U_MED_KAR"),
            mapping=self._mapping(),
            buscar_mensagem=buscar,
        )
        assert r.acao == "assinar"
        assert r.papel == "medico_karla"
        assert r.lead_id == 99 and r.paciente_idx == 2
