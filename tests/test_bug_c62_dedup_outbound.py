"""Bug C-62 — Dedup outbound anti-loop (Fábio 20/07/2026, lead 24325532).

Lia mandou 'Anotado. Qual dia da semana e turno funcionam melhor pra
vocês?' 7× em 5 minutos. Paciente disse 'meu deus' e desistiu.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent.dedup_outbound import (
    LIMITE_LOOP,
    _calcular_hash,
    _normalizar_texto,
    lead_esta_em_loop,
    resposta_canonica_loop,
    verificar_e_registrar,
)


class TestNormalizacao:
    def test_lower_strip(self):
        assert _normalizar_texto("  Olá Mundo  ") == "olá mundo"

    def test_colapsa_espacos(self):
        assert _normalizar_texto("A     B     C") == "a b c"

    def test_limita_300_chars(self):
        assert len(_normalizar_texto("x" * 500)) == 300

    def test_vazio(self):
        assert _normalizar_texto("") == ""
        assert _normalizar_texto(None) == ""


class TestHash:
    def test_mesma_msg_mesmo_hash(self):
        a = _calcular_hash("Anotado. Qual dia da semana?")
        b = _calcular_hash("Anotado. Qual dia da semana?")
        assert a == b
        assert len(a) == 16

    def test_variacao_case_msmo_hash(self):
        a = _calcular_hash("ANOTADO. QUAL DIA?")
        b = _calcular_hash("anotado. qual dia?")
        assert a == b

    def test_msg_diferente_hash_diferente(self):
        a = _calcular_hash("Anotado. Qual dia?")
        b = _calcular_hash("Perfeito! Qual dia?")
        assert a != b


class TestVerificarERegistrar:
    def _mock_redis(self, state=None):
        m = MagicMock()
        state = state or {"counts": {}}

        def incr(k):
            state["counts"][k] = state["counts"].get(k, 0) + 1
            return state["counts"][k]

        def get(k):
            return None

        def setex(k, ttl, v):
            pass

        def expire(k, ttl):
            pass

        m.incr = MagicMock(side_effect=incr)
        m.get = MagicMock(side_effect=get)
        m.setex = MagicMock(side_effect=setex)
        m.expire = MagicMock(side_effect=expire)
        return m, state

    def test_primeira_vez_permite(self):
        r_mock, _ = self._mock_redis()
        r = verificar_e_registrar(123, "Olá!", r_mock)
        assert r["permitir_envio"] is True
        assert r["eh_duplicata"] is False
        assert r["contador"] == 1

    def test_segunda_vez_permite_mas_marca_duplicata(self):
        r_mock, _ = self._mock_redis()
        verificar_e_registrar(123, "Olá!", r_mock)
        r = verificar_e_registrar(123, "Olá!", r_mock)
        assert r["permitir_envio"] is True
        assert r["eh_duplicata"] is True
        assert r["razao"] == "duplicata"
        assert r["contador"] == 2

    def test_terceira_vez_bloqueia_loop(self):
        r_mock, _ = self._mock_redis()
        verificar_e_registrar(123, "Anotado!", r_mock)
        verificar_e_registrar(123, "Anotado!", r_mock)
        r = verificar_e_registrar(123, "Anotado!", r_mock)
        assert r["permitir_envio"] is False
        assert r["loop_detectado"] is True
        assert r["razao"] == "loop"

    def test_lead_diferente_conta_separado(self):
        r_mock, _ = self._mock_redis()
        # Lead 123 manda 2x
        verificar_e_registrar(123, "X", r_mock)
        verificar_e_registrar(123, "X", r_mock)
        # Lead 456 manda 1x mesma msg — não conta como loop
        r = verificar_e_registrar(456, "X", r_mock)
        assert r["contador"] == 1
        assert r["permitir_envio"] is True

    def test_texto_vazio_permite(self):
        r_mock, _ = self._mock_redis()
        r = verificar_e_registrar(123, "", r_mock)
        assert r["permitir_envio"] is True

    def test_sem_redis_fail_open(self):
        r = verificar_e_registrar(123, "Olá!", None)
        assert r["permitir_envio"] is True

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("DEDUP_OUTBOUND_ATIVADO", "0")
        r_mock, _ = self._mock_redis()
        # Mesmo depois de 10 tentativas, sempre permite
        for _ in range(10):
            r = verificar_e_registrar(123, "X", r_mock)
        assert r["permitir_envio"] is True
        assert r["loop_detectado"] is False

    def test_redis_estoura_fail_open(self):
        m = MagicMock()
        m.incr = MagicMock(side_effect=Exception("redis down"))
        r = verificar_e_registrar(123, "Olá!", m)
        assert r["permitir_envio"] is True


class TestCasoRealFabio:
    def test_lead_24325532_loop_detectado_no_3o(self):
        """Reproduz cenário Fábio 20/07 — Lia mandou 7× 'Anotado. Qual dia...'."""
        from voice_agent.dedup_outbound import LIMITE_LOOP as LIMIT
        assert LIMIT == 3

        r_mock = MagicMock()
        state = {"n": 0}

        def incr(k):
            state["n"] += 1
            return state["n"]

        r_mock.incr = MagicMock(side_effect=incr)
        r_mock.expire = MagicMock()
        r_mock.setex = MagicMock()

        texto = "Anotado. Qual dia da semana e turno funcionam melhor pra vocês?"

        r1 = verificar_e_registrar(24325532, texto, r_mock)
        assert r1["permitir_envio"] is True

        r2 = verificar_e_registrar(24325532, texto, r_mock)
        assert r2["eh_duplicata"] is True
        assert r2["permitir_envio"] is True  # 2ª ainda passa

        r3 = verificar_e_registrar(24325532, texto, r_mock)
        assert r3["loop_detectado"] is True
        assert r3["permitir_envio"] is False  # 3ª BLOQUEIA

        # 4ª tentativa continua bloqueando
        r4 = verificar_e_registrar(24325532, texto, r_mock)
        assert r4["permitir_envio"] is False


class TestRespostaCanonica:
    def test_com_nome(self):
        r = resposta_canonica_loop("Ana Silva")
        assert "Ana" in r
        assert "desculpas" in r.lower() or "repetição" in r.lower()

    def test_sem_nome(self):
        r = resposta_canonica_loop(None)
        assert "desculpas" in r.lower() or "repetição" in r.lower()

    def test_curta(self):
        r = resposta_canonica_loop("Paciente")
        assert len(r) < 250


class TestLeadEmLoop:
    def test_sem_redis_retorna_false(self):
        assert lead_esta_em_loop(123, None) is False

    def test_flag_ausente_retorna_false(self):
        m = MagicMock()
        m.get = MagicMock(return_value=None)
        assert lead_esta_em_loop(123, m) is False

    def test_flag_presente_retorna_true(self):
        m = MagicMock()
        m.get = MagicMock(return_value=b"hash_x")
        assert lead_esta_em_loop(123, m) is True
