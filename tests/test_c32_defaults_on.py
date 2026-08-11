"""Pytest Bug C-32 — Defaults ON pra envs críticas.

Origem: Fábio 16/06/2026, lead 24113652. Healthz revelou que LIA_TOOLS_ENABLED
e TRACING_ENABLED estavam ausentes/=0 em prod, então fix #183 (tool calling
forçado) e replay estavam INERTES. Modelo continuava escrevendo texto livre
em FSM=AGENDA e inventando data/dia da semana.

Lição arquitetural: env esquecida = code completed mas inerte. Reincidente
em C-29 (watchdog erros:6), C-30 (filtro hesitação atrás de gate), C-31
(filtros calendário atrás de FILTROS_LEGACY). Causa raiz comum: padrão
"default OFF, ligar pra usar".

Fix C-32: inverter pra DEFAULT ON.
- LIA_TOOLS_ENABLED default ON
- TRACING_ENABLED default ON
- PIPELINE_LOCK_ENABLED já era default ON ✅

Pra desligar (rollback emergencial): setar pra "0" / "false" / "no" / "off".
"""
import os
from unittest.mock import patch

import pytest

from voice_agent.tools_lia import tools_habilitadas
from voice_agent.tracing import esta_habilitado as tracing_habilitado


class TestLiaToolsEnabledDefaultOn:
    """LIA_TOOLS_ENABLED default ON desde C-32."""

    def test_sem_env_default_on(self):
        """Sem env setada = ligado. (Caso default em prod novos.)"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIA_TOOLS_ENABLED", None)
            assert tools_habilitadas() is True

    def test_env_vazia_default_on(self):
        """Env="" também é tratada como ausente — ligado."""
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": ""}):
            # String vazia cai no `or "1"` → fica ligado
            assert tools_habilitadas() is True

    def test_env_1_ligado(self):
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "1"}):
            assert tools_habilitadas() is True

    def test_env_true_ligado(self):
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "true"}):
            assert tools_habilitadas() is True

    def test_env_0_desligado(self):
        """Pra desligar precisa setar EXPLICITAMENTE."""
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "0"}):
            assert tools_habilitadas() is False

    def test_env_false_desligado(self):
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "false"}):
            assert tools_habilitadas() is False

    def test_env_no_desligado(self):
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "no"}):
            assert tools_habilitadas() is False

    def test_env_off_desligado(self):
        with patch.dict(os.environ, {"LIA_TOOLS_ENABLED": "off"}):
            assert tools_habilitadas() is False


class TestTracingEnabledDefaultOn:
    """TRACING_ENABLED default ON desde C-32."""

    def test_sem_env_default_on(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRACING_ENABLED", None)
            assert tracing_habilitado() is True

    def test_env_vazia_default_on(self):
        with patch.dict(os.environ, {"TRACING_ENABLED": ""}):
            assert tracing_habilitado() is True

    def test_env_1_ligado(self):
        with patch.dict(os.environ, {"TRACING_ENABLED": "1"}):
            assert tracing_habilitado() is True

    def test_env_0_desligado(self):
        with patch.dict(os.environ, {"TRACING_ENABLED": "0"}):
            assert tracing_habilitado() is False

    def test_env_false_desligado(self):
        with patch.dict(os.environ, {"TRACING_ENABLED": "false"}):
            assert tracing_habilitado() is False


class TestRollbackPath:
    """Rollback emergencial — setar explicitamente pra '0' desliga."""

    def test_tools_e_tracing_off_em_emergencia(self):
        with patch.dict(os.environ, {
            "LIA_TOOLS_ENABLED": "0",
            "TRACING_ENABLED": "0",
        }):
            assert tools_habilitadas() is False
            assert tracing_habilitado() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
