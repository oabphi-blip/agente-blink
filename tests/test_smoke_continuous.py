"""Pytest do smoke_continuous: valida cenários + executor + alerta Slack.

Não bate em produção — usa httpx mock pra simular respostas.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.smoke_continuous import (  # noqa: E402
    CENARIOS_CORE,
    Cenario,
    _validar_resposta,
    executar_cenario,
    rodar_batch_completo,
)


# ----------------------------------------------------------------------
# Cenarios catalogados — sanidade
# ----------------------------------------------------------------------

class TestCenariosCore:

    def test_pelo_menos_5_cenarios(self):
        assert len(CENARIOS_CORE) >= 5

    def test_todos_tem_nome_unico(self):
        nomes = [c.nome for c in CENARIOS_CORE]
        assert len(nomes) == len(set(nomes))

    def test_juliene_evasiva_blinda_frase_exata(self):
        """C3 precisa proteger contra a frase original do bug Juliene."""
        c3 = next(c for c in CENARIOS_CORE if c.nome == "C3-juliene-evasiva")
        patterns = " | ".join(c3.must_not_contain)
        assert "registrar" in patterns
        assert "comercial" in patterns


# ----------------------------------------------------------------------
# Validador de resposta — regex matches
# ----------------------------------------------------------------------

class TestValidarResposta:

    @pytest.fixture
    def cenario_juliene(self):
        return Cenario(
            nome="test", descricao="d", phone="x", text="y",
            must_contain=(),
            must_not_contain=(
                r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
                r"retorno em hor[áa]rio comercial",
            ),
        )

    def test_resposta_segura_passa(self, cenario_juliene):
        ok, motivo = _validar_resposta(
            cenario_juliene,
            "Tenho terça-feira 02/06 às 09:00. Fica bom pra você?",
        )
        assert ok is True
        assert motivo == "ok"

    def test_frase_juliene_falha(self, cenario_juliene):
        ok, motivo = _validar_resposta(
            cenario_juliene,
            "Vou registrar sua preferência para a equipe finalizar — "
            "retorno em horário comercial.",
        )
        assert ok is False
        assert "must_not_contain" in motivo or "BATEU" in motivo

    def test_resposta_vazia_falha(self, cenario_juliene):
        ok, motivo = _validar_resposta(cenario_juliene, "")
        assert ok is False
        assert "vazio" in motivo or "curto" in motivo

    def test_must_contain_obrigatorio(self):
        c = Cenario(
            nome="t", descricao="d", phone="x", text="y",
            must_contain=(r"\blia\b", r"\bblink\b"),
            must_not_contain=(),
        )
        # Falta "blink" → falha
        ok, motivo = _validar_resposta(c, "Oi, sou a Lia. Como posso ajudar?")
        assert ok is False
        assert "blink" in motivo.lower()
        # Com os 2 → passa
        ok, motivo = _validar_resposta(c, "Oi, sou a Lia, da Blink Oftalmologia")
        assert ok is True


# ----------------------------------------------------------------------
# Execução com httpx mockado
# ----------------------------------------------------------------------

class TestExecutarCenario:

    @patch("voice_agent.smoke_continuous.httpx.get")
    def test_resposta_ok_passa(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": "Olá! Sou a Lia, da Blink Oftalmologia."
        }
        mock_get.return_value = mock_response
        c = CENARIOS_CORE[0]  # C1-saudacao
        r = executar_cenario(c)
        assert r.ok is True
        assert r.motivo == "ok"
        assert r.nome == "C1-saudacao"

    @patch("voice_agent.smoke_continuous.httpx.get")
    def test_frase_juliene_e_pega(self, mock_get):
        """Se a Lia retornasse a frase original do bug, smoke detecta."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "answer": (
                "Perfeito! Vou registrar sua preferência para a equipe "
                "finalizar — retorno em horário comercial (seg–sex, 8h–18h)."
            )
        }
        mock_get.return_value = mock_response
        # C3 ou qualquer cenário com must_not_contain "registrar...equipe"
        c3 = next(c for c in CENARIOS_CORE if c.nome == "C3-juliene-evasiva")
        r = executar_cenario(c3)
        assert r.ok is False
        assert "registrar" in r.motivo or "BATEU" in r.motivo

    @patch("voice_agent.smoke_continuous.httpx.get")
    def test_http_500_falha(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "server error"
        mock_get.return_value = mock_response
        r = executar_cenario(CENARIOS_CORE[0])
        assert r.ok is False
        assert "HTTP 500" in r.motivo

    @patch("voice_agent.smoke_continuous.httpx.get")
    def test_exception_de_rede_falha(self, mock_get):
        mock_get.side_effect = RuntimeError("connection refused")
        r = executar_cenario(CENARIOS_CORE[0])
        assert r.ok is False
        assert "exception" in r.motivo.lower()


# ----------------------------------------------------------------------
# Batch completo — agrega resultados
# ----------------------------------------------------------------------

class TestBatch:

    @patch("voice_agent.smoke_continuous.executar_cenario")
    def test_batch_todos_passam(self, mock_exec):
        from voice_agent.smoke_continuous import ResultadoCenario
        mock_exec.return_value = ResultadoCenario(
            nome="x", ok=True, motivo="ok",
            answer_preview="", elapsed_ms=10,
        )
        rel = rodar_batch_completo()
        assert rel.ok == len(CENARIOS_CORE)
        assert rel.falhas == []

    @patch("voice_agent.smoke_continuous._enviar_slack_alerta")
    @patch("voice_agent.smoke_continuous.executar_cenario")
    def test_batch_com_falha_alerta_slack(self, mock_exec, mock_slack):
        from voice_agent.smoke_continuous import ResultadoCenario
        # Primeiro passa, resto falha
        respostas = [
            ResultadoCenario("x", True, "ok", "", 10)
        ] + [
            ResultadoCenario("y", False, "must_not_contain BATEU", "", 12)
            for _ in CENARIOS_CORE[1:]
        ]
        mock_exec.side_effect = respostas
        rel = rodar_batch_completo()
        assert rel.ok == 1
        assert len(rel.falhas) == len(CENARIOS_CORE) - 1
        assert mock_slack.called

    @patch("voice_agent.smoke_continuous._enviar_slack_alerta")
    @patch("voice_agent.smoke_continuous.executar_cenario")
    def test_batch_sem_falha_nao_alerta(self, mock_exec, mock_slack):
        from voice_agent.smoke_continuous import ResultadoCenario
        mock_exec.return_value = ResultadoCenario(
            "x", True, "ok", "", 10,
        )
        rodar_batch_completo()
        assert mock_slack.called is False


# ----------------------------------------------------------------------
# Worker daemon — só sobe se SMOKE_ENABLED=1
# ----------------------------------------------------------------------

class TestWorkerToggle:

    def test_smoke_desabilitado_nao_sobe(self, monkeypatch):
        monkeypatch.delenv("SMOKE_ENABLED", raising=False)
        from voice_agent.smoke_continuous import iniciar_smoke_worker
        stop = iniciar_smoke_worker()
        assert stop is None

    def test_smoke_habilitado_sobe_thread(self, monkeypatch):
        monkeypatch.setenv("SMOKE_ENABLED", "1")
        # Não queremos esperar 60s — patch wait pra retornar True imediato
        with patch("voice_agent.smoke_continuous.threading.Event") as mock_ev:
            mock_instance = MagicMock()
            mock_instance.wait.return_value = True
            mock_instance.is_set.return_value = False
            mock_ev.return_value = mock_instance
            from voice_agent.smoke_continuous import iniciar_smoke_worker
            stop = iniciar_smoke_worker()
            assert stop is not None
