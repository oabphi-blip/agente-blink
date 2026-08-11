"""Pytest blindando Bug C-37 — Lia inventou comunicação interna.

Origem: lead 21341221 Lívia/Linielle (18/06/2026 12:41 BRT).
Paciente avisou que estava atrasada → Lia respondeu:
  "já aviso a equipe que você está chegando em breve"
  "Aviso a equipe para que a Dra. Karla saiba"
  "A equipe já está ciente do atraso"
  "A Dra. Karla fará sua consulta normalmente"

Lia NÃO tem canal pra falar com a recepção física da clínica nem com
o médico em consulta. Toda afirmação assim é invenção.
"""
from voice_agent.responder import (
    _viola_invencao_comunicacao_interna,
    _INVENCAO_COMUNICACAO_INTERNA_FALLBACK,
)


class TestFrasesProibidasCasoLivia:
    """Frases EXATAS que a Lia disse pra Linielle no lead 21341221."""

    def test_ja_aviso_a_equipe(self):
        assert _viola_invencao_comunicacao_interna(
            "Já aviso a equipe que você está chegando em breve."
        )

    def test_aviso_a_equipe_pra_dra(self):
        assert _viola_invencao_comunicacao_interna(
            "Aviso a equipe para que a Dra. Karla Delalíbera saiba."
        )

    def test_equipe_ja_esta_ciente_do_atraso(self):
        assert _viola_invencao_comunicacao_interna(
            "A equipe já está ciente do atraso."
        )

    def test_dra_fara_consulta_normalmente(self):
        assert _viola_invencao_comunicacao_interna(
            "Quando você chegar, a Dra. Karla Delalíbera fará "
            "sua consulta normalmente."
        )

    def test_dra_aguarda(self):
        assert _viola_invencao_comunicacao_interna(
            "A Dra. Karla aguarda a Livia."
        )


class TestVariantesAvisarEquipe:
    """Variantes textuais comuns que devem ser bloqueadas."""

    def test_vou_avisar_a_equipe(self):
        assert _viola_invencao_comunicacao_interna(
            "Vou avisar a equipe sobre seu atraso."
        )

    def test_estou_avisando_a_recepcao(self):
        assert _viola_invencao_comunicacao_interna(
            "Estou avisando a recepção."
        )

    def test_a_recepcao_foi_notificada(self):
        assert _viola_invencao_comunicacao_interna(
            "A recepção foi notificada."
        )

    def test_recepcao_esta_ciente(self):
        assert _viola_invencao_comunicacao_interna(
            "A recepção está ciente do seu atraso."
        )

    def test_informei_a_medica(self):
        assert _viola_invencao_comunicacao_interna(
            "Já informei a médica sobre seu atraso."
        )

    def test_vou_comunicar_internamente(self):
        assert _viola_invencao_comunicacao_interna(
            "Vou comunicar internamente o atraso."
        )

    def test_aviso_a_medica(self):
        assert _viola_invencao_comunicacao_interna(
            "Aviso a médica pra ela saber."
        )


class TestFrasesPermitidas:
    """Frases LEGÍTIMAS que NÃO devem ser bloqueadas."""

    def test_escalation_honesta_passa(self):
        assert not _viola_invencao_comunicacao_interna(
            "Entendido. Vou escalar pra equipe humana confirmar com a "
            "médica. Te aviso em poucos minutos."
        )

    def test_pergunta_ao_paciente_passa(self):
        assert not _viola_invencao_comunicacao_interna(
            "Linielle, quanto tempo você acha que vai levar pra chegar?"
        )

    def test_confirmacao_horario_passa(self):
        assert not _viola_invencao_comunicacao_interna(
            "Sua consulta está marcada pra quinta-feira, 18/06, às 12:00."
        )

    def test_endereco_passa(self):
        assert not _viola_invencao_comunicacao_interna(
            "Endereço de Águas Claras: R. 36 Norte, Felicittá Shopping."
        )

    def test_oferta_slot_passa(self):
        assert not _viola_invencao_comunicacao_interna(
            "Tenho 2 horários: quinta às 14:30 ou sexta às 09:00."
        )


class TestFallback:
    def test_fallback_eh_escalation_honesta(self):
        msg = _INVENCAO_COMUNICACAO_INTERNA_FALLBACK
        assert "escalar" in msg.lower()
        assert "equipe humana" in msg.lower()
        # NÃO pode prometer comunicação interna no próprio fallback
        assert not _viola_invencao_comunicacao_interna(msg)
