"""Bug Carolina Abdala Rosa 24145994 (13/06/2026 sábado).

Lia ofereceu slot inventado (17/06 08:30 Águas Claras), depois enviou
"✨ Agendamento confirmado!" com dia/hora/médica/unidade SEM ter chamado
medware.criar_agendamento. Logo após confirmação entrou em loop
"deixa eu reconsultar a agenda". Mesmo bug Carmen 24142996 e Maitê 24128026.

Fix: filtro _viola_confirmacao_sem_gravacao em responder.py detecta
texto de Conclusão de Agendamento + bloqueia se ctx.medware_grava_ok != True.
"""

import pytest

from voice_agent.responder import (
    _viola_confirmacao_sem_gravacao,
    _FRASES_CONFIRMACAO_RGX,
    _MARCADORES_CONCLUSAO_RGX,
)


class TestRegexConfirmacao:
    def test_regex_confirmacao_pega_emoji_check(self):
        assert _FRASES_CONFIRMACAO_RGX.search("✨ Agendamento confirmado!")

    def test_regex_confirmacao_pega_palavra_check(self):
        assert _FRASES_CONFIRMACAO_RGX.search("✅ agendamento finalizado")

    def test_regex_confirmacao_aceita_concluido(self):
        assert _FRASES_CONFIRMACAO_RGX.search("Agendamento concluído com sucesso")

    def test_regex_confirmacao_aceita_concluida(self):
        assert _FRASES_CONFIRMACAO_RGX.search("Agendamento concluida")

    def test_regex_confirmacao_ignora_outras_frases(self):
        assert not _FRASES_CONFIRMACAO_RGX.search("oi tudo bem")
        assert not _FRASES_CONFIRMACAO_RGX.search("vou consultar a agenda")

    def test_regex_marcadores_pega_dia_hora(self):
        assert _MARCADORES_CONCLUSAO_RGX.search("Dia/Hora: 17/06 08:30")

    def test_regex_marcadores_pega_unidade(self):
        assert _MARCADORES_CONCLUSAO_RGX.search(
            "Unidade de Atendimento: Águas Claras"
        )


class TestViolaConfirmacaoSemGravacao:
    def test_caso_real_carolina_24145994(self):
        """Texto da Lia que disparou bug."""
        text = (
            "✨ Agendamento confirmado!\n\n"
            "Agradecemos por escolher a Dra. Karla Delalíbera.\n\n"
            "Resumo do Atendimento:\n\n"
            "Dia/Hora: 17/06/2026 — terça-feira — às 08:30\n"
            "Pacientes: Carolina Abdala Rosa e Heloísa Abdala Rosa\n"
            "Médica: Dra. Karla Delalíbera\n"
            "Especialidade: Oftalmopediatria\n"
            "Motivo da Consulta: Rotina / Revisão de grau\n"
            "Convênio: Plan Assiste - MPF (MPU)\n"
            "Unidade de Atendimento: Águas Claras"
        )
        ctx = {"medware_grava_ok": False}
        assert _viola_confirmacao_sem_gravacao(text, ctx)

    def test_caso_carmen_24142996(self):
        """Texto similar do bug Carmen."""
        text = (
            "✨ Em continuidade ao atendimento!\n\n"
            "Agradecemos por escolher a médica Dra. Karla\n\n"
            "Dia/Hora: 19/06/2026 09:30\n"
            "Médica: Dra. Karla Delalibera"
        )
        ctx = {"medware_grava_ok": False}
        assert _viola_confirmacao_sem_gravacao(text, ctx)

    def test_libera_quando_gravacao_ok(self):
        text = (
            "✨ Agendamento confirmado!\n"
            "Dia/Hora: 16/06 às 10:30"
        )
        ctx = {"medware_grava_ok": True, "medware_cod_agendamento": 12345}
        assert not _viola_confirmacao_sem_gravacao(text, ctx)

    def test_bloqueia_quando_ctx_sem_flag(self):
        text = (
            "Agendamento confirmado!\n"
            "Dia/Hora: 16/06"
        )
        ctx = {}
        # sem flag = considera não-gravado = bloqueia
        assert _viola_confirmacao_sem_gravacao(text, ctx)

    def test_bloqueia_quando_ctx_none(self):
        text = (
            "Agendamento concluído!\n"
            "Unidade de Atendimento: Asa Norte"
        )
        assert _viola_confirmacao_sem_gravacao(text, None)

    def test_libera_acknowledgment_generico(self):
        # frase "confirmado" sem detalhes operacionais não é conclusão real
        text = "Ok, confirmado por aqui!"
        ctx = {"medware_grava_ok": False}
        assert not _viola_confirmacao_sem_gravacao(text, ctx)

    def test_libera_texto_vazio(self):
        assert not _viola_confirmacao_sem_gravacao("", {"medware_grava_ok": False})
        assert not _viola_confirmacao_sem_gravacao(None, {"medware_grava_ok": False})

    def test_libera_frase_de_oferta_de_agenda(self):
        # oferecer slots NÃO é confirmação
        text = (
            "Tenho 2 horários disponíveis:\n"
            "1️⃣ Terça 16/06 às 10:30\n"
            "2️⃣ Quinta 18/06 às 08:30\n"
            "Qual prefere?"
        )
        ctx = {"medware_grava_ok": False}
        assert not _viola_confirmacao_sem_gravacao(text, ctx)


class TestIntegracaoScrubProhibited:
    """Verifica que _scrub_prohibited integra o filtro novo."""

    def test_filtro_substitui_texto_quando_bloqueia(self):
        from voice_agent.responder import _scrub_prohibited, _CONFIRMACAO_FAKE_FALLBACK

        text = (
            "✨ Agendamento confirmado!\n"
            "Dia/Hora: 17/06 08:30\n"
            "Unidade de Atendimento: Águas Claras"
        )
        ctx = {"medware_grava_ok": False}
        out = _scrub_prohibited(text, ctx=ctx)
        assert out != text
        assert "deixa eu finalizar" in out.lower() or "finalizar" in out.lower()

    def test_filtro_libera_texto_quando_gravou(self):
        from voice_agent.responder import _scrub_prohibited

        text = (
            "✨ Agendamento confirmado!\n"
            "Dia/Hora: 16/06 às 10:30\n"
            "Médica: Dra. Karla\n"
            "Unidade: Águas Claras"
        )
        ctx = {"medware_grava_ok": True, "medware_cod_agendamento": 999}
        out = _scrub_prohibited(text, ctx=ctx)
        # quando gravou ok, texto NÃO deve ser substituído por esse filtro
        # (outros filtros podem ainda atuar, mas o de confirmação-fake não)
        assert "deixa eu finalizar a gravação" not in out.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
