"""Pytest da camada 3 do ja_agendado — parser de NOTA HUMANA.

Origem: Fábio 02/06/2026. Atendente humano agenda no Medware + escreve
nota livre, sem atualizar status_id (camada 1) nem 1.DIA CONSULTA
(camada 2). Lia ficava cega e oferecia slot do zero. Camada 3 procura
nas notas dos últimos 72h por padrão "agendei + data".
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def _iso_ago(horas: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(hours=horas)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ----------------------------------------------------------------------
# _ja_agendado_por_nota_humana
# ----------------------------------------------------------------------

class TestNotaHumana:

    def test_nota_humana_recente_com_agendei_e_data_DISPARA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(2),
            "created_by": 11132911,
            "text": "Stephany: Agendei 09/06 às 18:30 com Dra Karla, paciente confirmou.",
        }]
        ok, preview = _ja_agendado_por_nota_humana(notas)
        assert ok is True
        assert "agendei" in preview.lower()
        assert "09/06" in preview

    def test_nota_humana_velha_72h_IGNORA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(100),  # 100h > 72h
            "created_by": 11132911,
            "text": "Agendei consulta 09/06 às 18:30",
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is False

    def test_nota_do_bot_created_by_zero_IGNORA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 0,  # bot
            "text": "Agendei 09/06 com Karla",
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is False

    def test_nota_humana_sem_palavra_chave_IGNORA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 11132911,
            "text": "Paciente ligou perguntando, vou retornar amanhã.",
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is False

    def test_nota_humana_palavra_mas_sem_data_IGNORA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 11132911,
            "text": "Agendei a consulta",  # sem data
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is False

    def test_variantes_palavra_chave(self):
        """Marquei, gravei, confirmei, salvei, reservei — todos disparam."""
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        variantes = [
            "Marquei 09/06 às 14h",
            "Gravei no Medware 10/06",
            "Confirmou para 09/06 18:30",
            "Salvei agendamento 09/06",
            "Reservei sexta 09/06",
            "Agendamento feito 09/06",
        ]
        for texto in variantes:
            notas = [{
                "created_at": _iso_ago(1),
                "created_by": 11132911,
                "text": texto,
            }]
            ok, _ = _ja_agendado_por_nota_humana(notas)
            assert ok, f"deveria disparar pra: {texto!r}"

    def test_data_com_dia_da_semana_basta(self):
        """Mesmo sem DD/MM, dia da semana conta como data."""
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 11132911,
            "text": "Agendei para terça-feira de manhã com Karla",
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is True

    def test_data_so_hora_basta(self):
        """14h sozinho conta como data parseável."""
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 11132911,
            "text": "Agendei consulta às 14h",
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is True

    def test_pega_a_primeira_nota_humana_que_bate(self):
        """Se há múltiplas notas, retorna a primeira encontrada."""
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [
            {
                "created_at": _iso_ago(2),
                "created_by": 0,  # bot ignora
                "text": "Lia agendou 09/06 às 18h",
            },
            {
                "created_at": _iso_ago(1),
                "created_by": 11132911,
                "text": "Stephany: Confirmou 09/06 às 18:30",
            },
        ]
        ok, preview = _ja_agendado_por_nota_humana(notas)
        assert ok is True
        assert "Stephany" in preview

    def test_lista_vazia_devolve_False(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        assert _ja_agendado_por_nota_humana([]) == (False, None)
        assert _ja_agendado_por_nota_humana(None) == (False, None)

    def test_nota_sem_text_IGNORA(self):
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(1),
            "created_by": 11132911,
            "text": None,
        }]
        ok, _ = _ja_agendado_por_nota_humana(notas)
        assert ok is False

    def test_janela_h_customizavel(self):
        """Permite override da janela."""
        from voice_agent.kommo import _ja_agendado_por_nota_humana
        notas = [{
            "created_at": _iso_ago(50),  # 50h
            "created_by": 11132911,
            "text": "Agendei 09/06 às 18h",
        }]
        # Janela default 72h → dispara
        ok, _ = _ja_agendado_por_nota_humana(notas, janela_h=72)
        assert ok is True
        # Janela 24h → não dispara
        ok, _ = _ja_agendado_por_nota_humana(notas, janela_h=24)
        assert ok is False
