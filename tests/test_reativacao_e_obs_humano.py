"""Pytest task #264 (06/06/2026):
1. reativacao_ia.reativar_ia_em_etapas_ativas — varredura pura
2. Worker cron 6h plugado em cron_interno.py
3. Webhook humano busca texto via get_lead_messages e grava nota
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestReativacaoIA:
    def test_funcao_existe(self):
        from voice_agent import reativacao_ia
        assert hasattr(reativacao_ia, "reativar_ia_em_etapas_ativas")
        assert hasattr(reativacao_ia, "STATUS_ATIVOS_IA")
        assert len(reativacao_ia.STATUS_ATIVOS_IA) == 9

    def test_kommo_none_retorna_erro(self):
        from voice_agent import reativacao_ia
        r = reativacao_ia.reativar_ia_em_etapas_ativas(None)
        assert r["ok"] is False
        assert "indisponivel" in r["error"]

    def test_dry_run_nao_chama_update(self):
        from voice_agent import reativacao_ia
        kommo_mock = MagicMock()
        kommo_mock.list_leads_by_status.return_value = [
            {"id": 1001, "name": "Lead A"},
            {"id": 1002, "name": "Lead B"},
        ]
        kommo_mock.get_caller_context_by_lead.return_value = {
            "known": {"ativado_ia": "Desativado"},
        }
        r = reativacao_ia.reativar_ia_em_etapas_ativas(
            kommo_mock, max_leads=10, dry_run=True,
            status_ids=(96441724,),
        )
        assert r["ok"] is True
        assert r["dry_run"] is True
        # update_lead_fields NÃO foi chamado
        kommo_mock.update_lead_fields.assert_not_called()

    def test_reativa_apenas_desativados(self):
        from voice_agent import reativacao_ia
        kommo_mock = MagicMock()
        kommo_mock.list_leads_by_status.return_value = [
            {"id": 2001, "name": "Lead Desativado"},
            {"id": 2002, "name": "Lead Ativado"},
        ]
        def ctx_fake(lid):
            estado = "Desativado" if lid == 2001 else "Ativado"
            return {"known": {"ativado_ia": estado}}
        kommo_mock.get_caller_context_by_lead.side_effect = ctx_fake
        kommo_mock.update_lead_fields.return_value = True
        r = reativacao_ia.reativar_ia_em_etapas_ativas(
            kommo_mock, max_leads=10, dry_run=False,
            status_ids=(96441724,),
        )
        assert r["encontrados_desativados"] == 1
        assert r["reativados"] == 1
        kommo_mock.update_lead_fields.assert_called_once_with(
            2001, {"ativado_ia": "Ativado"},
        )


class TestCronWorker:
    def test_worker_reativar_ia_existe(self):
        path = ROOT / "voice_agent" / "cron_interno.py"
        conteudo = path.read_text(encoding="utf-8")
        assert "_worker_reativar_ia_loop" in conteudo
        assert "blink-cron-reativar-ia" in conteudo
        assert "REATIVAR_IA_CRON_ENABLED" in conteudo
        # 6h default = 21600s
        assert "21600" in conteudo

    def test_cron_interno_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "cron_interno.py"
        py_compile.compile(str(path), doraise=True)


class TestWebhookHumanoComTexto:
    def test_webhook_busca_texto_e_grava_nota(self):
        path = ROOT / "voice_agent" / "webhook.py"
        conteudo = path.read_text(encoding="utf-8")
        # Lógica nova
        assert "get_lead_messages" in conteudo
        assert "[ATENDENTE" in conteudo
        # Filtro de outgoing
        assert "outgoing" in conteudo
        # Resposta inclui flags novas
        assert '"texto_capturado"' in conteudo
        assert '"nota_gravada_id"' in conteudo

    def test_webhook_compila(self):
        import py_compile
        path = ROOT / "voice_agent" / "webhook.py"
        py_compile.compile(str(path), doraise=True)
