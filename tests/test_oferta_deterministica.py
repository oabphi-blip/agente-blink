"""Pytest do bypass determinístico da mensagem de oferta de agenda.

Cenários reais de leads que travaram nos últimos 60 dias. Cada teste
verifica que o texto de saída (Python puro, sem LLM):
    1) contém as datas literais dos slots
    2) NÃO contém frases banidas historicamente inventadas pela Lia
    3) apresenta médico com nome+sobrenome canônico
    4) tem dia da semana correto (calculado, não inventado)

Se algum desses testes quebrar, deploy NÃO sai.
"""

from __future__ import annotations

import pytest

from voice_agent.oferta_deterministica import (
    FRASES_BANIDAS,
    deve_ofertar_agora,
    frase_escalacao_humano,
    montar_texto_2_slots,
    selecionar_2_slots,
)


# ===========================================================================
# Fixtures — contextos reais reproduzidos dos leads
# ===========================================================================

def _ctx_mariana_24273236() -> dict:
    """Lead 24273236 — mãe Mariana, João Miguel 4a, TJDFT Pró-Saúde,
    Karla, Águas Claras, preferência 'depois das 17h30 ou manhã ter/qui'.
    """
    return {
        "fsm": {"estado": "AGENDA"},
        "ja_agendado": False,
        "known": {
            "nome_paciente": "João Miguel Costa",
            "data_nascimento": "2021-12-15",  # 4a em 07/2026
            "convenio": "TJDFT Pró-Saúde",
            "medico": "Dra. Karla Delalibera",
            "unidade": "Águas Claras",
        },
    }


def _ctx_sofia_24158652() -> dict:
    """Lead 24158652 — Sofia 7a, Bacen, Karla Asa Norte, rotina."""
    return {
        "fsm": {"estado": "AGENDA"},
        "ja_agendado": False,
        "known": {
            "nome_paciente": "Sofia Almeida",
            "data_nascimento": "2019-03-10",
            "convenio": "Bacen",
            "medico": "Karla",
            "unidade": "Asa Norte",
        },
    }


def _ctx_juliene_24053159() -> dict:
    """Lead 24053159 — Juliene, adulta, particular, Karla Asa Norte."""
    return {
        "fsm": {"estado": "AGENDA"},
        "ja_agendado": False,
        "known": {
            "nome_paciente": "Juliene Silva",
            "data_nascimento": "1990-05-20",
            "cpf_paciente": "12345678909",  # dígito válido não importa aqui
            "convenio": "Particular",
            "medico": "Karla",
            "unidade": "Asa Norte",
        },
    }


def _ctx_maite_24128026() -> dict:
    """Lead 24128026 — Maitê 8 meses, Karla Águas Claras, pediátrico."""
    return {
        "fsm": {"estado": "AGENDA"},
        "ja_agendado": False,
        "known": {
            "nome_paciente": "Maitê Costa",
            "data_nascimento": "2025-11-01",
            "convenio": "Saúde Caixa",
            "medico": "Karla",
            "unidade": "Águas Claras",
        },
    }


def _ctx_pedro_catarata() -> dict:
    """Adulto 60a, catarata, Fabrício Asa Norte."""
    return {
        "fsm": {"estado": "AGENDA"},
        "ja_agendado": False,
        "known": {
            "nome_paciente": "Pedro Ferreira",
            "data_nascimento": "1965-04-12",
            "cpf_paciente": "11122233344",
            "convenio": "Particular",
            "medico": "Fabrício",
            "unidade": "Asa Norte",
        },
    }


# Slots que o Medware DE FATO retornou pra Mariana (chamada mcp__medware__
# em 08/07/2026 22:15 BRT). Não é fictício — é o payload real.
def _slots_mariana_reais() -> list[dict]:
    return [
        {
            "data_iso": "2026-07-14",
            "data_br": "14/07",
            "dia_semana": "Terça-feira",
            "hora": "17:30",
            "cod_agenda": 5, "cod_unidade": 3, "cod_medico": 12080,
        },
        {
            "data_iso": "2026-07-16",
            "data_br": "16/07",
            "dia_semana": "Quinta-feira",
            "hora": "11:30",
            "cod_agenda": 5, "cod_unidade": 3, "cod_medico": 12080,
        },
        {
            "data_iso": "2026-07-16",
            "data_br": "16/07",
            "dia_semana": "Quinta-feira",
            "hora": "17:00",
            "cod_agenda": 5, "cod_unidade": 3, "cod_medico": 12080,
        },
        {
            "data_iso": "2026-07-16",
            "data_br": "16/07",
            "dia_semana": "Quinta-feira",
            "hora": "17:30",
            "cod_agenda": 5, "cod_unidade": 3, "cod_medico": 12080,
        },
    ]


# ===========================================================================
# 1. Contrato de saída — texto canônico, sempre
# ===========================================================================

class TestMarianaLead24273236:
    """Cenário exato que motivou o fix (Fábio 08/07/2026)."""

    def test_texto_contem_data_terca_14_07(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "14/07" in texto
        assert "17h30" in texto
        # Dia da semana correto (14/07/2026 é uma TERÇA — bug C-35 blindado)
        assert "Terça-feira" in texto

    def test_texto_contem_data_alternativa(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        # Um segundo slot deve aparecer (dia diferente pela regra de seleção)
        assert "16/07" in texto
        assert "Quinta-feira" in texto

    def test_medico_com_nome_e_sobrenome(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "Dra. Karla Delalíbera" in texto

    def test_unidade_canonica(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "Águas Claras" in texto

    def test_convenio_mencionado(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "TJDFT" in texto

    def test_saudacao_com_nome_paciente(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert texto.startswith("João")  # primeiro nome

    def test_nao_contem_frase_reconferir(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "reconferir" not in texto.lower()
        assert "calendário" not in texto.lower()

    def test_nao_contem_especialista_em_remarcacao(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "especialista em remarcação" not in texto.lower()
        assert "especialista em remarcacao" not in texto.lower()

    def test_nao_contem_fora_do_ar(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx)
        assert "fora do ar" not in texto.lower()
        assert "não está retornando" not in texto.lower()

    def test_todas_frases_banidas_ausentes(self):
        ctx = _ctx_mariana_24273236()
        slots = _slots_mariana_reais()
        texto = montar_texto_2_slots(slots, ctx).lower()
        for frase in FRASES_BANIDAS:
            assert frase not in texto, f"Frase banida vazou: {frase!r}"


# ===========================================================================
# 2. Cenários pra outros leads que já travaram
# ===========================================================================

class TestSofia24158652:
    """Bug C-30/C-30A original — Karla Asa Norte."""

    def test_dr_karla_delalibera_em_asa_norte(self):
        ctx = _ctx_sofia_24158652()
        slots = [
            {"data_iso": "2026-07-13", "hora": "09:00"},
            {"data_iso": "2026-07-15", "hora": "10:30"},
        ]
        texto = montar_texto_2_slots(slots, ctx)
        assert "Dra. Karla Delalíbera" in texto
        assert "Asa Norte" in texto
        # 13/07/2026 é SEGUNDA (blinda bug C-35)
        assert "Segunda-feira" in texto
        # 15/07/2026 é QUARTA
        assert "Quarta-feira" in texto


class TestJuliene24053159:
    """Bug filtro anti-'horário comercial' — Juliene 02/06/2026."""

    def test_zero_horario_comercial(self):
        ctx = _ctx_juliene_24053159()
        slots = [
            {"data_iso": "2026-07-13", "hora": "14:00"},
            {"data_iso": "2026-07-15", "hora": "15:30"},
        ]
        texto = montar_texto_2_slots(slots, ctx).lower()
        assert "horário comercial" not in texto
        assert "horario comercial" not in texto
        assert "seg-sex" not in texto


class TestMaite24128026:
    """Bug C-17 — dia mais próximo PRIMEIRO."""

    def test_slot_mais_proximo_e_o_primeiro(self):
        ctx = _ctx_maite_24128026()
        # Medware retorna 3 slots em ordem cronológica
        slots = [
            {"data_iso": "2026-07-14", "hora": "09:00"},
            {"data_iso": "2026-07-21", "hora": "10:00"},
            {"data_iso": "2026-07-28", "hora": "11:00"},
        ]
        texto = montar_texto_2_slots(slots, ctx)
        # slot 1️⃣ deve ser 14/07, não 21 ou 28
        idx_14 = texto.find("14/07")
        idx_21 = texto.find("21/07")
        assert idx_14 > 0
        assert idx_14 < idx_21


class TestFabricioCatarata:
    """Fabrício aparece como 'Dr. Fabrício Freitas' — nome+sobrenome."""

    def test_dr_fabricio_freitas(self):
        ctx = _ctx_pedro_catarata()
        slots = [
            {"data_iso": "2026-07-14", "hora": "08:30"},
            {"data_iso": "2026-07-16", "hora": "14:00"},
        ]
        texto = montar_texto_2_slots(slots, ctx)
        assert "Dr. Fabrício Freitas" in texto
        # Nunca "exclusivamente catarata" (bug C-24b)
        assert "exclusivamente catarata" not in texto.lower()


# ===========================================================================
# 3. Gate deve_ofertar_agora — só True quando é seguro
# ===========================================================================

class TestGateDeveOfertar:
    def test_true_no_cenario_mariana(self):
        assert deve_ofertar_agora(_ctx_mariana_24273236()) is True

    def test_false_se_fsm_nao_agenda(self):
        ctx = _ctx_mariana_24273236()
        ctx["fsm"]["estado"] = "TRIAGEM"
        assert deve_ofertar_agora(ctx) is False

    def test_false_se_ja_agendado(self):
        ctx = _ctx_mariana_24273236()
        ctx["ja_agendado"] = True
        assert deve_ofertar_agora(ctx) is False

    def test_false_se_sem_medico(self):
        ctx = _ctx_mariana_24273236()
        ctx["known"].pop("medico")
        assert deve_ofertar_agora(ctx) is False

    def test_false_se_sem_unidade(self):
        ctx = _ctx_mariana_24273236()
        ctx["known"].pop("unidade")
        assert deve_ofertar_agora(ctx) is False

    def test_false_se_dados_minimos_incompletos(self):
        ctx = _ctx_mariana_24273236()
        ctx["known"].pop("data_nascimento")
        assert deve_ofertar_agora(ctx) is False

    def test_false_se_toggle_off(self, monkeypatch):
        monkeypatch.setenv("AGENDA_DETERMINISTICA", "0")
        assert deve_ofertar_agora(_ctx_mariana_24273236()) is False

    def test_true_com_toggle_1_explicito(self, monkeypatch):
        monkeypatch.setenv("AGENDA_DETERMINISTICA", "1")
        assert deve_ofertar_agora(_ctx_mariana_24273236()) is True

    def test_true_com_toggle_vazio_default_on(self, monkeypatch):
        monkeypatch.delenv("AGENDA_DETERMINISTICA", raising=False)
        assert deve_ofertar_agora(_ctx_mariana_24273236()) is True


# ===========================================================================
# 4. Seleção de 2 slots — regra manhã/tarde e dia diferente
# ===========================================================================

class TestSelecionar2Slots:
    def test_retorna_2_slots_de_dias_diferentes(self):
        slots = [
            {"data_iso": "2026-07-14", "hora": "17:30"},
            {"data_iso": "2026-07-14", "hora": "18:00"},
            {"data_iso": "2026-07-16", "hora": "11:30"},
        ]
        out = selecionar_2_slots(slots)
        assert len(out) == 2
        assert out[0]["data_iso"] == "2026-07-14"
        assert out[1]["data_iso"] == "2026-07-16"

    def test_prefere_turno_diferente_quando_possivel(self):
        # slot 1 é tarde (17:30), deve preferir slot de manhã em outro dia
        slots = [
            {"data_iso": "2026-07-14", "hora": "17:30"},
            {"data_iso": "2026-07-15", "hora": "16:00"},  # tarde
            {"data_iso": "2026-07-16", "hora": "10:30"},  # manhã
        ]
        out = selecionar_2_slots(slots)
        assert out[1]["hora"] == "10:30"

    def test_um_slot_so_retorna_um(self):
        slots = [{"data_iso": "2026-07-14", "hora": "17:30"}]
        out = selecionar_2_slots(slots)
        assert len(out) == 1

    def test_slots_vazios(self):
        assert selecionar_2_slots([]) == []


# ===========================================================================
# 5. Escalação humano — Medware vazio
# ===========================================================================

class TestEscalacaoHumano:
    def test_frase_escalacao_zero_banidas(self):
        ctx = _ctx_mariana_24273236()
        texto = frase_escalacao_humano(ctx).lower()
        for frase in FRASES_BANIDAS:
            assert frase not in texto, f"escalação viola: {frase!r}"

    def test_frase_escalacao_menciona_paciente(self):
        ctx = _ctx_mariana_24273236()
        texto = frase_escalacao_humano(ctx)
        assert "João" in texto  # primeiro nome do paciente

    def test_frase_escalacao_curta(self):
        # Uma única frase (não 4 variantes como bug Mariana).
        ctx = _ctx_mariana_24273236()
        texto = frase_escalacao_humano(ctx)
        assert len(texto) < 400  # concisa

    def test_frase_escalacao_sem_horario_comercial(self):
        ctx = _ctx_juliene_24053159()
        texto = frase_escalacao_humano(ctx).lower()
        assert "horário comercial" not in texto
        assert "horario comercial" not in texto


# ===========================================================================
# 6. Adversarial — nenhuma frase banida sob nenhuma combinação
# ===========================================================================

class TestAdversarialZeroFrasesBanidas:
    """Roda montar_texto e frase_escalacao em 30 combinações de médico/
    unidade/convênio/dia e valida que NENHUMA frase banida aparece."""

    @pytest.mark.parametrize("medico", ["Karla", "Fabrício", "Dra. Karla Delalibera"])
    @pytest.mark.parametrize("unidade", ["Asa Norte", "Águas Claras", "aguas claras"])
    @pytest.mark.parametrize("data_iso,hora", [
        ("2026-07-13", "08:00"),
        ("2026-07-14", "17:30"),
        ("2026-07-16", "11:30"),
    ])
    def test_texto_oferta_nunca_viola(self, medico, unidade, data_iso, hora):
        ctx = {
            "fsm": {"estado": "AGENDA"},
            "known": {
                "nome_paciente": "Teste Silva",
                "data_nascimento": "2000-01-01",
                "cpf_paciente": "11122233344",
                "convenio": "Particular",
                "medico": medico,
                "unidade": unidade,
            },
        }
        slots = [
            {"data_iso": data_iso, "hora": hora},
            {"data_iso": "2026-07-20", "hora": "10:00"},
        ]
        texto = montar_texto_2_slots(slots, ctx).lower()
        for frase in FRASES_BANIDAS:
            assert frase not in texto


# ===========================================================================
# 7. Dias da semana calculados por weekday() — nunca inventa (bug C-35)
# ===========================================================================

class TestDiaSemanaCorreto:
    @pytest.mark.parametrize("data_iso,esperado", [
        ("2026-07-13", "Segunda-feira"),
        ("2026-07-14", "Terça-feira"),
        ("2026-07-15", "Quarta-feira"),
        ("2026-07-16", "Quinta-feira"),
        ("2026-07-17", "Sexta-feira"),
        ("2026-07-18", "Sábado"),
        ("2026-07-19", "Domingo"),
    ])
    def test_dia_semana_correto(self, data_iso, esperado):
        ctx = _ctx_mariana_24273236()
        slots = [{"data_iso": data_iso, "hora": "10:00"}]
        texto = montar_texto_2_slots(slots, ctx)
        assert esperado in texto
