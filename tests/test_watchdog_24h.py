"""Blindagem do fix watchdog 24h (task #178 / 04/06/2026).

Antes: watchdog só rodava seg-sáb 8h-18h BRT. Blink atende 24h via
Lia (e equipe humana em rodízio), então o watchdog também tem que
varrer 24h.

Plus: novo nível de silêncio CRÍTICO (30min) que indica que humano
precisa intervir, não só "Lia muda" leve.
"""
import os
from unittest.mock import patch


def test_eh_horario_comercial_sempre_true_por_default():
    """Sem env, Blink atende 24h."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WATCHDOG_RESTRINGIR_HORARIO", None)
        from voice_agent.watchdog_lia import _eh_horario_comercial
        assert _eh_horario_comercial() is True


def test_eh_horario_comercial_pode_ser_restringido_via_env():
    """Toggle reversa: setar 1 reativa janela seg-sáb 8-18."""
    from datetime import datetime, timedelta, timezone
    domingo_14h = datetime(2026, 6, 7, 14, 0,
                            tzinfo=timezone(timedelta(hours=-3)))
    with patch.dict(os.environ, {"WATCHDOG_RESTRINGIR_HORARIO": "1"}):
        from voice_agent.watchdog_lia import _eh_horario_comercial
        # Domingo é bloqueado quando restrição ativa
        assert _eh_horario_comercial(domingo_14h) is False


def test_silencio_critico_default_30min():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WATCHDOG_SILENCIO_CRITICO_SEG", None)
        from voice_agent.watchdog_lia import _silencio_critico_seg
        assert _silencio_critico_seg() == 30 * 60


def test_silencio_critico_configuravel_via_env():
    with patch.dict(os.environ, {"WATCHDOG_SILENCIO_CRITICO_SEG": "900"}):
        from voice_agent.watchdog_lia import _silencio_critico_seg
        assert _silencio_critico_seg() == 900


def test_silencio_critico_valor_invalido_cai_no_default():
    with patch.dict(os.environ,
                     {"WATCHDOG_SILENCIO_CRITICO_SEG": "abc"}):
        from voice_agent.watchdog_lia import _silencio_critico_seg
        assert _silencio_critico_seg() == 30 * 60


def test_constante_critico_30min_correta():
    from voice_agent.watchdog_lia import SILENCIO_CRITICO_SEG
    assert SILENCIO_CRITICO_SEG == 30 * 60
