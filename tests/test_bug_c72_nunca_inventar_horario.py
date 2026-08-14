"""Bug C-72 — Filtro nunca inventar horário (Fábio 14/08/2026).

Caso real Lucas Machado Casotti (lead 20325187, Asa Norte, bebê 0-2):
Lia ofertou "Segunda 17/08 10:00" + "Quarta 19/08 14:00" — os dias da semana
batem (Karla ATENDE Asa Norte seg/qua), mas os horários 10:00 e 14:00 foram
INVENTADOS sem consultar Medware. Filtro C-72 detecta isso e escala humano.
"""
from __future__ import annotations

import pytest

from voice_agent.nunca_inventar_horario import (
    _texto_e_oferta,
    extrair_horarios,
    horarios_medware_ctx,
    montar_nota_handoff_c72,
    validar_horarios_contra_medware,
)


# ═════════════════════════════════════════════════════════════════════════
# extrair_horarios
# ═════════════════════════════════════════════════════════════════════════

class TestExtrairHorarios:
    def test_hh_colon_mm(self):
        assert extrair_horarios("às 10:00") == {"10:00"}

    def test_multiplos_horarios(self):
        t = "1️⃣ 17/08 às 10:00\n2️⃣ 19/08 às 14:00"
        assert extrair_horarios(t) == {"10:00", "14:00"}

    def test_formato_h_brasileiro(self):
        assert extrair_horarios("às 10h") == {"10:00"}
        assert extrair_horarios("às 14h30") == {"14:30"}

    def test_hh_com_zero_prefixo(self):
        assert extrair_horarios("08:30") == {"08:30"}

    def test_sem_horario(self):
        assert extrair_horarios("Bom dia, tudo bem?") == set()

    def test_hora_invalida_25(self):
        # 25:00 não é hora válida — não deve capturar
        assert extrair_horarios("às 25:00") == set()

    def test_caso_real_lucas(self):
        texto = (
            "Tenho esses horários disponíveis com a Dra. Karla Delalibera, Asa Norte:\n\n"
            "1️⃣ Segunda-feira (17/08/2026) às 10:00\n"
            "2️⃣ Quarta-feira (19/08/2026) às 14:00\n\n"
            "Qual fica melhor pra você?"
        )
        assert extrair_horarios(texto) == {"10:00", "14:00"}


# ═════════════════════════════════════════════════════════════════════════
# horarios_medware_ctx
# ═════════════════════════════════════════════════════════════════════════

class TestHorariosMedwareCtx:
    def test_formato_dict(self):
        ctx = {
            "agenda": [
                {"data": "17/08/2026", "hora": "09:00"},
                {"data": "17/08/2026", "hora": "09:30"},
            ]
        }
        assert horarios_medware_ctx(ctx) == {"09:00", "09:30"}

    def test_formato_string(self):
        ctx = {"agenda": ["17/08/2026 09:00", "17/08/2026 09:30"]}
        assert horarios_medware_ctx(ctx) == {"09:00", "09:30"}

    def test_agenda_vazia(self):
        assert horarios_medware_ctx({"agenda": []}) == set()

    def test_ctx_none(self):
        assert horarios_medware_ctx(None) == set()

    def test_sem_key_agenda(self):
        assert horarios_medware_ctx({"outra_coisa": 1}) == set()


# ═════════════════════════════════════════════════════════════════════════
# _texto_e_oferta
# ═════════════════════════════════════════════════════════════════════════

class TestTextoEOferta:
    def test_texto_com_emoji_1(self):
        assert _texto_e_oferta("1️⃣ Segunda") is True

    def test_texto_com_tenho_horarios(self):
        assert _texto_e_oferta("Tenho estes horários disponíveis") is True

    def test_texto_com_dia_data(self):
        assert _texto_e_oferta("Segunda-feira (17/08)") is True

    def test_confirmacao_nao_e_oferta(self):
        assert _texto_e_oferta("Perfeito, agendei pra você!") is False

    def test_pergunta_livre_nao_e_oferta(self):
        assert _texto_e_oferta("Qual o motivo da consulta?") is False


# ═════════════════════════════════════════════════════════════════════════
# validar_horarios_contra_medware — filtro principal
# ═════════════════════════════════════════════════════════════════════════

class TestValidarHorariosContraMedware:
    def test_horarios_todos_batem(self):
        text = "1️⃣ (17/08) às 09:00\n2️⃣ (17/08) às 09:30"
        ctx = {
            "agenda": [
                {"data": "17/08/2026", "hora": "09:00"},
                {"data": "17/08/2026", "hora": "09:30"},
            ]
        }
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is False
        assert txt == text  # texto original

    def test_horario_inventado_bloqueia(self):
        text = "1️⃣ (17/08) às 10:00\n2️⃣ (19/08) às 14:00"
        ctx = {
            "agenda": [
                {"data": "17/08/2026", "hora": "09:00"},
                {"data": "17/08/2026", "hora": "09:30"},
            ]
        }
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is True
        assert "reconferir" in txt.lower()
        assert "10:00" not in txt
        assert "14:00" not in txt

    def test_agenda_vazia_com_horario_ofertado_bloqueia(self):
        text = "1️⃣ (17/08) às 10:00\n2️⃣ (19/08) às 14:00"
        ctx = {"agenda": [], "lead_id": "20325187"}
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is True

    def test_texto_sem_horario_passa(self):
        text = "Perfeito, Olívia! Qual o motivo da consulta?"
        ctx = {"agenda": []}
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is False
        assert txt == text

    def test_texto_nao_e_oferta_passa(self):
        # Confirmação com hora ainda passa (não é oferta)
        text = "Confirmado às 10:00, te espero!"
        ctx = {"agenda": []}
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        # "Confirmado" sem padrão de oferta — passa
        assert bloqueado is False

    def test_toggle_off_passa(self, monkeypatch):
        monkeypatch.setenv("NUNCA_INVENTAR_HORARIO_ATIVADO", "0")
        text = "1️⃣ (17/08) às 10:00\n2️⃣ (19/08) às 14:00"
        ctx = {"agenda": [{"data": "17/08/2026", "hora": "09:00"}]}
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is False
        assert txt == text

    def test_caso_real_lucas_lead_20325187(self):
        # Reproduz caso real Fábio 14/08/2026:
        # Lia ofertou 10:00 e 14:00, Medware não retornou agenda (vazio).
        text = (
            "Tenho esses horários disponíveis com a Dra. Karla Delalibera, Asa Norte:\n\n"
            "1️⃣ Segunda-feira (17/08/2026) às 10:00\n"
            "2️⃣ Quarta-feira (19/08/2026) às 14:00\n\n"
            "Qual fica melhor pra você?"
        )
        ctx = {"agenda": [], "lead_id": "20325187"}
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is True
        assert "10:00" not in txt
        assert "14:00" not in txt
        assert "reconferir" in txt.lower() or "equipe" in txt.lower()

    def test_um_horario_bate_outro_nao(self):
        # Só bloqueia se PELO MENOS UM horário é inventado
        text = "1️⃣ (17/08) às 09:00\n2️⃣ (19/08) às 14:00"
        ctx = {
            "agenda": [
                {"data": "17/08/2026", "hora": "09:00"},
                # 14:00 não está!
            ]
        }
        txt, bloqueado = validar_horarios_contra_medware(text, ctx)
        assert bloqueado is True


# ═════════════════════════════════════════════════════════════════════════
# montar_nota_handoff_c72
# ═════════════════════════════════════════════════════════════════════════

class TestNotaHandoff:
    def test_menciona_c72(self):
        n = montar_nota_handoff_c72(
            "1️⃣ 10:00\n2️⃣ 14:00",
            {"10:00", "14:00"},
            set(),
        )
        assert "C-72" in n
        assert "HORÁRIO INVENTADO" in n
        assert "10:00" in n
