"""Bug C-70 — Sábado família determinístico + modo estrito (Fábio 14/08/2026).

Testa:
    - sabado_familia_do_mes: cálculo correto Águas Claras (último) / Asa Norte (penúltimo)
    - proximo_sabado_familia: avança pro mês seguinte quando o do mês passou
    - deve_ofertar_sabado: bypass responde quando paciente pede sábado + tem unidade
    - modo_estrito: bloqueia LLM quando toggle ON e bypass é None
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from voice_agent.sabado_familia import (
    _sabados_do_mes,
    deve_ofertar_sabado,
    formatar_sabado_pt,
    proximo_sabado_familia,
    sabado_familia_do_mes,
)
from voice_agent.modo_estrito import (
    deve_bloquear_llm_e_escalar,
    modo_estrito_ativo,
    montar_nota_handoff,
    silencio_estrito,
)


# ═════════════════════════════════════════════════════════════════════════
# _sabados_do_mes
# ═════════════════════════════════════════════════════════════════════════

class TestSabadosDoMes:
    def test_agosto_2026(self):
        sabs = _sabados_do_mes(2026, 8)
        assert sabs == [
            date(2026, 8, 1),
            date(2026, 8, 8),
            date(2026, 8, 15),
            date(2026, 8, 22),
            date(2026, 8, 29),
        ]

    def test_setembro_2026(self):
        sabs = _sabados_do_mes(2026, 9)
        assert sabs == [
            date(2026, 9, 5),
            date(2026, 9, 12),
            date(2026, 9, 19),
            date(2026, 9, 26),
        ]

    def test_fevereiro_2027(self):
        # fevereiro 2027 tem 4 sábados
        sabs = _sabados_do_mes(2027, 2)
        assert len(sabs) == 4


# ═════════════════════════════════════════════════════════════════════════
# sabado_familia_do_mes — regra canônica
# ═════════════════════════════════════════════════════════════════════════

class TestSabadoFamiliaDoMes:
    def test_aguas_claras_agosto_2026_ultimo_sabado(self):
        # último sábado de agosto/2026 = 29/08
        d = sabado_familia_do_mes(2026, 8, "Águas Claras")
        assert d == date(2026, 8, 29)

    def test_asa_norte_agosto_2026_penultimo_sabado(self):
        # penúltimo sábado de agosto/2026 = 22/08
        d = sabado_familia_do_mes(2026, 8, "Asa Norte")
        assert d == date(2026, 8, 22)

    def test_aguas_claras_setembro_2026(self):
        d = sabado_familia_do_mes(2026, 9, "Águas Claras")
        assert d == date(2026, 9, 26)

    def test_asa_norte_setembro_2026(self):
        d = sabado_familia_do_mes(2026, 9, "Asa Norte")
        assert d == date(2026, 9, 19)

    def test_aceita_variantes_grafia(self):
        # "aguas claras" sem acento também vale
        d = sabado_familia_do_mes(2026, 8, "aguas claras")
        assert d == date(2026, 8, 29)

    def test_unidade_desconhecida_retorna_none(self):
        d = sabado_familia_do_mes(2026, 8, "Brasília Sul")
        assert d is None


# ═════════════════════════════════════════════════════════════════════════
# proximo_sabado_familia — avança mês quando já passou
# ═════════════════════════════════════════════════════════════════════════

class TestProximoSabadoFamilia:
    def test_meio_do_mes_retorna_sabado_do_proprio_mes(self):
        # 14/08 sexta, sábado família Águas Claras é 29/08 → futuro
        hoje = date(2026, 8, 14)
        d = proximo_sabado_familia(hoje, "Águas Claras")
        assert d == date(2026, 8, 29)

    def test_apos_ultimo_sabado_avanca_pro_proximo_mes(self):
        # 30/08 domingo — sábado família agosto já passou → set/2026
        hoje = date(2026, 8, 30)
        d = proximo_sabado_familia(hoje, "Águas Claras")
        assert d == date(2026, 9, 26)

    def test_dia_do_sabado_familia_ainda_retorna_ele(self):
        # 29/08 sábado — o próprio dia é válido
        hoje = date(2026, 8, 29)
        d = proximo_sabado_familia(hoje, "Águas Claras")
        assert d == date(2026, 8, 29)

    def test_dezembro_para_janeiro(self):
        # 31/12/2026 quinta — último sábado dezembro é 26/12 → já passou
        # → avança pra janeiro/2027, cujo último sábado é 30/01
        hoje = date(2026, 12, 31)
        d = proximo_sabado_familia(hoje, "Águas Claras")
        assert d == date(2027, 1, 30)


# ═════════════════════════════════════════════════════════════════════════
# formatar_sabado_pt
# ═════════════════════════════════════════════════════════════════════════

class TestFormatarSabadoPT:
    def test_formato_padrao(self):
        assert formatar_sabado_pt(date(2026, 8, 29)) == "sábado (29/08)"

    def test_dias_com_um_digito(self):
        assert formatar_sabado_pt(date(2026, 8, 1)) == "sábado (01/08)"


# ═════════════════════════════════════════════════════════════════════════
# deve_ofertar_sabado — bypass conversacional
# ═════════════════════════════════════════════════════════════════════════

class TestDeveOfertarSabado:
    def _ctx(self, unidade="Águas Claras", nome="Karina"):
        return {
            "known": {"unidade": unidade, "nome_contato": nome},
            "lead_id": "23469368",
        }

    def test_paciente_pede_sabado_aguas_claras(self):
        ctx = self._ctx()
        r = deve_ofertar_sabado(ctx, "Tem sábado?", hoje=date(2026, 8, 14))
        assert r is not None
        assert "29/08" in r
        assert "Águas Claras" in r
        assert "Karina" in r

    def test_paciente_pede_sabado_asa_norte(self):
        ctx = self._ctx(unidade="Asa Norte")
        r = deve_ofertar_sabado(ctx, "Atende sábado?", hoje=date(2026, 8, 14))
        assert r is not None
        assert "22/08" in r
        assert "Asa Norte" in r

    def test_paciente_nao_menciona_sabado(self):
        ctx = self._ctx()
        r = deve_ofertar_sabado(ctx, "Quero terça de manhã", hoje=date(2026, 8, 14))
        assert r is None

    def test_paciente_nega_sabado(self):
        ctx = self._ctx()
        r = deve_ofertar_sabado(ctx, "Não posso sábado", hoje=date(2026, 8, 14))
        assert r is None

    def test_sem_unidade_no_ctx(self):
        ctx = {"known": {"nome_contato": "Karina"}}
        r = deve_ofertar_sabado(ctx, "Tem sábado?", hoje=date(2026, 8, 14))
        assert r is None

    def test_ctx_none(self):
        r = deve_ofertar_sabado(None, "Tem sábado?", hoje=date(2026, 8, 14))
        assert r is None

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("SABADO_FAMILIA_ATIVADO", "0")
        ctx = self._ctx()
        r = deve_ofertar_sabado(ctx, "Tem sábado?", hoje=date(2026, 8, 14))
        assert r is None

    def test_caso_real_karina_lead_23469368(self):
        # Karina Lícia — Águas Claras, hoje 14/08/2026 sexta
        # Ela perguntou "Atende sábado?" — resposta canônica deve ser 29/08
        ctx = {
            "known": {
                "unidade": "Águas Claras",
                "nome_contato": "Karina Lícia",
            },
            "lead_id": "23469368",
        }
        r = deve_ofertar_sabado(ctx, "Atende sábado?", hoje=date(2026, 8, 14))
        assert r is not None
        assert "29/08" in r
        assert "Águas Claras" in r
        assert "Karina" in r  # saudação com primeiro nome
        # Não deve mencionar 15/08 nem 22/08 (datas erradas que Lia inventou)
        assert "15/08" not in r
        assert "22/08" not in r


# ═════════════════════════════════════════════════════════════════════════
# modo_estrito — bloqueio LLM
# ═════════════════════════════════════════════════════════════════════════

class TestModoEstrito:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("MODO_ESTRITO_DETERMINISTICO", raising=False)
        assert modo_estrito_ativo() is False

    def test_ligado_via_env(self, monkeypatch):
        monkeypatch.setenv("MODO_ESTRITO_DETERMINISTICO", "1")
        assert modo_estrito_ativo() is True

    def test_bypass_respondeu_nao_escala(self, monkeypatch):
        monkeypatch.setenv("MODO_ESTRITO_DETERMINISTICO", "1")
        assert (
            deve_bloquear_llm_e_escalar("alguma resposta", {"lead_id": "1"})
            is False
        )

    def test_bypass_vazio_com_toggle_off_nao_escala(self, monkeypatch):
        monkeypatch.delenv("MODO_ESTRITO_DETERMINISTICO", raising=False)
        assert (
            deve_bloquear_llm_e_escalar(None, {"lead_id": "1"})
            is False
        )

    def test_bypass_vazio_com_toggle_on_escala(self, monkeypatch):
        monkeypatch.setenv("MODO_ESTRITO_DETERMINISTICO", "1")
        assert (
            deve_bloquear_llm_e_escalar(None, {"lead_id": "1"})
            is True
        )

    def test_bypass_string_vazia_com_toggle_on_escala(self, monkeypatch):
        monkeypatch.setenv("MODO_ESTRITO_DETERMINISTICO", "1")
        assert (
            deve_bloquear_llm_e_escalar("", {"lead_id": "1"})
            is True
        )

    def test_silencio_estrito_payload(self):
        p = silencio_estrito()
        assert p["answer"] == ""
        assert p["modo_estrito_escalado"] is True

    def test_nota_handoff_menciona_mensagem_paciente(self):
        n = montar_nota_handoff("Tem quinta 8h?")
        assert "C-70" in n
        assert "Tem quinta 8h" in n
        assert "MODO ESTRITO" in n
