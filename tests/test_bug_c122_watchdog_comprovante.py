"""
Pytest C-122 — Watchdog comprovante Pix pós-C-114 reserva.

Cenários cobertos:
  1. Sem Redis → retorna ResultadoWatchdogComprovante vazio (fail-open)
  2. Nenhuma key c114 ativa → varridos=0
  3. Key c114 ativa < 2h → não envia (elapsed < limiar)
  4. Key c114 ativa > 2h com c116 já detectado → skip
  5. Key c114 ativa > 2h com lembrete já enviado → dedup
  6. Key c114 ativa > 2h, sem c116, sem lembrete → dry_run → enviados=1 sem WA real
  7. Key c114 ativa > 2h, sem c116, sem lembrete → not dry_run → chama wa_cloud.send_text
  8. wa_cloud retorna wamid → detalhe tem wamid
  9. wa_cloud lança exception → erros=1, lead skipped
  10. kommo retorna None para get_lead_main_contact → sem_telefone, skip
  11. kommo retorna contato sem telefone → sem_telefone, skip
  12. nome com número (inválido) → _montar_msg_lembrete usa fallback sem_nome
  13. nome correto → _montar_msg_lembrete inclui primeiro nome
  14. max_leads cap: 3 candidatos, max_leads=2 → enviados=2
  15. esta_habilitado() OFF por padrão (WATCHDOG_COMPROVANTE_ENABLED não setado)
  16. esta_habilitado() ON quando env=1
  17. _varrer_leads_pendentes lida com key bytes (decode)
  18. TTL negativo → skip (key sem TTL configurado)
  19. add_note Kommo falha → não bloqueia (enviados conta mesmo assim)
  20. Múltiplas keys, lead_id inválido na key → skip silencioso
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Stubs mínimos para importar watchdog_comprovante
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """Garante que watchdog_comprovante importa sem infra real."""
    # noop — o módulo só usa stdlib + logging
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fixture
# ─────────────────────────────────────────────────────────────────────────────
def _make_redis(keys_ttl: dict) -> MagicMock:
    """
    Cria mock Redis com scan retornando as keys fornecidas.
    keys_ttl: {key_str: ttl_residual}  (ttl < 0 = sem TTL)
    """
    redis = MagicMock()
    all_keys = [k.encode() for k in keys_ttl]
    redis.scan.side_effect = [(0, all_keys)]
    redis.ttl.side_effect = lambda k: keys_ttl.get(
        k.decode() if isinstance(k, bytes) else k, -1
    )
    redis.exists.return_value = False
    redis.setex.return_value = True
    return redis


def _make_kommo(telefone: str = "5561999990000", nome: str = "Maria Silva") -> MagicMock:
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": telefone,
        "nome": nome,
        "status_id": 102560495,
    }
    kommo.add_note.return_value = {"id": 999}
    return kommo


def _make_wa(wamid: str = "wamid.ABC123") -> MagicMock:
    wa = MagicMock()
    wa.send_text.return_value = {"messages": [{"id": wamid}]}
    return wa


_TTL_7D = 7 * 24 * 3600   # 604800 s
_TTL_AGUARDANDO = _TTL_7D

# ─────────────────────────────────────────────────────────────────────────────
# Importar sob test
# ─────────────────────────────────────────────────────────────────────────────
from voice_agent.watchdog_comprovante import (
    ResultadoWatchdogComprovante,
    _montar_msg_lembrete,
    _varrer_leads_pendentes,
    esta_habilitado,
    tick,
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Sem Redis → retorna vazio
# ─────────────────────────────────────────────────────────────────────────────
def test_sem_redis_retorna_vazio():
    res = tick(
        kommo_client=None,
        wa_cloud_client=None,
        redis_client=None,
        dry_run=True,
    )
    assert isinstance(res, ResultadoWatchdogComprovante)
    assert res.varridos == 0
    assert res.enviados == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Nenhuma key → varridos=0
# ─────────────────────────────────────────────────────────────────────────────
def test_sem_keys_varridos_zero():
    redis = MagicMock()
    redis.scan.side_effect = [(0, [])]
    res = tick(kommo_client=None, wa_cloud_client=None, redis_client=redis, dry_run=True)
    assert res.varridos == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Key < 2h → não envia
# ─────────────────────────────────────────────────────────────────────────────
def test_key_recente_menos_de_2h_nao_envia():
    # elapsed = 7d - (7d - 30min) = 30min < 2h
    ttl_residual = _TTL_AGUARDANDO - 30 * 60  # 30 min decorridos
    key = "blink:c114_aguardando_comprovante:12345"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False  # sem c116, sem lembrete

    res = tick(kommo_client=None, wa_cloud_client=None, redis_client=redis, dry_run=True)
    assert res.varridos == 0   # candidatos < limiar → não chega a lista
    assert res.enviados == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Key > 2h mas c116 ativo → skip
# ─────────────────────────────────────────────────────────────────────────────
def test_c116_detectado_skip():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600  # 3h decorridas
    key = "blink:c114_aguardando_comprovante:22222"
    redis = _make_redis({key: ttl_residual})

    def _exists_c116(k):
        k_str = k.decode() if isinstance(k, bytes) else k
        return "c116_comprovante_detectado:22222" in k_str

    redis.exists.side_effect = _exists_c116

    res = tick(kommo_client=None, wa_cloud_client=None, redis_client=redis, dry_run=True)
    assert res.varridos == 0   # filtrado dentro de _varrer
    assert res.enviados == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Lembrete já enviado → dedup
#    _varrer_leads_pendentes retorna o candidato (não filtra lembrete).
#    tick() verifica lembrete e incrementa ja_dedup.
# ─────────────────────────────────────────────────────────────────────────────
def test_lembrete_ja_enviado_dedup():
    ttl_residual = _TTL_AGUARDANDO - 4 * 3600  # 4h decorridas
    key = "blink:c114_aguardando_comprovante:33333"
    redis = _make_redis({key: ttl_residual})

    def _exists(k):
        k_str = k.decode() if isinstance(k, bytes) else k
        # c116 não existe → candidato passa pela varredura
        if "c116_comprovante_detectado" in k_str:
            return False
        # lembrete já existe → tick() detecta e conta como dedup
        if "c122_lembrete_enviado" in k_str:
            return True
        return False

    redis.exists.side_effect = _exists

    res = tick(kommo_client=None, wa_cloud_client=None, redis_client=redis, dry_run=True)
    assert res.ja_dedup == 1
    assert res.enviados == 0
    assert res.varridos == 1  # candidato foi varredido


# ─────────────────────────────────────────────────────────────────────────────
# 6. Dry run → não chama wa_cloud, conta como enviado
# ─────────────────────────────────────────────────────────────────────────────
def test_dry_run_nao_chama_wa():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:44444"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(telefone="5561999990000", nome="João Souza")
    wa = _make_wa()

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=True,
    )
    wa.send_text.assert_not_called()
    assert res.enviados == 1
    assert res.detalhes[0]["acao"] == "dry_run"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Not dry_run → chama wa_cloud.send_text
# ─────────────────────────────────────────────────────────────────────────────
def test_not_dry_run_chama_wa():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:55555"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(telefone="5561999990000", nome="Ana Lima")
    wa = _make_wa()

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=False,
        max_leads=5,
    )
    wa.send_text.assert_called_once()
    call_kwargs = wa.send_text.call_args
    # "5561999990000" já começa com "55" → não adiciona outro prefixo
    to_sent = call_kwargs[1].get("to", "") or call_kwargs[0][0] if call_kwargs[0] else ""
    assert "5561999990000" in str(call_kwargs)
    assert res.enviados == 1
    assert res.detalhes[0]["acao"] == "enviado"


# ─────────────────────────────────────────────────────────────────────────────
# 8. wa_cloud retorna wamid → detalhe tem wamid
# ─────────────────────────────────────────────────────────────────────────────
def test_wamid_no_detalhe():
    ttl_residual = _TTL_AGUARDANDO - 2 * 3600 - 60  # pouco mais de 2h
    key = "blink:c114_aguardando_comprovante:66666"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(nome="Pedro Costa")
    wa = _make_wa(wamid="wamid.XYZABC")

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=False,
    )
    assert res.enviados == 1
    assert res.detalhes[0]["wamid"] == "wamid.XYZABC"


# ─────────────────────────────────────────────────────────────────────────────
# 9. wa_cloud lança exception → erros=1
# ─────────────────────────────────────────────────────────────────────────────
def test_wa_exception_erros_um():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:77777"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(nome="Renata Andrade")
    wa = MagicMock()
    wa.send_text.side_effect = RuntimeError("timeout")

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=False,
    )
    assert res.erros == 1
    assert res.enviados == 0
    assert res.detalhes[0]["acao"] == "wa_erro"


# ─────────────────────────────────────────────────────────────────────────────
# 10. kommo retorna None → sem_telefone
# ─────────────────────────────────────────────────────────────────────────────
def test_kommo_none_contato_sem_telefone():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:88888"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = None

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=_make_wa(),
        redis_client=redis,
        dry_run=False,
    )
    assert res.enviados == 0
    assert res.detalhes[0]["acao"] == "sem_telefone"


# ─────────────────────────────────────────────────────────────────────────────
# 11. kommo retorna contato sem telefone
# ─────────────────────────────────────────────────────────────────────────────
def test_kommo_contato_telefone_vazio():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:99999"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {"telefone": None, "nome": "Vitor", "status_id": 1}

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=_make_wa(),
        redis_client=redis,
        dry_run=False,
    )
    assert res.enviados == 0
    assert res.detalhes[0]["acao"] == "sem_telefone"


# ─────────────────────────────────────────────────────────────────────────────
# 12 & 13. _montar_msg_lembrete
# ─────────────────────────────────────────────────────────────────────────────
def test_montar_msg_nome_invalido_numero():
    msg = _montar_msg_lembrete("12345")
    assert "Olá" in msg
    # não deve conter sequência numérica como saudação
    assert "12345," not in msg


def test_montar_msg_nome_valido_inclui_primeiro():
    msg = _montar_msg_lembrete("Fernanda Costa")
    assert "Fernanda" in msg


def test_montar_msg_nome_vazio():
    msg = _montar_msg_lembrete("")
    assert "Olá" in msg


def test_montar_msg_conteudo_essencial():
    msg = _montar_msg_lembrete("Thamilla")
    assert "comprovante" in msg.lower()
    assert "Pix" in msg or "pix" in msg.lower()
    assert "Thamilla" in msg


# ─────────────────────────────────────────────────────────────────────────────
# 14. max_leads cap
# ─────────────────────────────────────────────────────────────────────────────
def test_max_leads_cap():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600  # 3h decorridas
    keys_ttl = {
        "blink:c114_aguardando_comprovante:11": ttl_residual,
        "blink:c114_aguardando_comprovante:22": ttl_residual,
        "blink:c114_aguardando_comprovante:33": ttl_residual,
    }
    all_keys = [k.encode() for k in keys_ttl]
    redis = MagicMock()
    redis.scan.side_effect = [(0, all_keys)]
    redis.ttl.side_effect = lambda k: ttl_residual
    redis.exists.return_value = False
    redis.setex.return_value = True

    kommo = _make_kommo()
    wa = _make_wa()

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=True,
        max_leads=2,
    )
    assert res.enviados == 2  # cap aplicado
    assert res.varridos == 3


# ─────────────────────────────────────────────────────────────────────────────
# 15 & 16. esta_habilitado
# ─────────────────────────────────────────────────────────────────────────────
def test_habilitado_default_off():
    orig = os.environ.pop("WATCHDOG_COMPROVANTE_ENABLED", None)
    try:
        assert esta_habilitado() is False
    finally:
        if orig is not None:
            os.environ["WATCHDOG_COMPROVANTE_ENABLED"] = orig


def test_habilitado_on():
    with patch.dict(os.environ, {"WATCHDOG_COMPROVANTE_ENABLED": "1"}):
        assert esta_habilitado() is True


def test_habilitado_zero():
    with patch.dict(os.environ, {"WATCHDOG_COMPROVANTE_ENABLED": "0"}):
        assert esta_habilitado() is False


# ─────────────────────────────────────────────────────────────────────────────
# 17. _varrer_leads_pendentes com keys em bytes
# ─────────────────────────────────────────────────────────────────────────────
def test_varrer_keys_bytes():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    redis = MagicMock()
    # keys em bytes — Redis real retorna bytes
    redis.scan.side_effect = [(0, [b"blink:c114_aguardando_comprovante:55501"])]
    redis.ttl.return_value = ttl_residual
    redis.exists.return_value = False

    pendentes = _varrer_leads_pendentes(redis)
    assert len(pendentes) == 1
    assert pendentes[0]["lead_id"] == 55501


# ─────────────────────────────────────────────────────────────────────────────
# 18. TTL negativo → skip
# ─────────────────────────────────────────────────────────────────────────────
def test_ttl_negativo_skip():
    redis = MagicMock()
    redis.scan.side_effect = [(0, [b"blink:c114_aguardando_comprovante:12399"])]
    redis.ttl.return_value = -1  # sem TTL
    redis.exists.return_value = False

    pendentes = _varrer_leads_pendentes(redis)
    assert len(pendentes) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 19. add_note falha → não bloqueia envio
# ─────────────────────────────────────────────────────────────────────────────
def test_add_note_falha_nao_bloqueia():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:10001"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(nome="Carlos Braga")
    kommo.add_note.side_effect = RuntimeError("timeout kommo")

    wa = _make_wa()

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=wa,
        redis_client=redis,
        dry_run=False,
    )
    # Mesmo com add_note falhando, o envio foi feito
    assert res.enviados == 1
    assert res.erros == 0


# ─────────────────────────────────────────────────────────────────────────────
# 20. Key com lead_id inválido → skip silencioso
# ─────────────────────────────────────────────────────────────────────────────
def test_lead_id_invalido_na_key():
    redis = MagicMock()
    redis.scan.side_effect = [(0, [b"blink:c114_aguardando_comprovante:NAO_NUMERO"])]
    redis.ttl.return_value = _TTL_AGUARDANDO - 3 * 3600
    redis.exists.return_value = False

    pendentes = _varrer_leads_pendentes(redis)
    assert len(pendentes) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 21. wa_cloud_client None → sem_wa_client
# ─────────────────────────────────────────────────────────────────────────────
def test_wa_client_none_sem_wa_client():
    ttl_residual = _TTL_AGUARDANDO - 3 * 3600
    key = "blink:c114_aguardando_comprovante:20002"
    redis = _make_redis({key: ttl_residual})
    redis.exists.return_value = False

    kommo = _make_kommo(nome="Lucia Ferreira")

    res = tick(
        kommo_client=kommo,
        wa_cloud_client=None,
        redis_client=redis,
        dry_run=False,
    )
    assert res.enviados == 0
    assert res.detalhes[0]["acao"] == "sem_wa_client"


# ─────────────────────────────────────────────────────────────────────────────
# 22. Resultado as_dict tem todas as chaves
# ─────────────────────────────────────────────────────────────────────────────
def test_resultado_as_dict_completo():
    r = ResultadoWatchdogComprovante(
        varridos=5, candidatos=3, enviados=2, ja_dedup=1, erros=0,
    )
    d = r.as_dict()
    for k in ("varridos", "candidatos", "enviados", "ja_dedup", "erros", "detalhes"):
        assert k in d
