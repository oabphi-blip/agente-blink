"""Testes do classificador de JANELA 24H (observabilidade do prazo WhatsApp).

Origem: Fábio 05/07/2026 — campo pra observar tempo restante pra fechar a
janela de 24h. Classificação a partir do último inbound do paciente:
  < 22h   → aberta
  22h-24h → expirando (< 2h pra fechar)
  >= 24h  → fechada (só template)
"""
from datetime import datetime, timezone, timedelta

import pytest

from voice_agent.campos_acompanhamento import (
    classificar_janela_24h,
    segundos_restantes_janela,
    campos_janela_24h,
    JANELA_ABERTA,
    JANELA_EXPIRANDO,
    JANELA_FECHADA,
)

HORA = 3600


class TestClassificar:
    def test_sem_inbound_retorna_none(self):
        assert classificar_janela_24h(None) is None

    def test_acabou_de_falar_aberta(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora - 60, agora) == JANELA_ABERTA

    def test_meio_da_janela_aberta(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora - 10 * HORA, agora) == JANELA_ABERTA

    def test_borda_inferior_expirando_exatamente_22h(self):
        agora = 1_000_000
        assert (
            classificar_janela_24h(agora - 22 * HORA, agora) == JANELA_EXPIRANDO
        )

    def test_23h_expirando(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora - 23 * HORA, agora) == JANELA_EXPIRANDO

    def test_borda_exatamente_24h_fechada(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora - 24 * HORA, agora) == JANELA_FECHADA

    def test_muito_depois_fechada(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora - 50 * HORA, agora) == JANELA_FECHADA

    def test_aceita_datetime_aware(self):
        agora = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
        ultima = agora - timedelta(hours=23)
        assert classificar_janela_24h(ultima, agora) == JANELA_EXPIRANDO

    def test_aceita_datetime_naive_tratado_utc(self):
        agora = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
        ultima = datetime(2026, 7, 5, 11, 0)  # naive → UTC, 1h atrás
        assert classificar_janela_24h(ultima, agora) == JANELA_ABERTA

    def test_ts_futuro_nao_quebra_trata_como_aberta(self):
        agora = 1_000_000
        assert classificar_janela_24h(agora + 5 * HORA, agora) == JANELA_ABERTA

    def test_string_invalida_retorna_none(self):
        assert classificar_janela_24h("abc", 1_000_000) is None


class TestSegundosRestantes:
    def test_sem_inbound_none(self):
        assert segundos_restantes_janela(None) is None

    def test_acabou_de_falar_quase_24h(self):
        agora = 1_000_000
        r = segundos_restantes_janela(agora - 60, agora)
        assert 23 * HORA < r <= 24 * HORA

    def test_expirando_menos_de_2h(self):
        agora = 1_000_000
        r = segundos_restantes_janela(agora - 23 * HORA, agora)
        assert 0 < r <= 2 * HORA

    def test_fechada_zero(self):
        agora = 1_000_000
        assert segundos_restantes_janela(agora - 30 * HORA, agora) == 0


class TestCamposJanela:
    def test_sem_inbound_dict_vazio(self):
        assert campos_janela_24h(None) == {}

    def test_gera_ts_e_status_aberta(self):
        agora = 1_000_000
        out = campos_janela_24h(agora - HORA, agora)
        assert out["ts_ultima_msg_paciente"] == agora - HORA
        assert out["janela_24h"] == JANELA_ABERTA

    def test_gera_status_fechada(self):
        agora = 1_000_000
        out = campos_janela_24h(agora - 25 * HORA, agora)
        assert out["janela_24h"] == JANELA_FECHADA

    def test_ts_convertido_para_int(self):
        agora = 1_000_000.0
        out = campos_janela_24h(agora - HORA, agora)
        assert isinstance(out["ts_ultima_msg_paciente"], int)


class TestMapeamentoKommo:
    """Valida a cadeia status → enum_id real do Kommo (criados 05/07/2026)."""

    def test_field_ids_reais(self):
        from voice_agent.campos_acompanhamento import (
            FIELD_TS_ULTIMA_MSG_PACIENTE, FIELD_JANELA_24H,
        )
        assert FIELD_TS_ULTIMA_MSG_PACIENTE == 1260984
        assert FIELD_JANELA_24H[0] == 1260986

    def test_enum_ids_por_status(self):
        from voice_agent.campos_acompanhamento import FIELD_JANELA_24H
        _, enums = FIELD_JANELA_24H
        assert enums["aberta"] == 927302
        assert enums["expirando"] == 927304
        assert enums["fechada"] == 927306

    def test_pick_enum_resolve_cada_status(self):
        from voice_agent.kommo import _pick_enum
        from voice_agent.campos_acompanhamento import FIELD_JANELA_24H
        _, enums = FIELD_JANELA_24H
        assert _pick_enum(enums, "aberta") == 927302
        assert _pick_enum(enums, "expirando") == 927304
        assert _pick_enum(enums, "fechada") == 927306

    def test_cadeia_completa_campos_para_enum(self):
        """campos_janela_24h → janela_24h → _pick_enum → enum_id correto."""
        from voice_agent.kommo import _pick_enum
        from voice_agent.campos_acompanhamento import (
            campos_janela_24h, FIELD_JANELA_24H,
        )
        agora = 1_000_000
        _, enums = FIELD_JANELA_24H
        casos = {
            agora - HORA: 927302,          # aberta
            agora - 23 * HORA: 927304,     # expirando
            agora - 25 * HORA: 927306,     # fechada
        }
        for ts, esperado in casos.items():
            campos = campos_janela_24h(ts, agora)
            assert _pick_enum(enums, campos["janela_24h"]) == esperado


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
