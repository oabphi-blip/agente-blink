"""Testes do campo JANELA 24H — contagem regressiva do prazo WhatsApp.

Origem: Fábio 05-06/07/2026. O campo mostra quanto FALTA pra fechar a janela
de 24h (Falta 20h … Falta 01h → Expirou), recalculado a partir do último
inbound do paciente. Nova mensagem renova pro topo (Falta 20h).

Faixas (arredonda pra baixo):
  >= 20h → Falta 20h    5–10h → Falta 05h    2–3h → Falta 02h
  15–20h → Falta 15h    4–5h  → Falta 04h    <2h  → Falta 01h
  10–15h → Falta 10h    3–4h  → Falta 03h    <=0  → Expirou
"""
from datetime import datetime, timezone, timedelta

import pytest

from voice_agent.campos_acompanhamento import (
    classificar_janela_24h,
    segundos_restantes_janela,
    campos_janela_24h,
    JANELA_EXPIROU,
)

HORA = 3600


def rotulo(horas_desde_ultima, agora=1_000_000):
    """Helper: dado quantas horas se passaram desde a última msg, retorna rótulo."""
    return classificar_janela_24h(agora - horas_desde_ultima * HORA, agora)


class TestContagemRegressiva:
    def test_sem_inbound_retorna_none(self):
        assert classificar_janela_24h(None) is None

    def test_mensagem_nova_mostra_topo_falta_20h(self):
        # acabou de mandar msg → restam ~24h → topo
        assert rotulo(0) == "Falta 20h"

    def test_2h_depois_ainda_falta_20h(self):
        # restam 22h → >= 20 → Falta 20h
        assert rotulo(2) == "Falta 20h"

    def test_5h_depois_falta_15h(self):
        # restam 19h → 15–20 → Falta 15h
        assert rotulo(5) == "Falta 15h"

    def test_10h_depois_falta_10h(self):
        # restam 14h → 10–15 → Falta 10h
        assert rotulo(10) == "Falta 10h"

    def test_15h_depois_falta_05h(self):
        # restam 9h → 5–10 → Falta 05h
        assert rotulo(15) == "Falta 05h"

    def test_19h_depois_falta_05h(self):
        # restam 5h → >=5 → Falta 05h
        assert rotulo(19) == "Falta 05h"

    def test_20h_depois_falta_04h(self):
        # restam 4h → 4–5 → Falta 04h
        assert rotulo(20) == "Falta 04h"

    def test_21h_depois_falta_03h(self):
        # restam 3h → 3–4 → Falta 03h
        assert rotulo(21) == "Falta 03h"

    def test_22h_depois_falta_02h(self):
        # restam 2h → 2–3 → Falta 02h
        assert rotulo(22) == "Falta 02h"

    def test_23h_depois_falta_01h(self):
        # restam 1h → 1–2 → Falta 01h
        assert rotulo(23) == "Falta 01h"

    def test_23h30_depois_falta_01h(self):
        # restam 0.5h → >0 e <1 → Falta 01h
        agora = 1_000_000
        assert classificar_janela_24h(agora - 23.5 * HORA, agora) == "Falta 01h"

    def test_exatamente_24h_expirou(self):
        assert rotulo(24) == JANELA_EXPIROU

    def test_muito_depois_expirou(self):
        assert rotulo(48) == JANELA_EXPIROU

    def test_aceita_datetime_aware(self):
        agora = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
        ultima = agora - timedelta(hours=10)  # restam 14h
        assert classificar_janela_24h(ultima, agora) == "Falta 10h"

    def test_string_invalida_retorna_none(self):
        assert classificar_janela_24h("abc", 1_000_000) is None


class TestSegundosRestantes:
    def test_sem_inbound_none(self):
        assert segundos_restantes_janela(None) is None

    def test_acabou_de_falar_quase_24h(self):
        agora = 1_000_000
        r = segundos_restantes_janela(agora - 60, agora)
        assert 23 * HORA < r <= 24 * HORA

    def test_fechada_zero(self):
        agora = 1_000_000
        assert segundos_restantes_janela(agora - 30 * HORA, agora) == 0


class TestCamposJanela:
    def test_sem_inbound_dict_vazio(self):
        assert campos_janela_24h(None) == {}

    def test_gera_ts_e_rotulo_topo(self):
        agora = 1_000_000
        out = campos_janela_24h(agora - HORA, agora)
        assert out["ts_ultima_msg_paciente"] == agora - HORA
        assert out["janela_24h"] == "Falta 20h"

    def test_gera_rotulo_expirou(self):
        agora = 1_000_000
        out = campos_janela_24h(agora - 25 * HORA, agora)
        assert out["janela_24h"] == JANELA_EXPIROU

    def test_ts_convertido_para_int(self):
        agora = 1_000_000.0
        out = campos_janela_24h(agora - HORA, agora)
        assert isinstance(out["ts_ultima_msg_paciente"], int)


class TestMapeamentoKommo:
    """Cadeia rótulo → enum_id real do Kommo (contagem regressiva, 06/07/2026)."""

    def test_field_ids_reais(self):
        from voice_agent.campos_acompanhamento import (
            FIELD_TS_ULTIMA_MSG_PACIENTE, FIELD_JANELA_24H,
        )
        assert FIELD_TS_ULTIMA_MSG_PACIENTE == 1260984
        assert FIELD_JANELA_24H[0] == 1260986

    def test_enum_ids_por_rotulo(self):
        from voice_agent.campos_acompanhamento import FIELD_JANELA_24H
        _, enums = FIELD_JANELA_24H
        assert enums["Falta 20h"] == 927302
        assert enums["Falta 15h"] == 927304
        assert enums["Falta 10h"] == 927306
        assert enums["Falta 05h"] == 927308
        assert enums["Falta 04h"] == 927310
        assert enums["Falta 03h"] == 927312
        assert enums["Falta 02h"] == 927314
        assert enums["Falta 01h"] == 927316
        assert enums["Expirou"] == 927318

    def test_cadeia_completa_rotulo_para_enum(self):
        from voice_agent.kommo import _pick_enum
        from voice_agent.campos_acompanhamento import (
            campos_janela_24h, FIELD_JANELA_24H,
        )
        agora = 1_000_000
        _, enums = FIELD_JANELA_24H
        casos = {
            agora - 1 * HORA: 927302,    # Falta 20h
            agora - 5 * HORA: 927304,    # Falta 15h
            agora - 20 * HORA: 927310,   # Falta 04h
            agora - 23 * HORA: 927316,   # Falta 01h
            agora - 25 * HORA: 927318,   # Expirou
        }
        for ts, esperado in casos.items():
            campos = campos_janela_24h(ts, agora)
            assert _pick_enum(enums, campos["janela_24h"]) == esperado


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
