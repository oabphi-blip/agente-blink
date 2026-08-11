"""Pytest — Fallback de agenda via Kommo quando Medware cai (02/07/2026).

Origem: lead 21225483 Carolina (02/07/2026 ~10:46-11:06 BRT). Medware ao vivo
intermitente → ctx.agenda=[]. Lia entrou em loop "deixa eu reconsultar a agenda
real aqui pra você — volto em 1 minuto" 4x, MESMO com os campos "1./2. DIA COM
CONVÊNIO" do Kommo já preenchidos (14/07 14:00 terça + 23/07 14:30 quinta,
Águas Claras, batendo a preferência dela).

FONTE B: quando o Medware não responde, a Lia lê esses campos do Kommo
(known['dia_conv_1_ts'] / ['dia_conv_2_ts']) e oferta agenda real. O
dia-da-semana é DERIVADO do epoch (nunca digitado) → imune ao Bug C-35.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from voice_agent.responder import (
    _TZ_BRT,
    _fallback_slots_from_kommo,
    _gerar_resposta_honesta_medware_down,
    _scrub_prohibited,
)

# Epochs reais gravados no lead Carolina 21225483
TS_CAROLINA_1 = 1784048400  # 14/07/2026 14:00 BRT (terça)
TS_CAROLINA_2 = 1784827800  # 23/07/2026 14:30 BRT (quinta)


def _futuro_ts(dias: int, hora: int = 14, minuto: int = 0) -> int:
    d = datetime.now(_TZ_BRT) + timedelta(days=dias)
    d = d.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    return int(d.timestamp())


# ============================================================
# _fallback_slots_from_kommo — extração dos campos
# ============================================================

class TestFallbackSlots:
    def test_dois_campos_futuros_geram_dois_slots(self):
        ctx = {"known": {
            "dia_conv_1_ts": _futuro_ts(10),
            "dia_conv_2_ts": _futuro_ts(17),
        }}
        slots = _fallback_slots_from_kommo(ctx)
        assert len(slots) == 2
        assert all(s["_origem"] == "kommo_fallback" for s in slots)
        assert all("data_br" in s and "hora" in s and "dia_semana" in s
                   for s in slots)

    def test_carolina_epochs_reais_dia_semana_correto(self):
        # Guard contra Bug C-35 — weekday derivado do epoch, não inventado
        ctx = {"known": {
            "dia_conv_1_ts": TS_CAROLINA_1,
            "dia_conv_2_ts": TS_CAROLINA_2,
        }}
        slots = _fallback_slots_from_kommo(ctx)
        assert len(slots) == 2
        assert slots[0]["data_br"] == "14/07"
        assert slots[0]["hora"] == "14:00"
        assert slots[0]["dia_semana"] == "terça-feira"
        assert slots[1]["data_br"] == "23/07"
        assert slots[1]["hora"] == "14:30"
        assert slots[1]["dia_semana"] == "quinta-feira"

    def test_epoch_passado_descartado(self):
        ctx = {"known": {
            "dia_conv_1_ts": 1000000000,   # 2001 — passado
            "dia_conv_2_ts": _futuro_ts(12),
        }}
        slots = _fallback_slots_from_kommo(ctx)
        assert len(slots) == 1  # só o futuro sobrevive

    def test_ordena_cronologicamente(self):
        ctx = {"known": {
            "dia_conv_1_ts": _futuro_ts(20),
            "dia_conv_2_ts": _futuro_ts(5),
        }}
        slots = _fallback_slots_from_kommo(ctx)
        assert slots[0]["_epoch"] < slots[1]["_epoch"]

    def test_sem_campos_retorna_vazio(self):
        assert _fallback_slots_from_kommo({"known": {}}) == []
        assert _fallback_slots_from_kommo({}) == []
        assert _fallback_slots_from_kommo(None) == []

    def test_valor_invalido_nao_quebra(self):
        ctx = {"known": {"dia_conv_1_ts": "lixo", "dia_conv_2_ts": None}}
        assert _fallback_slots_from_kommo(ctx) == []


# ============================================================
# _gerar_resposta_honesta_medware_down — usa fallback antes de hesitar
# ============================================================

class TestHonestaUsaFallback:
    def test_com_campos_kommo_gera_oferta_nao_frase_espera(self):
        ctx = {"known": {
            "nome_contato": "Carolina",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Águas Claras",
            "dia_conv_1_ts": TS_CAROLINA_1,
            "dia_conv_2_ts": TS_CAROLINA_2,
        }, "agenda": []}
        out = _gerar_resposta_honesta_medware_down(ctx)
        # É uma OFERTA real, com as duas datas — não a frase de espera
        assert "14/07" in out
        assert "23/07" in out
        assert "fora do ar" not in out
        assert "volto em 1 minuto" not in out

    def test_agenda_do_medware_tem_prioridade_sobre_kommo(self):
        ctx = {"known": {
            "medico": "Karla", "unidade": "Asa Norte",
            "dia_conv_1_ts": TS_CAROLINA_1,
        }, "agenda": [
            {"dia_semana": "quarta-feira", "data_br": "08/07", "hora": "09:00"},
        ]}
        out = _gerar_resposta_honesta_medware_down(ctx)
        assert "08/07" in out          # slot do Medware
        assert "14/07" not in out      # não caiu no fallback Kommo

    def test_sem_nenhuma_fonte_frase_honesta_sem_loop(self):
        ctx = {"known": {"nome_contato": "Sofia"}, "agenda": []}
        out = _gerar_resposta_honesta_medware_down(ctx)
        # Admite honestamente, NÃO promete "volto em 1 minuto" (padrão de loop)
        assert "fora do ar" in out
        assert "volto em 1 minuto" not in out
        assert out.startswith("Sofia,")


# ============================================================
# End-to-end: o loop da Carolina vira oferta real
# ============================================================

class TestCarolinaEndToEnd:
    def _ctx_carolina(self):
        return {
            "known": {
                "nome_contato": "Carolina",
                "medico": "Dra. Karla Delalíbera",
                "unidade": "Águas Claras",
                "motivo": "rotina",
                "dia_conv_1_ts": TS_CAROLINA_1,
                "dia_conv_2_ts": TS_CAROLINA_2,
            },
            "agenda": [],          # Medware fora
            "fsm": "AGENDA",
            "lead_id": 21225483,
        }

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_stall_vira_oferta_real(self):
        texto_loop = (
            "Carolina, deixa eu reconsultar a agenda real aqui pra você — "
            "volto em 1 minuto com os horários certos."
        )
        out = _scrub_prohibited(texto_loop, self._ctx_carolina())
        assert out != texto_loop
        assert "14/07" in out and "23/07" in out
        assert "volto em 1 minuto" not in out

    @patch.dict(os.environ, {"LIA_ANTI_HESITACAO_AGENDA": "1"})
    def test_sem_campos_kommo_cai_na_frase_honesta(self):
        ctx = self._ctx_carolina()
        ctx["known"].pop("dia_conv_1_ts")
        ctx["known"].pop("dia_conv_2_ts")
        texto_loop = "Carolina, deixa eu reconsultar a agenda real — volto em 1 minuto"
        out = _scrub_prohibited(texto_loop, ctx)
        assert out != texto_loop
        assert "fora do ar" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
