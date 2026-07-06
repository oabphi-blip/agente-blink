"""Testes de ÚLTIMA MENS HUMANO — carimbo do último humano (created_by != 0).

Origem: Fábio 06/07/2026. Backend puro, sem webhook do Kommo: lê notas do
lead e devolve o created_at da mais recente com autor humano.
"""
import pytest

from voice_agent.kommo import _parse_created_at_epoch


class TestParseCreatedAt:
    def test_none(self):
        assert _parse_created_at_epoch(None) is None

    def test_epoch_int(self):
        assert _parse_created_at_epoch(1783270139) == 1783270139.0

    def test_epoch_float(self):
        assert _parse_created_at_epoch(1783270139.5) == 1783270139.5

    def test_epoch_string(self):
        assert _parse_created_at_epoch("1783270139") == 1783270139.0

    def test_iso_utc(self):
        # 2026-07-06T11:00:00Z
        val = _parse_created_at_epoch("2026-07-06T11:00:00Z")
        assert isinstance(val, float) and val > 0

    def test_iso_offset(self):
        val = _parse_created_at_epoch("2026-07-06T08:00:00-03:00")
        assert isinstance(val, float) and val > 0

    def test_string_invalida(self):
        assert _parse_created_at_epoch("nao-e-data") is None

    def test_vazio(self):
        assert _parse_created_at_epoch("") is None


class _FakeKommo:
    """Stub mínimo que expõe get_lead_notes + o método real."""
    def __init__(self, notas):
        self._notas = notas

    def get_lead_notes(self, lead_id, limit=50):
        return self._notas

    # reusa a implementação real
    from voice_agent.kommo import KommoClient as _KC
    ts_ultima_msg_humano = _KC.ts_ultima_msg_humano


class TestTsUltimaMsgHumano:
    def test_sem_notas_none(self):
        assert _FakeKommo([]).ts_ultima_msg_humano(1) is None

    def test_so_bot_none(self):
        notas = [
            {"created_by": 0, "created_at": 1783000000},
            {"created_by": 0, "created_at": 1783000100},
        ]
        assert _FakeKommo(notas).ts_ultima_msg_humano(1) is None

    def test_pega_humano_mais_recente(self):
        notas = [
            {"created_by": 0, "created_at": 1783000300},        # bot
            {"created_by": 8834455, "created_at": 1783000200},  # humano
            {"created_by": 8834455, "created_at": 1783000100},  # humano antigo
        ]
        assert _FakeKommo(notas).ts_ultima_msg_humano(1) == 1783000200.0

    def test_ignora_bot_mesmo_sendo_mais_recente(self):
        notas = [
            {"created_by": 0, "created_at": 1783999999},        # bot recente
            {"created_by": 12345, "created_at": 1783000200},    # humano
        ]
        assert _FakeKommo(notas).ts_ultima_msg_humano(1) == 1783000200.0

    def test_created_at_iso(self):
        notas = [
            {"created_by": 999, "created_at": "2026-07-06T11:00:00Z"},
        ]
        v = _FakeKommo(notas).ts_ultima_msg_humano(1)
        assert isinstance(v, float) and v > 0

    def test_created_by_ausente_tratado_como_bot(self):
        notas = [{"created_at": 1783000000}]  # sem created_by → 0 → bot
        assert _FakeKommo(notas).ts_ultima_msg_humano(1) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
