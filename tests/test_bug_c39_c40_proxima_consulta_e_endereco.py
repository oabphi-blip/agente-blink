"""Bug C-39 + C-40 — modo acompanhamento (PRÓXIMA CONSULTA 106157327) +
resumo + endereço pós-agendamento.

C-39: Lia em lead PRÓXIMA CONSULTA (status_id=106157327) NÃO oferece
      slot, NÃO afirma "consulta marcada" com dia_consulta_ts no passado.
      2 filtros SEMPRE-ON (independem de FILTROS_LEGACY).

C-40: `handle_gravar_agendamento_medware` sucesso → dispara 2 mensagens
      sequenciais: (1) resumo canônico (2) endereço via
      resolver_modelo_localizacao.

Tudo mockado. Não bate rede.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from voice_agent import responder as _responder
from voice_agent.responder import (
    _viola_agendar_em_proxima_consulta,
    _viola_afirmou_consulta_marcada_data_passada,
    _scrub_prohibited,
)
from voice_agent.mensagens_ciclo import montar_resumo_agendamento
from voice_agent.templates_ativacao import resolver_modelo_localizacao
from voice_agent.tools_lia import handle_gravar_agendamento_medware


# ---------------------------------------------------------------------------
# 1. C-39: lead status=106157327 + Lia disse "posso agendar" → filtro pega
# ---------------------------------------------------------------------------
def test_c39_agendar_em_proxima_consulta_bloqueia(monkeypatch):
    monkeypatch.setenv("FILTROS_LEGACY", "0")
    ctx = {
        "lead": {
            "status_id": 106157327,
            "known": {"ultima_medware": "10/06/2026"},
        },
        "known": {"ultima_medware": "10/06/2026"},
    }
    text = "Perfeito! posso agendar sua próxima consulta agora."
    assert _viola_agendar_em_proxima_consulta(text, ctx) is True

    resultado = _scrub_prohibited(text, ctx)
    assert resultado != text
    assert "próxima consulta está prevista" in resultado
    assert "10/06/2026" in resultado


# ---------------------------------------------------------------------------
# 2. C-39: lead status=106157327 + dia_consulta_ts PASSADO + Lia diz "marcada"
# ---------------------------------------------------------------------------
def test_c39_afirmou_consulta_marcada_data_passada_bloqueia(monkeypatch):
    monkeypatch.setenv("FILTROS_LEGACY", "0")
    ts_passado = time.time() - 30 * 86400  # 30 dias atrás
    ctx = {
        "lead": {
            "status_id": 106157327,
            "known": {
                "dia_consulta_ts": ts_passado,
                "ultima_medware": "01/06/2026",
            },
        },
    }
    text = "Sua consulta marcada é só comparecer no dia."
    assert _viola_afirmou_consulta_marcada_data_passada(text, ctx) is True

    resultado = _scrub_prohibited(text, ctx)
    assert resultado != text
    assert "próxima consulta está prevista" in resultado


# ---------------------------------------------------------------------------
# 3. C-39: lead status=102560495 (3-AGENDAR) + "posso agendar" → NÃO viola
# ---------------------------------------------------------------------------
def test_c39_agendar_em_status_agendar_nao_bloqueia():
    ctx = {"lead": {"status_id": 102560495, "known": {}}}
    text = "Perfeito! posso agendar sua próxima consulta agora."
    assert _viola_agendar_em_proxima_consulta(text, ctx) is False


# ---------------------------------------------------------------------------
# 4. C-40: handle_gravar_agendamento_medware sucesso → dispara 2 sends
# ---------------------------------------------------------------------------
def test_c40_gravar_agendamento_dispara_resumo_e_endereco():
    fake_wa = MagicMock()
    fake_wa.send_text = MagicMock(return_value={"ok": True})

    fake_medware = MagicMock()
    fake_medware.criar_agendamento = MagicMock(
        return_value={"ok": True, "cod_agendamento": 12345}
    )

    fake_redis = MagicMock()
    fake_redis.get = MagicMock(return_value=None)
    fake_redis.setex = MagicMock(return_value=True)

    caller_context = {
        "conversation_key": "conv-c40-test",
        "checklist_dados_minimos": {
            "pronto_para_oferecer_slot": True,
            "campos_pendentes": [],
        },
        "agenda": [{"data_iso": "2026-07-15", "hora": "09:30"}],
        "name": "Marcela",
        "telefone": "5561999998888",
        "whatsapp_cloud_client": fake_wa,
        "known": {
            "medico": "Karla Delalíbera",
            "unidade": "Águas Claras",
            "nome_paciente": "Marcela Torres",
            "cpf": "12345678900",
            "data_nasc": "1990-01-01",
            "celular": "5561999998888",
            "convenio": "Saúde Caixa",
            "nome_contato": "Marcela",
        },
    }

    inputs = {
        "cod_agenda": 42,
        "data_iso": "2026-07-15",
        "hora": "09:30",
        "mensagem_humana": "Combinado! Agendado.",
    }

    res = handle_gravar_agendamento_medware(
        inputs=inputs,
        caller_context=caller_context,
        medware_client=fake_medware,
        redis_client=fake_redis,
    )

    assert res.erro is None or res.erro == ""
    # Deve ter enviado EXATAMENTE 2 mensagens (resumo + endereço)
    assert fake_wa.send_text.call_count == 2
    # 1ª msg = resumo (contém "Resumo")
    call_1_text = fake_wa.send_text.call_args_list[0][0][1]
    assert "📋 Resumo" in call_1_text or "Resumo" in call_1_text
    # 2ª msg = endereço (contém "Águas Claras")
    call_2_text = fake_wa.send_text.call_args_list[1][0][1]
    assert "Águas Claras" in call_2_text


# ---------------------------------------------------------------------------
# 5. C-40: montar_resumo_agendamento tem TODOS os campos
# ---------------------------------------------------------------------------
def test_c40_montar_resumo_contem_todos_campos():
    resumo = montar_resumo_agendamento(
        paciente="Marcela Torres",
        dia_hora="15/07 às 09:30",
        medico="Dra. Karla Delalíbera",
        unidade="Águas Claras",
        convenio_ou_valor="Saúde Caixa",
    )
    assert "Marcela Torres" in resumo
    assert "15/07 às 09:30" in resumo
    assert "Dra. Karla Delalíbera" in resumo
    assert "Águas Claras" in resumo
    assert "Saúde Caixa" in resumo
    assert "Resumo" in resumo


# ---------------------------------------------------------------------------
# 6. C-40: resolver_modelo_localizacao Asa Norte → contém "Asa Norte"
# ---------------------------------------------------------------------------
def test_c40_resolver_localizacao_asa_norte():
    texto = resolver_modelo_localizacao(
        unidade="Asa Norte",
        nome_contato="Marcela",
        dia_hora_consulta="15/07 às 09:30",
    )
    assert "Asa Norte" in texto


# ---------------------------------------------------------------------------
# 7. C-40: resolver_modelo_localizacao Águas Claras → contém "Águas Claras"
# ---------------------------------------------------------------------------
def test_c40_resolver_localizacao_aguas_claras():
    texto = resolver_modelo_localizacao(
        unidade="Águas Claras",
        nome_contato="Marcela",
        dia_hora_consulta="15/07 às 09:30",
    )
    assert "Águas Claras" in texto


# ---------------------------------------------------------------------------
# 8. Prompt tem regras FE.1, FE.2, FE.3
# ---------------------------------------------------------------------------
def test_prompt_master_tem_regras_fe():
    import pathlib
    p = pathlib.Path(
        "voice_agent/knowledge_base/_MASTER_INSTRUCTION.md"
    )
    conteudo = p.read_text(encoding="utf-8")
    assert "FE.1" in conteudo
    assert "FE.2" in conteudo
    assert "FE.3" in conteudo


# ---------------------------------------------------------------------------
# 9. VERSAO_PROMPT bumped
# ---------------------------------------------------------------------------
def test_versao_prompt_bumped():
    import pathlib
    p = pathlib.Path(
        "voice_agent/knowledge_base/_MASTER_INSTRUCTION.md"
    )
    conteudo = p.read_text(encoding="utf-8")
    assert (
        "2026-07-01-c39-proxima-consulta+c40-endereco-pos-agenda"
        in conteudo
    )


# ---------------------------------------------------------------------------
# 10. Filtros SEMPRE-ON: FILTROS_LEGACY=0 e ainda assim disparam
# ---------------------------------------------------------------------------
def test_c39_filtros_sempre_on_independem_filtros_legacy(monkeypatch):
    monkeypatch.setenv("FILTROS_LEGACY", "0")

    # Filtro C-39a: lead PRÓXIMA CONSULTA + "posso agendar" ainda bloqueia
    ctx_a = {
        "lead": {
            "status_id": 106157327,
            "known": {"ultima_medware": "15/06/2026"},
        },
    }
    text_a = "posso agendar sua próxima consulta?"
    assert _viola_agendar_em_proxima_consulta(text_a, ctx_a) is True
    scrub_a = _scrub_prohibited(text_a, ctx_a)
    assert scrub_a != text_a
    assert "próxima consulta está prevista" in scrub_a

    # Filtro C-39b: dia_consulta_ts PASSADO + "consulta marcada" bloqueia
    ctx_b = {
        "lead": {
            "status_id": 106157327,
            "known": {
                "dia_consulta_ts": time.time() - 86400,
                "ultima_medware": "07/06/2026",
            },
        },
    }
    text_b = "sua consulta agendada, é só comparecer."
    assert _viola_afirmou_consulta_marcada_data_passada(text_b, ctx_b) is True
    scrub_b = _scrub_prohibited(text_b, ctx_b)
    assert scrub_b != text_b
