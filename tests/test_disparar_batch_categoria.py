"""Blindagem dos endpoints A+C de disparo automático (tasks #213/#214).

A — /admin/disparar-batch
  - POST JSON {lead_ids: [...]} → dispara N leads → JSON consolidado

C — /admin/disparar-categoria
  - GET ?categoria=R/E/C&unidade=...&medico=... → filtra leads → dispara
  - Easypanel agenda semanal pra automação total

Cobre testes unit das HEURÍSTICAS de filtro (não chama Kommo real).
"""
import pytest


# ---------------------------------------------------------------------------
# Heurística de categoria (extraída do endpoint pra testar isoladamente)
# ---------------------------------------------------------------------------

KEYWORDS_POR_CATEGORIA = {
    "R": ["REAGENDAR", "REMARCAÇÃO", "REMARCACAO", "FALTOU", "DESMARCOU",
          "DESMARCAÇÃO", "DESMARCACAO"],
    "E": ["COM CONVÊNIO", "COM CONVENIO"],
    "C": ["SEM CONVÊNIO", "SEM CONVENIO", "PARTICULAR"],
}
EXCLUIR_KEYWORDS = ["INAS", "GDF", "CASSI", "SULAMERICA", "BRADESCO"]


def categorizar_lead(nome: str, categoria_alvo: str) -> bool:
    """Retorna True se o lead casa a categoria alvo (e não está excluído)."""
    nome_up = (nome or "").upper()
    if any(ex in nome_up for ex in EXCLUIR_KEYWORDS):
        return False
    kw = KEYWORDS_POR_CATEGORIA.get(categoria_alvo, [])
    return any(k in nome_up for k in kw)


# ---------------------------------------------------------------------------
# Casos de categorização — Categoria R (Reagendar)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome,esperado", [
    ("REAGENDAR _ aguardo documento", True),
    ("AGENDAR REMARCAÇÃO_recebido justificação", True),
    ("Faltou consulta!", True),
    ("AGENDAR PÓS DESMARCAÇÃO", True),
    ("paciente desmarcou ontem", True),
    ("AGENDAR ROTINA SEM CONVÊNIO", False),
    ("AGENDAR_ COM CONVÊNIO", False),
])
def test_categoria_R_reagendar(nome, esperado):
    assert categorizar_lead(nome, "R") is esperado


# ---------------------------------------------------------------------------
# Casos de categorização — Categoria E (Com convênio)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome,esperado", [
    ("AGENDAR_ COM CONVÊNIO", True),
    ("AGENDAR COM CONVENIO_sem resposta", True),
    ("AGENDAR_ SEM CONVÊNIO", False),
    ("REAGENDAR _ aguardo documento", False),
])
def test_categoria_E_com_convenio(nome, esperado):
    assert categorizar_lead(nome, "E") is esperado


# ---------------------------------------------------------------------------
# Casos de categorização — Categoria C (Sem convênio / Particular)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome,esperado", [
    ("AGENDAR_ SEM CONVÊNIO", True),
    ("LEAD FRIO SEM CONVENIO_19/12", True),
    ("AGENDAR ROTINA SEM CONVÊNIO", True),
    ("PARTICULAR_aguardando retorno", True),
    ("AGENDAR_ COM CONVÊNIO", False),
])
def test_categoria_C_sem_convenio(nome, esperado):
    assert categorizar_lead(nome, "C") is esperado


# ---------------------------------------------------------------------------
# Exclusões — Inas GDF, Cassi, SulAmerica, Bradesco NÃO entram em NENHUMA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome", [
    "INAS_Se não conseguir pelo convênio volta",
    "paciente deseja agendar pelo conv, GDF",
    "AGENDAR_CASSI",
    "REAGENDAR SULAMERICA",
    "REAGENDAR BRADESCO",
])
def test_excluir_convenios_nao_aceitos(nome):
    """Mesmo casando categoria R, leads com Inas/GDF/etc são excluídos."""
    assert categorizar_lead(nome, "R") is False
    assert categorizar_lead(nome, "E") is False
    assert categorizar_lead(nome, "C") is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_nome_vazio_nao_casa_nada():
    assert categorizar_lead("", "R") is False
    assert categorizar_lead(None, "R") is False


def test_nome_apenas_agendar_nao_casa_R_E_C():
    """Lead só 'AGENDAR_' sem contexto → não casa nenhuma categoria principal."""
    nome = "AGENDAR_"
    assert categorizar_lead(nome, "R") is False
    assert categorizar_lead(nome, "E") is False
    assert categorizar_lead(nome, "C") is False


def test_categoria_invalida_nao_casa():
    nome = "REAGENDAR aguardo doc"
    assert categorizar_lead(nome, "X") is False
    assert categorizar_lead(nome, "Z") is False


# ---------------------------------------------------------------------------
# Caso integrado: 4 leads top da campanha 04/06 + categorização correta
# ---------------------------------------------------------------------------

def test_caso_real_4_leads_reagendar_08_06():
    """Cenário canônico — campanha 08/06 disparada em 04/06."""
    leads = [
        # Noah 22982854 — Faltou consulta + Particular → casa R (faltou)
        {"id": 22982854, "name": "Faltou consulta!"},
        # Flávia 21710873 — REMARCAÇÃO + convênio → casa R
        {"id": 21710873, "name": "AGENDAR REMARCAÇÃO_recebido justificação"},
        # Liz 22789618 — REAGENDAR → casa R
        {"id": 22789618, "name": "REAGENDAR _ aguardo documento"},
        # GDF 22703954 — Inas excluído → NÃO casa nada
        {"id": 22703954, "name": "AGENDAR_ paciente deseja agendar pelo conv, GDF"},
    ]
    matches_R = [
        l["id"] for l in leads if categorizar_lead(l["name"], "R")
    ]
    assert 22982854 in matches_R
    assert 21710873 in matches_R
    assert 22789618 in matches_R
    assert 22703954 not in matches_R  # excluído (GDF)
