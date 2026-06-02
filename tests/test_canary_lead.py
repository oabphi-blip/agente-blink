"""Pytest do canary lead diário (Pilar #5)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# _validar_step
# ----------------------------------------------------------------------

class TestValidarStep:

    def test_must_contain_bate_passa(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(
            nome="x", user_text="oi", must_contain=["olá", "ajud"],
        )
        assert _validar_step(s, "Olá! Posso te ajudar?") is True

    def test_must_contain_nao_bate_falha(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(
            nome="x", user_text="oi", must_contain=["agendamento"],
        )
        assert _validar_step(s, "Olá!") is False

    def test_must_not_contain_bate_falha(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(
            nome="x", user_text="oi",
            must_contain=["olá"],
            must_not_contain=["pix", "300,50"],
        )
        # Tem must_contain mas tb tem proibido
        assert _validar_step(
            s, "Olá! Envie 300,50 via Pix",
        ) is False

    def test_basta_um_must_contain(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(
            nome="x", user_text="oi",
            must_contain=["nome", "nasc"],
        )
        # Só tem "nome" — passa
        assert _validar_step(s, "Qual seu nome?") is True

    def test_resposta_vazia_falha(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(
            nome="x", user_text="oi", must_contain=["olá"],
        )
        assert _validar_step(s, "") is False

    def test_sem_must_contain_passa(self):
        from voice_agent.canary_lead import (
            _validar_step, StepResultado,
        )
        s = StepResultado(nome="x", user_text="oi")
        assert _validar_step(s, "qualquer coisa") is True


# ----------------------------------------------------------------------
# tick (com simulate_inbound mockado)
# ----------------------------------------------------------------------

class TestTick:

    def test_todos_steps_OK(self, monkeypatch):
        from voice_agent.canary_lead import tick

        # Mock que retorna respostas que satisfazem todos os 14 steps
        # (7 happy + 7 bugs históricos).
        def fake(phone, text):
            tl = text.lower()
            # Happy path
            if "gostaria de agendar" in tl:
                return {"resposta_lia": "Olá! Posso te ajudar"}
            if "rotina" in tl:
                return {"resposta_lia": "Qual seu nome e data de nascimento?"}
            if "nasci" in tl:
                return {"resposta_lia": "Qual seu convênio?"}
            if "stf-med" in tl:
                return {"resposta_lia": "Tenho opções de agenda e horários"}
            if "prefiro manhã" in tl:
                return {"resposta_lia": "Tenho 08:00, 09:00, 10:00, 11:00"}
            if "primeiro horário" in tl:
                return {"resposta_lia": "Confirma seu CPF, por favor?"}
            if "cpf é 111" in tl:
                return {"resposta_lia": "Consulta confirmada e marcada!"}
            # Bugs históricos (08-14)
            if "imagem pelo whatsapp" in tl:
                return {"resposta_lia": "Recebi, obrigado! Vou conferir."}
            if "confirma minha consulta" in tl:
                return {"resposta_lia": "Sua consulta está marcada para o dia 09/06"}
            if "quanto custa" in tl:
                return {"resposta_lia": "O valor da consulta é R$..."}
            if "pedro silva" in tl:
                return {"resposta_lia": "Vou marcar pro Pedro, qual a data de nasc dele?"}
            if "dr. fabrício" in tl or "dr. fabricio" in tl:
                return {"resposta_lia": "Vou confirmar com a Karla ou o Fabricio"}
            if "qualquer horário" in tl:
                return {"resposta_lia": "Tenho horários disponíveis"}
            if "não vou usar convênio" in tl:
                return {"resposta_lia": "Particular: o valor da consulta é R$..."}
            return {"resposta_lia": "?"}

        res = tick(
            fake, MagicMock(),
            phone="5561900000000", dry_run=True,
            pular_medware=True, pular_cleanup=True,
        )
        assert res.steps_total == 14
        assert res.steps_ok == 14
        assert res.steps_falhou == []
        assert res.duracao_total_ms >= 0

    def test_step_1_falha_para_no_meio(self):
        from voice_agent.canary_lead import tick

        def fake_quebrada(phone, text):
            # Resposta sempre vazia → falha no 1º step
            return {"resposta_lia": ""}

        res = tick(
            fake_quebrada, MagicMock(),
            phone="5561900000000", dry_run=False,
        )
        # Para no 1º (sem alertar porque webhook não configurado)
        assert res.steps_ok == 0
        assert len(res.steps_falhou) == 1
        assert res.steps_falhou[0] == "01_saudacao"

    def test_excecao_no_simulate_marca_erro_no_step(self):
        from voice_agent.canary_lead import tick

        def fake_explode(phone, text):
            raise RuntimeError("api down")

        res = tick(
            fake_explode, MagicMock(),
            phone="5561900000000", dry_run=True,
            pular_medware=True, pular_cleanup=True,
        )
        # Em dry_run continua, todos os 14 falham
        assert res.steps_ok == 0
        assert len(res.steps_falhou) == 14
        # Cada step capturou o erro
        for d in res.steps_detalhe:
            assert d["erro"] is not None
            assert "api down" in d["erro"]

    def test_dry_run_NAO_envia_slack(self, monkeypatch):
        from voice_agent import canary_lead

        chamadas = []

        def fake_post(*a, **kw):
            chamadas.append(1)
            return True

        monkeypatch.setattr(canary_lead, "_envia_slack", fake_post)

        def fake(phone, text):
            return {"resposta_lia": ""}

        canary_lead.tick(
            fake, MagicMock(),
            phone="5561900000000", dry_run=True,
        )
        assert chamadas == []


# ----------------------------------------------------------------------
# Habilitado / phone / webhook
# ----------------------------------------------------------------------

class TestConfig:

    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("CANARY_ENABLED", raising=False)
        from voice_agent.canary_lead import esta_habilitado
        assert esta_habilitado() is False

    def test_on(self, monkeypatch):
        monkeypatch.setenv("CANARY_ENABLED", "1")
        from voice_agent.canary_lead import esta_habilitado
        assert esta_habilitado() is True

    def test_canary_phone_default(self, monkeypatch):
        monkeypatch.delenv("CANARY_PHONE", raising=False)
        from voice_agent.canary_lead import _canary_phone, CANARY_PHONE_DEFAULT
        assert _canary_phone() == CANARY_PHONE_DEFAULT

    def test_canary_phone_custom(self, monkeypatch):
        monkeypatch.setenv("CANARY_PHONE", "5561999999999")
        from voice_agent.canary_lead import _canary_phone
        assert _canary_phone() == "5561999999999"

    def test_webhook_fallback(self, monkeypatch):
        monkeypatch.delenv("SLACK_WEBHOOK_CANARY_URL", raising=False)
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://fallback")
        from voice_agent.canary_lead import _webhook_url
        assert _webhook_url() == "http://fallback"

    def test_webhook_especifico_vence(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_CANARY_URL", "http://especifico")
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://fallback")
        from voice_agent.canary_lead import _webhook_url
        assert _webhook_url() == "http://especifico"


# ----------------------------------------------------------------------
# Payload Slack
# ----------------------------------------------------------------------

class TestPayloadSlack:

    def test_payload_falha_lista_steps(self):
        from voice_agent.canary_lead import (
            _payload_falha, CanaryResultado,
        )
        res = CanaryResultado(
            canary_phone="5561900000000",
            iniciado_em="2026-06-02T00:00:00",
            steps_total=7,
            steps_ok=3,
            steps_falhou=["04_convenio", "05_preferencia"],
            duracao_total_ms=4500,
        )
        p = _payload_falha(res)
        assert "FALHOU" in p["text"]
        assert "3/7" in p["text"]
        assert "04_convenio" in p["text"]

    def test_payload_ok_compacto(self):
        from voice_agent.canary_lead import (
            _payload_ok, CanaryResultado,
        )
        res = CanaryResultado(
            canary_phone="5561900000000",
            steps_total=7,
            steps_ok=7,
            duracao_total_ms=4500,
        )
        p = _payload_ok(res)
        assert "OK" in p["text"]
        assert "7/7" in p["text"]
