"""
Bug C-88 (05/08/2026) — Turno já respondido guard no _caller_context_block.

O IntentClassifier injeta known["turno_preferido"] e known["dia_pref"] via
_injetar_pre_slots() no pipeline, mas _caller_context_block() não os exibia
— o LLM não sabia que turno já foi respondido e ficava em loop re-perguntando
(causa raiz do loop C-84 Juliana 24413852 com 11 repetições "manhã ou tarde?").

Fix: turno_preferido e dia_pref adicionados ao rotulos dict (seção dados)
e ao bloco TRAVA MÉDICO/UNIDADE (instrução explícita de não reperguntar).
"""
import pytest
from voice_agent.responder import _caller_context_block


# ── helpers ──────────────────────────────────────────────────────────────────

def ctx_com(known: dict) -> dict:
    """Monta ctx mínimo com found=True pra entrar no branch known."""
    return {"found": True, "known": known, "agenda": []}


# ── turno_preferido aparece na seção dados ────────────────────────────────────

def test_turno_preferido_aparece_em_dados():
    ctx = ctx_com({"turno_preferido": "manhã"})
    bloco = _caller_context_block(ctx)
    assert "manhã" in bloco
    assert "RESPONDIDO" in bloco.upper() or "reperguntar" in bloco.lower()


def test_turno_tarde_aparece_em_dados():
    ctx = ctx_com({"turno_preferido": "tarde"})
    bloco = _caller_context_block(ctx)
    assert "tarde" in bloco


def test_dia_pref_aparece_em_dados():
    ctx = ctx_com({"dia_pref": "segunda"})
    bloco = _caller_context_block(ctx)
    assert "segunda" in bloco


# ── turno_preferido aparece no bloco TRAVA ───────────────────────────────────

def test_turno_preferido_aparece_na_trava():
    ctx = ctx_com({"turno_preferido": "manhã", "medico": "Karla", "unidade": "Asa Norte"})
    bloco = _caller_context_block(ctx)
    assert "TURNO JÁ RESPONDIDO" in bloco
    assert "manhã" in bloco
    assert "NÃO reperguntar" in bloco


def test_trava_instrucao_anti_loop_quando_turno_respondido():
    """O bloco deve conter aviso explícito de não reperguntar 'manhã ou tarde?'."""
    ctx = ctx_com({"turno_preferido": "tarde", "unidade": "Águas Claras"})
    bloco = _caller_context_block(ctx)
    assert "manhã ou tarde" in bloco.lower() or "reperguntar" in bloco.lower()


def test_dia_pref_aparece_na_trava():
    ctx = ctx_com({"dia_pref": "quarta", "medico": "Karla"})
    bloco = _caller_context_block(ctx)
    assert "DIA PREFERIDO" in bloco
    assert "quarta" in bloco


def test_turno_e_dia_juntos_na_trava():
    ctx = ctx_com({
        "turno_preferido": "manhã",
        "dia_pref": "segunda",
        "medico": "Dra. Karla Delalíbera",
        "unidade": "Asa Norte",
    })
    bloco = _caller_context_block(ctx)
    assert "TURNO JÁ RESPONDIDO" in bloco
    assert "manhã" in bloco
    assert "DIA PREFERIDO" in bloco
    assert "segunda" in bloco


# ── trava aparece mesmo SEM medico/unidade ───────────────────────────────────

def test_trava_aparece_so_com_turno_sem_medico():
    """Antes do fix a trava só aparecia se known.medico ou known.unidade.
    Com C-88 deve aparecer mesmo com só turno_preferido."""
    ctx = ctx_com({"turno_preferido": "manhã"})
    bloco = _caller_context_block(ctx)
    # trava deve estar presente
    assert "TURNO JÁ RESPONDIDO" in bloco or "RESPONDIDO" in bloco


def test_trava_aparece_so_com_dia_sem_medico():
    ctx = ctx_com({"dia_pref": "quinta"})
    bloco = _caller_context_block(ctx)
    assert "DIA PREFERIDO" in bloco or "quinta" in bloco


# ── sem turno/dia_pref → NÃO polui o bloco ───────────────────────────────────

def test_sem_turno_preferido_nao_aparece_turno_respondido():
    """'TURNO JÁ RESPONDIDO:' (com dois-pontos e valor) não deve aparecer
    quando known não tem turno_preferido. Nota: o texto da instrução
    'Se TURNO JÁ RESPONDIDO estiver acima' pode aparecer mesmo sem valor."""
    ctx = ctx_com({"medico": "Karla", "unidade": "Asa Norte"})
    bloco = _caller_context_block(ctx)
    # O VALUE pattern "TURNO JÁ RESPONDIDO: **X**" só aparece quando há valor
    assert "TURNO JÁ RESPONDIDO: **" not in bloco


def test_sem_dia_pref_nao_aparece_dia_preferido():
    ctx = ctx_com({"medico": "Karla"})
    bloco = _caller_context_block(ctx)
    assert "DIA PREFERIDO" not in bloco


def test_known_vazio_nao_aparece_turno():
    ctx = ctx_com({})
    bloco = _caller_context_block(ctx)
    assert "TURNO JÁ RESPONDIDO" not in bloco
    assert "DIA PREFERIDO" not in bloco


# ── dia_turno (campo Kommo) ainda funciona ───────────────────────────────────

def test_dia_turno_kommo_ainda_aparece():
    """Regressão: campo Kommo dia_turno ainda deve aparecer normalmente."""
    ctx = ctx_com({"medico": "Karla", "dia_turno": "Terça-feira — manhã"})
    bloco = _caller_context_block(ctx)
    assert "Terça-feira" in bloco
    assert "manhã" in bloco


# ── ctx=None fail-open ───────────────────────────────────────────────────────

def test_ctx_none_nao_quebra():
    bloco = _caller_context_block(None)
    assert isinstance(bloco, str)
    assert len(bloco) > 0


# ── ctx.found=False → CONTATO NOVO (sem trava) ───────────────────────────────

def test_contato_novo_sem_trava():
    ctx = {"found": False, "known": {"turno_preferido": "manhã"}, "agenda": []}
    bloco = _caller_context_block(ctx)
    # contato novo não deve ter TRAVA
    assert "CONTATO NOVO" in bloco
    assert "TURNO JÁ RESPONDIDO" not in bloco
