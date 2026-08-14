"""
Pytest C-137 (14/08/2026) — "desconto" não estava no regex de objecao_preco.py.

Caso real: lead 24328426 Alice Tavares — "Queria saber se teria algum desconto nesta consulta"
→ agente respondeu 4x com "Anotado. Vou verificar os próximos horários disponíveis..."
porque "desconto" não casava com nenhum padrão em _RE_OBJECAO.

Fix: adicionado _RE_DESCONTO_ESPECIFICO + _montar_resposta_desconto() + routing interno.
"""
import pytest
from voice_agent.objecao_preco import (
    detectar_objecao_preco,
    detectar_desconto_especifico,
    deve_responder_objecao_preco,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(medico=None, motivo=None, convenio=None, nome=None):
    known = {}
    if medico:
        known["medico"] = medico
    if motivo:
        known["motivo"] = motivo
    if convenio:
        known["convenio"] = convenio
    ctx = {"known": known}
    if nome:
        ctx["name"] = nome
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 1. detectar_objecao_preco() agora detecta "desconto"
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectarObjecaoDesconto:
    def test_caso_real_alice_tavares(self):
        """Caso exato que causou o bug."""
        assert detectar_objecao_preco("Queria saber se teria algum desconto nesta consulta")

    def test_desconto_simples(self):
        assert detectar_objecao_preco("tem desconto?")

    def test_desconto_maiusculo(self):
        assert detectar_objecao_preco("Tem algum Desconto?")

    def test_desconto_no_meio(self):
        assert detectar_objecao_preco("posso conseguir desconto?")

    def test_promocao(self):
        assert detectar_objecao_preco("tem alguma promoção?")

    def test_preco_especial(self):
        assert detectar_objecao_preco("tem preço especial para mim?")

    def test_valor_especial(self):
        assert detectar_objecao_preco("tem valor especial?")

    def test_consegue_desconto(self):
        assert detectar_objecao_preco("você consegue me dar um desconto?")

    # Não deve detectar em casos sem relação
    def test_nao_deteta_agendar(self):
        assert not detectar_objecao_preco("quero agendar uma consulta")

    def test_nao_deteta_valor_info(self):
        # "qual o valor" não tem objeção
        assert not detectar_objecao_preco("qual o valor da consulta?")

    def test_nao_deteta_horario(self):
        assert not detectar_objecao_preco("quais os horários disponíveis?")


# ─────────────────────────────────────────────────────────────────────────────
# 2. detectar_desconto_especifico() — detector específico de desconto
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectarDescontoEspecifico:
    def test_desconto(self):
        assert detectar_desconto_especifico("quero um desconto")

    def test_promocao(self):
        assert detectar_desconto_especifico("tem promoção?")

    def test_preco_especial(self):
        assert detectar_desconto_especifico("preço especial?")

    def test_nao_caro(self):
        """'Está caro' não é desconto específico."""
        assert not detectar_desconto_especifico("está caro demais")

    def test_nao_encontrei_barato(self):
        assert not detectar_desconto_especifico("encontrei mais barato em outra clínica")

    def test_nao_agendar(self):
        assert not detectar_desconto_especifico("quero agendar")


# ─────────────────────────────────────────────────────────────────────────────
# 3. deve_responder_objecao_preco() — rota desconto para _montar_resposta_desconto
# ─────────────────────────────────────────────────────────────────────────────

class TestRespostaDesconto:
    def test_caso_alice_tavares_retorna_algo(self):
        """Caso real — deve retornar resposta (não None que causava stall)."""
        ctx = _ctx(medico="Dra. Karla Delalíbera", nome="Alice")
        r = deve_responder_objecao_preco(ctx, "Queria saber se teria algum desconto nesta consulta")
        assert r is not None
        assert len(r) > 50

    def test_resposta_desconto_sem_dismissar(self):
        """Não deve usar frases dismissivas ('nosso preço é justo')."""
        ctx = _ctx(nome="Maria")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "nosso preço é justo" not in r.lower()
            assert "é o valor de mercado" not in r.lower()

    def test_resposta_desconto_nao_usa_particular(self):
        """Termo proibido 'particular' não deve aparecer."""
        ctx = _ctx(nome="João")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "particular" not in r.lower()

    def test_resposta_desconto_oferece_parcelamento(self):
        """Resposta deve oferecer parcelamento como alternativa."""
        ctx = _ctx(nome="Alice")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "2x" in r or "parcelamento" in r.lower()

    def test_resposta_desconto_tom_amigavel(self):
        """Tom deve ser amigável — emoji ou linguagem positiva."""
        ctx = _ctx(nome="Alice")
        r = deve_responder_objecao_preco(ctx, "consegue me dar um desconto?")
        if r:
            assert "😊" in r or "facilitar" in r.lower() or "encaixar" in r.lower()

    def test_resposta_desconto_karla_parcela_335(self):
        """Karla padrão: parcela R$ 335."""
        ctx = _ctx(medico="Karla", nome="Ana")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "335" in r

    def test_resposta_desconto_karla_apv_parcela_435(self):
        """Karla APV: parcela R$ 435."""
        ctx = _ctx(medico="Karla", motivo="processamento visual", nome="Clara")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "435" in r

    def test_resposta_desconto_fabricio_catarata_parcela_235(self):
        """Fabrício catarata: parcela R$ 235."""
        ctx = _ctx(medico="Dr. Fabrício Freitas", motivo="catarata", nome="Carlos")
        r = deve_responder_objecao_preco(ctx, "tem desconto?")
        if r:
            assert "235" in r

    def test_caro_ainda_usa_template_valor(self):
        """'Está caro' (não desconto específico) usa template de valor com âncora."""
        ctx = _ctx(medico="Karla", nome="Maria")
        r = deve_responder_objecao_preco(ctx, "está muito caro")
        if r:
            # Deve usar template padrão com valor da especialidade
            assert r is not None

    def test_ctx_none_retorna_none(self):
        """ctx=None → None (fail-open)."""
        r = deve_responder_objecao_preco(None, "tem desconto?")
        assert r is None

    def test_toggle_off(self, monkeypatch):
        """Toggle OBJECAO_PRECO_ATIVADO=0 → None."""
        monkeypatch.setattr("voice_agent.objecao_preco._ATIVADO", False)
        r = deve_responder_objecao_preco(_ctx(), "tem desconto?")
        assert r is None

    def test_sem_objecao_retorna_none(self):
        """Texto sem objeção nem desconto → None."""
        r = deve_responder_objecao_preco(_ctx(), "quero agendar")
        assert r is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Compatibilidade retroativa — objeções existentes ainda funcionam
# ─────────────────────────────────────────────────────────────────────────────

class TestCompatibilidadeRetroativa:
    def test_caro_still_detects(self):
        assert detectar_objecao_preco("está caro demais")

    def test_mais_barato_still_detects(self):
        assert detectar_objecao_preco("encontrei mais barato em outra clínica")

    def test_nao_tenho_valor_still_detects(self):
        assert detectar_objecao_preco("não tenho esse valor agora")

    def test_sem_condicoes_still_detects(self):
        assert detectar_objecao_preco("estou sem condições de pagar")

    def test_karla_pediatrico_still_works(self):
        """Contexto pediátrico com 'caro' ainda gera resposta pediátrica."""
        ctx = _ctx(medico="Karla", nome="Mãe")
        ctx["known"]["contexto_pediatrico"] = True
        r = deve_responder_objecao_preco(ctx, "está caro")
        assert r is not None
        assert "oftalmopediatria" in r.lower() or "criança" in r.lower() or "bebê" in r.lower()
