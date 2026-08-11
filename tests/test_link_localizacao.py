"""Pytest — _append_link_localizacao (Fábio 27/07/2026).

Regra: sempre que unidade for definida no ctx, appenda o link Maps da unidade
na resposta — 1x por lead (dedup Redis 24h).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

MAPS_ASA_NORTE = "https://maps.app.goo.gl/jPfjSsXA1bHhsyw56"
MAPS_AGUAS_CLARAS = "https://maps.app.goo.gl/FRbkUtg4U4xG55q18"


def _import_fn():
    from voice_agent.responder import _append_link_localizacao
    return _append_link_localizacao


def _ctx(unidade: str, lead_id: int = 99999) -> dict:
    return {"known": {"unidade": unidade}, "lead_id": lead_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_redis_fresh():
    """Redis client sem dedup ativo (exists → False)."""
    r = MagicMock()
    r.exists.return_value = False
    return r


def _mock_redis_seen():
    """Redis client com dedup ativo (exists → True)."""
    r = MagicMock()
    r.exists.return_value = True
    return r


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_asa_norte_appenda_link():
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Temos horário disponível!", _ctx("Asa Norte"))
    assert MAPS_ASA_NORTE in result
    assert "📍 Localização — Asa Norte" in result


def test_aguas_claras_appenda_link():
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Ótimo!", _ctx("Águas Claras"))
    assert MAPS_AGUAS_CLARAS in result
    assert "📍 Localização — Águas Claras" in result


def test_aguas_claras_sem_acento():
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Ótimo!", _ctx("aguas claras"))
    assert MAPS_AGUAS_CLARAS in result


def test_dedup_redis_nao_repete():
    """Quando Redis já marcou lead como enviado, NÃO appenda novamente."""
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_seen()):
        result = fn("Temos horário!", _ctx("Asa Norte"))
    assert MAPS_ASA_NORTE not in result
    assert result == "Temos horário!"


def test_sem_unidade_nao_appenda():
    fn = _import_fn()
    ctx = {"known": {}, "lead_id": 123}
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Olá!", ctx)
    assert result == "Olá!"
    assert "📍" not in result


def test_sem_lead_id_nao_appenda():
    fn = _import_fn()
    ctx = {"known": {"unidade": "Asa Norte"}}  # sem lead_id
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Olá!", ctx)
    assert MAPS_ASA_NORTE not in result


def test_ctx_none_nao_quebra():
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Texto qualquer.", None)
    assert result == "Texto qualquer."


def test_unidade_desconhecida_nao_appenda():
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_fresh()):
        result = fn("Texto.", _ctx("Taguatinga"))
    assert "📍" not in result


def test_redis_exception_nao_quebra():
    """Se Redis falhar, função não levanta exceção — apenas não appenda dedup."""
    fn = _import_fn()
    with patch("voice_agent.redis_client.get_redis", side_effect=Exception("conn refused")):
        # Deve retornar sem levantar
        result = fn("Texto.", _ctx("Asa Norte"))
    # Sem Redis, dedup não funciona — mas pode ou não ter appendado o link
    # O importante é NÃO quebrar
    assert isinstance(result, str)


def test_redis_setex_chamado_com_ttl_24h():
    """Valida que dedup é setado com TTL de 24h (86400s)."""
    fn = _import_fn()
    mock_r = _mock_redis_fresh()
    with patch("voice_agent.redis_client.get_redis", return_value=mock_r):
        fn("Texto.", _ctx("Asa Norte", lead_id=42))
    mock_r.setex.assert_called_once_with("blink:link_loc_enviado:42", 86400, "1")


def test_link_nao_duplicado_na_mesma_resposta():
    """Mesmo que texto já contenha o link, não appenda segundo bloco."""
    fn = _import_fn()
    texto_ja_tem_link = f"Ótimo!\n\n📍 Localização — Asa Norte: {MAPS_ASA_NORTE}"
    with patch("voice_agent.redis_client.get_redis", return_value=_mock_redis_seen()):
        result = fn(texto_ja_tem_link, _ctx("Asa Norte"))
    # dedup Redis ativo → não appenda
    assert result.count(MAPS_ASA_NORTE) == 1
