"""
Pytest Bug C-74 — FAQ especialidade/médico via bypass determinístico.

Origem: lead 24348742 Kenya. Paciente perguntou "Tem oftalmologista pediátrico"
e Lia respondeu com fallback C-56 ("vou te conectar com nossa equipe") em vez de
anunciar a Dra. Karla Delalíbera.

Fix: deve_responder_faq_especialidade() em blindagens_deterministicas.py intercep-
ta antes do LLM. Zero chance de acionar circuit breaker nessas perguntas simples.
"""
from __future__ import annotations

import pytest

from voice_agent.blindagens_deterministicas import (
    deve_responder_faq_especialidade,
    tentar_bypass_deterministico,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ctx():
    return {"known": {}}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PEDIATRIA → Dra. Karla
# ═══════════════════════════════════════════════════════════════════════════════

class TestPediatria:
    def test_kenya_exato(self):
        """Caso real: lead 24348742 Kenya."""
        r = deve_responder_faq_especialidade(_ctx(), "Tem oftalmologista pediátrico")
        assert r is not None
        assert "Karla" in r
        assert "oftalmopediatria" in r

    def test_tem_pediatra(self):
        r = deve_responder_faq_especialidade(_ctx(), "tem pediatra?")
        assert r is not None
        assert "Karla" in r

    def test_atende_crianca(self):
        r = deve_responder_faq_especialidade(_ctx(), "atende crianças?")
        assert r is not None
        assert "Karla" in r

    def test_atende_bebe(self):
        r = deve_responder_faq_especialidade(_ctx(), "Vocês atendem bebê?")
        assert r is not None
        assert "Karla" in r

    def test_tem_oftalmo_infantil(self):
        r = deve_responder_faq_especialidade(_ctx(), "tem oftalmologista infantil?")
        assert r is not None
        assert "Karla" in r

    def test_consulta_pra_crianca(self):
        r = deve_responder_faq_especialidade(_ctx(), "quero consulta pra minha filha de 5 anos")
        assert r is not None
        assert "Karla" in r

    def test_pede_nome_data_nasc(self):
        """Resposta pediátrica pede nome + data de nascimento para avançar."""
        r = deve_responder_faq_especialidade(_ctx(), "tem pediatra")
        assert "nome" in r.lower()
        assert "nascimento" in r.lower() or "nasc" in r.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ESTRABISMO → Dra. Karla
# ═══════════════════════════════════════════════════════════════════════════════

class TestEstrabismo:
    def test_tem_estrabismo(self):
        r = deve_responder_faq_especialidade(_ctx(), "tem estrabismo?")
        assert r is not None
        assert "Karla" in r
        assert "estrabismo" in r

    def test_faz_estrabismo(self):
        r = deve_responder_faq_especialidade(_ctx(), "vocês fazem tratamento de estrabismo?")
        assert r is not None
        assert "Karla" in r

    def test_olho_torto(self):
        r = deve_responder_faq_especialidade(_ctx(), "olho torto, atendem?")
        assert r is not None
        assert "Karla" in r

    def test_olho_desviado(self):
        r = deve_responder_faq_especialidade(_ctx(), "meu filho tem olho desviado")
        assert r is not None
        assert "Karla" in r

    def test_desvio_ocular(self):
        r = deve_responder_faq_especialidade(_ctx(), "desvio ocular tem tratamento?")
        assert r is not None
        assert "Karla" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CATARATA → Dr. Fabrício
# ═══════════════════════════════════════════════════════════════════════════════

class TestCatarata:
    def test_faz_catarata(self):
        r = deve_responder_faq_especialidade(_ctx(), "fazem cirurgia de catarata?")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r
        assert "catarata" in r.lower()

    def test_tem_catarata(self):
        r = deve_responder_faq_especialidade(_ctx(), "tem catarata?")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r

    def test_operacao_catarata(self):
        r = deve_responder_faq_especialidade(_ctx(), "minha mãe precisa de operação de catarata")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r

    def test_nao_confunde_karla(self):
        """Catarata deve ir pra Fabrício, não pra Karla."""
        r = deve_responder_faq_especialidade(_ctx(), "faz catarata")
        assert r is not None
        assert "Karla" not in r
        assert "Fabrício" in r or "Fabricio" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CÓRNEA / PTERÍGIO → Dr. Fabrício
# ═══════════════════════════════════════════════════════════════════════════════

class TestCornea:
    def test_pterigio(self):
        r = deve_responder_faq_especialidade(_ctx(), "vocês fazem pterígio?")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r

    def test_carne_no_olho(self):
        r = deve_responder_faq_especialidade(_ctx(), "minha mãe tem carne no olho")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r

    def test_ceratocone(self):
        r = deve_responder_faq_especialidade(_ctx(), "tratam ceratocone?")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r

    def test_transplante_cornea(self):
        r = deve_responder_faq_especialidade(_ctx(), "fazem transplante de córnea?")
        assert r is not None
        assert "Fabrício" in r or "Fabricio" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NÃO INTERCEPTAR — perguntas genéricas que LLM deve responder
# ═══════════════════════════════════════════════════════════════════════════════

class TestNaoInterceptar:
    def test_quero_marcar_consulta(self):
        """Paciente só quer agendar — não é FAQ especialidade."""
        r = deve_responder_faq_especialidade(_ctx(), "quero marcar uma consulta")
        assert r is None

    def test_quanto_custa(self):
        """Valor vai pro bypass valor, não FAQ."""
        r = deve_responder_faq_especialidade(_ctx(), "quanto custa a consulta?")
        assert r is None

    def test_vocês_aceitam_plano(self):
        """Convênio vai pro classificador_convenio, não FAQ."""
        r = deve_responder_faq_especialidade(_ctx(), "vocês aceitam plano de saúde?")
        assert r is None

    def test_boa_tarde(self):
        """Saudação não é FAQ."""
        r = deve_responder_faq_especialidade(_ctx(), "Boa tarde!")
        assert r is None

    def test_user_text_vazio(self):
        r = deve_responder_faq_especialidade(_ctx(), "")
        assert r is None

    def test_user_text_none(self):
        r = deve_responder_faq_especialidade(_ctx(), None)
        assert r is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. INTEGRAÇÃO — tentar_bypass_deterministico retorna nome correto
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegracaoBypass:
    def test_kenya_via_bypass_chain(self):
        """Pergunta da Kenya chega pelo chain e retorna faq_especialidade."""
        result = tentar_bypass_deterministico(_ctx(), "Tem oftalmologista pediátrico")
        assert result is not None
        nome, texto = result
        assert nome == "faq_especialidade"
        assert "Karla" in texto

    def test_catarata_via_bypass_chain(self):
        result = tentar_bypass_deterministico(_ctx(), "fazem cirurgia de catarata?")
        assert result is not None
        nome, texto = result
        assert nome == "faq_especialidade"
        assert "Fabrício" in texto or "Fabricio" in texto

    def test_perguntas_nao_faq_passam_adiante(self):
        """Pergunta não coberta retorna None (LLM vai responder)."""
        result = tentar_bypass_deterministico(_ctx(), "Boa tarde, quero agendar")
        # Pode retornar None ou outro bypass — mas NOT faq_especialidade
        if result is not None:
            assert result[0] != "faq_especialidade"

    def test_toggle_off_nao_intercepta(self, monkeypatch):
        """BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO=0 → bypass desligado."""
        monkeypatch.setenv("BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO", "0")
        r = deve_responder_faq_especialidade(_ctx(), "Tem oftalmologista pediátrico")
        assert r is None

    def test_toggle_on_padrao_intercepta(self, monkeypatch):
        """Sem env (default ON) → intercepta."""
        monkeypatch.delenv("BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO", raising=False)
        r = deve_responder_faq_especialidade(_ctx(), "tem pediatra?")
        assert r is not None
        assert "Karla" in r
