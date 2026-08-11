"""
Bug C-89 (05/08/2026) — Oferta imediata de 3 slots em turnos diferentes.

Em vez de perguntar "manhã ou tarde?" e depois "início, meio ou fim?",
Lia apresenta 3 horários concretos diretamente (1 manhã + 1 tarde + 1 alternativo
quando sem preferência; 3 do turno preferido quando há preferência no ctx).

Fábio confirmou: mais coerente, ágil e assertivo — reduz 2-3 turnos de
back-and-forth (caso lead 24415586, 05/08/2026).
"""
import pytest
from voice_agent.responder import (
    _selecionar_3_slots_para_oferta,
    _gerar_oferta_3_slots,
    _gerar_oferta_2_slots,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

SLOTS_MANHA = [
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "08:30"},
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "09:00"},
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "10:00"},
]

SLOTS_TARDE = [
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "14:00"},
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "15:30"},
    {"dia_semana": "segunda", "data_br": "11/08", "hora": "17:00"},
]

SLOTS_MISTOS = SLOTS_MANHA[:2] + SLOTS_TARDE[:2]  # 2 manhã + 2 tarde

SLOTS_SO_TARDE = SLOTS_TARDE.copy()

SLOTS_SO_MANHA = SLOTS_MANHA.copy()


# ── _selecionar_3_slots_para_oferta ───────────────────────────────────────────

class TestSelecionar3Slots:

    def test_sem_preferencia_retorna_1_manha_1_tarde_1_extra(self):
        result = _selecionar_3_slots_para_oferta(SLOTS_MISTOS)
        assert len(result) == 3
        horas = [int(s["hora"][:2]) for s in result]
        # deve ter pelo menos 1 manhã e 1 tarde
        assert any(h < 12 for h in horas), "Esperava pelo menos 1 slot de manhã"
        assert any(h >= 12 for h in horas), "Esperava pelo menos 1 slot de tarde"

    def test_sem_preferencia_agenda_vazia_retorna_lista_vazia(self):
        assert _selecionar_3_slots_para_oferta([]) == []

    def test_com_preferencia_manha_retorna_3_de_manha(self):
        # SLOTS_SO_MANHA tem 3 slots de manhã — todos devem ser manhã
        result = _selecionar_3_slots_para_oferta(SLOTS_SO_MANHA, turno_preferido="manhã")
        assert len(result) == 3
        for s in result:
            assert int(s["hora"][:2]) < 12, f"Slot {s['hora']} não é de manhã"

    def test_com_preferencia_tarde_retorna_3_de_tarde(self):
        # SLOTS_SO_TARDE tem 3 slots de tarde — todos devem ser tarde
        result = _selecionar_3_slots_para_oferta(SLOTS_SO_TARDE, turno_preferido="tarde")
        assert len(result) == 3
        for s in result:
            assert int(s["hora"][:2]) >= 12, f"Slot {s['hora']} não é de tarde"

    def test_com_preferencia_manha_mistos_prioriza_manha(self):
        # SLOTS_MISTOS tem 2 manhã + 2 tarde — com pref manhã, os 2 primeiros são manhã
        result = _selecionar_3_slots_para_oferta(SLOTS_MISTOS, turno_preferido="manhã")
        assert len(result) == 3
        # O primeiro slot deve ser de manhã
        assert int(result[0]["hora"][:2]) < 12
        # Deve ter pelo menos 2 de manhã (os disponíveis) + 1 de tarde pra completar
        horas = [int(s["hora"][:2]) < 12 for s in result]
        assert sum(horas) >= 2, "Esperava pelo menos 2 slots de manhã"

    def test_preferencia_manha_sem_manha_suficiente_completa_com_tarde(self):
        # Só 1 slot de manhã + 2 de tarde → devolve 1 manhã + 2 tarde
        agenda = [SLOTS_MANHA[0]] + SLOTS_TARDE[:2]
        result = _selecionar_3_slots_para_oferta(agenda, turno_preferido="manhã")
        assert len(result) == 3
        # O de manhã deve ser o primeiro
        assert int(result[0]["hora"][:2]) < 12

    def test_so_slots_manha_sem_preferencia_retorna_3_manha(self):
        result = _selecionar_3_slots_para_oferta(SLOTS_SO_MANHA)
        assert len(result) == 3
        for s in result:
            assert int(s["hora"][:2]) < 12

    def test_so_slots_tarde_sem_preferencia_retorna_3_tarde(self):
        result = _selecionar_3_slots_para_oferta(SLOTS_SO_TARDE)
        assert len(result) == 3
        for s in result:
            assert int(s["hora"][:2]) >= 12

    def test_retorna_maximo_3_mesmo_com_agenda_grande(self):
        agenda = SLOTS_MANHA + SLOTS_TARDE  # 6 slots
        result = _selecionar_3_slots_para_oferta(agenda)
        assert len(result) == 3

    def test_agenda_com_1_slot_retorna_1(self):
        result = _selecionar_3_slots_para_oferta([SLOTS_MANHA[0]])
        assert len(result) == 1

    def test_preferencia_case_insensitive_manha(self):
        result = _selecionar_3_slots_para_oferta(SLOTS_MISTOS, turno_preferido="MANHÃ")
        # deve funcionar case-insensitive
        assert isinstance(result, list)

    def test_preferencia_variante_manha_sem_acento(self):
        result = _selecionar_3_slots_para_oferta(SLOTS_MISTOS, turno_preferido="manha")
        assert isinstance(result, list)
        assert len(result) > 0


# ── _gerar_oferta_3_slots ─────────────────────────────────────────────────────

def ctx_com_agenda(agenda, known=None):
    return {
        "found": True,
        "agenda": agenda,
        "medico": "Dra. Karla Delalíbera",
        "known": known or {"unidade": "Asa Norte"},
    }


class TestGerarOferta3Slots:

    def test_retorna_string(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        assert isinstance(result, str)
        assert len(result) > 10

    def test_contem_3_emojis_numerados(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        assert "1️⃣" in result
        assert "2️⃣" in result
        assert "3️⃣" in result

    def test_contem_nome_medico(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        assert "Karla" in result

    def test_contem_unidade(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        assert "Asa Norte" in result

    def test_contem_horas_dos_slots(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        # pelo menos uma hora deve aparecer
        assert "08:30" in result or "09:00" in result or "14:00" in result

    def test_contem_pergunta_ao_final(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        assert "?" in result  # deve ter pergunta

    def test_agenda_vazia_retorna_fallback_reconferir(self):
        ctx = ctx_com_agenda([])
        result = _gerar_oferta_3_slots(ctx)
        # deve retornar mensagem de fallback (não quebrar)
        assert isinstance(result, str)
        assert "minuto" in result.lower() or "agenda" in result.lower()

    def test_ctx_none_nao_quebra(self):
        result = _gerar_oferta_3_slots(None)
        assert isinstance(result, str)
        assert len(result) > 5

    def test_turno_preferido_tarde_inclui_slots_tarde(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS, known={"unidade": "Asa Norte", "turno_preferido": "tarde"})
        result = _gerar_oferta_3_slots(ctx)
        # todos os 3 slots devem ser de tarde (>=12h)
        # verificar que pelo menos "14:" aparece
        assert "14:" in result or "15:" in result or "17:" in result

    def test_nao_menciona_periodo_turno(self):
        """❌ NUNCA deve sugerir 'início, meio ou fim do turno' na oferta."""
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        result_lower = result.lower()
        assert "início, meio ou fim" not in result_lower
        assert "período do turno" not in result_lower
        assert "início do turno" not in result_lower

    def test_nao_pergunta_manha_ou_tarde(self):
        """❌ NUNCA deve perguntar 'manhã ou tarde?' — já mostra as opções."""
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_3_slots(ctx)
        result_lower = result.lower()
        assert "manhã ou tarde" not in result_lower
        assert "qual turno" not in result_lower


# ── _gerar_oferta_2_slots delegação para _gerar_oferta_3_slots ───────────────

class TestGerarOferta2SlotsDelega:
    """Garante que _gerar_oferta_2_slots delegue para _gerar_oferta_3_slots (compat)."""

    def test_2_slots_retorna_mesmo_que_3_slots(self):
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result_2 = _gerar_oferta_2_slots(ctx)
        result_3 = _gerar_oferta_3_slots(ctx)
        assert result_2 == result_3

    def test_2_slots_contem_3_emojis(self):
        """Backward-compat: _gerar_oferta_2_slots agora devolve 3 opções."""
        ctx = ctx_com_agenda(SLOTS_MISTOS)
        result = _gerar_oferta_2_slots(ctx)
        assert "1️⃣" in result
        assert "2️⃣" in result
        assert "3️⃣" in result


# ── integração: ctx.known.turno_preferido flui até seleção ───────────────────

class TestIntegracaoTurnoPref:

    def test_turno_pref_do_intent_classifier_flui_ate_selecao(self):
        """Simula que IntentClassifier injetou turno_preferido='manhã'."""
        ctx = ctx_com_agenda(SLOTS_MISTOS, known={"unidade": "Asa Norte", "turno_preferido": "manhã"})
        result = _gerar_oferta_3_slots(ctx)
        # Com preferência manhã, esperamos ver slots de manhã
        assert "08:" in result or "09:" in result or "10:" in result
