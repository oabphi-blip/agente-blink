"""
Bug C-54 (13/07/2026) — Ubirata/Lucas 24185000.

Pai pediu pra remarcar (virose do Lucas), disse "quinta ou sexta". Lia
gravou preferência 'quinta ou sexta na Asa Norte'. Impossível: quinta
em Asa Norte é impossível (Karla está em Águas Claras nesse dia).

Filtro C-31b anterior só detectava mismatch quando texto tinha data
numérica DD/MM. Aqui a Lia só usou dia-da-semana sem data. Novo filtro
_viola_dia_sem_data_incompativel_unidade fecha o gap: usa a MESMA tabela
do calendar_atendimento.json (fonte única) e valida dia-da-semana isolado
contra ctx.medico + ctx.unidade.
"""

from __future__ import annotations

from voice_agent.responder import (
    _viola_dia_sem_data_incompativel_unidade,
)


# ---------- Casos que DEVEM bloquear ----------

def test_ubirata_so_quinta_asa_norte_bloqueia_duro():
    """Só quinta em Asa Norte é impossível."""
    texto = "Combinado! Vou reservar quinta na Asa Norte com a Dra. Karla."
    ctx = {"known": {"medico": "Karla Delalibera", "unidade": "Asa Norte"}}
    resultado = _viola_dia_sem_data_incompativel_unidade(texto, ctx)
    assert resultado is not None
    dia, medico, unidade = resultado
    assert dia == "quinta"
    assert medico == "karla"


def test_terca_asa_norte_bloqueia():
    texto = "Terça na Asa Norte com a Dra. Karla."
    ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is not None


def test_segunda_aguas_claras_bloqueia():
    texto = "Segunda em Águas Claras com a Karla Delalibera."
    ctx = {"known": {"medico": "Karla", "unidade": "Águas Claras"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is not None


def test_sabado_qualquer_unidade_bloqueia():
    texto = "Sábado com a Dra. Karla."
    for unidade in ("Asa Norte", "Águas Claras"):
        ctx = {"known": {"medico": "Karla", "unidade": unidade}}
        r = _viola_dia_sem_data_incompativel_unidade(texto, ctx)
        assert r is not None, f"Sábado deve bloquear em {unidade}"


# ---------- Casos que NÃO devem bloquear ----------

def test_sexta_asa_norte_ok():
    """Sexta é dia válido em Asa Norte (Karla atende seg/qua/sex)."""
    texto = "Sexta com a Dra. Karla em Asa Norte fica bom?"
    ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_quinta_aguas_claras_ok():
    texto = "Quinta em Águas Claras com a Dra. Karla."
    ctx = {"known": {"medico": "Karla", "unidade": "Águas Claras"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_multiplos_dias_pelo_menos_um_valido():
    """Se algum dia mencionado bate, filtro NÃO bloqueia (paciente
    ainda tem opção — Lia deve ofertar o dia certo, mas isso é
    trabalho de outro loop)."""
    texto = "Quinta ou sexta com a Dra. Karla em Asa Norte."
    ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
    # Sexta é válido → filtro passa (deixa a Lia responder, ela
    # deve ofertar só sexta ou perguntar sobre AC pra quinta)
    resultado = _viola_dia_sem_data_incompativel_unidade(texto, ctx)
    # Como sexta é ok em AN, retorna None (política menos restritiva)
    assert resultado is None


def test_texto_com_data_numerica_deixa_c31b_tratar():
    """Se texto tem DD/MM, filtro C-54 não age — deixa C-31b tratar."""
    texto = "Quinta-feira (16/07) às 10h na Asa Norte."
    ctx = {"known": {"medico": "Karla", "unidade": "Asa Norte"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_sem_medico_no_ctx_nao_bloqueia():
    texto = "Quinta na Asa Norte."
    ctx = {"known": {"unidade": "Asa Norte"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_sem_unidade_no_ctx_nao_bloqueia():
    texto = "Quinta com a Dra. Karla."
    ctx = {"known": {"medico": "Karla"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_medico_desconhecido_nao_bloqueia():
    texto = "Quinta em Asa Norte com Dr. Fulano."
    ctx = {"known": {"medico": "Dr. Fulano", "unidade": "Asa Norte"}}
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None


def test_katia_pausa_nao_bloqueia():
    """Kátia está em pausa — não bloqueia (deixa outro filtro tratar)."""
    texto = "Quinta com a Dra. Kátia em Asa Norte."
    ctx = {"known": {"medico": "Katia", "unidade": "Asa Norte"}}
    # Kátia tem set() vazio → not permitidos → filtro pula
    assert _viola_dia_sem_data_incompativel_unidade(texto, ctx) is None
