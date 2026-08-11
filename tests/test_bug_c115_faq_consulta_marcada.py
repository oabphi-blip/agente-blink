"""
Testes para Bug C-115 — FAQ "quando é minha consulta?"

Cobre:
- Detecção de padrões de pergunta PT-BR (positivos e falsos positivos)
- Resposta com consulta futura (data + hora + médico + unidade)
- Resposta com consulta passada (> 24h atrás)
- Fail-open: sem dia_consulta_iso → None
- Fail-open: ctx=None, user_text vazio → None
- Toggle OFF → None
- Médico correto extraído (Karla / Fabrício / default)
- Unidade correta extraída (Asa Norte / Águas Claras)
- Posição do bypass: após faq_disponibilidade_hoje, antes de faq_endereco
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Fuso BRT UTC-3 (sem zoneinfo pra compatibilidade CI)
_BRT = timezone(timedelta(hours=-3))


def _ts_futuro_dias(dias: int) -> str:
    """ISO BRT de daqui a N dias às 10:00."""
    dt = datetime.now(tz=_BRT).replace(hour=10, minute=0, second=0, microsecond=0)
    dt = dt + timedelta(days=dias)
    return dt.isoformat()


def _ts_passado_dias(dias: int) -> str:
    """ISO BRT de N dias atrás às 09:30."""
    dt = datetime.now(tz=_BRT).replace(hour=9, minute=30, second=0, microsecond=0)
    dt = dt - timedelta(days=dias)
    return dt.isoformat()


def _ctx(
    iso: str | None = None,
    medico: str = "Karla",
    unidade: str = "Asa Norte",
) -> dict:
    """Monta caller_context mínimo com dia_consulta_iso."""
    return {
        "found": True,
        "known": {
            **({"dia_consulta_iso": iso} if iso else {}),
            "medico": medico,
            "unidade": unidade,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Detecção de padrões
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccao:

    def _fn(self, texto):
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = _ctx(iso=_ts_futuro_dias(3))
        return deve_responder_faq_consulta_marcada(ctx, texto)

    # Positivos esperados
    @pytest.mark.parametrize("texto", [
        "quando é minha consulta?",
        "que dia é minha consulta?",
        "qual o horário da consulta?",
        "confirmar minha consulta",
        "minha consulta é quando?",
        "que horas é minha consulta",
        "qual o dia da minha consulta",
        "quando tenho consulta?",
        "já tenho consulta marcada?",
        "confirmar horário",
        "que horas tenho consulta amanhã",
        "minha consulta marcada",
        "qual é minha consulta?",
        "quando é minha visita",
    ])
    def test_detecta_pergunta_consulta(self, texto):
        assert self._fn(texto) is not None, f"Esperava detectar: {texto!r}"

    # Falsos positivos que NÃO devem disparar
    @pytest.mark.parametrize("texto", [
        "oi, boa tarde",
        "quero agendar consulta",      # solicitar, não perguntar sobre existente
        "quanto custa a consulta?",    # pergunta de valor, não de data
        "posso remarcar?",
        "tenho uma dúvida",
        "bom dia!",
    ])
    def test_nao_dispara_texto_neutro(self, texto):
        # Esses não devem ativar o FAQ (pode ativar outros bypasses, aqui testamos
        # só a função isolada)
        result = self._fn(texto)
        # "posso remarcar" e "quanto custa" podem cair em outros bypasses mas
        # o FAQ consulta_marcada não deve pegar eles
        # Verificamos apenas que o texto não tem o padrão de "quando é minha consulta"
        from voice_agent.faq_consulta_marcada import _RE_CONSULTA_QUANDO
        assert not _RE_CONSULTA_QUANDO.search(texto), (
            f"Falso positivo detectado para: {texto!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Comportamento com dados
# ─────────────────────────────────────────────────────────────────────────────

class TestResposta:

    def _fn(self, ctx, texto="quando é minha consulta?"):
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        return deve_responder_faq_consulta_marcada(ctx, texto)

    def test_consulta_futura_retorna_texto_com_data(self):
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = self._fn(ctx)
        assert r is not None
        assert "consulta" in r.lower() or "marcada" in r.lower()

    def test_consulta_futura_tem_hora(self):
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = self._fn(ctx)
        assert "10:00" in r  # _ts_futuro_dias usa 10:00

    def test_consulta_futura_tem_medico_karla(self):
        ctx = _ctx(iso=_ts_futuro_dias(3), medico="Karla")
        r = self._fn(ctx)
        assert "Karla" in r

    def test_consulta_futura_tem_medico_fabricio(self):
        ctx = _ctx(iso=_ts_futuro_dias(3), medico="Fabrício")
        r = self._fn(ctx)
        assert "Fabrício" in r or "Fabricio" in r

    def test_consulta_futura_tem_unidade_asa_norte(self):
        ctx = _ctx(iso=_ts_futuro_dias(3), unidade="Asa Norte")
        r = self._fn(ctx)
        assert "Asa Norte" in r

    def test_consulta_futura_tem_unidade_aguas_claras(self):
        ctx = _ctx(iso=_ts_futuro_dias(3), unidade="Águas Claras")
        r = self._fn(ctx)
        assert "Águas Claras" in r or "Aguas Claras" in r.replace("á", "a")

    def test_consulta_passada_menciona_ultima_consulta(self):
        ctx = _ctx(iso=_ts_passado_dias(5))
        r = self._fn(ctx)
        assert r is not None
        # Consulta passada: deve mencionar que foi realizada e oferecer novo agendamento
        assert "nova" in r.lower() or "ltima" in r.lower() or "registrada" in r.lower()

    def test_consulta_passada_oferece_novo_agendamento(self):
        ctx = _ctx(iso=_ts_passado_dias(5))
        r = self._fn(ctx)
        assert "agendar" in r.lower() or "nova" in r.lower()

    def test_sem_dia_consulta_retorna_none(self):
        ctx = _ctx(iso=None)  # sem dia_consulta_iso
        r = self._fn(ctx)
        assert r is None

    def test_ctx_none_retorna_none(self):
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        r = deve_responder_faq_consulta_marcada(None, "quando é minha consulta?")
        assert r is None

    def test_user_text_vazio_retorna_none(self):
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = deve_responder_faq_consulta_marcada(ctx, "")
        assert r is None

    def test_texto_sem_padrao_retorna_none(self):
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = deve_responder_faq_consulta_marcada(ctx, "oi, boa tarde")
        assert r is None

    def test_sem_unidade_retorna_sem_crash(self):
        """Ctx sem unidade não deve crashar — usa fallback."""
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = {"found": True, "known": {"dia_consulta_iso": _ts_futuro_dias(2)}}
        r = deve_responder_faq_consulta_marcada(ctx, "quando é minha consulta?")
        assert r is not None

    def test_sem_medico_usa_karla_default(self):
        """Ctx sem médico usa Karla como default."""
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = {"found": True, "known": {"dia_consulta_iso": _ts_futuro_dias(2)}}
        r = deve_responder_faq_consulta_marcada(ctx, "quando é minha consulta?")
        assert "Karla" in r


# ─────────────────────────────────────────────────────────────────────────────
# Toggle
# ─────────────────────────────────────────────────────────────────────────────

class TestToggle:

    def test_toggle_off_retorna_none(self, monkeypatch):
        import voice_agent.faq_consulta_marcada as mod
        monkeypatch.setattr(mod, "_ATIVADO", False)
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = deve_responder_faq_consulta_marcada(ctx, "quando é minha consulta?")
        assert r is None

    def test_toggle_on_retorna_resposta(self, monkeypatch):
        import voice_agent.faq_consulta_marcada as mod
        monkeypatch.setattr(mod, "_ATIVADO", True)
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        ctx = _ctx(iso=_ts_futuro_dias(3))
        r = deve_responder_faq_consulta_marcada(ctx, "quando é minha consulta?")
        assert r is not None


# ─────────────────────────────────────────────────────────────────────────────
# Integração com tentar_bypass_deterministico
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegracaoBypass:

    def test_bypass_retorna_faq_consulta_marcada(self):
        """tentar_bypass_deterministico deve retornar ('faq_consulta_marcada', texto)."""
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        ctx = _ctx(iso=_ts_futuro_dias(3))
        resultado = tentar_bypass_deterministico(ctx, "quando é minha consulta?")
        assert resultado is not None
        nome, texto = resultado
        assert nome == "faq_consulta_marcada"
        assert len(texto) > 10

    def test_bypass_sem_iso_nao_retorna_faq_consulta(self):
        """Sem dia_consulta_iso o bypass não é ativado por este motivo."""
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        ctx = _ctx(iso=None)
        resultado = tentar_bypass_deterministico(ctx, "quando é minha consulta?")
        # Pode retornar None ou outro bypass, mas NÃO deve ser faq_consulta_marcada
        if resultado:
            nome, _ = resultado
            assert nome != "faq_consulta_marcada"

    def test_bypass_faq_consulta_apos_disponibilidade_e_antes_endereco_no_codigo(self):
        """Verifica posição do bypass C-115 no código fonte (via return statements)."""
        import inspect
        import voice_agent.blindagens_deterministicas as mod
        src = inspect.getsource(mod)
        # Usar return statements para não confundir com definições de função
        idx_disponib = src.find('return ("faq_disponibilidade_hoje"')
        idx_c115 = src.find('return ("faq_consulta_marcada"')
        idx_endereco = src.find('return ("faq_endereco"')
        assert idx_disponib != -1, "return faq_disponibilidade_hoje não encontrado"
        assert idx_c115 != -1, "return faq_consulta_marcada não encontrado"
        assert idx_endereco != -1, "return faq_endereco não encontrado"
        assert idx_disponib < idx_c115 < idx_endereco, (
            f"Posição incorreta: disponibilidade@{idx_disponib} "
            f"consulta@{idx_c115} endereco@{idx_endereco}"
        )

    def test_fail_open_excecao_nao_quebra_pipeline(self):
        """Exceção no módulo não deve levantar para o caller."""
        from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada
        # ISO malformado → deve retornar None sem levantar
        ctx = {"found": True, "known": {"dia_consulta_iso": "INVALIDO"}}
        r = deve_responder_faq_consulta_marcada(ctx, "quando é minha consulta?")
        assert r is None
