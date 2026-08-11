"""
Bug C-19 (Fábio 10/06/2026) — Filtro SEMPRE-ON contra fallback "equipe contata".

Origem: Medware HTTP 503 desde 16h BRT. Lia ficou em loop "vou consultar" →
caiu em "nossa equipe entra em contato em breve". Padrão Juliene.

Leads reais afetados hoje:
  - 24129390 Julia/Lucas (5 meses, TST Saúde — convênio aceito): Lia disse
    "Vou anotar sua preferência por 11h... nossa equipe entra em contato."
  - 24129498 Sarah Cordeiro Barros: "agenda não retorna... equipe entrará."

Fix: filtro `_viola_fallback_equipe_contata` SEMPRE-ON (independe de
FILTROS_LEGACY). Substitui pela frase honesta: "deixa eu reconsultar,
volto em 1 minuto."
"""

import pytest

from voice_agent.responder import (
    _viola_fallback_equipe_contata,
    _gerar_resposta_honesta_medware_down,
    _scrub_prohibited,
)


# -----------------------------------------------------------------------------
# Casos reais que dispararam o bug hoje
# -----------------------------------------------------------------------------

class TestCasosReaisHoje:
    def test_julia_lucas_lead_24129390(self):
        """Caso real Julia 21:16 BRT — 'equipe entra em contato em breve'."""
        text = (
            "Perfeito! a agenda está com uma lentidão técnica neste momento "
            "e não consigo trazer os horários exatos para você agora. "
            "Vou anotar sua preferência por 11h na Asa Norte com a Dra. Karla "
            "Delalíbera e nossa equipe entra em contato em breve com os "
            "horários disponíveis. Pode ser?"
        )
        assert _viola_fallback_equipe_contata(text) is True

    def test_sarah_lead_24129498(self):
        """Caso real Sarah 19:08 BRT — 'equipe entrará em contato'."""
        text = (
            "Ótimo saber que Sarah estará de férias! Isso facilita bastante. "
            "no momento a agenda do sistema não está retornando os horários "
            "específicos da próxima semana. Deixa eu fazer uma coisa — vou "
            "anotar sua preferência (segunda-feira de manhã, período do meio) "
            "e nossa equipe entrará em contato com você para confirmar os "
            "horários disponíveis e encontrar o melhor encaixe para as férias."
        )
        assert _viola_fallback_equipe_contata(text) is True


# -----------------------------------------------------------------------------
# Variações que devem ser detectadas
# -----------------------------------------------------------------------------

class TestVariacoesDetectadas:
    @pytest.mark.parametrize("frase", [
        "nossa equipe vai entrar em contato",
        "nossa equipe vai te avisar",
        "nossa equipe retorna em breve",
        "nossa equipe consulta a agenda",
        "vou anotar sua preferência e nossa equipe entra em contato",
        "vamos anotar e a equipe humano retorna",
        "vou passar pra nossa equipe consultar",
        "vou te passar pra um atendente humano",
        "retorno em contato em horário comercial",
        "voltarei em contato amanhã pela manhã",
    ])
    def test_padrao_detectado(self, frase):
        assert _viola_fallback_equipe_contata(frase) is True


# -----------------------------------------------------------------------------
# Falsos positivos que NÃO devem disparar
# -----------------------------------------------------------------------------

class TestNaoDisparaNaConversaNormal:
    @pytest.mark.parametrize("frase", [
        "Combinado, vou consultar a agenda e te retorno em 1 minuto.",
        "Posso te oferecer 2 horários esta semana?",
        "Deixa eu confirmar isso pra você.",
        "A Dra. Karla atende segundas, quartas e sextas.",
        "Sua consulta está agendada pra quinta às 10h.",
        "Vou registrar seus dados no sistema.",
        "Volto em 1 minuto com os horários reais.",
    ])
    def test_nao_dispara(self, frase):
        assert _viola_fallback_equipe_contata(frase) is False


# -----------------------------------------------------------------------------
# Substituição via _scrub_prohibited
# -----------------------------------------------------------------------------

class TestScrubSubstitui:
    def test_julia_substituido_pela_frase_honesta(self):
        ctx = {"known": {"nome_contato": "Julia"}}
        text_lia = (
            "Vou anotar sua preferência por 11h e nossa equipe entra em contato em breve."
        )
        out = _scrub_prohibited(text_lia, ctx)
        assert out != text_lia  # foi substituído
        assert "reconsultar" in out.lower() or "1 minuto" in out.lower()
        assert "equipe entra" not in out.lower()
        assert "Julia" in out  # preserva saudação

    def test_sem_nome_substitui_sem_quebrar(self):
        text_lia = "Nossa equipe vai entrar em contato com você em breve."
        out = _scrub_prohibited(text_lia, {})
        assert "equipe" not in out.lower() or "reconsultar" in out.lower()


# -----------------------------------------------------------------------------
# Gerador da frase honesta
# -----------------------------------------------------------------------------

class TestGeradorRespostaHonesta:
    def test_com_nome_inclui_saudacao(self):
        out = _gerar_resposta_honesta_medware_down({"known": {"nome_contato": "Julia Pereira"}})
        assert out.startswith("Julia, ")
        assert "reconsultar" in out.lower()
        assert "1 minuto" in out.lower() or "1 min" in out.lower()

    def test_sem_ctx_nao_quebra(self):
        out = _gerar_resposta_honesta_medware_down(None)
        assert "reconsultar" in out.lower()
        assert len(out) > 20
