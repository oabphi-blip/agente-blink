"""Pytest do fix Diones (lead 23742328 — 01/06/2026).

3 camadas blindadas:
 1. ST_JA_AGENDADO inclui 106653499 (7.CONFIRMADO)
 2. Bloco TRAVA MÉDICO/UNIDADE injetado quando ctx tem médico
 3. Filtro _viola_medico_trocado bloqueia menção de Fabrício quando
    ctx tem Karla (e vice-versa)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# Camada 1 — ST_JA_AGENDADO completo
# ----------------------------------------------------------------------

class TestStatusJaAgendado:

    def test_5_agendado_em_ja_agendado(self):
        from voice_agent.kommo import ST_JA_AGENDADO
        assert 101507507 in ST_JA_AGENDADO

    def test_6_confirmar_em_ja_agendado(self):
        from voice_agent.kommo import ST_JA_AGENDADO
        assert 101109455 in ST_JA_AGENDADO

    def test_7_confirmado_em_ja_agendado(self):
        """Bug Diones: 7.CONFIRMADO faltava no set."""
        from voice_agent.kommo import ST_JA_AGENDADO
        assert 106653499 in ST_JA_AGENDADO

    def test_3_agendar_NAO_esta_em_ja_agendado(self):
        """3-AGENDAR = ainda agendando, não tem consulta marcada."""
        from voice_agent.kommo import ST_JA_AGENDADO
        assert 102560495 not in ST_JA_AGENDADO


# ----------------------------------------------------------------------
# Camada 2 — TRAVA MÉDICO/UNIDADE no prompt
# ----------------------------------------------------------------------

class TestTravaMedicoUnidadeNoPrompt:

    def test_ctx_com_medico_injeta_trava(self):
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True, "name": "Diones", "lead_id": 23742328,
            "known": {
                "medico": "Dra. Karla Delalibera",
                "unidade": "Águas Claras",
                "dia_turno": "Quarta-feira — tarde",
            },
        }
        bloco = _caller_context_block(ctx)
        assert "TRAVA MÉDICO/UNIDADE" in bloco
        assert "Karla" in bloco
        assert "Águas Claras" in bloco
        assert "Quarta-feira" in bloco
        # Proibições explícitas
        assert "NÃO trocar" in bloco
        assert "PROIBIDO oferecer slot de OUTRO médico" in bloco
        assert "inventar dias fixos" in bloco

    def test_ctx_sem_medico_nao_injeta_trava(self):
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True, "name": "X", "lead_id": 1,
            "known": {"convenio": "STF-Med"},
        }
        bloco = _caller_context_block(ctx)
        assert "TRAVA MÉDICO/UNIDADE" not in bloco

    def test_ctx_so_unidade_injeta_trava(self):
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True, "name": "X", "lead_id": 1,
            "known": {"unidade": "Asa Norte"},
        }
        bloco = _caller_context_block(ctx)
        assert "TRAVA MÉDICO/UNIDADE" in bloco
        assert "Asa Norte" in bloco


# ----------------------------------------------------------------------
# Camada 3 — Filtro pós-geração _viola_medico_trocado
# ----------------------------------------------------------------------

class TestFiltroMedicoTrocado:

    def test_ctx_karla_resposta_fabricio_eh_bloqueado(self):
        """Bug exato do Diones."""
        from voice_agent.responder import _viola_medico_trocado
        ctx = {"known": {"medico": "Dra. Karla Delalibera"}}
        resp = (
            "Tenho essas opções com o Dr. Fabrício Freitas:\n"
            "1️⃣ segunda 08/06 às 13:30"
        )
        motivo = _viola_medico_trocado(resp, ctx)
        assert motivo is not None
        assert "karla" in motivo and "fabricio" in motivo

    def test_ctx_fabricio_resposta_karla_eh_bloqueado(self):
        from voice_agent.responder import _viola_medico_trocado
        ctx = {"known": {"medico": "Dr. Fabrício Freitas"}}
        resp = "Vou agendar com a Dra. Karla terça às 09:00"
        motivo = _viola_medico_trocado(resp, ctx)
        assert motivo is not None
        assert "fabricio" in motivo and "karla" in motivo

    def test_ctx_karla_resposta_karla_ok(self):
        from voice_agent.responder import _viola_medico_trocado
        ctx = {"known": {"medico": "Dra. Karla Delalibera"}}
        resp = "Tenho terça com a Dra. Karla às 09:00"
        assert _viola_medico_trocado(resp, ctx) is None

    def test_resposta_menciona_ambos_NAO_eh_bloqueado(self):
        """Lia pode dizer 'Dra Karla atende rotina, Dr Fabrício
        catarata' sem ser violação."""
        from voice_agent.responder import _viola_medico_trocado
        ctx = {"known": {"medico": "Dra. Karla Delalibera"}}
        resp = "A Dra. Karla atende rotina. O Dr. Fabrício é catarata."
        # Tem KARLA NA RESPOSTA → não dispara
        assert _viola_medico_trocado(resp, ctx) is None

    def test_sem_ctx_nao_dispara(self):
        from voice_agent.responder import _viola_medico_trocado
        resp = "Dra Karla terça 09:00"
        assert _viola_medico_trocado(resp, None) is None

    def test_ctx_sem_medico_nao_dispara(self):
        from voice_agent.responder import _viola_medico_trocado
        ctx = {"known": {"convenio": "STF-Med"}}
        resp = "Dr. Fabrício às 14:00"
        assert _viola_medico_trocado(resp, ctx) is None

    def test_scrub_prohibited_substitui_por_fallback(self):
        """Cenário Diones completo via _scrub_prohibited."""
        from voice_agent.responder import _scrub_prohibited
        ctx = {
            "agenda": [{"data_iso": "2026-06-08", "hora": "13:30",
                        "dia_semana": "segunda-feira"}],
            "known": {"medico": "Dra. Karla Delalibera"},
        }
        resposta_buggy = (
            "Recebi, obrigada! Tenho essas opções com o Dr. Fabrício "
            "Freitas em Águas Claras:\n1️⃣ segunda 08/06 às 13:30"
        )
        substituida = _scrub_prohibited(resposta_buggy, ctx=ctx)
        # Resposta foi substituída pelo fallback
        assert "Fabrício" not in substituida and "Fabricio" not in substituida
        # Fallback pede pra reconfirmar médico
        assert "médico" in substituida.lower()
