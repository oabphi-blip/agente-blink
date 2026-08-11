"""Bug C-68 — Valor persuasivo + C-62 janela 5min (21/07/2026, lead 24331202).

Origem: Fábio 21/07/2026 — lead 24331202 Ângela.
2 bugs:
    (a) Lia disse 'consulta com Dra. Karla no atendimento particular é
        R$ 611. Pagamento pode ser via Pix, cartão ou dinheiro. Quer horários?'
        Cuspiu valor sem persuasão. Fábio quer exames inclusos + voucher
        óculos + encaminhamento interno gratuito ANTES do valor.
    (b) Loop 'Anotado. Qual dia da semana?' 4min18s de gap escapou do
        C-62 (janela 3min). Aumentar pra 5min + limite 3→2.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from voice_agent.blindagens_deterministicas import deve_responder_valor
from voice_agent.dedup_outbound import (
    LIMITE_LOOP,
    TTL_JANELA_SEG,
    verificar_e_registrar,
)


# ═══════════════════════════════════════════════════════════════════════
# C-68 parte (a) — Valor persuasivo
# ═══════════════════════════════════════════════════════════════════════

class TestValorPersuasivo:
    def _ctx_karla_particular(self):
        return {
            "known": {
                "nome_paciente": "Ângela",
                "medico": "Dra. Karla Delalibera",
                "convenio": "Não se aplica",
            },
        }

    def test_apresenta_diferenciais_antes_do_valor(self):
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        assert r is not None
        # Deve mencionar os 3 diferenciais ANTES do valor (v2 modelo humano)
        pos_exames = r.lower().find("incluso na consulta")
        pos_especialistas = r.lower().find("especialistas do corpo clínico")
        pos_voucher = r.lower().find("voucher")
        pos_valor = r.find("R$ 611")
        assert pos_exames > 0
        assert pos_especialistas > 0
        assert pos_voucher > 0
        assert pos_valor > 0
        # Ordem: exames > especialistas > voucher > valor
        assert pos_exames < pos_especialistas < pos_voucher < pos_valor

    def test_menciona_3_exames_descritos(self):
        """Modelo humano descreve os 3 exames com linguagem acessível."""
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "qual o valor?")
        lower = r.lower()
        # Tonometria com descrição
        assert "tonometria" in lower
        assert "pressão ocular" in lower
        # Alinhamento e coordenação (versão humanizada de "motilidade")
        assert "alinhamento" in lower
        # Fundo do olho / mapeamento de retina
        assert "mapeamento" in lower
        assert "fundo do olho" in lower

    def test_menciona_voucher_oculos(self):
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        assert "voucher" in r.lower()
        assert "óculos" in r.lower() or "oculos" in r.lower()

    def test_menciona_5_especialistas_corpo_clinico(self):
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        lower = r.lower()
        # Modelo humano lista 5 especialistas
        assert "corpo clínico" in lower
        assert "catarata" in lower
        assert "refrativa" in lower
        assert "plástica ocular" in lower or "plastica ocular" in lower
        assert "retina" in lower
        assert "vítreo" in lower or "vitreo" in lower

    def test_termina_com_qual_sua_escolha(self):
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        # CTA v2: "Qual a sua escolha?" (não mais "quer horários?")
        assert "qual a sua escolha" in r.lower()

    def test_menciona_primeiro_paciente(self):
        """Modelo humano encerra com 'para o primeiro paciente' (multi-pac)."""
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        assert "primeiro paciente" in r.lower()

    def test_valor_karla_particular_611(self):
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "qual valor?")
        assert "R$ 611" in r  # Pix
        assert "R$ 670" in r  # Cartão

    def test_valor_apv_800(self):
        ctx = self._ctx_karla_particular()
        ctx["known"]["motivo"] = "avaliação do processamento visual"
        r = deve_responder_valor(ctx, "quanto custa?")
        assert "R$ 800" in r
        assert "R$ 870" in r

    def test_valor_fabricio_catarata_445(self):
        ctx = {
            "known": {
                "nome_paciente": "João",
                "medico": "Dr. Fabrício Freitas",
                "motivo": "catarata",
                "convenio": "Particular",
            },
        }
        r = deve_responder_valor(ctx, "qual o valor?")
        assert "R$ 445" in r
        assert "R$ 470" in r
        # Ainda menciona diferenciais
        assert "voucher" in r.lower()

    def test_abre_com_ola_nome(self):
        """Modelo humano abre com 'Olá, [Nome]'."""
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "quanto custa?")
        assert r.startswith("Olá,") or r.startswith("Olá ")

    def test_anti_padrao_nao_cuspe_valor_direto(self):
        """Regressão: NÃO pode voltar ao anti-padrão que Ângela pegou."""
        ctx = self._ctx_karla_particular()
        r = deve_responder_valor(ctx, "qual o valor?")
        # Anti-padrão exato Fábio 21/07:
        assert "Pagamento pode ser via Pix, cartão ou dinheiro no dia" not in r


# ═══════════════════════════════════════════════════════════════════════
# C-68 parte (b) — C-62 janela 5min + limite 2 (mais rigoroso)
# ═══════════════════════════════════════════════════════════════════════

class TestC62MaisRigoroso:
    def test_janela_5min(self):
        # Bug C-68: era 180 (3min), agora 300 (5min)
        assert TTL_JANELA_SEG == 300

    def test_limite_2(self):
        # Bug C-68: era 3, agora 2 (mais rigoroso)
        assert LIMITE_LOOP == 2

    def test_segunda_vez_bloqueia_loop(self):
        """Com limite=2, 2ª tentativa idêntica já bloqueia."""
        r_mock = MagicMock()
        state = {"n": 0}

        def incr(k):
            state["n"] += 1
            return state["n"]

        r_mock.incr = MagicMock(side_effect=incr)
        r_mock.expire = MagicMock()
        r_mock.setex = MagicMock()

        # 1ª vez → passa
        r1 = verificar_e_registrar(999, "Anotado. Qual dia?", r_mock)
        assert r1["permitir_envio"] is True

        # 2ª vez → BLOQUEIA (limite=2)
        r2 = verificar_e_registrar(999, "Anotado. Qual dia?", r_mock)
        assert r2["loop_detectado"] is True
        assert r2["permitir_envio"] is False

    def test_cenario_real_angela_lead_24331202(self):
        """Reproduz cenário: 'Anotado. Qual unidade?' 2× em 30s."""
        r_mock = MagicMock()
        state = {"n": 0}

        def incr(k):
            state["n"] += 1
            return state["n"]

        r_mock.incr = MagicMock(side_effect=incr)
        r_mock.expire = MagicMock()
        r_mock.setex = MagicMock()

        texto_loop = "Anotado. Qual unidade fica melhor pra vocês — Asa Norte ou Águas Claras?"

        # 1ª — passa
        r1 = verificar_e_registrar(24331202, texto_loop, r_mock)
        assert r1["permitir_envio"] is True

        # 2ª — BLOQUEIA (antes precisava 3, agora 2)
        r2 = verificar_e_registrar(24331202, texto_loop, r_mock)
        assert r2["permitir_envio"] is False
        assert r2["loop_detectado"] is True
