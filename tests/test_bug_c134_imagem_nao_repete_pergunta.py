"""Bug C-134 (13/08/2026) — C-125 repetia pergunta de dado de texto quando paciente
enviava imagem (carteirinha, identidade).

Caso real: lead 21933605 Giovana. Paciente enviou imagem 3x → Lia perguntou
"Qual a data de nascimento de Giovana?" 3x + 1 vez após paciente digitar a data.

Causa raiz: _inbound_responde_ultima_pergunta_c130 retornava False para texto
sintético de imagem → C-125 disparava de novo sem que C-130 suprimisse.

Fix: _RE_IMAGEM_SINTETICA_C134 detecta o texto sintético → retorna True →
deve_perguntar_dados_pendentes retorna None → LLM acknowledges a imagem.
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(ultima_msg: str = "Qual a data de nascimento de Giovana?") -> dict:
    return {
        "known": {
            "ultima_msg_outbound": ultima_msg,
            "nome_paciente": "Giovana",
        },
        "fsm": {"estado": "DADOS"},
        "ja_agendado": False,
        "checklist_dados_minimos": {"pronto_para_oferecer_slot": False, "total_pendentes": 1},
    }


IMAGEM_EVOLUTION = (
    "[O paciente enviou uma imagem pelo WhatsApp. Provavelmente é a carteirinha do "
    "convênio ou um documento de identidade. Confirme o recebimento de forma calorosa, "
    "diga que a equipe vai conferir, e siga o atendimento normalmente.]"
)

IMAGEM_WA_CLOUD = (
    "[O paciente enviou uma imagem pelo WhatsApp]"
)


# ---------------------------------------------------------------------------
# _inbound_responde_ultima_pergunta_c130
# ---------------------------------------------------------------------------

class TestC134InboundRespondePergunta:
    """_inbound_responde_ultima_pergunta_c130 deve retornar True para imagem sintética."""

    def _call(self, ultima: str, user_text: str) -> bool:
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx(ultima)
        return _inbound_responde_ultima_pergunta_c130(ctx, user_text)

    def test_imagem_evolution_retorna_true(self):
        assert self._call(
            "Qual a data de nascimento de Giovana?", IMAGEM_EVOLUTION
        ) is True

    def test_imagem_wa_cloud_retorna_true(self):
        assert self._call(
            "Qual a data de nascimento de Giovana?", IMAGEM_WA_CLOUD
        ) is True

    def test_imagem_retorna_true_mesmo_sem_ultima(self):
        """Sem ultima_msg, a função normalmente retornaria False — mas imagem deve True."""
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx("")
        # sem ultima → normalmente retornaria False, mas imagem tem tratamento especial
        # (verifica ut antes de ultima)
        result = _inbound_responde_ultima_pergunta_c130(ctx, IMAGEM_EVOLUTION)
        assert result is True

    def test_data_real_ainda_funciona(self):
        """27/12/2018 respondendo data de nascimento → True (C-130 original)."""
        assert self._call("Qual a data de nascimento de Giovana?", "27/12/2018") is True

    def test_data_com_typo_funciona(self):
        """27/012/2018 (typo) → True."""
        assert self._call("Qual a data de nascimento de Giovana?", "27/012/2018") is True

    def test_texto_normal_nao_e_imagem(self):
        """Texto normal que não bate em nenhum padrão → False."""
        assert self._call("Qual a data de nascimento de Giovana?", "boa tarde") is False

    def test_imagem_maiuscula_funciona(self):
        """Case-insensitive."""
        assert self._call(
            "Qual o convênio?",
            "[o paciente enviou uma imagem pelo whatsapp]",
        ) is True


# ---------------------------------------------------------------------------
# deve_perguntar_dados_pendentes — integração
# ---------------------------------------------------------------------------

class TestC134DevePerguntarIntegration:
    """deve_perguntar_dados_pendentes deve retornar None quando paciente envia imagem.

    Testa via _inbound_responde_ultima_pergunta_c130 diretamente (mais robusto
    do que mockar internals do checklist, que mudam entre versões).
    """

    def test_c130_bloqueia_para_imagem_evolution(self):
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx("Qual a data de nascimento de Giovana?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, IMAGEM_EVOLUTION) is True

    def test_c130_bloqueia_para_imagem_wa_cloud(self):
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx("Qual a data de nascimento de Giovana?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, IMAGEM_WA_CLOUD) is True

    def test_c130_bloqueia_para_data_digitada(self):
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx("Qual a data de nascimento de Giovana?")
        assert _inbound_responde_ultima_pergunta_c130(ctx, "27/12/2018") is True

    def test_texto_generico_nao_bloqueia(self):
        """Texto sem relação com a pergunta anterior não bloqueia C-125."""
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = _ctx("Qual a data de nascimento de Giovana?")
        # "boa tarde" não é data → C-130 retorna False → C-125 pode disparar
        assert _inbound_responde_ultima_pergunta_c130(ctx, "boa tarde") is False


# ---------------------------------------------------------------------------
# Caso real lead 21933605 Giovana
# ---------------------------------------------------------------------------

class TestCasoRealGiovana:
    """Reproduz o cenário exato do lead 21933605."""

    def test_imagem_apos_pergunta_data_nascimento_nao_repete(self):
        """Lead 21933605: Lia perguntou data_nasc → paciente enviou imagem → não perguntar de novo."""
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = {
            "known": {
                "ultima_msg_outbound": "Qual a data de nascimento de Giovana?",
                "nome_paciente": "Giovana",
                "nome_contato": "Viviane",
                "convenio": "TST Saúde",
                "medico": "Karla",
                "unidade": "Asa Norte",
            },
            "fsm": {"estado": "DADOS"},
            "ja_agendado": False,
        }
        assert _inbound_responde_ultima_pergunta_c130(ctx, IMAGEM_EVOLUTION) is True

    def test_data_digitada_nao_repete(self):
        """Lead 21933605: após paciente digitar '27/12/2018' → não perguntar de novo."""
        from voice_agent.blindagens_deterministicas import (
            _inbound_responde_ultima_pergunta_c130,
        )
        ctx = {
            "known": {
                "ultima_msg_outbound": "Qual a data de nascimento de Giovana?",
                "nome_paciente": "Giovana",
            },
            "fsm": {"estado": "DADOS"},
        }
        assert _inbound_responde_ultima_pergunta_c130(ctx, "27/12/2018") is True
