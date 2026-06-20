"""Pytest do servidor blink-calendar — Sprint 1.

Cobertura:
1. validar_data_unidade: 8 cenários (Bug C-35 protegido)
2. proximas_datas_disponiveis: 4 cenários
3. gerar_oferta_pronta: 3 cenários
4. Resources: 3 leituras
5. Validação Pydantic: rejeita entradas inválidas (anti-alucinação)
"""
from __future__ import annotations
import pytest
from pydantic import ValidationError

from blink_calendar.server import (
    validar_data_unidade,
    proximas_datas_disponiveis,
    gerar_oferta_pronta,
    listar_medicos,
    agenda_karla,
    agenda_fabricio,
)
from blink_calendar.models import ValidarDataInput, ProximasDatasInput


# ─── validar_data_unidade ───────────────────────────────────────────

def test_karla_segunda_asa_norte_valido():
    out = validar_data_unidade("2026-06-22", "karla", "Asa Norte")
    assert out["dia"] == "Segunda-feira"
    assert out["unidade_atende"] == "Asa Norte"
    assert out["valido_para_oferta"] is True
    assert out["motivo_invalido"] is None


def test_karla_quinta_asa_norte_INVALIDO_bug_c35():
    """Bug C-35: 18/06/2026 é quinta — Karla atende Águas Claras, NÃO Asa Norte."""
    out = validar_data_unidade("2026-06-18", "karla", "Asa Norte")
    assert out["dia"] == "Quinta-feira"
    assert out["unidade_atende"] == "Águas Claras"
    assert out["valido_para_oferta"] is False
    assert "Águas Claras" in out["motivo_invalido"]
    assert "NÃO Asa Norte" in out["motivo_invalido"]


def test_karla_quinta_aguas_claras_VALIDO():
    out = validar_data_unidade("2026-06-18", "karla", "Águas Claras")
    assert out["valido_para_oferta"] is True


def test_karla_sabado_NAO_ATENDE():
    out = validar_data_unidade("2026-06-20", "karla")
    assert out["dia"] == "Sábado"
    assert out["unidade_atende"] is None
    assert out["valido_para_oferta"] is False
    assert "NÃO atende" in out["motivo_invalido"]


def test_karla_domingo_NAO_ATENDE():
    out = validar_data_unidade("2026-06-21", "karla")
    assert out["valido_para_oferta"] is False


def test_fabricio_terca_aguas_claras():
    out = validar_data_unidade("2026-06-23", "fabricio", "Águas Claras")
    assert out["valido_para_oferta"] is True


def test_fabricio_segunda_NAO_ATENDE():
    out = validar_data_unidade("2026-06-22", "fabricio")
    assert out["valido_para_oferta"] is False


def test_unidade_sem_acento_aceita():
    """Aceita 'Aguas Claras' sem cedilha — normalização robusta."""
    out = validar_data_unidade("2026-06-18", "karla", "Aguas Claras")
    assert out["valido_para_oferta"] is True


def test_validar_data_unidade_texto_pronto():
    out = validar_data_unidade("2026-06-22", "karla")
    assert "Segunda-feira" in out["texto_pronto"]
    assert "22/06" in out["texto_pronto"]
    assert "Asa Norte" in out["texto_pronto"]


# ─── proximas_datas_disponiveis ─────────────────────────────────────

def test_proximas_4_karla_asa_norte():
    out = proximas_datas_disponiveis("karla", "Asa Norte", 4, a_partir_de="2026-06-22")
    assert len(out) == 4
    # Segunda 22/06, Quarta 24/06, Sexta 26/06, Segunda 29/06
    assert out[0]["data_iso"] == "2026-06-22"
    assert out[0]["dia"] == "Segunda-feira"
    assert out[1]["data_iso"] == "2026-06-24"
    assert out[1]["dia"] == "Quarta-feira"
    assert out[2]["data_iso"] == "2026-06-26"
    assert out[3]["data_iso"] == "2026-06-29"


def test_proximas_aguas_claras_alterna_terca_quinta():
    out = proximas_datas_disponiveis("karla", "Águas Claras", 4, a_partir_de="2026-06-22")
    assert all(d["unidade"] == "Águas Claras" for d in out)
    assert out[0]["dia"] in ("Terça-feira", "Quinta-feira")


def test_proximas_fabricio_so_aguas_claras():
    out = proximas_datas_disponiveis("fabricio", "Águas Claras", 5, a_partir_de="2026-06-22")
    assert len(out) == 5
    assert all(d["dia"] in ("Terça-feira", "Quinta-feira") for d in out)


def test_proximas_n_minimo_1():
    out = proximas_datas_disponiveis("karla", "Asa Norte", 1, a_partir_de="2026-06-22")
    assert len(out) == 1


# ─── gerar_oferta_pronta ────────────────────────────────────────────

def test_oferta_pronta_formato_canonico():
    out = gerar_oferta_pronta(
        "karla", "Asa Norte", "09:00", "14:30", "Maria",
    )
    msg = out["mensagem"]
    assert "Maria!" in msg
    assert "1️⃣" in msg
    assert "2️⃣" in msg
    assert "Dra. Karla Delalíbera" in msg
    assert "Qual prefere?" in msg


def test_oferta_pronta_sem_nome():
    out = gerar_oferta_pronta("karla", "Asa Norte", "10:00", "11:30")
    msg = out["mensagem"]
    # Sem nome, abre direto com "Tenho estes horários..."
    assert msg.startswith("Tenho estes horários")


def test_oferta_pronta_horas_corretas():
    out = gerar_oferta_pronta(
        "karla", "Asa Norte", "08:30", "16:00", "João",
    )
    assert "08:30" in out["mensagem"]
    assert "16:00" in out["mensagem"]


# ─── Validação Pydantic (anti-alucinação) ───────────────────────────

def test_pydantic_data_invalida_rejeita():
    with pytest.raises(ValidationError):
        ValidarDataInput(data="18-06-2026", medico="karla")  # formato errado


def test_pydantic_n_alem_do_limite_rejeita():
    with pytest.raises(ValidationError):
        ProximasDatasInput(medico="karla", unidade="Asa Norte", n=50)


def test_pydantic_medico_normaliza_caixa():
    inp = ValidarDataInput(data="2026-06-22", medico="KARLA")
    assert inp.medico == "karla"


# ─── Resources ──────────────────────────────────────────────────────

def test_listar_medicos_inclui_karla_e_fabricio():
    txt = listar_medicos()
    assert "Karla" in txt
    assert "Fabrício" in txt


def test_agenda_karla_contem_dias_atendimento():
    txt = agenda_karla()
    assert "Segunda-feira: Asa Norte" in txt
    assert "Terça-feira: Águas Claras" in txt
    assert "Sábado: NÃO ATENDE" in txt


def test_agenda_fabricio_so_ter_qui():
    txt = agenda_fabricio()
    assert "Terça-feira: Águas Claras" in txt
    assert "Quinta-feira: Águas Claras" in txt
    assert "Segunda-feira: NÃO ATENDE" in txt
    assert "Quarta-feira: NÃO ATENDE" in txt
