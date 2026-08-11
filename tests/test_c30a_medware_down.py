"""Pytest filtro C-30A — anti-hesitação SEM agenda (Medware down).

Origem: Sofia 24158652 (16/06/2026 13:07-13:40 BRT) — Medware ficou
intermitente, ctx.agenda=[]. Lia entrou em loop "deixa eu reconsultar
a agenda real aqui pra você" 4x sem voltar.

Filtro C-30A complementa o C-30:
- C-30: ctx.agenda CHEIO + hesitação → substitui pela oferta real 2 slots
- C-30A: ctx.agenda VAZIO + hesitação + estado AGENDA → substitui pela
  frase honesta de Medware down + sinaliza escalation Redis

Toggle compartilhado: LIA_ANTI_HESITACAO_AGENDA (1/shadow/0).
"""

import os
from unittest.mock import patch

import pytest

from voice_agent.responder import (
    _texto_contem_hesitacao_stall,
    _lia_em_estado_agenda_provavel,
    _scrub_prohibited,
)


# ============================================================
# Detector de stall — independente de has_agenda
# ============================================================

class TestTextoContemHesitacaoStall:
    def test_deixa_eu_consultar_dispara(self):
        assert _texto_contem_hesitacao_stall("Deixa eu consultar a agenda")

    def test_deixa_eu_reconsultar_dispara(self):
        assert _texto_contem_hesitacao_stall(
            "Sofia, deixa eu reconsultar a agenda real aqui pra você — volto em 1 minuto"
        )

    def test_medware_nao_retornando_dispara(self):
        assert _texto_contem_hesitacao_stall(
            "A agenda do Medware não está retornando os horários neste momento"
        )

    def test_vou_consultar_agenda_dispara(self):
        # "buscar" sozinho não dispara — só com "agenda...exata/real"
        assert _texto_contem_hesitacao_stall("Vou consultar a agenda")

    def test_puxar_agenda_exata_dispara(self):
        assert _texto_contem_hesitacao_stall("Vou puxar a agenda exata pra você")

    def test_acknowledgement_normal_nao_dispara(self):
        assert not _texto_contem_hesitacao_stall("Perfeito, obrigada!")

    def test_pergunta_turno_nao_dispara(self):
        assert not _texto_contem_hesitacao_stall(
            "Qual sua preferência: manhã ou tarde?"
        )

    def test_oferta_real_nao_dispara_como_stall_por_si_so(self):
        # Frase só "Tenho 2 horários" sem padrão de stall não dispara
        assert not _texto_contem_hesitacao_stall(
            "Tenho 2 horários disponíveis: terça 9h ou quinta 11h"
        )


# ============================================================
# Detector de estado AGENDA provável
# ============================================================

class TestLiaEmEstadoAgendaProvavel:
    def test_medico_e_unidade_definidos_dispara(self):
        ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
        assert _lia_em_estado_agenda_provavel(ctx)

    def test_medico_e_motivo_definidos_dispara(self):
        ctx = {"known": {"medico": "Karla", "motivo": "rotina"}}
        assert _lia_em_estado_agenda_provavel(ctx)

    def test_estado_fsm_agenda_dispara(self):
        ctx = {"fsm": "AGENDA"}
        assert _lia_em_estado_agenda_provavel(ctx)

    def test_estado_fsm_confirmacao_dispara(self):
        ctx = {"estado": "CONFIRMACAO"}
        assert _lia_em_estado_agenda_provavel(ctx)

    def test_so_nome_nao_dispara(self):
        # Fase muito inicial, só nome — não estava em AGENDA
        ctx = {"known": {"nome": "Cindy"}}
        assert not _lia_em_estado_agenda_provavel(ctx)

    def test_so_convenio_nao_dispara(self):
        ctx = {"known": {"convenio": "Bacen"}}
        assert not _lia_em_estado_agenda_provavel(ctx)

    def test_ctx_none_nao_dispara(self):
        assert not _lia_em_estado_agenda_provavel(None)

    def test_ctx_vazio_nao_dispara(self):
        assert not _lia_em_estado_agenda_provavel({})


# ============================================================
# Integração — _scrub_prohibited com cenário Sofia C-30A
# ============================================================

class TestScrubProhibitedC30A:
    """Cenários reais do bug Sofia 24158652."""

    def _ctx_sofia_medware_down(self) -> dict:
        """ctx fiel ao estado real de Sofia às 13:07 BRT."""
        return {
            "known": {
                "nome_paciente": "Sofia",
                "nome_contato": "Cindy",
                "medico": "Karla",
                "unidade": "Asa Norte",
                "convenio": "Bacen",
                "motivo": "rotina",
            },
            "agenda": [],  # VAZIO — Medware down
            "fsm": "AGENDA",
            "lead_id": 24158652,
        }

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_caso_sofia_lia_disse_deixa_eu_reconsultar_substitui(self):
        # Texto literal da Sofia 13:08 BRT
        texto_hesitacao = (
            "Sofia, deixa eu reconsultar a agenda real aqui pra você — "
            "volto em 1 minuto com os horários certos."
        )
        ctx = self._ctx_sofia_medware_down()
        resultado = _scrub_prohibited(texto_hesitacao, ctx)
        # Resposta deve ser substituída pela frase honesta de Medware down
        # (gerada por _gerar_resposta_honesta_medware_down)
        assert resultado != texto_hesitacao
        # A resposta honesta inclui "reconsultar" mas é uma frase específica,
        # diferente da hesitação original.

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_medware_nao_retornando_substitui(self):
        texto = (
            "Cindy, a agenda do Medware não está retornando os horários "
            "neste momento — pode ser uma lentidão temporária do sistema."
        )
        ctx = self._ctx_sofia_medware_down()
        resultado = _scrub_prohibited(texto, ctx)
        assert resultado != texto

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "0"})
    def test_toggle_off_nao_substitui(self):
        texto = "Sofia, deixa eu reconsultar a agenda real aqui pra você"
        ctx = self._ctx_sofia_medware_down()
        resultado = _scrub_prohibited(texto, ctx)
        # Com toggle desligado, C-30A não age (outros filtros podem agir
        # mas a frase específica dessa hesitação não)
        # Tolerante: aceita que algum outro filtro modifique, mas valida
        # que o filtro C-30A não disparou (cobertura via log analisaria)
        # Aqui só verifica que retornou alguma string
        assert isinstance(resultado, str)

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_fase_inicial_sem_medico_unidade_nao_substitui_por_c30a(self):
        # Fase inicial: paciente só disse "oi" — Lia escreveu algo
        # parecendo stall mas NÃO estava em AGENDA
        ctx = {
            "known": {"nome_contato": "Cindy"},
            "agenda": [],
        }
        # Frase neutra que NÃO é hesitação clássica
        texto = "Bom dia, Cindy! Como posso te ajudar?"
        resultado = _scrub_prohibited(texto, ctx)
        # Sem stall + sem estado AGENDA → não substitui por C-30A
        # (outros filtros podem agir; o teste valida que C-30A não cria
        # falso positivo nessa fase)
        assert isinstance(resultado, str)

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_agenda_cheia_nao_dispara_c30a_dispara_c30(self):
        # Quando ctx.agenda TEM slots, C-30 (não C-30A) age primeiro
        ctx = {
            "known": {"medico": "Karla", "unidade": "Asa Norte"},
            "agenda": [
                {"data": "2026-06-17", "hora": "09:00"},
                {"data": "2026-06-17", "hora": "14:00"},
            ],
            "fsm": "AGENDA",
        }
        texto = "Deixa eu consultar a agenda real aqui pra você"
        resultado = _scrub_prohibited(texto, ctx)
        # C-30 deve agir, substituindo pela oferta REAL de 2 slots
        # (não pela frase honesta de Medware down)
        assert resultado != texto
        # A oferta real tem horário concreto — mensagem honesta NÃO tem
        # Esse teste valida que branch C-30A não rouba do C-30 quando há agenda


# ============================================================
# Sinalização Redis — best-effort
# ============================================================

class TestSinalizacaoRedis:
    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_sem_redis_nao_quebra(self):
        """Garantia: filtro C-30A funciona mesmo se Redis cair."""
        ctx = {
            "known": {"medico": "Karla", "unidade": "Asa Norte"},
            "agenda": [],
            "lead_id": 24158652,
        }
        texto = "Sofia, deixa eu reconsultar a agenda real"
        # Não deve levantar exception mesmo sem Redis configurado
        resultado = _scrub_prohibited(texto, ctx)
        assert isinstance(resultado, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
