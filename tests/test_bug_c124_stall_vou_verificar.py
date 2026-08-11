"""
Bug C-124 (11/08/2026) — Stall "Vou verificar os próximos horários disponíveis"
em loop (lead 20734711 Samuel Rosario Vargas).

Causa raiz:
  1. C-51.3 (despejou valor junto com slots) intercepta resposta LLM.
  2. Fallback: _gerar_proxima_pergunta_sem_convenio(ctx) retorna stall
     mesmo quando ctx["agenda"] tem slots reais.
  3. deve_ofertar_agora() retorna False para lead retorno (FSM != AGENDA).
  4. Stall emitido em cada turno sem sair do loop.

Fixes:
  1. _gerar_proxima_pergunta_sem_convenio: quando ctx.agenda → _gerar_oferta_2_slots
  2. _FAKE_AGENDA_LOOKUP: pega a frase exata do stall
  3. deve_ofertar_agora: bypass FSM para retorno com intenção + agenda + dados prontos
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO"):
    """Contexto representativo do lead 20734711 Samuel."""
    slots = []
    if tem_agenda:
        slots = [
            {"data": "2026-08-14", "hora": "09:30", "medico": "Karla", "unidade": "Asa Norte"},
            {"data": "2026-08-14", "hora": "14:00", "medico": "Karla", "unidade": "Asa Norte"},
        ]
    return {
        "agenda": slots,
        "fsm": {"estado": fsm_estado},
        "ja_agendado": False,
        "known": {
            "nome_contato": "Samuel Rosario Vargas",  # nome completo (checklist exige >=2 palavras)
            "nome_paciente": "Samuel Rosario Vargas",
            "data_nascimento": "1990-05-12",
            "convenio": "Saúde Caixa",
            "convenio_definido": True,
            "unidade": "Asa Norte",
            "medico": "Karla",
            "day_pref": "quinta",    # C-81 pré-extração
            "turno": "manhã",        # C-81 pré-extração
        },
    }


# =========================================================================
# FIX 1: _gerar_proxima_pergunta_sem_convenio retorna slots quando disponível
# =========================================================================

class TestFix1GeraPerguntaComSlots(unittest.TestCase):
    def _call(self, ctx):
        from voice_agent.responder import _gerar_proxima_pergunta_sem_convenio
        return _gerar_proxima_pergunta_sem_convenio(ctx)

    def test_com_agenda_retorna_slots_nao_stall(self):
        """Fix 1: ctx com agenda → deve retornar oferta de slots, não 'Vou verificar'."""
        ctx = _make_ctx_samuel(tem_agenda=True)
        result = self._call(ctx)
        self.assertNotIn("Vou verificar", result,
            "Fix 1 falhou: stall ainda emitido quando ctx.agenda tem slots")
        # Deve conter algo indicando horário real
        self.assertTrue(
            "1️⃣" in result or "2️⃣" in result or "09:30" in result or "14:00" in result
            or "Quinta" in result or "quinta" in result,
            f"Fix 1: resposta não parece oferta de slots: {result!r}"
        )

    def test_sem_agenda_retorna_stall_controlado(self):
        """Sem agenda → stall controlado ainda é esperado (Medware vazio)."""
        ctx = _make_ctx_samuel(tem_agenda=False)
        result = self._call(ctx)
        self.assertIn("Vou verificar", result,
            "Sem agenda, stall é a resposta esperada")

    def test_sem_unidade_retorna_pergunta_unidade(self):
        """Sem unidade → pergunta unidade (C-51 normal)."""
        ctx = _make_ctx_samuel(tem_agenda=True)
        ctx["known"].pop("unidade", None)
        result = self._call(ctx)
        self.assertIn("nidade", result.lower(),
            "Sem unidade deve perguntar Asa Norte ou Águas Claras")

    def test_ctx_none_nao_quebra(self):
        """ctx=None não deve levantar exceção."""
        result = self._call(None)
        self.assertIsInstance(result, str)

    def test_ctx_vazio_nao_quebra(self):
        """ctx vazio não deve levantar exceção."""
        result = self._call({})
        self.assertIsInstance(result, str)


# =========================================================================
# FIX 2: _FAKE_AGENDA_LOOKUP — frase exata do stall
# =========================================================================

class TestFix2FakeAgendaLookup(unittest.TestCase):
    def _viola(self, text, has_agenda=True):
        from voice_agent.responder import _viola_oferta_agenda
        return _viola_oferta_agenda(text, has_agenda)

    def test_frase_exata_stall_detectada(self):
        """Fix 2: frase exata 'Vou verificar os próximos horários disponíveis' → violação."""
        stall = "Anotado, Samuel. Vou verificar os próximos horários disponíveis e já te apresento as opções."
        self.assertTrue(self._viola(stall, has_agenda=True),
            "Frase exata do stall não detectada por _FAKE_AGENDA_LOOKUP")

    def test_variante_stall_detectada(self):
        """Variante: 'vou verificar os próximos horários' → violação."""
        stall = "Certo! Vou verificar os próximos horários disponíveis pra você."
        self.assertTrue(self._viola(stall, has_agenda=True))

    def test_apresenta_opcoes_detectada(self):
        """Fix 2: 'já te apresento as opções' → violação."""
        stall = "Um momento, já te apresento as opções de horário."
        self.assertTrue(self._viola(stall, has_agenda=True))

    def test_sem_agenda_nao_viola(self):
        """Sem agenda, filtro C-30 não age (C-30A cuida)."""
        stall = "Vou verificar os próximos horários disponíveis."
        self.assertFalse(self._viola(stall, has_agenda=False))

    def test_oferta_real_nao_viola(self):
        """Oferta legítima com emojis não é stall."""
        oferta = "1️⃣ Quinta-feira (14/08) às 09:30\n2️⃣ Quinta-feira (14/08) às 14:00"
        self.assertFalse(self._viola(oferta, has_agenda=True))


# =========================================================================
# FIX 3: deve_ofertar_agora — bypass FSM para retorno
# =========================================================================

class TestFix3DeveOfertarAgoraBypassFSM(unittest.TestCase):
    def _deve(self, ctx):
        from voice_agent.oferta_deterministica import deve_ofertar_agora
        return deve_ofertar_agora(ctx)

    def _patch_ativado(self):
        return patch(
            "voice_agent.oferta_deterministica._ativado",
            return_value=True
        )

    def test_fsm_agenda_funciona_normal(self):
        """Caminho normal: FSM=AGENDA com dados completos → True."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="AGENDA")
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertTrue(result, "FSM=AGENDA deveria retornar True")

    def test_bypass_fsm_pos_gravacao_com_intencao_e_agenda(self):
        """Fix 3: FSM=POS_GRAVACAO + intenção + agenda + dados prontos → True (retorno)."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertTrue(result,
            "Fix 3 falhou: deve_ofertar_agora retornou False para retorno com intenção+agenda")

    def test_bypass_fsm_triagem_com_intencao_e_agenda(self):
        """FSM=TRIAGEM + intenção + agenda + dados prontos → True."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="TRIAGEM")
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertTrue(result,
            "TRIAGEM + intenção + agenda deveria retornar True")

    def test_bypass_nao_dispara_sem_agenda(self):
        """FSM=POS_GRAVACAO + SEM agenda → False (sem slots para oferecer)."""
        ctx = _make_ctx_samuel(tem_agenda=False, fsm_estado="POS_GRAVACAO")
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertFalse(result, "Sem agenda não deve oferecer")

    def test_bypass_nao_dispara_sem_intencao(self):
        """FSM=POS_GRAVACAO + agenda + SEM intenção → False."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        # Remover todos os sinais de intenção
        ctx["known"].pop("day_pref", None)
        ctx["known"].pop("turno", None)
        ctx["known"].pop("intent_agendar", None)
        ctx["known"].pop("slots_selecionados", None)
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertFalse(result, "Sem intenção não deve bypassar FSM")

    def test_bypass_nao_dispara_sem_unidade(self):
        """Fix 3 requer unidade definida."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        ctx["known"].pop("unidade", None)
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertFalse(result, "Sem unidade não deve oferecer")

    def test_bypass_nao_dispara_sem_medico(self):
        """Fix 3 requer médico definido."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        ctx["known"].pop("medico", None)
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertFalse(result, "Sem médico não deve oferecer")

    def test_bypass_nao_dispara_ja_agendado(self):
        """ja_agendado=True → nunca ofertar (proteção Esther/Sophia)."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        ctx["ja_agendado"] = True
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertFalse(result, "ja_agendado=True deve bloquear mesmo com bypass")

    def test_bypass_com_intent_agendar(self):
        """intent_agendar como sinal de intenção → True."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        ctx["known"].pop("day_pref", None)
        ctx["known"].pop("turno", None)
        ctx["known"]["intent_agendar"] = True
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertTrue(result, "intent_agendar=True deve disparar bypass")

    def test_bypass_com_slots_selecionados(self):
        """slots_selecionados como sinal de intenção → True."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        ctx["known"].pop("day_pref", None)
        ctx["known"].pop("turno", None)
        ctx["known"]["slots_selecionados"] = [{"data": "2026-08-14", "hora": "09:30"}]
        with self._patch_ativado():
            result = self._deve(ctx)
        self.assertTrue(result, "slots_selecionados deve disparar bypass")

    def test_toggle_off_bloqueia_bypass(self):
        """Toggle AGENDA_DETERMINISTICA=0 bloqueia tudo incluindo bypass."""
        ctx = _make_ctx_samuel(tem_agenda=True, fsm_estado="POS_GRAVACAO")
        with patch("voice_agent.oferta_deterministica._ativado", return_value=False):
            result = self._deve(ctx)
        self.assertFalse(result, "Toggle OFF deve bloquear mesmo com bypass")

    def test_ctx_none_nao_quebra(self):
        """ctx=None não deve levantar exceção."""
        with self._patch_ativado():
            result = self._deve(None)
        self.assertFalse(result)


# =========================================================================
# INTEGRAÇÃO: teste do caso real Samuel 20734711
# =========================================================================

class TestCasoRealSamuel20734711(unittest.TestCase):
    """Simula o padrão exato do lead 20734711 que gerou o stall em loop."""

    def test_fim_do_loop_samuel(self):
        """
        Sequência real: paciente disse preferência → C-51 interceptou → stall.
        Com Fix 1: quando C-51.3 cai em _gerar_proxima_pergunta_sem_convenio
        e ctx.agenda tem slots, retorna oferta em vez de stall.
        """
        from voice_agent.responder import _gerar_proxima_pergunta_sem_convenio

        # Samuel: unidade definida, agenda disponível
        ctx = _make_ctx_samuel(tem_agenda=True)

        result = _gerar_proxima_pergunta_sem_convenio(ctx)

        # Não pode ser o stall
        self.assertNotIn("Vou verificar os próximos horários", result)
        # Deve ser uma oferta de slots
        has_slot_indicator = (
            "1️⃣" in result or "2️⃣" in result
            or "09:30" in result or "14:00" in result
            or any(dia in result for dia in ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"])
        )
        self.assertTrue(has_slot_indicator,
            f"Deveria ser oferta de slots, recebeu: {result!r}")

    def test_stall_capturado_quando_agendado_vazio(self):
        """Quando Medware retorna vazio, stall é capturado por _FAKE_AGENDA_LOOKUP."""
        from voice_agent.responder import _viola_oferta_agenda

        # Se de alguma forma o stall escapar para o LLM/filtros com agenda
        stall_text = "Anotado, Samuel. Vou verificar os próximos horários disponíveis e já te apresento as opções."
        # Com has_agenda=True: viola (deveria ter ofertado diretamente)
        self.assertTrue(
            _viola_oferta_agenda(stall_text, has_agenda=True),
            "Stall com agenda disponível deve ser capturado"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
