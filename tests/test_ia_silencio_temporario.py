"""Pytest da nova regra de silêncio temporário (Fábio 02/06/2026).

Lead Elisa 21392947: IA muda há 50 dias porque humano escreveu em
13/04 e ninguém reativou. Status atual = Closed-lost (143), que NÃO
está em ST_AGENT_OFF. Nova regra:

- Silêncio permanente APENAS se status_id em ST_AGENT_OFF.
- Silêncio temporário 30min após "🛑" mais recente.
- Após 30min, IA volta sozinha — independente de "🟢" explícito.
- Auto-cura: nenhum lead fica órfão permanentemente.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def _iso_min_ago(minutos: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(minutes=minutos)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _iso_dias_atras(dias: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=dias)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class _FakeKommo:
    """Stub do KommoClient pra exercitar agent_paused_for_lead sem rede."""

    def __init__(self, notas=None):
        self._notas = notas or []

    def get_lead_notes(self, lead_id, limit=50):
        return list(self._notas)


def _build_kommo(notas):
    """Constrói KommoClient real via __new__ + injeta fake."""
    from voice_agent.kommo import KommoClient
    k = KommoClient.__new__(KommoClient)
    k._notas = notas
    # Patch métodos pra usar nossa lista
    k.get_lead_notes = lambda lid, limit=50: list(notas)
    return k


# ----------------------------------------------------------------------
# Cenário Elisa — closed-lost, humano escreveu há 50 dias
# ----------------------------------------------------------------------

class TestElisaCasoReal:

    def test_closed_lost_com_humano_antigo_IA_RESPONDE(self):
        """Caso Elisa: status 143 + humano escreveu há 50 dias →
        IA deve responder (auto-cura)."""
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_dias_atras(50),
                "text": (
                    "🛑 Agentes de IA foram desativados neste chat "
                    "porque uma mensagem manual de saída foi detectada"
                ),
            },
        ]
        k = _build_kommo(notas)
        ctx = {
            "found": True, "lead_id": 21392947,
            "status_id": 143,  # Closed-lost
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None, (
            f"Caso Elisa: IA deveria responder mas pausou por {motivo}"
        )

    def test_humano_acabou_de_escrever_15min_SILENCIA(self):
        """Humano escreveu há 15min (< 30min) → silêncio temporário."""
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(15),
                "text": "🛑 Agentes de IA foram desativados",
            },
        ]
        k = _build_kommo(notas)
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 102560495,  # 3-AGENDAR (IA-on)
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "humano-escreveu-recente"

    def test_humano_45min_atras_IA_VOLTA(self):
        """Humano escreveu há 45min (> 30min) → IA auto-reativa."""
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(45),
                "text": "🛑 Agentes de IA foram desativados",
            },
        ]
        k = _build_kommo(notas)
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 102560495,
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None


# ----------------------------------------------------------------------
# Regra 1 (etapa humana) — comportamento preservado
# ----------------------------------------------------------------------

class TestEtapaHumana:

    def test_atendimento_humano_silencia(self):
        from voice_agent.kommo import KommoClient
        k = _build_kommo([])
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 106563343,  # 1-ATENDIMENTO HUMANO
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "etapa-humana"

    def test_cirurgia_em_andamento_silencia(self):
        from voice_agent.kommo import KommoClient
        k = _build_kommo([])
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 106157139,  # 7-CIRURGIAS ANDAMENTO
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "etapa-humana"

    def test_confirmar_silencia(self):
        """5-CONFIRMAR = paciente respondendo template — Lia espera."""
        from voice_agent.kommo import KommoClient
        k = _build_kommo([])
        ctx = {
            "found": True, "lead_id": 1,
            "status_id": 101109455,
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "etapa-humana"


# ----------------------------------------------------------------------
# Etapas onde IA SEMPRE responde (mesmo com "🛑" antigo)
# ----------------------------------------------------------------------

class TestEtapasIaSempreOn:

    @pytest.mark.parametrize("status_id,nome", [
        (96441724, "0-ENTRADA"),
        (106919911, "0-A CLASSIFICAR"),
        (101508307, "2-LEADS FRIO"),
        (102560495, "3-AGENDAR"),
        (106184631, "4-REAGENDAR"),
        (101507507, "5-AGENDADO"),
        (106184983, "7.1-NO-SHOW"),
        (143, "Closed-lost"),
    ])
    def test_etapa_naoHumana_humano_antigo_responde(self, status_id, nome):
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_dias_atras(10),
                "text": "🛑 Agentes de IA foram desativados",
            },
        ]
        k = _build_kommo(notas)
        ctx = {
            "found": True, "lead_id": 1, "status_id": status_id,
        }
        motivo = k.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None, (
            f"Etapa {nome} ({status_id}): IA deveria responder mas "
            f"pausou por {motivo}"
        )


# ----------------------------------------------------------------------
# _ts_ultimo_humano_escreveu — função auxiliar
# ----------------------------------------------------------------------

class TestTsUltimoHumano:

    def test_so_verde_devolve_None(self):
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(10),
                "text": "🟢 Agentes de IA foram ativados",
            },
        ]
        k = _build_kommo(notas)
        assert k._ts_ultimo_humano_escreveu(1) is None

    def test_vermelho_seguido_de_verde_devolve_None(self):
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(20),
                "text": "🛑 Agentes de IA foram desativados",
            },
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(10),
                "text": "🟢 Agentes de IA foram ativados",
            },
        ]
        k = _build_kommo(notas)
        # Última = verde → não há silêncio
        assert k._ts_ultimo_humano_escreveu(1) is None

    def test_verde_seguido_de_vermelho_devolve_ts_vermelho(self):
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(20),
                "text": "🟢 Agentes de IA foram ativados",
            },
            {
                "note_type": "service_message",
                "created_at": _iso_min_ago(10),
                "text": "🛑 Agentes de IA foram desativados",
            },
        ]
        k = _build_kommo(notas)
        ts = k._ts_ultimo_humano_escreveu(1)
        assert ts is not None
        # Deve ser aproximadamente 10 min atrás
        assert time.time() - ts < 700  # ~11 min

    def test_lista_vazia_None(self):
        from voice_agent.kommo import KommoClient
        k = _build_kommo([])
        assert k._ts_ultimo_humano_escreveu(1) is None

    def test_ignora_notas_que_nao_sao_service_message(self):
        from voice_agent.kommo import KommoClient
        notas = [
            {
                "note_type": "common",  # ignorado
                "created_at": _iso_min_ago(10),
                "text": "🛑 algum texto com emoji",
            },
        ]
        k = _build_kommo(notas)
        assert k._ts_ultimo_humano_escreveu(1) is None
