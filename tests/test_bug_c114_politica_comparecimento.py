"""
Pytest — Bug C-114: Política de comparecimento — sinal 50% pós-conclusão de agendamento.

Cobre:
  - Detecção de confirmação de dados: "sim", "correto", "dados corretos", "1. Tudo Correto"
  - Apenas para PARTICULAR (Não se aplica / "")
  - Convênio ativo (Saúde Caixa) → não dispara
  - Última outbound deve ser conclusão de agendamento
  - Mensagem contém chave Pix correta por unidade
  - Asa Norte → e-mail; Águas Claras → CNPJ
  - Valores: Karla APV R$400, Karla outros R$305,50, Fabrício catarata R$222,50
  - Redis flag impede repetição (TTL 24h)
  - Toggle OFF → None
  - ctx=None → None
  - user_text vazio → None
  - Posição na chain: depois de endereco_pos_agenda
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    convenio: str = "Não se aplica",
    unidade: str = "Asa Norte",
    medico: str = "Dra. Karla Delalíbera",
    especialidade: str = "Oftalmopediatria",
    ultima_msg: str = "✅ Agendamento confirmado! 14/08/2026 às 09:30",
    ja_agendado: bool = False,
    lead_id: int = 9901,
) -> dict:
    return {
        "lead_id": lead_id,
        "ja_agendado": ja_agendado,
        "known": {
            "convenio": convenio,
            "unidade": unidade,
            "medico": medico,
            "especialidade": especialidade,
            "ultima_msg_outbound": ultima_msg,
        },
    }


def _ctx_convenio(convenio: str, ultima_msg: str = "✅ Agendamento confirmado! 14/08/2026 às 09:30") -> dict:
    return _ctx(convenio=convenio, ultima_msg=ultima_msg)


def _redis_sem_flag():
    r = MagicMock()
    r.get.return_value = None
    return r


def _redis_com_flag():
    r = MagicMock()
    r.get.return_value = b"1"
    return r


def _solicitar(ctx, user_text="sim dados corretos", redis=None):
    from voice_agent.politica_comparecimento import deve_solicitar_sinal_particular
    return deve_solicitar_sinal_particular(ctx, user_text, redis)


# ---------------------------------------------------------------------------
# 1. Detecção de confirmação de dados
# ---------------------------------------------------------------------------

class TestDeteccaoConfirmacao:
    def test_sim_dispara(self):
        assert _solicitar(_ctx(), "sim") is not None

    def test_dados_corretos_dispara(self):
        assert _solicitar(_ctx(), "dados corretos") is not None

    def test_sim_dados_corretos_dispara(self):
        assert _solicitar(_ctx(), "sim dados corretos") is not None

    def test_confirmo_dispara(self):
        assert _solicitar(_ctx(), "confirmo") is not None

    def test_tudo_certo_dispara(self):
        assert _solicitar(_ctx(), "tudo certo") is not None

    def test_ta_certo_dispara(self):
        assert _solicitar(_ctx(), "tá certo") is not None

    def test_botao_salesbot_dispara(self):
        """'1. Tudo Correto' é o botão do Salesbot de confirmação."""
        assert _solicitar(_ctx(), "1. Tudo Correto") is not None

    def test_ok_dispara(self):
        assert _solicitar(_ctx(), "ok") is not None

    def test_perfeito_dispara(self):
        assert _solicitar(_ctx(), "perfeito") is not None

    def test_emoji_thumbsup_dispara(self):
        assert _solicitar(_ctx(), "👍") is not None

    def test_emoji_check_dispara(self):
        assert _solicitar(_ctx(), "✅") is not None

    def test_texto_aleatorio_nao_dispara(self):
        """Texto sem confirmação não dispara."""
        assert _solicitar(_ctx(), "quando é a consulta?") is None

    def test_texto_vazio_nao_dispara(self):
        assert _solicitar(_ctx(), "") is None


# ---------------------------------------------------------------------------
# 2. Apenas para PARTICULAR
# ---------------------------------------------------------------------------

class TestApenasParticular:
    def test_sem_convenio_vazio_dispara(self):
        assert _solicitar(_ctx_convenio(""),"sim") is not None

    def test_nao_se_aplica_dispara(self):
        assert _solicitar(_ctx_convenio("Não se aplica"), "sim") is not None

    def test_nao_se_aplica_sem_acento_dispara(self):
        assert _solicitar(_ctx_convenio("nao se aplica"), "sim") is not None

    def test_saude_caixa_nao_dispara(self):
        """Convênio ativo → não solicitar sinal."""
        assert _solicitar(_ctx_convenio("Saúde Caixa"), "sim") is None

    def test_bacen_nao_dispara(self):
        assert _solicitar(_ctx_convenio("Bacen"), "sim") is None

    def test_omint_nao_dispara(self):
        assert _solicitar(_ctx_convenio("Omint"), "sim") is None

    def test_care_plus_nao_dispara(self):
        assert _solicitar(_ctx_convenio("Care Plus"), "sim") is None


# ---------------------------------------------------------------------------
# 3. Última outbound deve ser conclusão de agendamento
# ---------------------------------------------------------------------------

class TestUltimaOutboundConclusao:
    def test_msg_com_data_hora_dispara(self):
        ctx = _ctx(ultima_msg="✅ Agendamento confirmado! 14/08/2026 às 09:30")
        assert _solicitar(ctx, "sim") is not None

    def test_msg_com_template_conclusao_dispara(self):
        ctx = _ctx(ultima_msg="Agendamento confirmado! Consulta na Asa Norte")
        assert _solicitar(ctx, "sim") is not None

    def test_msg_pergunta_dados_dispara(self):
        ctx = _ctx(ultima_msg="Os dados estão corretos? Confirme para finalizar")
        assert _solicitar(ctx, "sim") is not None

    def test_ja_agendado_true_dispara(self):
        """ja_agendado=True no ctx é suficiente (última outbound foi conclusão)."""
        ctx = _ctx(ultima_msg="", ja_agendado=True)
        assert _solicitar(ctx, "sim") is not None

    def test_msg_nao_relacionada_nao_dispara(self):
        """Se última outbound não era conclusão → não solicitar sinal."""
        ctx = _ctx(ultima_msg="Qual turno funciona melhor pra você?")
        assert _solicitar(ctx, "sim") is None

    def test_msg_vazia_sem_ja_agendado_nao_dispara(self):
        ctx = _ctx(ultima_msg="", ja_agendado=False)
        assert _solicitar(ctx, "sim") is None


# ---------------------------------------------------------------------------
# 4. Chave Pix por unidade
# ---------------------------------------------------------------------------

class TestPixPorUnidade:
    def test_asa_norte_email(self):
        ctx = _ctx(unidade="Asa Norte")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "karladelaliberaoftalmo@gmail.com" in msg

    def test_aguas_claras_cnpj(self):
        ctx = _ctx(unidade="Águas Claras")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "52.303.729/0001-30" in msg

    def test_aguas_claras_sem_acento(self):
        ctx = _ctx(unidade="Aguas Claras")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "52.303.729/0001-30" in msg


# ---------------------------------------------------------------------------
# 5. Valores por médico e especialidade
# ---------------------------------------------------------------------------

class TestValoresPorMedico:
    def test_karla_apv_400(self):
        ctx = _ctx(medico="Dra. Karla Delalíbera", especialidade="APV Processamento Visual")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 400,00" in msg

    def test_karla_sdp_400(self):
        ctx = _ctx(medico="Dra. Karla Delalíbera", especialidade="SDP Síndrome postural")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 400,00" in msg

    def test_karla_oftalmopediatria_305(self):
        ctx = _ctx(medico="Dra. Karla Delalíbera", especialidade="Oftalmopediatria")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 305,50" in msg

    def test_karla_estrabismo_305(self):
        ctx = _ctx(medico="Dra. Karla Delalíbera", especialidade="Estrabismo")
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 305,50" in msg

    def test_fabricio_catarata_222(self):
        ctx = _ctx(
            medico="Dr. Fabrício Freitas",
            especialidade="Avaliação catarata",
        )
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 222,50" in msg

    def test_fabricio_geral_305(self):
        ctx = _ctx(
            medico="Dr. Fabrício Freitas",
            especialidade="Saúde ocular adulto",
        )
        msg = _solicitar(ctx, "sim")
        assert msg is not None
        assert "R$ 305,50" in msg


# ---------------------------------------------------------------------------
# 6. Estrutura da mensagem
# ---------------------------------------------------------------------------

class TestEstruturaMensagem:
    def test_mensagem_tem_duas_opcoes(self):
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "1️⃣" in msg
        assert "2️⃣" in msg

    def test_mensagem_tem_reserva_garantida(self):
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "reserva" in msg.lower() or "garantid" in msg.lower()

    def test_mensagem_tem_fila_encaixe(self):
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "encaixe" in msg.lower() or "fila" in msg.lower()

    def test_mensagem_nao_contem_convenio_nao_aceito(self):
        """Mensagem não deve mencionar convênios — contexto é particular."""
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "convênio" not in msg.lower()

    def test_mensagem_contem_pix(self):
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "pix" in msg.lower() or "Pix" in msg

    def test_mensagem_menciona_24h(self):
        """Política de cancelamento 24h deve estar na mensagem."""
        msg = _solicitar(_ctx(), "sim")
        assert msg is not None
        assert "24h" in msg or "24 h" in msg


# ---------------------------------------------------------------------------
# 7. Redis flag e toggle
# ---------------------------------------------------------------------------

class TestRedisEToggle:
    def test_redis_flag_impede_repeticao(self):
        ctx = _ctx()
        msg = _solicitar(ctx, "sim", redis=_redis_com_flag())
        assert msg is None

    def test_redis_sem_flag_dispara(self):
        ctx = _ctx()
        msg = _solicitar(ctx, "sim", redis=_redis_sem_flag())
        assert msg is not None

    def test_toggle_off_retorna_none(self):
        from voice_agent import politica_comparecimento as mod
        original = mod._ATIVADO
        mod._ATIVADO = False
        try:
            assert mod.deve_solicitar_sinal_particular(_ctx(), "sim") is None
        finally:
            mod._ATIVADO = original

    def test_ctx_none_retorna_none(self):
        assert _solicitar(None, "sim") is None


# ---------------------------------------------------------------------------
# 8. Posição na chain
# ---------------------------------------------------------------------------

class TestPosicaoNaChain:
    def test_c114_depois_de_endereco_pos_agenda_na_chain(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/blindagens_deterministicas.py").read_text(encoding="utf-8")

        inicio = conteudo.find("def tentar_bypass_deterministico")
        assert inicio >= 0
        corpo = conteudo[inicio:]

        pos_endereco = corpo.find("endereco_pos_agenda")
        pos_c114 = corpo.find("C-114")

        assert pos_endereco >= 0, "endereco_pos_agenda não encontrado"
        assert pos_c114 >= 0, "C-114 não encontrado"
        assert pos_c114 > pos_endereco, "C-114 deve vir DEPOIS de endereco_pos_agenda"

    def test_c114_importa_modulo_correto(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/blindagens_deterministicas.py").read_text(encoding="utf-8")
        assert "politica_comparecimento" in conteudo, "import não encontrado em blindagens"
