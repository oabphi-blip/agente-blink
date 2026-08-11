"""Pytest da camada 5 — detector genérico no histórico de mensagens.

Complementa camada 4 (template Blink preciso). Quando atendente
improvisa fora do template, camada 5 ainda detecta procurando outbound
humano + palavra-chave conclusão + data em qualquer mensagem do
histórico recente (notas humanas + mensagens chat).
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


class TestDetectaConclusaoHistorico:

    def test_mensagem_improvisada_humana_DISPARA(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Stephany: confirmei pra 09/06 às 18h com a Karla, paciente OK",
            "created_at": _iso_ago(2),
            "created_by": 11132911,
        }]
        ok, preview = detectar_conclusao_no_historico(msgs)
        assert ok is True
        assert "Stephany" in preview

    def test_mensagem_robo_NAO_DISPARA(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Lia: agendei pra 09/06 às 18h",
            "created_at": _iso_ago(1),
            "created_by": 0,  # bot
        }]
        ok, _ = detectar_conclusao_no_historico(msgs)
        assert ok is False

    def test_mensagem_velha_72h_IGNORA(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Confirmei 09/06 às 18h",
            "created_at": _iso_ago(100),
            "created_by": 11132911,
        }]
        ok, _ = detectar_conclusao_no_historico(msgs)
        assert ok is False

    def test_palavra_sem_data_NAO_dispara(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Confirmei o agendamento",  # sem data
            "created_at": _iso_ago(1),
            "created_by": 11132911,
        }]
        ok, _ = detectar_conclusao_no_historico(msgs)
        assert ok is False

    def test_data_sem_palavra_NAO_dispara(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Lembrar paciente 09/06 às 18h",  # sem agendei/confirmei
            "created_at": _iso_ago(1),
            "created_by": 11132911,
        }]
        ok, _ = detectar_conclusao_no_historico(msgs)
        assert ok is False

    def test_finalizei_e_concluido_disparam(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        for texto in [
            "Finalizei agendamento 09/06",
            "Concluído 09/06 às 18h",
            "Conclui pra 09/06 18h",
            "Reservei 09/06 com Karla",
        ]:
            msgs = [{
                "text": texto, "created_at": _iso_ago(1),
                "created_by": 11132911,
            }]
            ok, _ = detectar_conclusao_no_historico(msgs)
            assert ok, f"deveria disparar para: {texto!r}"

    def test_pega_primeira_que_bate(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [
            {"text": "oi tudo bem?", "created_at": _iso_ago(3),
             "created_by": 11132911},
            {"text": "Confirmei agendamento 09/06 às 18h",
             "created_at": _iso_ago(1),
             "created_by": 11132911},
        ]
        ok, preview = detectar_conclusao_no_historico(msgs)
        assert ok is True
        assert "Confirmei" in preview

    def test_lista_vazia_None(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        ok, p = detectar_conclusao_no_historico([])
        assert ok is False
        assert p is None

    def test_mensagem_None_ignorada(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{"text": None, "created_at": _iso_ago(1),
                 "created_by": 11132911}]
        ok, _ = detectar_conclusao_no_historico(msgs)
        assert ok is False

    def test_janela_customizavel(self):
        from voice_agent.kommo import detectar_conclusao_no_historico
        msgs = [{
            "text": "Agendei 09/06 às 18h", "created_at": _iso_ago(50),
            "created_by": 11132911,
        }]
        assert detectar_conclusao_no_historico(msgs, janela_h=72)[0] is True
        assert detectar_conclusao_no_historico(msgs, janela_h=24)[0] is False
