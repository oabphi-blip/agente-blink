"""Pytest Bug C-69 — não-reconhecimento de unidade já informada.

Origem: Fábio 22/07/2026, leads 24335424 (Asa Norte) e 24334906 (Bárbara).
A paciente informou a unidade e a Lia perguntou a unidade de NOVO no mesmo
turno, porque known["unidade"] só era populado (via campo Kommo) no turno
seguinte. Fix: fundir o dado do inbound em known antes dos geradores
determinísticos + filtro anti-repergunta.
"""
from voice_agent.responder import (
    _extrair_unidade_do_inbound,
    _extrair_convenio_do_inbound,
    _enriquecer_known_com_inbound,
    _texto_repergunta_unidade,
    _scrub_prohibited,
)


class TestExtracaoInbound:
    def test_asa_norte(self):
        assert _extrair_unidade_do_inbound("pode ser asa norte") == "Asa Norte"

    def test_aguas_claras_com_acento(self):
        assert _extrair_unidade_do_inbound("Águas Claras") == "Águas Claras"

    def test_aguas_claras_sem_acento(self):
        assert _extrair_unidade_do_inbound("aguas claras mesmo") == "Águas Claras"

    def test_asa_sul(self):
        assert _extrair_unidade_do_inbound("prefiro asa sul") == "Asa Sul"

    def test_sem_unidade(self):
        assert _extrair_unidade_do_inbound("bom dia") is None

    def test_vazio(self):
        assert _extrair_unidade_do_inbound("") is None
        assert _extrair_unidade_do_inbound(None) is None

    def test_convenio_particular(self):
        assert _extrair_convenio_do_inbound("vai ser particular") == "Sem Convênio"

    def test_convenio_sem_convenio(self):
        assert _extrair_convenio_do_inbound("é sem convênio") == "Sem Convênio"

    def test_convenio_ausente(self):
        assert _extrair_convenio_do_inbound("tenho amil") is None


class TestEnriquecimentoKnown:
    def test_funde_unidade_do_inbound(self):
        ctx = {"inbound_text": "asa norte", "known": {}}
        _enriquecer_known_com_inbound(ctx)
        assert ctx["known"]["unidade"] == "Asa Norte"

    def test_nao_sobrescreve_known_existente(self):
        ctx = {"inbound_text": "aguas claras", "known": {"unidade": "Asa Norte"}}
        _enriquecer_known_com_inbound(ctx)
        assert ctx["known"]["unidade"] == "Asa Norte"

    def test_known_ausente_nao_quebra(self):
        ctx = {"inbound_text": "asa norte"}
        _enriquecer_known_com_inbound(ctx)
        assert ctx["known"]["unidade"] == "Asa Norte"

    def test_usa_user_text_como_fallback(self):
        ctx = {"user_text": "águas claras", "known": {}}
        _enriquecer_known_com_inbound(ctx)
        assert ctx["known"]["unidade"] == "Águas Claras"

    def test_ctx_none_nao_quebra(self):
        _enriquecer_known_com_inbound(None)  # não deve levantar


class TestFiltroC69:
    def test_repergunta_unidade_detectada(self):
        assert _texto_repergunta_unidade(
            "Anotado. Qual unidade fica melhor pra vocês — Asa Norte ou Águas Claras?"
        )

    def test_texto_normal_nao_dispara(self):
        assert not _texto_repergunta_unidade("Vou verificar os horários disponíveis.")

    def test_scrub_bloqueia_repergunta_e_avanca(self):
        # Paciente disse "Asa Norte"; Lia (erroneamente) reperguntou a unidade.
        ctx = {
            "inbound_text": "asa norte",
            "known": {"nome_contato": "Bárbara"},
        }
        texto_lia = (
            "Anotado. Qual unidade fica melhor pra vocês — "
            "Asa Norte ou Águas Claras?"
        )
        out = _scrub_prohibited(texto_lia, ctx)
        # Não pode continuar perguntando a unidade
        assert "qual unidade" not in out.lower()
        # E o known deve ter sido enriquecido com o que a paciente disse
        assert ctx["known"].get("unidade") == "Asa Norte"

    def test_scrub_preserva_pergunta_quando_unidade_desconhecida(self):
        # Sem inbound de unidade → a pergunta de unidade é legítima, mantém.
        ctx = {"inbound_text": "oi, quero marcar", "known": {}}
        texto_lia = "Qual unidade fica melhor — Asa Norte ou Águas Claras?"
        out = _scrub_prohibited(texto_lia, ctx)
        assert "unidade" in out.lower()
