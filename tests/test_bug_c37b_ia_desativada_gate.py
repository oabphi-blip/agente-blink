"""Pytest blindando Bug C-37b — agent_paused_for_lead lê ATIVADO IA?

Origem: lead 21341221 Lívia/Linielle (18/06/2026).
Bug fundamental dos retrocessos: agent ignorava o campo custom
"ATIVADO IA?" do Kommo. Humano clicava "Desativar IA" mas Lia
continuava respondendo. Causa raiz de TODOS os bugs C-37 e similares.

Fix: regra 0 em agent_paused_for_lead — se known["ativado_ia"] =
"Desativado", retorna "ia-desativada" antes de qualquer outra
checagem.
"""
import pytest

from voice_agent.kommo import KommoClient


@pytest.fixture
def cli():
    """Instância mínima do KommoClient (sem auth — só os métodos
    síncronos in-memory)."""
    return KommoClient.__new__(KommoClient)


class TestRegra0IADesativada:
    """Lead com ATIVADO IA? = Desativado nunca recebe resposta."""

    def test_ativado_ia_desativado_returns_ia_desativada(self, cli):
        ctx = {
            "found": True,
            "status_id": 102560495,  # 3-AGENDAR (etapa NORMAL)
            "known": {"ativado_ia": "Desativado"},
        }
        assert cli.agent_paused_for_lead(ctx, window_min=30) == "ia-desativada"

    def test_ativado_ia_uppercase(self, cli):
        ctx = {
            "found": True,
            "status_id": 102560495,
            "known": {"ativado_ia": "DESATIVADO"},
        }
        assert cli.agent_paused_for_lead(ctx, 30) == "ia-desativada"

    def test_ativado_ia_off_returns_ia_desativada(self, cli):
        ctx = {
            "found": True,
            "status_id": 102560495,
            "known": {"ativado_ia": "OFF"},
        }
        assert cli.agent_paused_for_lead(ctx, 30) == "ia-desativada"

    def test_ativado_ia_ativado_nao_pausa(self, cli):
        """Quando IA está Ativada, agent NÃO pausa por regra 0."""
        ctx = {
            "found": True,
            "status_id": 102560495,
            "known": {"ativado_ia": "Ativado"},
        }
        # Pode retornar None ou outro motivo (regra 1/2 etc), mas NÃO ia-desativada
        result = cli.agent_paused_for_lead(ctx, 30)
        assert result != "ia-desativada"

    def test_known_vazio_nao_quebra(self, cli):
        ctx = {"found": True, "status_id": 102560495, "known": {}}
        result = cli.agent_paused_for_lead(ctx, 30)
        assert result != "ia-desativada"

    def test_known_none_nao_quebra(self, cli):
        ctx = {"found": True, "status_id": 102560495, "known": None}
        result = cli.agent_paused_for_lead(ctx, 30)
        assert result != "ia-desativada"


class TestCasoRealLivia21341221:
    """Cenário exato do bug C-37."""

    def test_lead_livia_18_06_2026(self, cli):
        """Lead Lívia tinha ATIVADO IA = Desativado + status 5-AGENDADO
        (101507507). Antes do fix, agent respondia mesmo assim."""
        ctx = {
            "found": True,
            "status_id": 101507507,  # 5-AGENDADO (etapa NORMAL)
            "known": {"ativado_ia": "Desativado"},
        }
        motivo = cli.agent_paused_for_lead(ctx, 30)
        assert motivo == "ia-desativada", (
            "Lead Lívia (21341221) tinha ATIVADO IA = Desativado mas Lia "
            "continuou respondendo. Esse é o bug C-37b. Fix deve detectar."
        )


class TestPrioridadeRegras:
    """Regra 0 é avaliada ANTES das regras 1 e 2."""

    def test_ia_desativada_vence_etapa_humana(self, cli):
        """Lead em 1-ATENDIMENTO HUMANO + IA Desativada → ia-desativada
        (mais específico)."""
        ctx = {
            "found": True,
            "status_id": 106563343,  # 1-ATENDIMENTO HUMANO
            "known": {"ativado_ia": "Desativado"},
        }
        # Regra 0 retorna primeiro
        assert cli.agent_paused_for_lead(ctx, 30) == "ia-desativada"

    def test_ia_ativada_em_etapa_humana_retorna_etapa_humana(self, cli):
        """Lead em 1-ATENDIMENTO HUMANO + IA Ativada → etapa-humana
        (regra 1)."""
        ctx = {
            "found": True,
            "status_id": 106563343,
            "known": {"ativado_ia": "Ativado"},
        }
        assert cli.agent_paused_for_lead(ctx, 30) == "etapa-humana"
