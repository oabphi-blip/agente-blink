"""
Bug C-22 (Fábio 10/06/2026) — Lia ignora pergunta sobre convênio NÃO aceito.

Origem: lead 24130752 Sandra. Perguntou sobre GDF Saúde, Lia simplesmente
pulou pra "vamos marcar com Dra. Karla, me passa nome e data nascimento".

Diferença vs C-16:
  C-16: paciente menciona, Lia AFIRMA que atende (errado positivo).
  C-22: paciente PERGUNTA, Lia IGNORA (errado por omissão).
"""

import pytest

from voice_agent.responder import (
    _viola_omitiu_resposta_convenio_nao_aceito,
    _scrub_prohibited,
)


# -----------------------------------------------------------------------------
# Caso real Sandra GDF
# -----------------------------------------------------------------------------

class TestCasoSandraGDF:
    def test_sandra_perguntou_gdf_lia_ignorou_eh_bug(self):
        """Caso exato Sandra: perguntou GDF, Lia pulou pra 'vamos marcar'."""
        ctx = {
            "user_text": "Olá! Vocês atendem GDF Saúde?",
            "known": {"nome_contato": "Sandra"},
        }
        # Resposta da Lia que IGNOROU a pergunta
        text_lia = (
            "Ótimo! Então a consulta é com a Dra. Karla Delalíbera, certo? "
            "Para eu registrar tudo direito no sistema, me passa alguns dados: "
            "1. Nome completo de quem vai ser atendido(a) "
            "2. Data de nascimento (dia/mês/ano) "
            "Depois a gente segue com o agendamento!"
        )
        result = _viola_omitiu_resposta_convenio_nao_aceito(text_lia, ctx)
        assert result is not None
        assert "gdf" in result.lower()

    def test_sandra_caso_completo_scrub_substitui(self):
        """O scrub_prohibited deve substituir pela resposta canônica."""
        ctx = {
            "user_text": "vocês atendem GDF?",
            "known": {"nome_contato": "Sandra"},
        }
        text_lia = (
            "Ótimo! Vamos marcar com a Dra. Karla. Me passa nome e data de nascimento."
        )
        substituto = _scrub_prohibited(text_lia, ctx)
        assert substituto != text_lia  # foi substituído
        assert "credenc" in substituto.lower()
        # Tem 2 opções
        assert "1️⃣" in substituto
        assert "2️⃣" in substituto


# -----------------------------------------------------------------------------
# Não deve disparar quando Lia respondeu corretamente
# -----------------------------------------------------------------------------

class TestNaoDisparaQuandoLiaRespondeuCerto:
    @pytest.mark.parametrize("frase_lia", [
        "Sandra, o GDF Saúde não está credenciado na nossa rede.",
        "Não somos credenciados ao GDF, mas temos condições especiais sem convênio.",
        "Infelizmente não atendemos GDF. Mas oferecemos atendimento particular com incentivo.",
        "Não cobrimos GDF. Posso te apresentar nossas condições sem convênio?",
        "Como o GDF não está coberto pelo nosso atendimento, te ofereço seguir como particular com desconto.",
        "Temos opção de seguir sem convênio com valor diferenciado.",
        "Para planos que não cobrimos, temos um incentivo especial.",
    ])
    def test_resposta_correta_nao_dispara(self, frase_lia):
        ctx = {"user_text": "atendem GDF?"}
        assert _viola_omitiu_resposta_convenio_nao_aceito(frase_lia, ctx) is None


# -----------------------------------------------------------------------------
# Detecta variantes de convênios não aceitos
# -----------------------------------------------------------------------------

class TestVariantesConvenios:
    @pytest.mark.parametrize("pergunta_user", [
        "atendem GDF?",
        "vocês cobrem INAS?",
        "tenho Cassi, dá pra usar?",
        "Bradesco Saúde tá no rol?",
        "tenho SulAmérica, posso agendar?",
        "Amil é aceito?",
        "Unimed é credenciada?",
    ])
    def test_detecta_pergunta_sobre_convenios_nao_aceitos(self, pergunta_user):
        ctx = {"user_text": pergunta_user}
        # Resposta da Lia que ignora completamente
        text = "Ótimo! Vamos marcar. Me passa seu nome e data de nascimento."
        result = _viola_omitiu_resposta_convenio_nao_aceito(text, ctx)
        assert result is not None, f"Não detectou em: {pergunta_user!r}"


# -----------------------------------------------------------------------------
# Não dispara quando user_text não menciona convênio
# -----------------------------------------------------------------------------

class TestNaoDisparaQuandoUserSemConvenio:
    @pytest.mark.parametrize("user_text", [
        "Quero marcar consulta",
        "Quanto custa a consulta da Dra. Karla?",
        "Estou com olho vermelho",
        "Preciso de avaliação pra criança",
        "",
    ])
    def test_user_sem_convenio_nao_dispara(self, user_text):
        ctx = {"user_text": user_text}
        text = "Vamos marcar. Qual seu nome?"
        assert _viola_omitiu_resposta_convenio_nao_aceito(text, ctx) is None


# -----------------------------------------------------------------------------
# Edge: ctx vazio
# -----------------------------------------------------------------------------

def test_ctx_vazio_nao_quebra():
    assert _viola_omitiu_resposta_convenio_nao_aceito("Olá!", None) is None
    assert _viola_omitiu_resposta_convenio_nao_aceito("Olá!", {}) is None


# -----------------------------------------------------------------------------
# Histórico no ctx (sem user_text direto)
# -----------------------------------------------------------------------------

def test_history_no_ctx_funciona():
    """Quando user_text não está direto, mas tem no histórico recente."""
    ctx = {
        "history": [
            {"role": "user", "content": "olá"},
            {"role": "assistant", "content": "Olá! Como posso ajudar?"},
            {"role": "user", "content": "vocês atendem GDF?"},
        ],
    }
    text = "Ótimo! Me passa nome e data de nascimento."
    result = _viola_omitiu_resposta_convenio_nao_aceito(text, ctx)
    assert result is not None
