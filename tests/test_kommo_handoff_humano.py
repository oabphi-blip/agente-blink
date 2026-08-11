"""Pytest do gate agent_paused_for_lead — DUAS regras combinadas.

Origem do fix: 01/06/2026, Fábio detectou Lia respondendo POR CIMA
de mensagem do atendente humano. Causa: em 29/05/2026 o gate ficou
SÓ etapa-humana, ignorando o service_message automático do Kommo
'🛑 Agentes de IA foram desativados neste chat' que aparece quando
o humano escreve manualmente sem mover o lead pra etapa humana.

Fix: re-plugou ia_status_from_notes no gate.

Sentinela: este pytest blinda o gate pra NUNCA regredir pra
"só etapa-humana".
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def _make_kommo_stub(ia_status="ATIVADO"):
    """Stub minimalista do KommoClient pra exercer agent_paused_for_lead."""
    from voice_agent.kommo import KommoClient
    # KommoClient.__init__ é pesado — vamos construir um instance vazio
    # e injetar só o que precisamos
    k = object.__new__(KommoClient)
    k.ia_status_from_notes = MagicMock(return_value=ia_status)
    return k


# ----------------------------------------------------------------------
# Regra 1 — etapa humana (legacy)
# ----------------------------------------------------------------------

class TestRegraEtapaHumana:

    def test_etapa_atendimento_humano_pausa(self):
        from voice_agent.kommo import KommoClient, ST_AGENT_OFF
        k = _make_kommo_stub()
        # Pega 1 status_id que está em ST_AGENT_OFF
        etapa_humana = next(iter(ST_AGENT_OFF))
        ctx = {
            "found": True, "lead_id": 1, "status_id": etapa_humana,
        }
        assert KommoClient.agent_paused_for_lead(k, ctx, 30) == "etapa-humana"

    def test_etapa_agendar_nao_pausa_por_etapa(self):
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub(ia_status="ATIVADO")
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 102560495,  # 3-AGENDAR (não está em ST_AGENT_OFF)
        }
        assert KommoClient.agent_paused_for_lead(k, ctx, 30) is None


# ----------------------------------------------------------------------
# Regra 2 — service_message Kommo (humano escreveu sem mover lead)
# ----------------------------------------------------------------------

class TestRegraServiceMessage:

    def test_ia_desativada_RECENTE_pausa_temporariamente(self):
        """Regra refinada Fábio 02/06: humano escreveu há POUCO
        (15 min). Lia silencia TEMPORARIAMENTE. Após 30min IA
        reativa sozinha — não fica órfã como no bug Elisa."""
        from voice_agent.kommo import KommoClient
        from datetime import datetime, timezone, timedelta
        agora = datetime.now(timezone.utc)
        notas_recente = [{
            "note_type": "service_message",
            "created_at": (agora - timedelta(minutes=10)).strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            ),
            "text": "🛑 Agentes de IA foram desativados neste chat",
        }]
        k = _make_kommo_stub(ia_status="DESATIVADO")
        k.get_lead_notes = lambda lid, limit=50: notas_recente
        ctx = {
            "found": True, "lead_id": 23742328,
            "status_id": 102560495,  # 3-AGENDAR (não em ST_AGENT_OFF)
        }
        result = KommoClient.agent_paused_for_lead(k, ctx, 30)
        assert result == "humano-escreveu-recente"

    def test_ia_ativada_via_notes_nao_pausa(self):
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub(ia_status="ATIVADO")
        ctx = {
            "found": True, "lead_id": 1, "status_id": 102560495,
        }
        assert KommoClient.agent_paused_for_lead(k, ctx, 30) is None

    def test_ia_status_none_nao_pausa(self):
        """Quando lead não tem notas relevantes, segue normal."""
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub(ia_status=None)
        ctx = {
            "found": True, "lead_id": 1, "status_id": 102560495,
        }
        assert KommoClient.agent_paused_for_lead(k, ctx, 30) is None

    def test_exception_em_ia_status_nao_quebra(self):
        """Falha na chamada Kommo NÃO derruba o gate (degrada graciosa)."""
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub()
        k.ia_status_from_notes = MagicMock(side_effect=RuntimeError("kommo flaky"))
        ctx = {
            "found": True, "lead_id": 1, "status_id": 102560495,
        }
        # Não deve crashar — apenas retorna None (Lia segue normal)
        assert KommoClient.agent_paused_for_lead(k, ctx, 30) is None


# ----------------------------------------------------------------------
# Regra 1 tem PRECEDÊNCIA — etapa-humana evita chamada de notes
# ----------------------------------------------------------------------

class TestPrecedencia:

    def test_etapa_humana_evita_chamada_notes(self):
        """Otimização: se já é etapa-humana, nem precisa chamar notes."""
        from voice_agent.kommo import KommoClient, ST_AGENT_OFF
        k = _make_kommo_stub()
        etapa_humana = next(iter(ST_AGENT_OFF))
        ctx = {
            "found": True, "lead_id": 1, "status_id": etapa_humana,
        }
        result = KommoClient.agent_paused_for_lead(k, ctx, 30)
        assert result == "etapa-humana"
        # ia_status_from_notes NÃO foi chamada (etapa-humana retornou antes)
        assert not k.ia_status_from_notes.called


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------

class TestEdgeCases:

    def test_ctx_none(self):
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub()
        assert KommoClient.agent_paused_for_lead(k, None, 30) is None

    def test_ctx_not_found(self):
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub()
        assert KommoClient.agent_paused_for_lead(k, {"found": False}, 30) is None

    def test_ctx_sem_lead_id(self):
        """status_id sem lead_id (raro) — não chama notes."""
        from voice_agent.kommo import KommoClient
        k = _make_kommo_stub()
        ctx = {"found": True, "status_id": 102560495}
        result = KommoClient.agent_paused_for_lead(k, ctx, 30)
        # Sem lead_id, gate retorna None (Lia segue normal)
        assert result is None
        assert not k.ia_status_from_notes.called
