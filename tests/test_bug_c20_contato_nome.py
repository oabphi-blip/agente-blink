"""
Bug C-20 (Fábio 10/06/2026) — Lia pergunta nome do contato quando inválido.

Origem: batch ferias julho 10/06/2026 detectou 2 leads com nome do contato
inválido cadastrado no Kommo:
  - lead 12871624 (Wendel Teixeira Santos) → contato="Inbra" (rótulo CRM)
  - lead 20901861 (Fábio Junior Francisco Almeida) → contato vazio (fallback "Você")

Regra Fábio: PROIBIDO usar "Olá Inbra" / "Olá Você". Lia pergunta o nome do
contato em UMA frase curta antes de seguir, usa esse nome dali em diante.
"""

import pytest

from voice_agent.contato_nome import (
    PERGUNTA_PADRAO_NOME_CONTATO,
    PERGUNTA_PARA_RESPONSAVEL,
    nome_contato_invalido,
    pergunta_nome_contato,
    saudacao_segura,
)


# -----------------------------------------------------------------------------
# nome_contato_invalido
# -----------------------------------------------------------------------------

class TestNomeContatoInvalido:
    @pytest.mark.parametrize("nome", [
        None,
        "",
        " ",
        "\t\n",
        "A",            # 1 char
    ])
    def test_vazio_ou_muito_curto(self, nome):
        assert nome_contato_invalido(nome) is True

    @pytest.mark.parametrize("nome", [
        "Você", "voce", "VOCÊ", "VOCE",
        "Olá", "ola", "Oi",
        "Cliente", "Paciente", "Contato", "Usuário",
        "Responsável", "Lead",
        "Test", "Teste", "Demo", "Exemplo",
        "Inbra", "inbra", "INBRA",  # caso real lead 12871624
        "None", "null", "NaN",
    ])
    def test_fallbacks_tecnicos(self, nome):
        assert nome_contato_invalido(nome) is True

    @pytest.mark.parametrize("nome", [
        "Lia", "lia",
        "Karla", "Ariany", "Stephany",
        "Fabricio",
    ])
    def test_nomes_equipe_blink(self, nome):
        assert nome_contato_invalido(nome) is True

    @pytest.mark.parametrize("nome", [
        "12345", "999",
        "(61) 98765-4321",  # telefone como nome → só símbolos + dígitos
        "------",
        "...",
        "5561987654321",     # E.164 sem +
    ])
    def test_so_numeros_simbolos_ou_telefone(self, nome):
        assert nome_contato_invalido(nome) is True

    @pytest.mark.parametrize("nome", [
        "Carolina",
        "Carolina Souza",
        "Maria Fernanda da Silva",
        "Beatriz",
        "Sofia Ayami Veloso Yano",  # caso real lead 11979432
        "Antonio Pereira Abreu",     # caso real lead 7953316
        "Fábio",
        "Ana Laís",
    ])
    def test_nomes_validos(self, nome):
        assert nome_contato_invalido(nome) is False


# -----------------------------------------------------------------------------
# pergunta_nome_contato
# -----------------------------------------------------------------------------

class TestPerguntaNomeContato:
    def test_padrao_eh_curta_e_amigavel(self):
        q = pergunta_nome_contato()
        assert q == PERGUNTA_PADRAO_NOME_CONTATO
        assert "com quem estou falando" in q.lower()
        assert len(q) < 120  # curta

    def test_para_responsavel_difere(self):
        q = pergunta_nome_contato(contexto_paciente_menor=True)
        assert q == PERGUNTA_PARA_RESPONSAVEL
        assert "prazer" in q.lower()
        assert q != PERGUNTA_PADRAO_NOME_CONTATO

    def test_nenhuma_pergunta_usa_fallback_proibido(self):
        for q in [
            pergunta_nome_contato(),
            pergunta_nome_contato(contexto_paciente_menor=True),
        ]:
            assert "Inbra" not in q
            assert "Você?" not in q  # "Você?" como rótulo, não pronome


# -----------------------------------------------------------------------------
# saudacao_segura
# -----------------------------------------------------------------------------

class TestSaudacaoSegura:
    def test_nome_valido_usa_primeiro_nome_capitalizado(self):
        assert saudacao_segura("carolina souza") == "Olá, Carolina"
        assert saudacao_segura("CAROLINA SOUZA") == "Olá, Carolina"
        assert saudacao_segura("Sofia Ayami") == "Olá, Sofia"

    @pytest.mark.parametrize("nome_invalido", [
        None, "", "Você", "Inbra", "Test", "Cliente", "12345", "Lia",
    ])
    def test_nome_invalido_cai_no_fallback_limpo(self, nome_invalido):
        out = saudacao_segura(nome_invalido)
        assert out == "Olá"
        # GARANTIA absoluta: NUNCA "Olá Inbra" / "Olá Você"
        assert "Inbra" not in out
        assert "Você" not in out
        assert "Cliente" not in out

    def test_fallback_customizavel(self):
        assert saudacao_segura("Carolina", fallback="Bom dia") == "Bom dia, Carolina"
        assert saudacao_segura("Inbra", fallback="Bom dia") == "Bom dia"


# -----------------------------------------------------------------------------
# Cenários reais do batch ferias julho
# -----------------------------------------------------------------------------

class TestCasosReaisBatchJulho:
    """Replicar os 2 casos reais que motivaram o Bug C-20."""

    def test_lead_12871624_wendel_contato_inbra(self):
        """Lead Wendel Teixeira Santos: Kommo tinha contato="Inbra"."""
        nome_contato = "Inbra"
        assert nome_contato_invalido(nome_contato) is True
        saudacao = saudacao_segura(nome_contato)
        assert saudacao == "Olá"
        assert "Inbra" not in saudacao

    def test_lead_20901861_fabio_jr_contato_vazio(self):
        """Lead Fábio Junior: Kommo tinha contato="" (fallback "Você")."""
        nome_contato = ""
        assert nome_contato_invalido(nome_contato) is True
        saudacao = saudacao_segura(nome_contato)
        assert saudacao == "Olá"
        assert "Você" not in saudacao

    def test_lead_7953316_antonio_contato_valido(self):
        """Lead Antonio Pereira Abreu: contato OK, saudação normal."""
        nome_contato = "ANTONIO PEREIRA ABREU"
        assert nome_contato_invalido(nome_contato) is False
        saudacao = saudacao_segura(nome_contato)
        assert saudacao == "Olá, Antonio"


# -----------------------------------------------------------------------------
# Regra no _MASTER_INSTRUCTION.md
# -----------------------------------------------------------------------------

def test_master_instruction_documenta_e1_5_e_bug_c20():
    """A regra E1.5 deve estar no prompt mestre (referência direta)."""
    import pathlib
    kb = pathlib.Path(__file__).resolve().parent.parent / "voice_agent" / "knowledge_base"
    master = (kb / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    assert "E1.5" in master
    assert "Bug C-20" in master
    assert "com quem estou falando" in master.lower()
    # PROIBIDO usar saudação inválida
    assert "Olá Inbra" in master or 'Inbra' in master
    assert "Você" in master
