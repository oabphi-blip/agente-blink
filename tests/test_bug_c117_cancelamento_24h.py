"""
Testes para Bug C-117 — Cancelamento < 24h → política de sinal não devolvido.

Cobre:
1. Detecção de padrões de cancelamento PT-BR (positivos e negativos)
2. Sem dia_consulta_iso → None (fail-open)
3. Consulta >= 24h → None (cancelamento normal, sem política especial)
4. Consulta < 24h com sinal → mensagem com política
5. Consulta < 24h sem sinal → mensagem suave (sem mencionar sinal)
6. Consulta já passou → mensagem diferente
7. Toggle OFF → None
8. Fail-open: exceção/ISO inválido → None
9. Posição na chain: antes de C-108 (desistência)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

_BRT = timezone(timedelta(hours=-3))


def _iso_daqui_horas(horas: float) -> str:
    """ISO BRT de daqui a N horas."""
    dt = datetime.now(tz=_BRT) + timedelta(hours=horas)
    return dt.isoformat()


def _iso_atras_horas(horas: float) -> str:
    """ISO BRT de N horas atrás."""
    dt = datetime.now(tz=_BRT) - timedelta(hours=horas)
    return dt.isoformat()


def _ctx(iso=None, sinal_pago=False, nome="Ana"):
    c = {
        "lead_id": 9999,
        "known": {
            "nome_paciente": nome,
        }
    }
    if iso:
        c["known"]["dia_consulta_iso"] = iso
    if sinal_pago:
        c["known"]["sinal_pago"] = True
    return c


# ─────────────────────────────────────────────────────────────────────────────
# 1. Detecção de padrões
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccao:

    def _fn(self, texto):
        from voice_agent.cancelamento_24h import _e_cancelamento
        return _e_cancelamento(texto)

    @pytest.mark.parametrize("texto", [
        "quero cancelar",
        "preciso desmarcar",
        "preciso cancelar minha consulta",
        "vou ter que desmarcar",
        "não vou poder ir",
        "não posso comparecer",
        "gostaria de cancelar",
        "vou cancelar",
        "infelizmente não vou poder ir",
        "preciso remarcar o horário",
        "quero mudar o horário",
        "quero trocar o horário da consulta",
        "cancelamento",
    ])
    def test_detecta_cancelamento(self, texto):
        assert self._fn(texto) is True, f"Não detectou: {texto!r}"

    @pytest.mark.parametrize("texto", [
        "boa tarde",
        "quero agendar",
        "qual o horário?",
        "confirmar consulta",
        "não quero cancelar",         # falso positivo guardado
        "não vou cancelar",           # falso positivo guardado
        "ok, confirmo a consulta",
        "quando é minha consulta?",
    ])
    def test_nao_detecta_texto_neutro(self, texto):
        assert self._fn(texto) is False, f"Falso positivo: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Sem dia_consulta_iso
# ─────────────────────────────────────────────────────────────────────────────

class TestSemConsulta:

    def _fn(self, ctx, texto):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        return deve_informar_politica_cancelamento_24h(ctx, texto)

    def test_sem_iso_retorna_none(self):
        ctx = _ctx(iso=None)
        assert self._fn(ctx, "quero cancelar") is None

    def test_ctx_none_retorna_none(self):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        assert deve_informar_politica_cancelamento_24h(None, "quero cancelar") is None

    def test_user_text_vazio_retorna_none(self):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        assert deve_informar_politica_cancelamento_24h(_ctx(), "") is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Consulta >= 24h → None (sem política)
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultaLonge:

    def _fn(self, ctx, texto="quero cancelar"):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        return deve_informar_politica_cancelamento_24h(ctx, texto)

    def test_consulta_48h_sem_politica(self):
        """48h de antecedência → cancelamento normal → None."""
        ctx = _ctx(iso=_iso_daqui_horas(48), sinal_pago=True)
        assert self._fn(ctx) is None

    def test_consulta_25h_sem_politica(self):
        """25h de antecedência → > 24h → None."""
        ctx = _ctx(iso=_iso_daqui_horas(25), sinal_pago=True)
        assert self._fn(ctx) is None

    def test_consulta_exatamente_24h_sem_politica(self):
        """Exatamente 24h → sem política (margem está em <24h)."""
        ctx = _ctx(iso=_iso_daqui_horas(24.1), sinal_pago=True)
        assert self._fn(ctx) is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Consulta < 24h com sinal → mensagem com política
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultaProximaComSinal:

    def _fn(self, ctx, texto="quero cancelar"):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        return deve_informar_politica_cancelamento_24h(ctx, texto)

    def test_consulta_2h_com_sinal_retorna_politica(self):
        """2h de antecedência + sinal → mensagem com política."""
        ctx = _ctx(iso=_iso_daqui_horas(2), sinal_pago=True)
        result = self._fn(ctx)
        assert result is not None
        assert "sinal" in result.lower() or "devolvido" in result.lower() or "política" in result.lower() or "50%" in result.lower()

    def test_consulta_10h_com_sinal_retorna_politica(self):
        ctx = _ctx(iso=_iso_daqui_horas(10), sinal_pago=True)
        result = self._fn(ctx)
        assert result is not None

    def test_politica_menciona_reagendamento(self):
        """Mensagem deve sempre oferecer reagendamento."""
        ctx = _ctx(iso=_iso_daqui_horas(3), sinal_pago=True)
        result = self._fn(ctx)
        assert result is not None
        assert "remarcar" in result.lower() or "reagend" in result.lower() or "opções" in result.lower()

    def test_politica_menciona_nome_do_paciente(self):
        ctx = _ctx(iso=_iso_daqui_horas(3), sinal_pago=True, nome="Claudia")
        result = self._fn(ctx)
        assert result is not None
        assert "Claudia" in result

    def test_nao_posso_comparecer_dispara(self):
        ctx = _ctx(iso=_iso_daqui_horas(5), sinal_pago=True)
        result = self._fn(ctx, "não posso comparecer")
        assert result is not None

    def test_precisar_desmarcar_dispara(self):
        ctx = _ctx(iso=_iso_daqui_horas(8), sinal_pago=True)
        result = self._fn(ctx, "preciso desmarcar")
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Consulta < 24h SEM sinal → mensagem suave
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultaProximaSemSinal:

    def _fn(self, ctx, texto="quero cancelar"):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        return deve_informar_politica_cancelamento_24h(ctx, texto)

    def test_consulta_2h_sem_sinal_retorna_mensagem_suave(self):
        ctx = _ctx(iso=_iso_daqui_horas(2), sinal_pago=False)
        result = self._fn(ctx)
        assert result is not None
        # Sem sinal → sem mencionar sinal ou devolver
        assert "50%" not in result
        assert "não devolvido" not in result.lower()

    def test_consulta_suave_menciona_reagendamento(self):
        ctx = _ctx(iso=_iso_daqui_horas(4), sinal_pago=False)
        result = self._fn(ctx)
        assert result is not None
        assert "remarcar" in result.lower() or "opções" in result.lower() or "horário" in result.lower()

    def test_consulta_48h_sem_sinal_retorna_none(self):
        """Mesmo sem sinal, 48h de antecedência → None (sem urgência)."""
        ctx = _ctx(iso=_iso_daqui_horas(48), sinal_pago=False)
        assert self._fn(ctx) is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Consulta já passou
# ─────────────────────────────────────────────────────────────────────────────

class TestConsultaPassada:

    def _fn(self, ctx, texto="quero cancelar"):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        return deve_informar_politica_cancelamento_24h(ctx, texto)

    def test_consulta_ja_passou_com_sinal_retorna_mensagem_pos(self):
        """Consulta ontem + sinal → mensagem pós-consulta (sem política de devolução)."""
        ctx = _ctx(iso=_iso_atras_horas(25), sinal_pago=True)
        result = self._fn(ctx)
        assert result is not None
        # Mensagem pós-consulta não deve mencionar política de cancelamento futuro
        assert "24h" not in result.lower()

    def test_consulta_ja_passou_sem_sinal_retorna_none(self):
        """Consulta ontem sem sinal → sem política relevante → None."""
        ctx = _ctx(iso=_iso_atras_horas(25), sinal_pago=False)
        # Sem sinal pago e consulta passada → nem a mensagem suave deve disparar
        # (horas < 0, guard retorna None no branch sem sinal)
        result = self._fn(ctx)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Toggle
# ─────────────────────────────────────────────────────────────────────────────

class TestToggle:

    def test_toggle_off_retorna_none(self):
        import voice_agent.cancelamento_24h as mod
        orig = mod._ATIVADO
        mod._ATIVADO = False
        try:
            from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
            ctx = _ctx(iso=_iso_daqui_horas(2), sinal_pago=True)
            assert deve_informar_politica_cancelamento_24h(ctx, "quero cancelar") is None
        finally:
            mod._ATIVADO = orig

    def test_toggle_on_permite_execucao(self):
        import voice_agent.cancelamento_24h as mod
        orig = mod._ATIVADO
        mod._ATIVADO = True
        try:
            from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
            ctx = _ctx(iso=_iso_daqui_horas(2), sinal_pago=True)
            result = deve_informar_politica_cancelamento_24h(ctx, "quero cancelar")
            assert result is not None
        finally:
            mod._ATIVADO = orig


# ─────────────────────────────────────────────────────────────────────────────
# 8. Fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOpen:

    def test_iso_invalido_retorna_none(self):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        ctx = _ctx(iso="INVALIDO", sinal_pago=True)
        # Deve retornar None sem levantar exceção
        result = deve_informar_politica_cancelamento_24h(ctx, "quero cancelar")
        assert result is None

    def test_excecao_nao_vaza_para_caller(self):
        from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h
        # ctx com tipo errado
        result = deve_informar_politica_cancelamento_24h("nao_e_dict", "quero cancelar")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 9. Posição na chain
# ─────────────────────────────────────────────────────────────────────────────

class TestPosicaoNaChain:

    def test_c117_antes_de_c108_desistencia(self):
        """C-117 deve vir ANTES de C-108 (desistência) no código fonte."""
        import inspect
        import voice_agent.blindagens_deterministicas as mod
        src = inspect.getsource(mod)
        inicio = src.find("def tentar_bypass_deterministico")
        assert inicio >= 0
        corpo = src[inicio:]

        idx_c117 = corpo.find('return ("cancelamento_24h"')
        idx_c108 = corpo.find('return ("desistencia"')
        assert idx_c117 != -1, "return cancelamento_24h não encontrado"
        assert idx_c108 != -1, "return desistencia não encontrado"
        assert idx_c117 < idx_c108, (
            f"C-117 deveria vir ANTES de C-108. c117@{idx_c117} c108@{idx_c108}"
        )

    def test_bypass_retorna_cancelamento_24h_quando_disparado(self):
        """tentar_bypass_deterministico retorna ('cancelamento_24h', texto)."""
        import voice_agent.cancelamento_24h as mod
        orig = mod._ATIVADO
        mod._ATIVADO = True
        try:
            from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
            ctx = _ctx(iso=_iso_daqui_horas(3), sinal_pago=True)
            resultado = tentar_bypass_deterministico(ctx, "quero cancelar")
            assert resultado is not None
            nome, texto = resultado
            assert nome == "cancelamento_24h"
            assert len(texto) > 10
        finally:
            mod._ATIVADO = orig

    def test_bypass_sem_iso_nao_retorna_cancelamento_24h(self):
        """Sem dia_consulta_iso o bypass não dispara."""
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        ctx = _ctx(iso=None)  # sem consulta marcada
        resultado = tentar_bypass_deterministico(ctx, "quero cancelar")
        if resultado:
            nome, _ = resultado
            assert nome != "cancelamento_24h"
