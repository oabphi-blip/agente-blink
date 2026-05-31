"""Pytest da mensagem de renovação de janela 24h (task #87).

Cobre:
 - extração de primeiro nome em variantes (maiúsculas, com sobrenome, vazio)
 - personalização funciona
 - "oi" presente como gatilho de renovação
 - opção "outro momento" presente
 - vocabulário vetado NÃO aparece
 - menciona "Blink Oftalmologia"
 - menciona "24 horas" ou equivalente
 - validator detecta violações sintéticas
"""
from __future__ import annotations

import pytest

from datetime import datetime, timedelta, timezone

from voice_agent.mensagens_janela import (
    JANELA_24H_SEGUNDOS,
    LIMIAR_DISPARO_SEGUNDOS,
    RAZAO_AINDA_CEDO,
    RAZAO_JANELA_MORTA,
    RAZAO_SEM_INTERACAO,
    RAZAO_STATUS_POS_AGENDAMENTO,
    STATUS_IDS_ANTES_AGENDADO,
    _PALAVRAS_VETADAS,
    _primeiro_nome,
    elegivel_renovar_janela,
    render_mensagem_renovar_janela,
    validar_mensagem_renovacao,
)


class TestPrimeiroNome:

    def test_nome_simples_capitalizado(self):
        assert _primeiro_nome("marcela") == "Marcela"

    def test_nome_em_caixa_alta(self):
        assert _primeiro_nome("MARCELA SOUZA") == "Marcela"

    def test_nome_com_acentos(self):
        assert _primeiro_nome("João Pedro") == "João"
        assert _primeiro_nome("maría de la cruz") == "María"

    def test_nome_vazio(self):
        assert _primeiro_nome("") == ""
        assert _primeiro_nome(None) == ""
        assert _primeiro_nome("   ") == ""

    def test_espacos_extras(self):
        assert _primeiro_nome("   marcela    souza  ") == "Marcela"


class TestRenderMensagem:

    def test_inclui_nome_quando_presente(self):
        msg = render_mensagem_renovar_janela("Marcela Souza")
        assert "Marcela" in msg
        assert "Souza" not in msg  # só primeiro nome

    def test_saudacao_neutra_sem_nome(self):
        msg = render_mensagem_renovar_janela(None)
        assert msg.startswith("Olá!")
        msg2 = render_mensagem_renovar_janela("")
        assert msg2.startswith("Olá!")

    def test_menciona_blink_oftalmologia(self):
        msg = render_mensagem_renovar_janela("Ana")
        assert "Blink Oftalmologia" in msg

    def test_menciona_lia(self):
        msg = render_mensagem_renovar_janela("Ana")
        assert "Lia" in msg

    def test_pede_oi_explicitamente(self):
        msg = render_mensagem_renovar_janela("Ana")
        assert '"oi"' in msg or "'oi'" in msg

    def test_menciona_24_horas(self):
        msg = render_mensagem_renovar_janela("Ana")
        baixo = msg.lower()
        assert "24" in baixo

    def test_oferece_opcao_outro_momento(self):
        msg = render_mensagem_renovar_janela("Ana")
        baixo = msg.lower()
        assert "outro momento" in baixo or "quando você quiser" in baixo

    def test_tem_emoji_aceito(self):
        msg = render_mensagem_renovar_janela("Ana")
        # Apenas 👋 ou ✨ permitidos no acolhimento (regra 1.5).
        assert "👋" in msg or "✨" in msg

    def test_nao_tem_emoji_proibido(self):
        msg = render_mensagem_renovar_janela("Ana")
        for proibido in ("💙", "❤️", "😊", "🧸", "👁️", "🩺"):
            assert proibido not in msg, f"emoji proibido: {proibido}"

    def test_concisa_max_600_chars(self):
        # Ping 24h precisa ser curto (~ 600 chars). Limite global do
        # validador é 900 pra acomodar D-1 do ciclo.
        msg = render_mensagem_renovar_janela("Ana Carolina Almeida Souza")
        assert len(msg) < 600, f"ping 24h com {len(msg)} chars — longo demais"


class TestVocabularioVetado:

    def test_nao_contem_palavras_vetadas(self):
        msg = render_mensagem_renovar_janela("João")
        baixo = msg.lower()
        for palavra in _PALAVRAS_VETADAS:
            assert palavra not in baixo, f"palavra vetada presente: {palavra!r}"

    def test_nao_tem_particular(self):
        # Regra 1.4.1 — "particular" é proibido (usar "sem convênio").
        msg = render_mensagem_renovar_janela("João")
        assert "particular" not in msg.lower()


class TestValidador:

    def test_mensagem_padrao_passa_validacao(self):
        msg = render_mensagem_renovar_janela("Marcela")
        r = validar_mensagem_renovacao(msg)
        assert r["ok"] is True
        assert r["violacoes"] == []

    def test_detecta_palavra_vetada_sintetica(self):
        r = validar_mensagem_renovacao(
            "Olá! Oi rapidinho, retoma quando quiser, outro momento."
        )
        assert r["ok"] is False
        assert any("rapidinho" in v for v in r["violacoes"])

    def test_detecta_ausencia_de_oi(self):
        r = validar_mensagem_renovacao(
            "Mande qualquer mensagem pra renovar. Outro momento também serve."
        )
        # "oi" não aparece como palavra/dica explícita
        assert any("'oi'" in v for v in r["violacoes"])

    def test_detecta_ausencia_de_opcao_outro_momento(self):
        r = validar_mensagem_renovacao(
            "Olá. Mande um oi pra renovar. Obrigada."
        )
        assert any("retomar depois" in v for v in r["violacoes"])

    def test_detecta_mensagem_longa(self):
        # Limite global do validador é 900 chars.
        texto_longo = "Olá oi outro momento " + ("X" * 1000)
        assert len(texto_longo) > 900
        r = validar_mensagem_renovacao(texto_longo)
        assert any("longa demais" in v for v in r["violacoes"])

    def test_palavra_parcial_nao_dispara_falso_positivo(self):
        # "fofocar" contém "fofo" como substring — não pode disparar.
        r = validar_mensagem_renovacao(
            "Olá! Oi, outro momento — sem fofocar com terceiros."
        )
        # Pode ter outras violações, mas "fofo" sozinho não.
        violacoes_fofo = [v for v in r["violacoes"] if "fofo" in v]
        assert violacoes_fofo == []


# ===========================================================================
# Elegibilidade (task #88)
# ===========================================================================

# Timestamp fixo pra testes determinísticos: 31/05/2026 12:00 UTC.
_AGORA = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc).timestamp()


def _ts_horas_atras(horas: float) -> float:
    return _AGORA - horas * 3600


class TestStatusElegivel:

    def test_status_etapa_entrada_passa(self):
        r = elegivel_renovar_janela(
            status_id=96441724,
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_status_leads_frio_passa(self):
        r = elegivel_renovar_janela(
            status_id=101508307,
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_status_agendar_passa(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(23.5),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_status_reagendar_passa(self):
        r = elegivel_renovar_janela(
            status_id=106184631,
            ultima_msg_paciente_ts=_ts_horas_atras(22.5),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_status_no_show_passa(self):
        # 5.1-NO-SHOW também precisa reagendar → conta.
        r = elegivel_renovar_janela(
            status_id=106184983,
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_status_agendado_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=101507507,  # 4-AGENDADO
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_STATUS_POS_AGENDAMENTO

    def test_status_confirmar_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=101109455,  # 5-CONFIRMAR
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_STATUS_POS_AGENDAMENTO

    def test_status_realizado_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=91486864,  # 7-REALIZADO
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is False

    def test_status_none_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=None,
            ultima_msg_paciente_ts=_ts_horas_atras(23),
            agora=_AGORA,
        )
        assert r["elegivel"] is False


class TestInteracaoPaciente:

    def test_sem_interacao_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=None,
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_SEM_INTERACAO

    def test_zero_NAO_conta_como_interacao(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=0,
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_SEM_INTERACAO

    def test_string_invalida_NAO_passa(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts="invalido",
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_SEM_INTERACAO


class TestLimiarDeTempo:

    def test_delta_5h_ainda_cedo(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(5),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_AINDA_CEDO
        assert r["delta_seg"] == 5 * 3600

    def test_delta_20h_ainda_cedo(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(20),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_AINDA_CEDO

    def test_delta_22h_dispara(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(22.1),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_delta_23h59_ainda_dispara(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(23.99),
            agora=_AGORA,
        )
        assert r["elegivel"] is True

    def test_delta_24h_exato_janela_morta(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(24),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_JANELA_MORTA

    def test_delta_30h_janela_morta(self):
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=_ts_horas_atras(30),
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_JANELA_MORTA


class TestAceitaTiposVariados:

    def test_aceita_datetime(self):
        agora_dt = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        ultima_dt = agora_dt - timedelta(hours=23)
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=ultima_dt,
            agora=agora_dt,
        )
        assert r["elegivel"] is True

    def test_aceita_datetime_naive_como_utc(self):
        agora_naive = datetime(2026, 5, 31, 12, 0)  # sem tz
        ultima_naive = datetime(2026, 5, 31, 12, 0) - timedelta(hours=23)
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=ultima_naive,
            agora=agora_naive,
        )
        assert r["elegivel"] is True

    def test_agora_default_e_now(self):
        # Sem passar 'agora', usa now() — não deve quebrar.
        r = elegivel_renovar_janela(
            status_id=102560495,
            ultima_msg_paciente_ts=datetime.now(timezone.utc) - timedelta(hours=23),
        )
        # Pode ser True ou False dependendo do timing exato — o que importa
        # é não levantar exceção.
        assert "elegivel" in r


class TestPrecedenciaDasRegras:
    """Status irrelevante deve ser rejeitado ANTES de checar tempo."""

    def test_status_invalido_ignora_tempo(self):
        r = elegivel_renovar_janela(
            status_id=101507507,  # AGENDADO — não conta
            ultima_msg_paciente_ts=_ts_horas_atras(23),  # tempo ideal
            agora=_AGORA,
        )
        assert r["elegivel"] is False
        assert r["razao"] == RAZAO_STATUS_POS_AGENDAMENTO
        # Não calcula delta nesse caso (poupa CPU no cron).
        assert r["delta_seg"] is None


class TestConstantes:

    def test_status_validos_contem_4_etapas_antes_agendado(self):
        # Deve cobrir as etapas 0/1/2/3 pré-AGENDADO + NO-SHOW.
        assert 96441724 in STATUS_IDS_ANTES_AGENDADO    # 0
        assert 101508307 in STATUS_IDS_ANTES_AGENDADO   # 1
        assert 102560495 in STATUS_IDS_ANTES_AGENDADO   # 2
        assert 106184631 in STATUS_IDS_ANTES_AGENDADO   # 3
        assert 106184983 in STATUS_IDS_ANTES_AGENDADO   # 5.1 NO-SHOW

    def test_agendado_NAO_esta_em_validos(self):
        assert 101507507 not in STATUS_IDS_ANTES_AGENDADO

    def test_constantes_de_tempo_coerentes(self):
        assert JANELA_24H_SEGUNDOS == 86400
        assert LIMIAR_DISPARO_SEGUNDOS < JANELA_24H_SEGUNDOS
