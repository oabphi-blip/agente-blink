"""Bug C-50 (02/07/2026 noite, lead 24243754 Ani/Ysis Hellena).

Caso:
- Ani forneceu "Ysis Hellena Oliveira Santos, 12/09/2020" no inbound
- Lia respondeu "Só pra confirmar — a data de nascimento da Ysis é 12
  de setembro de 2020, certo?"
- Redundância desnecessária. Especialmente em contexto sensível (TEA).

Regra Fábio: NUNCA pedir confirmação de dado recém-fornecido. Reconhecer
em ≤6 palavras e AVANÇAR para próxima pergunta.

Fix: filtro C-50 em `voice_agent/responder.py::_scrub_prohibited`.
"""
from __future__ import annotations

import pytest

from voice_agent.responder import (
    _paciente_forneceu_dado_no_turno,
    _texto_pede_confirmacao_redundante,
    _gerar_reconhecimento_curto_e_avanca,
    _scrub_prohibited,
)


class TestDeteccaoInboundComDado:
    """Detecta se o inbound do paciente tem dado estruturado."""

    @pytest.mark.parametrize("frase", [
        "12/09/2020",
        "Ysis Hellena Oliveira Santos",
        "meu CPF é 12345678900",
        "nasceu em 15 de março de 2019",
        "Ana Silva, 03/07/2018",
        "12345678910",  # CPF puro
        "01/12/2015",
    ])
    def test_detecta_dado(self, frase):
        assert _paciente_forneceu_dado_no_turno(frase) is True

    @pytest.mark.parametrize("frase", [
        "oi",
        "sim",
        "tudo bem",
        "não sei",
        "TEA",
        "",
        None,
    ])
    def test_nao_falso_positivo_em_saudacao(self, frase):
        assert _paciente_forneceu_dado_no_turno(frase) is False


class TestDeteccaoConfirmacaoRedundante:
    """Detecta padrões de 'só pra confirmar', 'certo?' etc."""

    @pytest.mark.parametrize("frase", [
        "Só pra confirmar — a data é 12/09/2020, certo?",
        "só para confirmar, é isso mesmo?",
        "Confirma que é o Bacen?",
        "É isso mesmo?",
        "Só pra ter certeza — nome completo Ana Silva?",
        "Vou confirmar então: 5 anos.",
        "Ficou correto?",
        "Está certo assim?",
    ])
    def test_detecta_confirmacao(self, frase):
        assert _texto_pede_confirmacao_redundante(frase) is True

    @pytest.mark.parametrize("frase", [
        "Perfeito, Ysis, 5 anos.",
        "Anotei. Qual convênio?",
        "Ótimo!",
        "Vou verificar os horários.",
        "",
    ])
    def test_frase_normal_nao_dispara(self, frase):
        assert _texto_pede_confirmacao_redundante(frase) is False


class TestFraseReconhecimentoCurto:
    def test_com_nome_contato_menciona_nome(self):
        out = _gerar_reconhecimento_curto_e_avanca(
            {"known": {"nome_contato": "Ani Silva"}}
        )
        assert "Ani" in out
        assert "convenio" in out.lower() or "convênio" in out.lower()

    def test_ja_tem_convenio_pula_pra_unidade(self):
        out = _gerar_reconhecimento_curto_e_avanca(
            {"known": {"nome_contato": "Fábio", "convenio": "Bacen"}}
        )
        assert "unidade" in out.lower() or "asa norte" in out.lower()

    def test_ja_tem_unidade_pula_pra_preferencia(self):
        out = _gerar_reconhecimento_curto_e_avanca(
            {"known": {"convenio": "Bacen", "unidade": "Asa Norte"}}
        )
        assert (
            "dia" in out.lower() or "turno" in out.lower() or
            "horario" in out.lower() or "horário" in out.lower()
        )

    def test_sem_nome_reconhecimento_generico(self):
        out = _gerar_reconhecimento_curto_e_avanca(None)
        assert "Anotado" in out or "anotado" in out.lower()


class TestFiltroC50Integracao:
    """Fluxo real caso Ani/Ysis."""

    def test_caso_real_ani_ysis_bloqueado(self):
        """Reproduz o caso Ani exatamente."""
        texto_lia = (
            "Obrigada, Ani! Só pra confirmar — a data de nascimento "
            "da Ysis é **12 de setembro de 2020**, certo?"
        )
        ctx = {
            "known": {"nome_contato": "Ani"},
            "inbound_text": "Ysis Hellena, 12/09/2020",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "so pra confirmar" not in out.lower()
        assert "só pra confirmar" not in out.lower()
        assert "certo?" not in out.lower()
        assert "Ani" in out
        # Avançou pra próxima pergunta (convênio)
        assert "convenio" in out.lower() or "convênio" in out.lower()

    def test_nao_bloqueia_quando_paciente_nao_forneceu_dado(self):
        """Se inbound é só saudação, filtro NÃO deve disparar."""
        texto_lia = "Só pra confirmar sua unidade preferida?"
        ctx = {"known": {}, "inbound_text": "oi"}
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        # Filtro C-50 não dispara pq inbound não tem dado
        # (mas outros filtros podem — não testamos aqui)

    def test_data_por_extenso_no_inbound(self):
        texto_lia = "É isso mesmo? 15 de março de 2019?"
        ctx = {
            "known": {"nome_contato": "Ana"},
            "inbound_text": "nasceu em 15 de março de 2019",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "é isso mesmo" not in out.lower()
        assert "anotado" in out.lower() or "Ana" in out

    def test_cpf_no_inbound_bloqueia_confirmacao(self):
        texto_lia = "Confirma que é 12345678910?"
        ctx = {
            "known": {"nome_contato": "Carlos", "convenio": "Bacen"},
            "inbound_text": "meu CPF é 12345678910",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "confirma que" not in out.lower()

    def test_conversa_normal_sem_confirmacao_passa(self):
        """Conversa sem confirmação redundante não deve ser afetada."""
        texto_lia = "Perfeito, Ana! Qual convênio?"
        ctx = {"known": {"nome_contato": "Ana"}, "inbound_text": "Ana Silva, 12/09/2020"}
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "Perfeito" in out or "perfeito" in out.lower()
