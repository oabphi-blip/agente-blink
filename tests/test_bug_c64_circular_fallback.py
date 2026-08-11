"""
Bug C-64 (21/07/2026) — Loop circular: fallbacks C-31/C-54 contêm frases stall
que C-60 deveria bloquear. Testa que os 3 fallbacks NÃO iniciam com "Deixa eu".

Causa raiz: _DIA_SEMANA_FALLBACK, _DIA_NAO_ATENDIDO_FALLBACK e _DIA_SEM_DATA_FALLBACK
começavam com "Deixa eu reconferir/conferir..." — a frase exata que C-60 bloqueia.
Quando filtro C-31/C-54 acionava, gerava stall → C-60 deveria pegar mas não pegava
por regex estreito → paciente recebia loop infinito de frases de espera.
"""
import re
import pytest

from voice_agent.responder import (
    _DIA_SEMANA_FALLBACK,
    _DIA_NAO_ATENDIDO_FALLBACK,
    _DIA_SEM_DATA_FALLBACK,
    _FAKE_AGENDA_LOOKUP,
)

STALL_PATTERNS = [
    r"deixa eu\s+(?:conferir|reconferir|verificar|checar)",
    r"vou\s+(?:conferir|reconferir|verificar|checar|buscar|consultar)",
    r"volto em \d+ minuto",
    r"me dá um minutinho",
    r"aguarda\s+(?:só\s+)?um\s+(?:pouco|momentinho|minuto)",
]

def _has_stall(text: str) -> bool:
    for pat in STALL_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


class TestFallbacksNaoContemStall:
    """Os 3 fallbacks não podem conter frases de stall (C-64)."""

    def test_dia_semana_fallback_sem_stall(self):
        assert not _has_stall(_DIA_SEMANA_FALLBACK), (
            f"_DIA_SEMANA_FALLBACK contém stall phrase: {_DIA_SEMANA_FALLBACK!r}"
        )

    def test_dia_nao_atendido_fallback_sem_stall(self):
        assert not _has_stall(_DIA_NAO_ATENDIDO_FALLBACK), (
            f"_DIA_NAO_ATENDIDO_FALLBACK contém stall phrase: {_DIA_NAO_ATENDIDO_FALLBACK!r}"
        )

    def test_dia_sem_data_fallback_sem_stall(self):
        assert not _has_stall(_DIA_SEM_DATA_FALLBACK), (
            f"_DIA_SEM_DATA_FALLBACK contém stall phrase: {_DIA_SEM_DATA_FALLBACK!r}"
        )

    def test_fallbacks_sao_perguntas_diretas(self):
        """Fallbacks devem fazer uma pergunta ou dar info útil, não prometer retorno."""
        for fb, name in [
            (_DIA_SEMANA_FALLBACK, "DIA_SEMANA"),
            (_DIA_NAO_ATENDIDO_FALLBACK, "DIA_NAO_ATENDIDO"),
            (_DIA_SEM_DATA_FALLBACK, "DIA_SEM_DATA"),
        ]:
            # Pelo menos contém um "?" (pergunta direta)
            assert "?" in fb, f"{name} não contém pergunta direta: {fb!r}"

    def test_dia_sem_data_contem_info_calendário(self):
        """_DIA_SEM_DATA_FALLBACK deve mencionar Asa Norte e Águas Claras."""
        assert "Asa Norte" in _DIA_SEM_DATA_FALLBACK
        assert "guas Claras" in _DIA_SEM_DATA_FALLBACK  # Águas ou Aguas


class TestC60PegaFrasesConferirExpandido:
    """C-60 regex expandido (`.{0,60}`) pega frases com gap maior."""

    def _matches_c60(self, text: str) -> bool:
        for pat in _FAKE_AGENDA_LOOKUP:
            if pat.search(text):
                return True
        return False

    def test_frase_caroline_original(self):
        """Frase original Bug C-60 — Caroline 22949500."""
        frase = "Deixa eu conferir os dias direito antes de gravar."
        assert self._matches_c60(frase)

    def test_frase_reconferir_calendario_40chars_gap(self):
        """Gap ~40 chars entre 'reconferir' e 'dia da semana' — era .{0,25}, agora .{0,60}."""
        frase = "reconferir os horários com o calendário aqui. Qual dia da semana"
        assert self._matches_c60(frase)

    def test_frase_reconferir_horarios_aqui(self):
        """Padrão novo: reconferir + horários/calendário/agenda + aqui/correto."""
        frase = "Deixa eu reconferir os horários com o calendário aqui."
        assert self._matches_c60(frase)

    def test_frase_verificar_antes_confirmar(self):
        """verificar X antes de confirmar."""
        frase = "vou verificar a agenda antes de confirmar o horário."
        assert self._matches_c60(frase)

    def test_frase_checar_dias_antes_agendar(self):
        """checar Y dias antes de agendar."""
        frase = "preciso checar os dias certos antes de agendar."
        assert self._matches_c60(frase)

    def test_frase_normal_nao_bloqueada(self):
        """Oferta normal de slot não deve ser bloqueada."""
        frase = "Tenho dois horários: 1️⃣ Quinta (24/07) às 09:30 2️⃣ Terça (29/07) às 14:00"
        assert not self._matches_c60(frase)

    def test_pergunta_direta_nao_bloqueada(self):
        """Perguntar dia/turno sem stall não deve ser bloqueado."""
        frase = "Qual dia da semana e turno funcionam melhor pra você?"
        assert not self._matches_c60(frase)
