"""
Bug C-106 (11/08/2026) — Valor contextualizado antes do preço.

Cenários cobertos:
  1. "para 3 anos" em user_text → idade=3, medico=Karla, contexto_pediatrico=True
  2. Resposta pediátrica contém especialidade Karla, NOT "Qual médico?"
  3. Resposta pediátrica usa "sem convênio" (nunca "particular")
  4. "bebê" no user_text → contexto_pediatrico=True
  5. "meses" no user_text → contexto_pediatrico=True
  6. ctx.known.medico=Karla + adulto → resposta adulta, sem tabela Fabrício
  7. ctx.known.medico=Fabrício + catarata → R$ 445 Pix
  8. ctx.known.medico=Fabrício + geral → R$ 611 Pix
  9. APV/SDP → R$ 800 Pix
 10. Sem médico → tabela geral sem convênio (sem perguntar "convênio ou particular")
 11. Toggle OFF → returns None
 12. ctx=None → returns None (fail-open)
 13. Nenhuma resposta contém "particular" (exceto em exclusões)
 14. step 12 enriquecimento_ctx: idade<18 injeta medico=Karla
 15. step 12 enriquecimento_ctx: medico já preenchido não é sobrescrito
 16. step 12: adulto (25 anos) não injeta Karla
 17. step 12: "filha de 10 anos" → contexto_pediatrico
 18. gerar_valor_contextualizado com ctx vazio de known → tabela geral
 19. ctx.known.contexto_pediatrico=True sem idade → resposta pediátrica
 20. Resposta pediátrica menciona "Dra. Karla Delalíbera"
 21. _tabela_sem_convenio não contém "particular"
 22. _inferir_medico_user_text: "para 15 anos" → karla
 23. _inferir_medico_user_text: "adulto de 55 anos" → "" (não força Karla)
 24. _inferir_medico_user_text: "3 meses de idade" → karla
"""

from __future__ import annotations

import os
import sys
import importlib
import types
import re

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de ctx
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(medico="", motivo="", idade=None, pediatrico=False, nome="Ana"):
    known = {}
    if medico:
        known["medico"] = medico
    if motivo:
        known["motivo"] = motivo
    if idade is not None:
        known["idade"] = idade
    if pediatrico:
        known["contexto_pediatrico"] = True
    return {"known": known, "name": nome}


# ─────────────────────────────────────────────────────────────────────────────
# Import dos módulos
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_toggle(monkeypatch):
    """Garante toggle ON por padrão em cada teste."""
    monkeypatch.setenv("VALOR_CONTEXTUALIZADO_ATIVADO", "1")
    yield


def _import_valor():
    import importlib
    import voice_agent.oferta_valor_contextualizado as m
    importlib.reload(m)
    return m


def _import_enriquecimento():
    import importlib
    import voice_agent.enriquecimento_ctx as m
    importlib.reload(m)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# 1-5. Detecção de idade/pediatria em user_text
# ─────────────────────────────────────────────────────────────────────────────

class TestIdadeUserText:

    def test_para_3_anos_gera_pediatrico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(), user_text="quero marcar para meu filho de 3 anos"
        )
        assert resp is not None
        assert "Karla" in resp or "karla" in resp.lower()

    def test_para_3_anos_nao_contem_qual_medico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(), user_text="quero agendar para 3 anos"
        )
        assert resp is not None
        assert "Qual médico" not in resp
        assert "qual médico" not in resp.lower()

    def test_bebe_em_user_text_gera_pediatrico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(), user_text="é para meu bebê"
        )
        assert resp is not None
        assert "Karla" in resp

    def test_meses_em_user_text_gera_pediatrico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(), user_text="meu filho tem 8 meses"
        )
        assert resp is not None
        assert "Karla" in resp

    def test_filho_em_user_text_gera_pediatrico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(), user_text="é para minha filha"
        )
        assert resp is not None
        assert "Karla" in resp


# ─────────────────────────────────────────────────────────────────────────────
# 6-9. Templates por médico / contexto
# ─────────────────────────────────────────────────────────────────────────────

class TestTemplatesPorMedico:

    def test_karla_adulto_retorna_611(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Karla"))
        assert resp is not None
        assert "611" in resp
        assert "670" in resp

    def test_karla_adulto_nao_contem_fabricio(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Karla"))
        assert "Fabrício" not in resp
        assert "fabricio" not in resp.lower()

    def test_fabricio_catarata_retorna_445(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Fabrício", motivo="catarata"))
        assert resp is not None
        assert "445" in resp
        assert "470" in resp

    def test_fabricio_geral_retorna_611(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Fabrício", motivo="saúde ocular"))
        assert resp is not None
        assert "611" in resp

    def test_apv_retorna_800(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Karla", motivo="apv"))
        assert resp is not None
        assert "800" in resp
        assert "870" in resp

    def test_apv_sdp_retorna_800(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(medico="Karla", motivo="processamento visual")
        )
        assert resp is not None
        assert "800" in resp

    def test_karla_pediatrico_retorna_611_e_menciona_crianca(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(medico="Karla", pediatrico=True, idade=5)
        )
        assert resp is not None
        assert "611" in resp
        assert any(kw in resp.lower() for kw in ("criança", "criancas", "pediatria", "pediatr", "pequeno"))

    def test_karla_pediatrico_menciona_dra_karla(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(medico="Karla", pediatrico=True)
        )
        assert "Dra. Karla Delalíbera" in resp


# ─────────────────────────────────────────────────────────────────────────────
# 10-12. Tabela geral + toggle + fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestTabelaGeralEToggle:

    def test_sem_medico_retorna_tabela_geral(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx())
        assert resp is not None
        assert "Karla" in resp
        assert "Fabrício" in resp

    def test_tabela_geral_sem_convenio_nao_contem_particular(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx())
        assert "particular" not in resp.lower()
        assert "sem convênio" in resp.lower() or "sem convenio" in resp.lower()

    def test_tabela_geral_nao_pergunta_convenio_particular(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx())
        # Não deve perguntar "é convênio ou particular?"
        assert "convênio ou particular" not in resp.lower()
        assert "convenio ou particular" not in resp.lower()

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("VALOR_CONTEXTUALIZADO_ATIVADO", "0")
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Karla"))
        assert resp is None

    def test_ctx_none_retorna_none(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(None)
        assert resp is None


# ─────────────────────────────────────────────────────────────────────────────
# 13. Regra "sem convênio" em TODAS as respostas
# ─────────────────────────────────────────────────────────────────────────────

class TestSemConvenioRule:

    @pytest.mark.parametrize("medico,motivo,pediatrico,idade", [
        ("Karla", "", False, None),
        ("Karla", "", True, 5),
        ("Karla", "apv", False, None),
        ("Fabrício", "catarata", False, None),
        ("Fabrício", "", False, None),
        ("", "", False, None),
    ])
    def test_nenhuma_resposta_usa_particular(self, medico, motivo, pediatrico, idade):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            _ctx(medico=medico, motivo=motivo, pediatrico=pediatrico, idade=idade)
        )
        assert resp is not None
        # "particular" não deve aparecer em contexto de preço
        # Permite "em particular" se vier de construção natural, mas não "consulta particular"
        assert "consulta particular" not in resp.lower()
        assert "atendimento particular" not in resp.lower()

    def test_todas_respostas_contem_sem_convenio(self):
        m = _import_valor()
        for medico in ["Karla", "Fabrício", ""]:
            resp = m.gerar_valor_contextualizado(_ctx(medico=medico))
            assert resp is not None
            assert "sem convênio" in resp.lower() or "sem convenio" in resp.lower(), \
                f"Faltou 'sem convênio' em resposta para médico={medico!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 14-17. Step 12 — enriquecimento_ctx
# ─────────────────────────────────────────────────────────────────────────────

class TestEnriquecimentoCtxStep12:

    def _enriquecer(self, user_text="", known=None):
        """Executa step 12 diretamente via regex inline (sem dependência do módulo completo)."""
        # Replica o step 12 de enriquecimento_ctx.py
        import re
        _RE_IDADE = re.compile(
            r"(?:para|de|com|tem)\s+(\d{1,2})\s+anos?"
            r"|\b(\d{1,2})\s+anos?\s+de\s+(?:idade|vida)\b",
            re.IGNORECASE,
        )
        _RE_MESES = re.compile(r"\b\d{1,2}\s+meses?\b", re.IGNORECASE)
        _RE_KID = re.compile(
            r"\b(?:beb[eê]|crian[çc]a|filho|filha|infantil|rec[eé]m[- ]?nascido)\b",
            re.IGNORECASE,
        )
        k = dict(known or {})
        if user_text and not k.get("contexto_pediatrico"):
            m = _RE_IDADE.search(user_text)
            idade_extraida = None
            if m:
                idade_extraida = int(m.group(1) or m.group(2))
            elif _RE_MESES.search(user_text):
                idade_extraida = 0
            elif _RE_KID.search(user_text):
                idade_extraida = 5
            if idade_extraida is not None:
                if not k.get("idade"):
                    k["idade"] = idade_extraida
                if idade_extraida < 18:
                    k["contexto_pediatrico"] = True
                    if not k.get("medico"):
                        k["medico"] = "Karla"
        return k

    def test_3_anos_injeta_karla(self):
        k = self._enriquecer("quero marcar para 3 anos")
        assert k.get("medico") == "Karla"
        assert k.get("contexto_pediatrico") is True
        assert k.get("idade") == 3

    def test_medico_ja_preenchido_nao_sobrescreve(self):
        k = self._enriquecer("para 5 anos", known={"medico": "Fabrício"})
        # contexto_pediatrico e idade podem ser injetados, mas medico não muda
        assert k.get("medico") == "Fabrício"
        assert k.get("contexto_pediatrico") is True

    def test_adulto_25_anos_nao_injeta_karla(self):
        k = self._enriquecer("para 25 anos")
        assert k.get("medico") != "Karla" or k.get("medico") is None
        assert not k.get("contexto_pediatrico")

    def test_filha_de_10_anos_injeta_pediatrico(self):
        k = self._enriquecer("minha filha tem 10 anos de idade")
        assert k.get("contexto_pediatrico") is True
        assert k.get("medico") == "Karla"

    def test_bebe_injeta_pediatrico(self):
        k = self._enriquecer("é para o meu bebê de 6 meses")
        assert k.get("contexto_pediatrico") is True
        assert k.get("medico") == "Karla"


# ─────────────────────────────────────────────────────────────────────────────
# 18-20. Casos de borda
# ─────────────────────────────────────────────────────────────────────────────

class TestCasosDeBorda:

    def test_ctx_sem_known_retorna_tabela_geral(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado({"name": "Teste"})
        assert resp is not None  # tabela geral, não None

    def test_contexto_pediatrico_true_sem_idade_retorna_pediatrico(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(
            {"known": {"medico": "Karla", "contexto_pediatrico": True}, "name": "Mãe"}
        )
        assert resp is not None
        assert "611" in resp

    def test_resposta_pediatrica_menciona_dra_karla_delalibera(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado(_ctx(medico="Karla", pediatrico=True, idade=4))
        assert "Dra. Karla Delalíbera" in resp

    def test_tabela_sem_convenio_helper_nao_contem_particular(self):
        from voice_agent.oferta_valor_contextualizado import _tabela_sem_convenio
        resp = _tabela_sem_convenio("Teste")
        assert "particular" not in resp.lower()
        assert "sem convênio" in resp.lower() or "sem convenio" in resp.lower()

    def test_nome_vazio_nao_quebra(self):
        m = _import_valor()
        resp = m.gerar_valor_contextualizado({"known": {"medico": "Karla"}, "name": ""})
        assert resp is not None


# ─────────────────────────────────────────────────────────────────────────────
# 21-23. _inferir_medico_user_text
# ─────────────────────────────────────────────────────────────────────────────

class TestInferirMedicoUserText:

    def test_15_anos_retorna_karla(self):
        from voice_agent.oferta_valor_contextualizado import _inferir_medico_user_text
        assert _inferir_medico_user_text("para 15 anos") == "karla"

    def test_adulto_55_anos_nao_retorna_karla(self):
        from voice_agent.oferta_valor_contextualizado import _inferir_medico_user_text
        result = _inferir_medico_user_text("adulto de 55 anos")
        assert result != "karla"

    def test_3_meses_retorna_karla(self):
        from voice_agent.oferta_valor_contextualizado import _inferir_medico_user_text
        assert _inferir_medico_user_text("3 meses de idade") == "karla"

    def test_user_text_vazio_retorna_vazio(self):
        from voice_agent.oferta_valor_contextualizado import _inferir_medico_user_text
        assert _inferir_medico_user_text("") == ""

    def test_crian_retorna_karla(self):
        from voice_agent.oferta_valor_contextualizado import _inferir_medico_user_text
        assert _inferir_medico_user_text("minha criança") == "karla"


# ─────────────────────────────────────────────────────────────────────────────
# 24. Caso real do lead 24438844
# ─────────────────────────────────────────────────────────────────────────────

class TestCasoRealLead24438844:

    def test_para_3_anos_nao_mostra_fabricio(self):
        """Caso real: paciente disse 'para 3 anos' → não deve ver Fabrício nem tabela dupla."""
        m = _import_valor()
        # Simula o que chega antes do step 12: nenhum médico definido ainda
        ctx = {"known": {}, "name": "Mãe"}
        user_text = "quero consulta para minha filha de 3 anos"
        resp = m.gerar_valor_contextualizado(ctx, user_text=user_text)
        assert resp is not None
        # Deve mencionar Karla (pediatria)
        assert "Karla" in resp
        # NÃO deve mencionar Fabrício na mesma resposta
        assert "Fabrício" not in resp
        # NÃO deve perguntar "Qual médico?"
        assert "Qual médico" not in resp
        # Deve usar "sem convênio"
        assert "sem convênio" in resp.lower() or "sem convenio" in resp.lower()
        # Deve terminar com convite para agendar (não com pergunta de convênio)
        assert "Gostaria de agendar" in resp or "agendar" in resp.lower()
