"""Pytest das tools estruturadas da Lia.

Cobre:
 - schemas válidos (Anthropic tool_use)
 - handler oferecer_slot: validação contra agenda real, grava Redis
 - handler confirmar_dados: validação formato + escrita Kommo
 - handler gravar_agendamento: pré-condições duras
 - dispatcher genérico
 - toggle global LIA_TOOLS_ENABLED
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.tools_lia import (  # noqa: E402
    ALL_TOOLS,
    HANDLERS,
    ResultadoTool,
    TOOL_CONFIRMAR_DADOS_PACIENTE,
    TOOL_GRAVAR_AGENDAMENTO_MEDWARE,
    TOOL_OFERECER_SLOT,
    executar_tool,
    handle_confirmar_dados_paciente,
    handle_gravar_agendamento_medware,
    handle_oferecer_slot,
    tools_habilitadas,
)


# ----------------------------------------------------------------------
# Schemas — sanidade
# ----------------------------------------------------------------------

class TestSchemas:

    def test_3_tools_disponíveis(self):
        assert len(ALL_TOOLS) == 3
        nomes = {t["name"] for t in ALL_TOOLS}
        assert nomes == {
            "oferecer_slot",
            "confirmar_dados_paciente",
            "gravar_agendamento_medware",
        }

    @pytest.mark.parametrize("tool", ALL_TOOLS)
    def test_estrutura_anthropic_completa(self, tool):
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]
        assert "required" in tool["input_schema"]

    def test_oferecer_slot_limita_2_max(self):
        items = TOOL_OFERECER_SLOT["input_schema"]["properties"]["slots"]
        assert items["maxItems"] == 2


# ----------------------------------------------------------------------
# Toggle
# ----------------------------------------------------------------------

class TestToggle:

    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LIA_TOOLS_ENABLED", raising=False)
        assert tools_habilitadas() is False

    @pytest.mark.parametrize("val,esperado", [
        ("1", True), ("true", True), ("YES", True),
        ("0", False), ("false", False), ("", False),
    ])
    def test_valores(self, monkeypatch, val, esperado):
        monkeypatch.setenv("LIA_TOOLS_ENABLED", val)
        assert tools_habilitadas() is esperado


# ----------------------------------------------------------------------
# handle_oferecer_slot
# ----------------------------------------------------------------------

class TestOferecerSlot:

    def test_sem_slots_retorna_erro(self):
        r = handle_oferecer_slot({}, None)
        assert r.erro is not None
        assert "sem slots" in r.erro

    def test_slot_fora_da_agenda_real_eh_erro(self):
        """Lia tenta oferecer slot inventado → handler bloqueia."""
        ctx = {
            "agenda": [
                {"data_iso": "2026-06-02", "hora": "09:00"},
                {"data_iso": "2026-06-09", "hora": "09:30"},
            ],
        }
        inputs = {
            "slots": [
                {"data_iso": "2026-06-03", "hora": "14:00",
                 "dia_semana": "quarta-feira"},  # NÃO EXISTE
            ],
            "mensagem_humana": "Tenho 03/06 14h pra você",
        }
        r = handle_oferecer_slot(inputs, ctx)
        assert r.erro is not None
        assert "AGENDA REAL" in r.erro

    def test_slot_valido_passa(self):
        ctx = {
            "agenda": [
                {"data_iso": "2026-06-02", "hora": "09:00"},
            ],
            "conversation_key": "abc",
        }
        inputs = {
            "slots": [
                {"data_iso": "2026-06-02", "hora": "09:00",
                 "dia_semana": "terça-feira"},
            ],
            "mensagem_humana": "Terça, 02/06 às 09h. Fica bom?",
        }
        r = handle_oferecer_slot(inputs, ctx, redis_client=None)
        assert r.erro is None
        assert "02/06" in r.texto_para_paciente or "09h" in r.texto_para_paciente

    def test_grava_oferta_em_redis(self):
        ctx = {
            "agenda": [{"data_iso": "2026-06-02", "hora": "09:00"}],
            "conversation_key": "convo123",
        }
        fake_redis = MagicMock()
        inputs = {
            "slots": [{"data_iso": "2026-06-02", "hora": "09:00",
                       "dia_semana": "terça-feira"}],
            "mensagem_humana": "ok",
        }
        handle_oferecer_slot(inputs, ctx, redis_client=fake_redis)
        assert fake_redis.setex.called
        key = fake_redis.setex.call_args[0][0]
        assert "blink:oferta:convo123" in key


# ----------------------------------------------------------------------
# handle_confirmar_dados_paciente
# ----------------------------------------------------------------------

class TestConfirmarDados:

    def test_nome_invalido_eh_erro(self):
        r = handle_confirmar_dados_paciente(
            {"nome_completo_paciente": "Daniel",
             "mensagem_humana": "ok"},
            caller_context={},
        )
        assert r.erro is not None
        assert "nome" in r.erro.lower()

    def test_data_invalida_eh_erro(self):
        r = handle_confirmar_dados_paciente(
            {"data_nascimento": "ontem", "mensagem_humana": "ok"},
            caller_context={},
        )
        assert r.erro is not None

    def test_cpf_invalido_eh_erro(self):
        r = handle_confirmar_dados_paciente(
            {"cpf_paciente": "123", "mensagem_humana": "ok"},
            caller_context={},
        )
        assert r.erro is not None

    def test_dados_validos_grava_no_kommo(self):
        fake_kommo = MagicMock()
        ctx = {"lead_id": 24053159}
        inputs = {
            "nome_completo_paciente": "Daniel Silva Souza",
            "data_nascimento": "09/02/2023",
            "cpf_responsavel": "01305472633",
            "mensagem_humana": "Anotei tudo, Juliene!",
        }
        r = handle_confirmar_dados_paciente(
            inputs, caller_context=ctx, kommo_client=fake_kommo,
        )
        assert r.erro is None
        assert fake_kommo.update_lead_fields.called
        # Check os campos enviados
        args = fake_kommo.update_lead_fields.call_args
        assert args[0][0] == 24053159
        assert "nome_paciente" in args[0][1]


# ----------------------------------------------------------------------
# handle_gravar_agendamento_medware
# ----------------------------------------------------------------------

class TestGravarAgendamento:

    def test_checklist_incompleto_bloqueia(self):
        ctx = {
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": False,
                "campos_pendentes": ["CPF do paciente"],
            },
        }
        inputs = {
            "cod_agenda": 5, "data_iso": "2026-06-02",
            "hora": "09:00", "mensagem_humana": "ok",
        }
        r = handle_gravar_agendamento_medware(inputs, ctx)
        assert r.erro is not None
        assert "checklist" in r.erro.lower()

    def test_slot_fora_da_agenda_bloqueia(self):
        ctx = {
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": True},
            "agenda": [{"data_iso": "2026-06-02", "hora": "09:00"}],
        }
        inputs = {
            "cod_agenda": 99, "data_iso": "2099-12-31",
            "hora": "23:59", "mensagem_humana": "x",
        }
        r = handle_gravar_agendamento_medware(inputs, ctx)
        assert r.erro is not None
        assert "AGENDA REAL" in r.erro

    def test_tudo_ok_chama_medware_e_marca_dedup(self):
        """Pós task #208 (04/06/2026): handler chama medware.criar_agendamento
        direto E marca chave dedup 24h 'blink:agendamento_gravado:'.

        Antes era stub que só escrevia 'blink:tool_gravacao_solicitada:' e
        delegava pra um executor_agendamento.py que NUNCA EXISTIU.
        """
        ctx = {
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": True},
            "agenda": [{"data_iso": "2026-06-02", "hora": "09:00"}],
            "conversation_key": "convo1",
            "known": {
                "nome_paciente": "Teste",
                "cpf": "00000000191",
                "data_nasc": "01/01/1990",
                "convenio": "Saúde Caixa",
                "medico": "Dra. Karla Delalibera",
                "unidade": "Asa Norte",
            },
        }
        inputs = {
            "cod_agenda": 5, "data_iso": "2026-06-02",
            "hora": "09:00",
            "mensagem_humana": "Combinado, terça 02/06 09h.",
        }
        fake_redis = MagicMock()
        fake_redis.get.return_value = None  # sem dedup anterior
        fake_medware = MagicMock()
        fake_medware.criar_agendamento.return_value = {
            "ok": True, "cod_agendamento": 12345,
        }
        r = handle_gravar_agendamento_medware(
            inputs, ctx,
            medware_client=fake_medware, redis_client=fake_redis,
        )
        assert r.erro is None
        # Medware FOI chamado
        fake_medware.criar_agendamento.assert_called_once()
        # Redis marca dedup pós-sucesso
        assert fake_redis.setex.called
        chaves = [c.args[0] for c in fake_redis.setex.call_args_list]
        assert any("agendamento_gravado" in k for k in chaves)


# ----------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------

class TestDispatcher:

    def test_tool_desconhecida_retorna_erro(self):
        r = executar_tool("tool_que_nao_existe", {}, {})
        assert r.erro is not None
        assert "desconhecida" in r.erro

    def test_oferecer_slot_via_dispatcher(self):
        ctx = {"agenda": [{"data_iso": "2026-06-02", "hora": "09:00"}],
               "conversation_key": "x"}
        inputs = {
            "slots": [{"data_iso": "2026-06-02", "hora": "09:00",
                       "dia_semana": "terça-feira"}],
            "mensagem_humana": "Tenho terça 09h pra você.",
        }
        r = executar_tool("oferecer_slot", inputs, ctx)
        assert r.erro is None

    def test_exception_no_handler_e_capturada(self, monkeypatch):
        """Handler que joga exceção → executar_tool captura e devolve erro."""
        from voice_agent import tools_lia
        def handler_quebrado(inputs, **kwargs):
            raise RuntimeError("boom")
        monkeypatch.setitem(tools_lia.HANDLERS,
                            "confirmar_dados_paciente", handler_quebrado)
        r = executar_tool(
            "confirmar_dados_paciente",
            {"mensagem_humana": "ok"},
            {},
        )
        assert r.erro is not None
        assert "boom" in r.erro
