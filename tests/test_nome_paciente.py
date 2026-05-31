"""Pytest blindando a validação de nome civil completo do paciente.

Origem: bug do lead 24048691 (30/05/2026) — Lia aceitou "Marcela" como nome
completo do paciente e gravou no Kommo. Não deveria.

Regra 5.2.4 do _MASTER_INSTRUCTION.md. Implementada em voice_agent/nomes.py.
"""
from __future__ import annotations

import pytest

from voice_agent.nomes import (
    NomeStatus,
    avaliar_nome_paciente,
    mensagem_pedido_complemento,
)


class TestNomeCompleto:

    def test_nome_completo_3_tokens_fortes(self):
        assert avaliar_nome_paciente("Marcela Almeida Souza") == NomeStatus.COMPLETO

    def test_nome_completo_com_conectivos(self):
        assert (
            avaliar_nome_paciente("Maria de Souza e Silva")
            == NomeStatus.COMPLETO
        )

    def test_nome_completo_4_tokens(self):
        nome = "Renata Cristina Barbosa Eduarda Martins Coelho"
        assert avaliar_nome_paciente(nome) == NomeStatus.COMPLETO


class TestNomeIncompleto:

    def test_so_primeiro_nome_marcela_caso_real(self):
        """Caso real do lead 24048691 — Lia NÃO podia ter gravado."""
        assert avaliar_nome_paciente("Marcela") == NomeStatus.SO_PRIMEIRO_NOME

    def test_so_2_tokens_pede_complemento(self):
        assert (
            avaliar_nome_paciente("João Silva")
            == NomeStatus.SO_SOBRENOME_FALTANDO
        )

    def test_iniciais_no_meio(self):
        assert (
            avaliar_nome_paciente("Renata C B E M Coelho")
            == NomeStatus.INCOMPLETO_COM_INICIAIS
        )

    def test_iniciais_com_ponto(self):
        assert (
            avaliar_nome_paciente("Maria F. Silva")
            == NomeStatus.INCOMPLETO_COM_INICIAIS
        )

    def test_inicial_no_final(self):
        assert (
            avaliar_nome_paciente("João Pedro S")
            == NomeStatus.INCOMPLETO_COM_INICIAIS
        )


class TestCasosLimite:

    def test_vazio_devolve_vazio(self):
        assert avaliar_nome_paciente("") == NomeStatus.VAZIO
        assert avaliar_nome_paciente("   ") == NomeStatus.VAZIO
        assert avaliar_nome_paciente(None) == NomeStatus.VAZIO

    def test_conectivos_nao_contam_como_token_forte(self):
        # "da Silva" tem 1 conectivo + 1 token forte → ainda incompleto
        assert (
            avaliar_nome_paciente("Joana da Silva")
            == NomeStatus.SO_SOBRENOME_FALTANDO
        )

    def test_pontuacao_nao_quebra(self):
        # "Marcela, Almeida, Souza" → vírgulas removidas, é completo
        assert (
            avaliar_nome_paciente("Marcela, Almeida, Souza")
            == NomeStatus.COMPLETO
        )

    def test_apenas_conectivos_e_vazio_efetivo(self):
        assert avaliar_nome_paciente("de e da") == NomeStatus.VAZIO


class TestMensagemPedidoComplemento:
    """Sanity-check das frases — não pode citar 'iniciais' se for primeiro
    nome só, e vice-versa."""

    def test_mensagem_so_primeiro_nome_menciona_nome_meio(self):
        msg = mensagem_pedido_complemento(
            NomeStatus.SO_PRIMEIRO_NOME, primeiro_nome="Marcela"
        )
        assert "Marcela" in msg
        assert "nome do meio" in msg
        assert "iniciais" not in msg.lower()

    def test_mensagem_iniciais_menciona_iniciais(self):
        msg = mensagem_pedido_complemento(NomeStatus.INCOMPLETO_COM_INICIAIS)
        assert "iniciais" in msg.lower()

    def test_mensagem_sem_primeiro_nome(self):
        msg = mensagem_pedido_complemento(NomeStatus.SO_PRIMEIRO_NOME)
        # Não deve quebrar; saudação genérica.
        assert "Obrigada" in msg
        assert "{" not in msg  # sem placeholder vazado

    def test_mensagem_sobrenome_faltando(self):
        msg = mensagem_pedido_complemento(
            NomeStatus.SO_SOBRENOME_FALTANDO, primeiro_nome="João"
        )
        assert "sobrenome" in msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
