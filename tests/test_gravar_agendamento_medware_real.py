"""Blindagem do fix do gap crítico de 15 dias (task #208 / 04/06/2026).

Antes do fix: `handle_gravar_agendamento_medware` só escrevia uma flag
em Redis (`blink:tool_gravacao_solicitada:{convo}`) e deixava um TODO
referenciando um `executor_agendamento.py` que NUNCA FOI CRIADO.
Resultado: Lia conversava, oferecia slot, paciente aceitava — e a
gravação no Medware dependia de humano (Stephany/Ariany).

Depois do fix: handler chama `medware_client.criar_agendamento()`
direto, com map COD_MEDICO/COD_UNIDADE por nome humano. Dedup Redis
24h evita re-gravação. Logs estruturados pra rastreabilidade.

Casos cobertos:
  1. Maps COD_MEDICO_POR_NOME / COD_UNIDADE_POR_NOME
  2. Handler chama criar_agendamento com args certos
  3. Sucesso Medware → marca Redis dedup
  4. Falha Medware → retorna erro estruturado
  5. Re-call em conversa já gravada → dedup, NÃO chama Medware de novo
  6. Sem medware_client (modo teste) → fallback flag Redis legado
"""
from unittest.mock import MagicMock

from voice_agent.tools_lia import (
    cod_medico_por_nome,
    cod_unidade_por_nome,
    handle_gravar_agendamento_medware,
    COD_MEDICO_POR_NOME,
    COD_UNIDADE_POR_NOME,
)


# ---------------------------------------------------------------------------
# Maps codMedico / codUnidade
# ---------------------------------------------------------------------------

def test_cod_medico_karla_variantes():
    assert cod_medico_por_nome("Karla") == 12080
    assert cod_medico_por_nome("Dra. Karla Delalibera") == 12080
    assert cod_medico_por_nome("dra karla") == 12080
    assert cod_medico_por_nome("DRA. KARLA") == 12080
    assert cod_medico_por_nome("  Karla  ") == 12080


def test_cod_medico_fabricio_variantes():
    assert cod_medico_por_nome("Fabricio") == 12081
    assert cod_medico_por_nome("Fabrício") == 12081
    assert cod_medico_por_nome("Dr. Fabrício Freitas") == 12081
    assert cod_medico_por_nome("dr. fabricio freitas") == 12081


def test_cod_medico_desconhecido_cai_em_karla_default():
    """Default seguro: cai na Karla (oftalmopediatra principal)."""
    assert cod_medico_por_nome("") == 12080
    assert cod_medico_por_nome("Dr. Inexistente") == 12080


def test_cod_unidade_asa_norte():
    assert cod_unidade_por_nome("Asa Norte") == 5
    assert cod_unidade_por_nome("asa norte") == 5
    assert cod_unidade_por_nome("AN") == 5


def test_cod_unidade_aguas_claras():
    assert cod_unidade_por_nome("Águas Claras") == 3
    assert cod_unidade_por_nome("Aguas Claras") == 3
    assert cod_unidade_por_nome("AC") == 3


def test_cod_unidade_default_asa_norte():
    """Default seguro: Asa Norte (unidade principal)."""
    assert cod_unidade_por_nome("") == 5
    assert cod_unidade_por_nome("Bairro X") == 5


# ---------------------------------------------------------------------------
# Handler — sucesso end-to-end
# ---------------------------------------------------------------------------

def _ctx_pronto() -> dict:
    """ctx mínimo válido pro handler aceitar gravação."""
    return {
        "conversation_key": "conv-test-001",
        "known": {
            "nome_paciente": "Maria Teste da Silva",
            "cpf": "00000000191",
            "data_nasc": "01/01/1990",
            "celular": "61999999999",
            "convenio": "Saúde Caixa",
            "medico": "Dra. Karla Delalibera",
            "unidade": "Asa Norte",
        },
        "checklist_dados_minimos": {"pronto_para_oferecer_slot": True},
        "agenda": [{"data_iso": "2026-06-08", "hora": "10:30"}],
    }


def test_handler_chama_criar_agendamento_com_args_certos():
    medware = MagicMock()
    medware.criar_agendamento.return_value = {
        "ok": True, "cod_agendamento": 99999,
    }
    redis_mock = MagicMock()
    redis_mock.get.return_value = None  # não tem dedup anterior

    inputs = {
        "cod_agenda": 1234,
        "data_iso": "2026-06-08",
        "hora": "10:30",
        "mensagem_humana": "Confirmado!",
    }

    res = handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=medware, redis_client=redis_mock,
    )

    # Chamou Medware com args corretos
    medware.criar_agendamento.assert_called_once()
    kwargs = medware.criar_agendamento.call_args.kwargs
    assert kwargs["cod_medico"] == 12080
    assert kwargs["cod_unidade"] == 5
    assert kwargs["cod_agenda"] == 1234
    assert kwargs["data_hora"] == "2026-06-08T10:30"
    assert kwargs["nome"] == "Maria Teste da Silva"
    assert kwargs["cpf"] == "00000000191"
    assert kwargs["convenio"] == "Saúde Caixa"

    # Resposta humana preservada + efeitos colaterais
    assert res.texto_para_paciente == "Confirmado!"
    assert any("MEDWARE OK" in e for e in res.efeitos_colaterais)
    assert any("99999" in e for e in res.efeitos_colaterais)
    assert res.erro is None


def test_handler_marca_redis_dedup_apos_sucesso():
    medware = MagicMock()
    medware.criar_agendamento.return_value = {
        "ok": True, "cod_agendamento": 88888,
    }
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=medware, redis_client=redis_mock,
    )

    # Chamou setex com chave dedup 24h
    setex_call = None
    for call in redis_mock.setex.call_args_list:
        if "agendamento_gravado" in call.args[0]:
            setex_call = call
            break
    assert setex_call is not None
    assert setex_call.args[1] == 86400  # 24h TTL
    payload = setex_call.args[2]
    assert "88888" in payload


# ---------------------------------------------------------------------------
# Handler — falhas
# ---------------------------------------------------------------------------

def test_handler_medware_falha_retorna_erro_estruturado():
    medware = MagicMock()
    medware.criar_agendamento.return_value = {
        "ok": False,
        "motivo": "convenio_desconhecido",
        "detalhe": "plano X não mapeado",
    }
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=medware, redis_client=redis_mock,
    )

    assert res.erro is not None
    assert "convenio_desconhecido" in res.erro
    assert res.texto_para_paciente == ""  # não responde paciente em caso de erro


def test_handler_medware_exception_NAO_propaga_quebra_conversa():
    """Exception interna do Medware vira erro estruturado, não 500."""
    medware = MagicMock()
    medware.criar_agendamento.side_effect = RuntimeError("timeout")
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=medware, redis_client=redis_mock,
    )

    assert res.erro is not None
    assert "medware_exception" in res.erro
    assert "timeout" in res.erro


# ---------------------------------------------------------------------------
# Dedup — não regrava se já gravou nas últimas 24h
# ---------------------------------------------------------------------------

def test_handler_dedup_nao_chama_medware_se_ja_gravado():
    medware = MagicMock()
    redis_mock = MagicMock()
    # Simula que já existe registro de gravação anterior
    redis_mock.get.return_value = b'{"cod_agendamento": 77777}'

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=medware, redis_client=redis_mock,
    )

    # Medware NÃO foi chamado
    medware.criar_agendamento.assert_not_called()
    # Resposta humana preservada
    assert res.texto_para_paciente == "ok"
    assert any("dedup" in e for e in res.efeitos_colaterais)


# ---------------------------------------------------------------------------
# Pré-validações (mantidas do código original)
# ---------------------------------------------------------------------------

def test_handler_bloqueia_se_checklist_incompleto():
    medware = MagicMock()
    redis_mock = MagicMock()
    ctx = _ctx_pronto()
    ctx["checklist_dados_minimos"]["pronto_para_oferecer_slot"] = False
    ctx["checklist_dados_minimos"]["campos_pendentes"] = ["cpf"]

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, ctx, medware_client=medware, redis_client=redis_mock,
    )

    assert res.erro is not None
    assert "checklist incompleto" in res.erro
    medware.criar_agendamento.assert_not_called()


def test_handler_bloqueia_slot_fora_agenda_real():
    medware = MagicMock()
    redis_mock = MagicMock()
    ctx = _ctx_pronto()
    # agenda tem (2026-06-08, 10:30) mas tool pede (2026-06-09, 15:00)

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-09", "hora": "15:00",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, ctx, medware_client=medware, redis_client=redis_mock,
    )

    assert res.erro is not None
    assert "NÃO está na AGENDA REAL" in res.erro
    medware.criar_agendamento.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback — sem medware_client (modo teste/unit)
# ---------------------------------------------------------------------------

def test_handler_sem_medware_client_cai_em_flag_redis_legado():
    """Compatibilidade: se ninguém passar medware_client, ainda funciona."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    inputs = {"cod_agenda": 1, "data_iso": "2026-06-08", "hora": "10:30",
              "mensagem_humana": "ok"}
    res = handle_gravar_agendamento_medware(
        inputs, _ctx_pronto(), medware_client=None, redis_client=redis_mock,
    )

    # Texto preservado, sem erro
    assert res.texto_para_paciente == "ok"
    assert res.erro is None
    # Flag legada
    assert any("solicitação gravada" in e for e in res.efeitos_colaterais)


# ---------------------------------------------------------------------------
# Sanity check — maps refletem dados reais Medware (04/06/2026)
# ---------------------------------------------------------------------------

def test_maps_consistencia_basica():
    """Sanity check pra não quebrar nada se alguém editar os maps."""
    # Karla = 12080 (oftalmopediatra principal)
    assert COD_MEDICO_POR_NOME["karla"] == 12080
    # Fabrício = 12081 (catarata)
    assert COD_MEDICO_POR_NOME["fabricio"] == 12081
    # Asa Norte = 5
    assert COD_UNIDADE_POR_NOME["asa norte"] == 5
    # Águas Claras = 3
    assert COD_UNIDADE_POR_NOME["aguas claras"] == 3
