"""Bug C-30 (lead Sofia 24158652, 16/06/2026) — zero hesitação com agenda real.

Quando o ctx tem slots reais do Medware e a Lia escreve qualquer variação de
stall ("deixa eu consultar/reconsultar a agenda", "Medware não está
retornando", "volto em 1 minuto", "vou puxar a agenda exata"), o filtro
SEMPRE-ON substitui pela oferta real de 2 slots. Antes, esse filtro estava
atrás de FILTROS_LEGACY (OFF em prod) e a Lia hesitou até escalar pra humano.
"""
import pytest

from voice_agent.responder import (
    _scrub_prohibited,
    _viola_oferta_agenda,
    _gerar_oferta_2_slots,
)

# ctx como o pipeline monta: agenda real + médico/unidade conhecidos
CTX = {
    "agenda": [
        {"dia_semana": "quarta-feira", "data_br": "08/07", "hora": "09:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
        {"dia_semana": "sexta-feira", "data_br": "10/07", "hora": "14:00",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
        {"dia_semana": "segunda-feira", "data_br": "13/07", "hora": "08:30",
         "cod_agenda": 4, "cod_medico": 12080, "cod_unidade": 5},
    ],
    "medico": "Dra. Karla Delalibera",
    "known": {"medico": "Dra. Karla Delalibera", "unidade": "Asa Norte"},
}

# Frases reais da conversa da Sofia (notas Kommo) + variações
FRASES_STALL = [
    "Deixa eu consultar a agenda exata para esse período e volto com os horários reais pra você em um instante.",
    "Cindy, a agenda do Medware não está retornando os horários neste momento — pode ser uma lentidão temporária do sistema.",
    "Deixa eu reconsultar aqui e volto com as opções concretas em 1 minuto.",
    "Sofia, deixa eu reconsultar a agenda real aqui pra você — volto em 1 minuto com os horários certos.",
    "Vou puxar a agenda exata aqui e já te respondo.",
    "Deixa eu reconferir a agenda e volto já com as opções.",
]


class TestSubstituiHesitacao:
    @pytest.mark.parametrize("frase", FRASES_STALL)
    def test_hesitacao_com_agenda_vira_oferta_real(self, frase):
        out = _scrub_prohibited(frase, CTX)
        # Substituiu pela oferta real (2 slots no formato 1️⃣/2️⃣)
        assert "2 horários" in out or "2 horarios" in out
        assert "1️⃣" in out and "2️⃣" in out
        # Contém pelo menos um horário real da agenda
        assert "09:00" in out or "14:00" in out
        # Não contém mais a hesitação
        assert "não está retornando" not in out
        assert "reconsultar" not in out.lower()
        assert "volto em 1 minuto" not in out.lower()

    @pytest.mark.parametrize("frase", FRASES_STALL)
    def test_deteccao_padrao(self, frase):
        assert _viola_oferta_agenda(frase, has_agenda=True) is True


class TestNaoFalsosPositivos:
    def test_oferta_real_passa_sem_substituir(self):
        oferta = (
            "Tenho 2 horários abertos com a Dra. Karla, Asa Norte:\n\n"
            "1️⃣ Quarta-feira (08/07) às 09:00\n"
            "2️⃣ Sexta-feira (10/07) às 14:00\n\n"
            "Algum desses cabe pra você?"
        )
        out = _scrub_prohibited(oferta, CTX)
        assert out == oferta  # inalterado

    def test_sem_agenda_nao_substitui_por_oferta(self):
        # Sem agenda no ctx, a hesitação não vira oferta de 2 slots (não há
        # slots pra oferecer). O filtro C-30 não dispara.
        ctx_sem = {"known": {"medico": "Dra. Karla Delalibera"}}
        frase = "Deixa eu consultar a agenda e volto."
        out = _scrub_prohibited(frase, ctx_sem)
        assert "1️⃣" not in out  # não inventou oferta sem agenda


class TestGeradorOferta:
    def test_gera_dois_slots_manha_e_tarde(self):
        msg = _gerar_oferta_2_slots(CTX)
        assert "1️⃣" in msg and "2️⃣" in msg
        assert "Dra. Karla" in msg
        assert "Asa Norte" in msg
