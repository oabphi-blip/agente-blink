"""Bug C-47 (02/07/2026, lead 22838100 Manoela Dantas Vale).

Dois bugs simultâneos:

1. Timezone — kommo.py gravava `dia_consulta_iso` sem timezone (container
   Easypanel roda em UTC). Timestamp 1783711800 (= 10/07 16:30 BRT) virava
   string "2026-07-10T19:30:00" (naive UTC). Lia lia e imprimia "19:30 BRT".
   Fix: `datetime.fromtimestamp(ts, tz=ZoneInfo("America/Sao_Paulo"))`.

2. Remarcação — quando paciente pede remarcação, Lia mencionava "equipe
   humana"/"atendimento humano" ao encaminhar. Regra Fábio: NÃO expor
   camada. Frase canônica: "vou encaminhar você para nossa especialista
   em remarcação".
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


BR = ZoneInfo("America/Sao_Paulo")


# =====================================================================
# 1. Fix timezone
# =====================================================================
class TestTimezoneFix:
    """Timestamp Kommo deve render em BRT, não UTC."""

    def test_timestamp_manoela_1_dia_consulta_bate_1630_brt(self):
        # 1.DIA CONSULTA = 1783711800 → 10/07/2026 16:30 BRT
        ts = 1783711800
        d_brt = datetime.fromtimestamp(ts, tz=BR)
        assert d_brt.hour == 16
        assert d_brt.minute == 30
        assert d_brt.day == 10
        assert d_brt.month == 7

    def test_timestamp_manoela_2_dia_consulta_bate_1700_brt(self):
        # 2.DIA CONSULTA = 1783713600 → 10/07/2026 17:00 BRT
        ts = 1783713600
        d_brt = datetime.fromtimestamp(ts, tz=BR)
        assert d_brt.hour == 17
        assert d_brt.minute == 0

    def test_fromtimestamp_sem_tz_devolve_utc_no_container(self):
        # Simula o bug: sem tz, hora vem UTC (19:30).
        ts = 1783711800
        d_naive_utc = datetime.utcfromtimestamp(ts)
        assert d_naive_utc.hour == 19  # bug: 19:30 UTC
        # Com fix, hora vem BRT (16:30).
        d_brt = datetime.fromtimestamp(ts, tz=BR)
        assert d_brt.hour == 16

    def test_isoformat_com_tz_carrega_offset_menos_3(self):
        ts = 1783711800
        iso = datetime.fromtimestamp(ts, tz=BR).isoformat()
        assert "-03:00" in iso
        assert "T16:30:00" in iso


# =====================================================================
# 2. Regra remarcação
# =====================================================================
from voice_agent.responder import (
    _paciente_pediu_remarcacao,
    _texto_menciona_atendimento_humano,
    _gerar_encaminhamento_remarcacao,
    _scrub_prohibited,
)


class TestDeteccaoRemarcacao:
    @pytest.mark.parametrize("frase", [
        "quero remarcar minha consulta",
        "preciso remarcar para outro dia",
        "queria mudar o horário",
        "posso trocar o dia?",
        "quero adiar a consulta",
        "não vou conseguir na quarta",
        "queria reagendar",
        "gostaria de reagendamento",
    ])
    def test_detecta_intencao_remarcacao(self, frase):
        assert _paciente_pediu_remarcacao(frase) is True

    @pytest.mark.parametrize("frase", [
        "quero confirmar meu horário",
        "está tudo bem, vou comparecer",
        "obrigada!",
        "vou levar meu filho junto",
        "",
        None,
    ])
    def test_nao_falso_positivo(self, frase):
        assert _paciente_pediu_remarcacao(frase) is False


class TestDeteccaoTermosProibidos:
    @pytest.mark.parametrize("frase", [
        "vou encaminhar você para nossa equipe humana",
        "vai passar pro atendimento humano",
        "vou passar pra equipe agora",
        "encaminho para atendimento humano",
        "vou transferir para nossa equipe humana",
    ])
    def test_detecta_termos_proibidos(self, frase):
        assert _texto_menciona_atendimento_humano(frase) is True

    @pytest.mark.parametrize("frase", [
        "vou encaminhar você para nossa especialista em remarcação",
        "vou verificar sua agenda",
        "seu horário é sexta 10/07 às 16:30",
        "",
    ])
    def test_frases_ok_nao_disparam(self, frase):
        assert _texto_menciona_atendimento_humano(frase) is False


class TestFraseCanonicaEncaminhamento:
    def test_frase_menciona_especialista_remarcacao(self):
        out = _gerar_encaminhamento_remarcacao({"known": {"nome_contato": "Manoela Dantas"}})
        assert "especialista em remarcação" in out.lower()
        assert "manoela" in out.lower()

    def test_frase_nao_menciona_humano_ou_ia(self):
        out = _gerar_encaminhamento_remarcacao({"known": {"nome_contato": "Fábio"}})
        baixo = out.lower()
        assert "humano" not in baixo
        assert "equipe humana" not in baixo
        assert "atendente" not in baixo
        assert "ia" not in baixo or "especialista" in baixo  # 'especialista' pode ter 'ista'

    def test_sem_nome_saudacao_generica(self):
        out = _gerar_encaminhamento_remarcacao(None)
        assert "especialista em remarcação" in out.lower()


class TestFiltroC47ScrubIntegracao:
    def test_scrub_substitui_quando_mencionou_humano(self):
        texto_lia = "Ok Manoela, vou passar pra nossa equipe humana atender."
        ctx = {"known": {"nome_contato": "Manoela"}}
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "equipe humana" not in out.lower()
        assert "especialista em remarcação" in out.lower()

    def test_scrub_substitui_quando_paciente_pediu_remarcar(self):
        texto_lia = "Consulta marcada para 10/07 às 19:30. Confirma?"
        ctx = {
            "known": {"nome_contato": "Manoela"},
            "inbound_text": "quero remarcar minha consulta",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "especialista em remarcação" in out.lower()
        # Não repete o horário errado.
        assert "19:30" not in out

    def test_scrub_nao_altera_conversa_normal(self):
        texto_lia = "Perfeito! Vou verificar horários disponíveis."
        ctx = {"known": {"nome_contato": "Ana"}, "inbound_text": "quero agendar"}
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        # Não é remarcação nem menciona humano — texto não muda.
        assert "verificar horários" in out.lower() or "verificar hor" in out.lower()

    def test_scrub_case_insensitive(self):
        texto_lia = "Vou passar para NOSSA EQUIPE HUMANA agora."
        out = _scrub_prohibited(texto_lia, ctx={"known": {}})
        assert "equipe humana" not in out.lower()
        assert "especialista em remarcação" in out.lower()


# =====================================================================
# Bug C-48 — Vazamento de nome de campo interno (lead 21259287 Samuel)
# =====================================================================
class TestFiltroC48VazamentoCampoInterno:
    """Frase real do lead 21259287:
    'A consulta da Samuel Elias já está marcada (data no campo 1.DIA CONSULTA).'
    Filtro deve substituir por frase segura."""

    @pytest.mark.parametrize("texto", [
        "A consulta já está marcada (data no campo 1.DIA CONSULTA).",
        "Vou consultar o 1.DIA CONSULTA e volto.",
        "Você já tem consulta na N.DIA CONSULTA.",
        "Verificando ctx.known e ctx.agenda",
        "kommo.get_lead retornou vazio",
        "Erro em responder.py",
        "custom_fields do lead não tem field_id",
        "Confira o campo 1. no seu cadastro",
    ])
    def test_detecta_vazamento_campo_interno(self, texto):
        out = _scrub_prohibited(texto, ctx={"known": {"nome_contato": "Samuel"}})
        assert "1.dia consulta" not in out.lower()
        assert "campo 1." not in out.lower()
        assert "custom_fields" not in out.lower()
        assert "responder.py" not in out.lower()
        # Substituiu pela frase canônica de encaminhamento.
        assert "especialista em remarcação" in out.lower()

    def test_texto_normal_nao_e_afetado(self):
        texto = "Olá! Como posso te ajudar hoje?"
        out = _scrub_prohibited(texto, ctx={"known": {"convenio": "Bacen"}})
        # Não menciona campo interno — passa direto.
        assert "campo 1." not in out.lower()
        assert "especialista em remarcação" not in out.lower()

    def test_lead_21259287_texto_real_bloqueado(self):
        """Repro exato do caso Samuel."""
        texto_real = (
            "Recebi, obrigada! A consulta da Samuel Elias da Silva Souza "
            "já está marcada (data no campo 1.DIA CONSULTA). Nossa equipe "
            "vai conferir tudo. Se precisar remarcar ou cancelar, é só "
            "me avisar — caso contrário, te espero no dia marcado!"
        )
        ctx = {"known": {"nome_contato": "Rafael"}}
        out = _scrub_prohibited(texto_real, ctx=ctx)
        assert "campo 1.dia consulta" not in out.lower()
        assert "campo 1." not in out.lower()
        assert "especialista em remarcação" in out.lower()


# =====================================================================
# Fallback pós-agendado sem data — NÃO vazar texto técnico
# =====================================================================
from voice_agent.responder import _gerar_oferta_pos_agendado_fallback


class TestFallbackPosAgendadoSemVazamento:
    def test_com_data_iso_valida_menciona_data_humana(self):
        # dia_consulta_iso presente → formata data humana
        ctx = {
            "known": {
                "nome_paciente": "Samuel",
                "dia_consulta_iso": "2025-12-18T09:00:00-03:00",
            }
        }
        out = _gerar_oferta_pos_agendado_fallback(ctx)
        # NÃO vaza campo interno
        assert "campo 1." not in out.lower()
        assert "1.dia consulta" not in out.lower()
        # Menciona a data legível
        assert "18/12" in out

    def test_sem_data_encaminha_remarcacao(self):
        # dia_consulta_iso ausente → NÃO vaza campo, encaminha especialista
        ctx = {"known": {"nome_paciente": "Samuel"}}
        out = _gerar_oferta_pos_agendado_fallback(ctx)
        assert "campo 1." not in out.lower()
        assert "1.dia consulta" not in out.lower()
        assert "especialista em remarcação" in out.lower()

    def test_iso_invalido_encaminha_remarcacao(self):
        # dia_consulta_iso corrompido → data_humano fica vazio → encaminha
        ctx = {"known": {"nome_paciente": "X", "dia_consulta_iso": "lixo"}}
        out = _gerar_oferta_pos_agendado_fallback(ctx)
        assert "campo 1." not in out.lower()
        assert "especialista em remarcação" in out.lower()
