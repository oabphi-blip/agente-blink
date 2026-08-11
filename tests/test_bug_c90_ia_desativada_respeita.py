"""
Bug C-90 (05/08/2026) — P0: agente respondia mesmo com ATIVADO IA = Desativado
ou lead em 1-ATENDIMENTO HUMANO.

Causa raiz: bloco C-49 em pipeline.py auto-resetava o campo de "Desativado"
para "Ativado" em cada mensagem ANTES de agent_paused_for_lead() ser chamado.
Resultado: na 1ª mensagem Lia ficava silenciosa (context ainda "Desativado"),
mas na 2ª mensagem C-49 já tinha gravado "Ativado" no Kommo → Lia respondia.

Fix: remoção completa do bloco C-49. O webhook /admin/kommo-trigger-status-change
é responsável por reativar IA quando o lead muda de etapa legitimamente.
Desativação manual por atendente DEVE ser respeitada permanentemente.
"""
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from voice_agent.kommo import ST_AGENT_OFF


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_kommo_client():
    """Retorna instância mínima de KommoClient com mocks para I/O."""
    from voice_agent.kommo import KommoClient
    client = KommoClient.__new__(KommoClient)
    # Mock de _ts_ultimo_humano_escreveu para não precisar de Redis
    client._ts_ultimo_humano_escreveu = MagicMock(return_value=None)
    # Mock de _verifica_bloqueio_clinico para não precisar de I/O
    client._verifica_bloqueio_clinico = MagicMock(return_value=None)
    return client


def _ctx(status_id: int = 102560495, ativado_ia: str = "Ativado") -> dict:
    return {
        "found": True,
        "lead_id": 99999,
        "status_id": status_id,
        "known": {"ativado_ia": ativado_ia},
    }


# ── Testes: C-49 removido do pipeline.py ──────────────────────────────────────

class TestC49Removido:
    """Garantir que o bloco C-49 foi removido do pipeline.py."""

    def _pipeline_src(self) -> str:
        path = os.path.join(os.path.dirname(__file__), "..", "voice_agent", "pipeline.py")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_pipeline_nao_tem_STATUS_ATIVOS_IA_PIPELINE(self):
        assert "_STATUS_ATIVOS_IA_PIPELINE" not in self._pipeline_src(), (
            "REGRESSÃO C-90: _STATUS_ATIVOS_IA_PIPELINE presente em pipeline.py. "
            "O bloco C-49 que reativava ATIVADO IA automaticamente foi reintroduzido."
        )

    def test_pipeline_nao_tem_log_auto_reset_c49(self):
        assert "Auto-reset ATIVADO IA=Ativado" not in self._pipeline_src(), (
            "REGRESSÃO C-90: log do C-49 ainda presente em pipeline.py"
        )

    def test_pipeline_tem_comentario_remocao(self):
        assert "REMOVIDO Bug C-49" in self._pipeline_src(), (
            "Comentário 'REMOVIDO Bug C-49' não encontrado — fix C-90 pode ter sido revertido"
        )


# ── Testes: ST_AGENT_OFF correto ─────────────────────────────────────────────

class TestSTAgentOff:

    def test_atendimento_humano_em_ST_AGENT_OFF(self):
        assert 106563343 in ST_AGENT_OFF

    def test_etapas_ativas_nao_estao_em_ST_AGENT_OFF(self):
        etapas_ativas = {96441724, 101508307, 102560495, 106184631}
        for etapa in etapas_ativas:
            assert etapa not in ST_AGENT_OFF, f"Etapa {etapa} não deveria estar em ST_AGENT_OFF"


# ── Testes: agent_paused_for_lead comportamento ───────────────────────────────

class TestAgentPausedBehavior:

    def test_desativado_retorna_ia_desativada(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="Desativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "ia-desativada"

    def test_desativado_uppercase_retorna_ia_desativada(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="DESATIVADO")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "ia-desativada"

    def test_desativada_feminino_retorna_ia_desativada(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="Desativada")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "ia-desativada"

    def test_off_retorna_ia_desativada(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="off")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "ia-desativada"

    def test_atendimento_humano_retorna_etapa_humana(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=106563343, ativado_ia="Ativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "etapa-humana"

    def test_ativado_em_etapa_ativa_retorna_none(self):
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="Ativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None

    def test_ctx_none_retorna_none(self):
        client = _make_kommo_client()
        motivo = client.agent_paused_for_lead(None, window_min=30)
        assert motivo is None

    def test_ctx_not_found_retorna_none(self):
        client = _make_kommo_client()
        ctx = {"found": False, "lead_id": 1, "status_id": 102560495, "known": {}}
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None

    def test_desativado_tem_prioridade_sobre_etapa_ativa(self):
        """Mesmo em etapa ativa (3-AGENDAR), Desativado bloqueia."""
        client = _make_kommo_client()
        ctx = _ctx(status_id=102560495, ativado_ia="Desativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "ia-desativada"

    def test_humano_escreveu_recente_bloqueia(self):
        """Se humano escreveu há menos de 30min → silêncio temporário."""
        client = _make_kommo_client()
        # Simula humano escrevendo 5 min atrás
        client._ts_ultimo_humano_escreveu = MagicMock(
            return_value=time.time() - 5 * 60
        )
        ctx = _ctx(status_id=102560495, ativado_ia="Ativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo == "humano-escreveu-recente"

    def test_humano_escreveu_ha_mais_de_30min_nao_bloqueia(self):
        """Após 30min do humano escrever, IA volta automaticamente."""
        client = _make_kommo_client()
        # 35 min atrás
        client._ts_ultimo_humano_escreveu = MagicMock(
            return_value=time.time() - 35 * 60
        )
        ctx = _ctx(status_id=102560495, ativado_ia="Ativado")
        motivo = client.agent_paused_for_lead(ctx, window_min=30)
        assert motivo is None
