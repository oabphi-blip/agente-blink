"""Pytest dos 3 fixes do bug Adelia (lead 24056883 — 01/06/2026).

1. Retry no horarios_para_agente (3x com backoff)
2. Circuit breaker: 3 ctx[agenda]=[] consecutivos → escalonar humano
3. selecionar_agrupador early no pipeline (preenche 1.EXAMES sem gravar)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# Retry no Medware
# ----------------------------------------------------------------------

class TestRetryHorariosParaAgente:

    def _make_client(self, respostas_listar):
        """Cria um MedwareClient com listar_horarios_livres mockado."""
        from voice_agent.medware import MedwareClient
        c = object.__new__(MedwareClient)
        c.listar_horarios_livres = MagicMock(side_effect=respostas_listar)
        # MedwareClient.horarios_para_agente é unbound, vamos chamar direto
        return c

    def test_sucesso_na_primeira_nao_chama_de_novo(self):
        from voice_agent.medware import MedwareClient
        slots_ok = [{"data": "2026-06-02", "horario": "09:00", "codAgenda": 5,
                     "codUnidade": 5, "codMedico": 12080}]
        c = self._make_client([slots_ok])
        with patch("voice_agent.medware.time.sleep") as mock_sleep:
            out = MedwareClient.horarios_para_agente(
                c, "Dra. Karla Delalibera", "Asa Norte",
            )
        assert len(out) == 1
        assert c.listar_horarios_livres.call_count == 1
        assert not mock_sleep.called

    def test_3_chamadas_vazias_retorna_lista_vazia(self):
        from voice_agent.medware import MedwareClient
        c = self._make_client([[], [], []])
        with patch("voice_agent.medware.time.sleep"):
            out = MedwareClient.horarios_para_agente(
                c, "Dra. Karla Delalibera",
            )
        assert out == []
        assert c.listar_horarios_livres.call_count == 3

    def test_sucesso_apos_2_falhas_pega_resultado(self):
        from voice_agent.medware import MedwareClient
        slots_ok = [{"data": "2026-06-02", "horario": "09:00", "codAgenda": 5,
                     "codUnidade": 5, "codMedico": 12080}]
        c = self._make_client([[], [], slots_ok])
        with patch("voice_agent.medware.time.sleep") as mock_sleep:
            out = MedwareClient.horarios_para_agente(
                c, "Dra. Karla Delalibera",
            )
        assert len(out) == 1
        assert c.listar_horarios_livres.call_count == 3
        # 2 sleeps entre as 3 tentativas
        assert mock_sleep.call_count == 2

    def test_exception_e_tratada_como_vazio_e_tenta_de_novo(self):
        from voice_agent.medware import MedwareClient
        slots_ok = [{"data": "2026-06-02", "horario": "09:00", "codAgenda": 5,
                     "codUnidade": 5, "codMedico": 12080}]
        # 1ª exception, 2ª vazia, 3ª sucesso
        c = self._make_client([
            RuntimeError("medware down"),
            [],
            slots_ok,
        ])
        with patch("voice_agent.medware.time.sleep"):
            out = MedwareClient.horarios_para_agente(
                c, "Dra. Karla Delalibera",
            )
        assert len(out) == 1
        assert c.listar_horarios_livres.call_count == 3

    def test_medico_nao_mapeado_nao_tenta(self):
        from voice_agent.medware import MedwareClient
        c = self._make_client([])
        out = MedwareClient.horarios_para_agente(
            c, "Dr. Inexistente",
        )
        assert out == []
        # listar_horarios_livres NÃO foi chamado nenhuma vez
        assert c.listar_horarios_livres.call_count == 0

    def test_backoff_progressivo(self):
        """Backoff dobra: 0.5s → 1s → 2s."""
        from voice_agent.medware import MedwareClient
        c = self._make_client([[], [], []])
        with patch("voice_agent.medware.time.sleep") as mock_sleep:
            MedwareClient.horarios_para_agente(c, "Dra. Karla Delalibera")
        # 2 sleeps entre as 3 tentativas, com valores 0.5 e 1
        sleeps = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleeps == [0.5, 1.0]


# ----------------------------------------------------------------------
# Bloco _agenda_block sem exemplo literal copiável
# ----------------------------------------------------------------------

class TestAgendaBlockSemExemploLiteral:

    def test_nao_tem_mais_exemplo_aprovado_copiavel(self):
        from voice_agent.responder import _agenda_block
        bloco = _agenda_block({"agenda": []})
        # Não deve ter texto idêntico ao fallback antigo que Lia copiava
        assert "Deixa eu reconsultar a agenda real aqui pra você. Me responde" not in bloco
        assert "Exemplo aprovado:" not in bloco

    def test_continua_com_proibicoes_e_instrucao_positiva(self):
        from voice_agent.responder import _agenda_block
        bloco = _agenda_block({"agenda": []})
        # Continua proibindo padrões alucinatórios
        baixa = bloco.lower()
        assert "registrar sua preferência" in baixa
        assert "retorno em horário comercial" in baixa
        # E ensinando o caminho positivo
        assert "reconsult" in baixa or "consult" in baixa

    def test_pede_paciente_diversificar_palavras(self):
        from voice_agent.responder import _agenda_block
        bloco = _agenda_block({"agenda": []})
        # Pede pra Lia variar as palavras
        baixa = bloco.lower()
        assert "diversifique" in baixa or "suas próprias palavras" in baixa


# ----------------------------------------------------------------------
# Agrupador early — método _gravar_agrupador_silencioso
# ----------------------------------------------------------------------

class TestAgrupadorEarly:

    def test_metodo_gravar_agrupador_existe(self):
        from voice_agent.pipeline import VoicePipeline
        assert hasattr(VoicePipeline, "_gravar_agrupador_silencioso")

    def test_grava_silencioso_chama_update(self):
        from voice_agent.pipeline import VoicePipeline
        p = object.__new__(VoicePipeline)
        p.kommo = MagicMock()
        p.kommo.update_lead_fields = MagicMock()
        VoicePipeline._gravar_agrupador_silencioso(
            p, 24056883,
            {"motivo_tipo_paciente_1": "Rotina",
             "agrupador_exames_paciente_1": "Agrupa1-Adulto Rotina (9 exames)"},
        )
        assert p.kommo.update_lead_fields.called
        args = p.kommo.update_lead_fields.call_args
        assert args[0][0] == 24056883
        assert "motivo_tipo_paciente_1" in args[0][1]
        assert "agrupador_exames_paciente_1" in args[0][1]

    def test_grava_silencioso_kommo_none_nao_levanta(self):
        from voice_agent.pipeline import VoicePipeline
        p = object.__new__(VoicePipeline)
        p.kommo = None
        # Não deve crashar
        VoicePipeline._gravar_agrupador_silencioso(p, 1, {"x": "y"})

    def test_grava_silencioso_exception_kommo_nao_levanta(self):
        from voice_agent.pipeline import VoicePipeline
        p = object.__new__(VoicePipeline)
        p.kommo = MagicMock()
        p.kommo.update_lead_fields = MagicMock(
            side_effect=RuntimeError("kommo flaky"),
        )
        # Não deve crashar
        VoicePipeline._gravar_agrupador_silencioso(p, 1, {"x": "y"})
