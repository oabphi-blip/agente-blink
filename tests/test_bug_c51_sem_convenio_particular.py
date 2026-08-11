"""Bug C-51 (03/07/2026 madrugada, lead 24243754 Ani/Ysis Hellena).

Caso real (msg 29037748):
Ani disse "sem convênio" (CONVENIO=Não se aplica gravado no Kommo). Lia
respondeu:
    "Ani, posso pré-reservar esse horário por 10 minutos enquanto você
    me confirma uma coisa: o atendimento vai ser por convênio ou
    particular? • Por convênio: me envia a foto da carteirinha + RG...
    • Particular: consulta com Dra. Karla Delalíbera = R$ 670, e pra
    firmar a reserva pedimos um sinal de 50% via Pix (R$ 335). Chave
    Pix: karladelaliberaoftalmo@gmail.com..."

4 bugs simultâneos:
1. Reperguntou convênio (Ani já respondeu sem convênio)
2. Usou palavra "particular" (proibida — trocar por "sem convênio")
3. Despejou valor sem paciente perguntar
4. Múltiplos assuntos em 1 mensagem

Fix: filtro C-51 em `voice_agent/responder.py::_scrub_prohibited`.
"""
from __future__ import annotations

import pytest

from voice_agent.responder import (
    _paciente_ja_definiu_convenio,
    _texto_repergunta_convenio,
    _texto_usa_palavra_particular,
    _paciente_perguntou_valor,
    _texto_despeja_valor,
    _gerar_proxima_pergunta_sem_convenio,
    _substituir_particular_por_sem_convenio,
    _scrub_prohibited,
)


class TestDeteccaoConvenioJaDefinido:
    def test_nao_se_aplica_e_definido(self):
        ctx = {"known": {"convenio": "Não se aplica"}}
        assert _paciente_ja_definiu_convenio(ctx) is True

    def test_convenio_aceito_e_definido(self):
        ctx = {"known": {"convenio": "Bacen"}}
        assert _paciente_ja_definiu_convenio(ctx) is True

    def test_vazio_nao_e_definido(self):
        assert _paciente_ja_definiu_convenio({"known": {}}) is False
        assert _paciente_ja_definiu_convenio(None) is False

    def test_string_vazia_nao_e_definido(self):
        ctx = {"known": {"convenio": ""}}
        assert _paciente_ja_definiu_convenio(ctx) is False


class TestDeteccaoRepergutaConvenio:
    @pytest.mark.parametrize("frase", [
        "o atendimento vai ser por convênio ou particular?",
        "sera por convenio ou particular?",
        "por convênio ou sem convênio?",
        "atendimento será por convênio?",
        "o atendimento será por convênio ou particular?",
    ])
    def test_detecta(self, frase):
        assert _texto_repergunta_convenio(frase) is True

    @pytest.mark.parametrize("frase", [
        "qual sua preferência de dia?",
        "vou verificar a agenda",
        "obrigada, Ani!",
    ])
    def test_nao_dispara_falso(self, frase):
        assert _texto_repergunta_convenio(frase) is False


class TestPalavraParticular:
    def test_detecta_palavra_particular(self):
        assert _texto_usa_palavra_particular("Particular: R$ 670") is True
        assert _texto_usa_palavra_particular("por particular") is True

    def test_substitui_particular(self):
        original = "Convênio ou Particular? Particular: R$ 670."
        out = _substituir_particular_por_sem_convenio(original)
        assert "particular" not in out.lower()
        assert "sem convênio" in out.lower()

    def test_substitui_case_variantes(self):
        out = _substituir_particular_por_sem_convenio(
            "Como particular voce paga R$ 670. Por Particular é diferente."
        )
        assert "particular" not in out.lower()


class TestPacientePerguntouValor:
    @pytest.mark.parametrize("frase", [
        "quanto custa?",
        "qual o valor?",
        "quanto é a consulta?",
        "tem pix?",
        "posso pagar r$ 670?",
        "e o sinal?",
    ])
    def test_detecta_pergunta_valor(self, frase):
        assert _paciente_perguntou_valor(frase) is True

    @pytest.mark.parametrize("frase", [
        "sem convênio",
        "Ysis Hellena",
        "12/09/2020",
        "sim",
    ])
    def test_nao_falso_positivo(self, frase):
        assert _paciente_perguntou_valor(frase) is False


class TestDespejoValor:
    @pytest.mark.parametrize("frase", [
        "R$ 670 pra consulta",
        "chave pix karladelaliberaoftalmo@gmail.com",
        "sinal de 50% via Pix R$ 335",
        "cancelamento <24h não é devolvido",
        "valor da consulta é R$ 670",
    ])
    def test_detecta_despejo(self, frase):
        assert _texto_despeja_valor(frase) is True

    def test_texto_neutro_nao_dispara(self):
        assert _texto_despeja_valor("Qual dia da semana?") is False


class TestFiltroC51IntegracaoScrub:
    def test_caso_real_ani_ysis_bloqueado(self):
        """Reproduz mensagem exata do lead 24243754."""
        texto_lia = (
            "Ani, posso pré-reservar esse horário por 10 minutos enquanto "
            "você me confirma uma coisa: o atendimento vai ser por "
            "convênio ou particular? • Por convênio: me envia a foto da "
            "carteirinha. • Particular: consulta com Dra. Karla = R$ 670, "
            "e pra firmar a reserva pedimos um sinal de 50% via Pix "
            "(R$ 335). Chave Pix: karladelaliberaoftalmo@gmail.com."
        )
        ctx = {
            "known": {
                "nome_contato": "Ani",
                "convenio": "Não se aplica",
            },
            "inbound_text": "sem convênio",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        # Não repete pergunta de convênio
        assert "convenio ou particular" not in out.lower()
        assert "convênio ou particular" not in out.lower()
        # Não vaza valor/Pix
        assert "670" not in out
        assert "335" not in out
        assert "karladelalibera" not in out.lower()
        # Não usa palavra particular
        assert "particular" not in out.lower()
        # Avança pra próxima pergunta
        assert "unidade" in out.lower() or "asa norte" in out.lower()

    def test_paciente_perguntou_valor_permite(self):
        """Se paciente perguntou valor, Lia PODE mencionar R$."""
        texto_lia = "Consulta R$ 670. Aceita?"
        ctx = {
            "known": {"convenio": "Não se aplica"},
            "inbound_text": "quanto custa?",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        # Neste caso o filtro 3 NÃO deve substituir — paciente perguntou
        assert "670" in out or "sem convênio" in out.lower()

    def test_convenio_ainda_nao_definido_permite_pergunta(self):
        """Se ctx.known.convenio vazio, pode perguntar 'convênio ou sem'."""
        texto_lia = "Será por convênio ou sem convênio?"
        ctx = {"known": {}, "inbound_text": "Ana Silva"}
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        # Filtro C-51.1 não dispara pq convenio ainda não está no ctx
        # Só troca 'particular' se tiver — aqui não tem
        assert "convênio" in out.lower() or "convenio" in out.lower()

    def test_substituicao_particular_isolada(self):
        """Quando só o problema é a palavra 'particular'."""
        texto_lia = "No plano particular fica R$ 670."
        ctx = {
            "known": {"convenio": "Não se aplica"},
            "inbound_text": "quanto?",
        }
        out = _scrub_prohibited(texto_lia, ctx=ctx)
        assert "particular" not in out.lower()
        assert "sem convênio" in out.lower() or "670" in out
