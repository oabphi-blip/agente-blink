"""Blindagem da renomeação em massa de leads (task #227).

Atende pedido do Fábio (04/06/2026): renomear 368 leads em 2.LEADS FRIO
de forma autônoma, classificando por categoria R/E/V/C/A/X via heurística
no nome atual.
"""
import pytest

from voice_agent.renomear_leads import (
    categorizar_nome,
    limpar_nome,
    gerar_novo_nome,
)


# ---------------------------------------------------------------------------
# Categorização — casos da amostra real
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome,cat_esperada", [
    # X - excluir (convênio não aceito)
    ("INAS_Se não conseguir pelo convênio volta", "X"),
    ("paciente deseja agendar pelo conv, GDF que não autoriza", "X"),
    ("AGENDAR_CASSI", "X"),
    ("Sem reposta apos informar que nao atendemos o convenio Sulamerica", "X"),
    ("AGENDAR PARTICULAR_Bradesco", "X"),

    # R - reagendar
    ("REAGENDAR", "R"),
    ("TENTANTO REAGENDAR REMARCAÇÃO", "R"),
    ("Faltou consulta!", "R"),
    ("AGENDAR PÓS DESMARCAÇÃO", "R"),
    ("REMARCAR / C DOC", "R"),
    ("paciente desmarcou ontem", "R"),

    # E - com convênio declarado
    ("AGENDAR_ COM CONVÊNIO", "E"),
    ("AGENDAR COM CONVENIO_sem resposta", "E"),

    # V - sem resposta após valor
    ("AGENDAR_ não respondeu após valor", "V"),
    ("AGUARDANDO RETORNO da paciente", "V"),
    ("verificar valor com marido", "V"),
    ("AGUARDANDO CONCORDANCIA COM O VALOR", "V"),
    ("Paciente parou de responder após envio de valor", "V"),

    # C - sem convênio / particular
    ("AGENDAR_ SEM CONVÊNIO", "C"),
    ("AGENDAR SEM CONVENIO_apresentado valor", "C"),  # tem "sem convenio" antes de "valor"
    ("LEAD FRIO SEM CONVÊNIO_19/12", "C"),
    ("PARTICULAR_aguardando retorno", "C"),

    # A - genérico
    ("AGENDAR_", "A"),
    ("AGENDAR ROTINA", "A"),
    ("Captação 26/02", "A"),
    ("ATIVADO 24h", "A"),
])
def test_categorizacao_amostra_real(nome, cat_esperada):
    assert categorizar_nome(nome) == cat_esperada


def test_categorizacao_nome_vazio_default_A():
    assert categorizar_nome("") == "A"
    assert categorizar_nome(None) == "A"


def test_categorizacao_priorizacao_X_acima_de_outras():
    """Lead com INAS + REAGENDAR deve ser X (não R)."""
    nome = "INAS_paciente quer REAGENDAR mas convênio não aceita"
    assert categorizar_nome(nome) == "X"


# ---------------------------------------------------------------------------
# Limpeza de nome
# ---------------------------------------------------------------------------

def test_limpar_remove_prefixo_AGENDAR_():
    res = limpar_nome("AGENDAR_ paciente não respondeu")
    assert "AGENDAR_" not in res
    assert "paciente" in res


def test_limpar_substitui_underscores_por_espaco():
    res = limpar_nome("teste_com_underscores")
    assert "_" not in res
    assert "teste com underscores" == res


def test_limpar_normaliza_espacos_multiplos():
    res = limpar_nome("texto    com  muitos   espacos")
    assert "  " not in res


def test_limpar_trunca_nomes_muito_longos():
    nome = "x" * 100
    res = limpar_nome(nome, max_chars=20)
    assert len(res) <= 21  # 20 chars + elipse
    assert res.endswith("…")


def test_limpar_nome_vazio_devolve_placeholder():
    assert limpar_nome("") == ""
    assert limpar_nome("AGENDAR_") == "(sem contexto)"


# ---------------------------------------------------------------------------
# Gerar novo nome — fluxo end-to-end
# ---------------------------------------------------------------------------

def test_gerar_novo_nome_formato_correto():
    cat, novo = gerar_novo_nome("REAGENDAR")
    assert cat == "R"
    assert novo.startswith("[R] ")


def test_gerar_novo_nome_ja_padronizado_nao_duplica_prefixo():
    cat, novo = gerar_novo_nome("[E] Déborah · paciente Maria Teresa")
    assert cat == "E"
    # Não deve virar "[E] [E] Déborah..." — devolve original
    assert novo == "[E] Déborah · paciente Maria Teresa"


def test_gerar_novo_nome_amostra_real_lead_22982854():
    """Lead Noah Vieira — Faltou consulta."""
    cat, novo = gerar_novo_nome("Faltou consulta!")
    assert cat == "R"
    assert "[R]" in novo
    assert "Faltou" in novo or "consulta" in novo


def test_gerar_novo_nome_amostra_real_lead_21203181():
    """Lead Déborah — Captação 26/02 CONV 2 ESTRELAS."""
    cat, novo = gerar_novo_nome("Captação 26/02_CONV 2 ESTRELAS")
    assert cat == "A"  # Captação genérica
    assert novo.startswith("[A] ")


def test_gerar_novo_nome_amostra_real_lead_22703954():
    """Lead INAS GDF."""
    cat, novo = gerar_novo_nome(
        "AGENDAR_ paciente deseja agendar pelo conv, GDF que não autoriza no dia"
    )
    assert cat == "X"
    assert novo.startswith("[X] ")


def test_gerar_novo_nome_amostra_real_lead_22982854_padrao():
    """Antes: 'Faltou consulta!' → Depois: '[R] Faltou consulta!'"""
    cat, novo = gerar_novo_nome("Faltou consulta!")
    assert cat == "R"
    assert novo == "[R] Faltou consulta!"
