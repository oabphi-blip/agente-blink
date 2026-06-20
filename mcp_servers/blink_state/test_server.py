"""Pytest blink-state — Sprint 3 com fakeredis."""
from __future__ import annotations
import pytest
import fakeredis


@pytest.fixture
def srv(monkeypatch):
    """Servidor com fakeredis."""
    from blink_state import server as s
    fake = fakeredis.FakeRedis(decode_responses=True)
    s._set_redis(fake)
    yield s
    fake.flushall()


def test_dedup_primeira_msg_eh_nova(srv):
    assert srv.dedup_check("5561999", "oi") is True


def test_dedup_msg_repetida_eh_duplicata(srv):
    srv.dedup_check("5561999", "oi")
    assert srv.dedup_check("5561999", "oi") is False


def test_dedup_msg_diferente_passa(srv):
    srv.dedup_check("5561999", "oi")
    assert srv.dedup_check("5561999", "outra msg") is True


def test_dedup_msg_diferente_phone_passa(srv):
    srv.dedup_check("5561999", "oi")
    assert srv.dedup_check("5561111", "oi") is True


def test_lock_primeira_pegada_ok(srv):
    assert srv.acquire_conversation_lock("5561999") is True


def test_lock_segunda_pegada_falha(srv):
    srv.acquire_conversation_lock("5561999")
    assert srv.acquire_conversation_lock("5561999") is False


def test_lock_libera_e_pega_de_novo(srv):
    srv.acquire_conversation_lock("5561999")
    srv.release_conversation_lock("5561999")
    assert srv.acquire_conversation_lock("5561999") is True


def test_reservar_slot_primeira_vez(srv):
    out = srv.reservar_slot_temporariamente(
        phone="5561999", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    assert out["ok"] is True
    assert out["ja_reservado_por_outro"] is False


def test_reservar_slot_ja_pego_por_outro(srv):
    srv.reservar_slot_temporariamente(
        phone="5561111", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    out = srv.reservar_slot_temporariamente(
        phone="5561999", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    assert out["ok"] is False
    assert out["ja_reservado_por_outro"] is True
    assert out["phone_dono"] == "5561111"


def test_reservar_slot_mesmo_phone_renova(srv):
    """Mesmo phone pode renovar a própria reserva sem conflito."""
    srv.reservar_slot_temporariamente(
        phone="5561999", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    out = srv.reservar_slot_temporariamente(
        phone="5561999", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    assert out["ok"] is True


def test_liberar_reserva_permite_outro_pegar(srv):
    srv.reservar_slot_temporariamente(
        phone="5561111", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    srv.liberar_reserva_slot(
        cod_agenda=4, cod_medico=12080, cod_unidade=5,
        data_iso="2026-06-22", hora="09:30",
    )
    out = srv.reservar_slot_temporariamente(
        phone="5561999", cod_agenda=4, cod_medico=12080,
        cod_unidade=5, data_iso="2026-06-22", hora="09:30",
    )
    assert out["ok"] is True


def test_turno_dia_incrementa(srv):
    assert srv.incrementar_turno_dia("5561999") == 1
    assert srv.incrementar_turno_dia("5561999") == 2
    assert srv.incrementar_turno_dia("5561999") == 3


def test_consultar_turno_dia_zero_se_nao_existe(srv):
    assert srv.consultar_turno_dia("5561999") == 0


def test_ctx_known_salva_e_carrega(srv):
    ctx = {"nome": "Maria", "medico": "Karla", "unidade": "Asa Norte"}
    srv.salvar_ctx_known("5561999", ctx)
    out = srv.carregar_ctx_known("5561999")
    assert out == ctx


def test_ctx_known_inexistente_retorna_none(srv):
    assert srv.carregar_ctx_known("5561888") is None


def test_pydantic_data_iso_invalida_rejeita(srv):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        srv.reservar_slot_temporariamente(
            phone="5561999", cod_agenda=4, cod_medico=12080,
            cod_unidade=5, data_iso="22/06/2026", hora="09:30",  # formato BR errado
        )


def test_pydantic_hora_invalida_rejeita(srv):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        srv.reservar_slot_temporariamente(
            phone="5561999", cod_agenda=4, cod_medico=12080,
            cod_unidade=5, data_iso="2026-06-22", hora="9:30",  # sem zero à esquerda
        )
