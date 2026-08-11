"""
Bug C-107 (11/08/2026) — Quebra de objeção de preço.

Cenários cobertos:
  1.  "caro" → detectado
  2.  "muito cara" → detectado
  3.  "encontrei mais barato" → detectado
  4.  "sai mais barato em outro lugar" → detectado
  5.  "não tenho esse valor" → detectado
  6.  "consegui por menos" → detectado
  7.  "preço alto" → detectado
  8.  "não tenho esse dinheiro" → detectado
  9.  "sem condições de pagar" → detectado
 10.  "outra clínica é mais barato" → detectado
 11.  "achei mais barato" → detectado
 12.  "não é caro" → NÃO detectado (negação protege)
 13.  "bom preço" → NÃO detectado
 14.  "aceito o valor" → NÃO detectado
 15.  user_text vazio → NÃO detectado
 16.  Resposta pediátrica (Dra. Karla Delalíbera) contém: especialidade pediátrica,
      parcelamento 2x R$ 335, alternativas, pergunta final
 17.  Resposta pediátrica NÃO fecha a conversa (não diz "encerramos")
 18.  Resposta APV menciona "2 a 3 horas" / R$ 435/parcela
 19.  Resposta Dra. Karla Delalíbera adulto contém tonometria + retina + parcelamento
 20.  Resposta Dr. Fabrício Freitas catarata menciona biometria + R$ 235/parcela
 21.  Resposta Dr. Fabrício Freitas geral menciona saúde ocular + parcelamento
 22.  Resposta geral (sem médico) contém alternativas
 23.  Âncora clínica: sintoma + semanas → aparece na resposta
 24.  Âncora clínica: sintoma sem tempo → aparece de forma genérica
 25.  Âncora clínica: sem sintoma → não aparece
 26.  Toggle OFF → None
 27.  ctx=None → None (fail-open)
 28.  step 13 enriquecimento: "caro" → objecao_preco=True
 29.  step 13: texto neutro → objecao_preco não injetado
 30.  step 13: objecao_preco já True → não reprocessa
 31.  Nenhuma resposta contém "justo" / "mercado" (não dismissar)
 32.  Nenhuma resposta contém "particular" (regra sem convênio)
 33.  Todas as respostas terminam com pergunta ao paciente
 34.  Caso real Gael lead 24436018: bebê + conjuntivite 3 semanas → resposta pediátrica
      com âncora "3 semanas" e alternativas
 35.  known.objecao_preco=True → ativa mesmo sem regex no user_text
 36.  Resposta pediátrica menciona "Dra. Karla Delalíbera" nome completo
 37.  Resposta Fabrício catarata menciona "Dr. Fabrício Freitas" nome completo
"""

from __future__ import annotations

import os
import re
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def toggle_on(monkeypatch):
    monkeypatch.setenv("OBJECAO_PRECO_ATIVADO", "1")
    yield


def _import():
    import importlib
    import voice_agent.objecao_preco as m
    importlib.reload(m)
    return m


def _ctx(medico="", motivo="", idade=None, pediatrico=False, nome="Suely", notas=None):
    known = {}
    if medico:
        known["medico"] = medico
    if motivo:
        known["motivo"] = motivo
    if idade is not None:
        known["idade"] = idade
    if pediatrico:
        known["contexto_pediatrico"] = True
    c = {"known": known, "name": nome}
    if notas:
        c["notas"] = notas
    return c


# ─────────────────────────────────────────────────────────────────────────────
# 1-11. Detecção positiva
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccaoPositiva:

    @pytest.mark.parametrize("texto", [
        "está caro",
        "muito cara",
        "achei muito caro",
        "encontrei mais barato em outro lugar",
        "sai mais barato no hospital",
        "não tenho esse valor",
        "consegui por menos",
        "o preço está alto",
        "não tenho esse dinheiro",
        "sem condições de pagar",
        "outra clínica é mais barato",
        "achei mais barato",
        "é caríssimo",
        "ficou caro demais",
        "não dá para pagar",
        "encontrei por 170 reais",
    ])
    def test_detecta_objecao(self, texto):
        m = _import()
        assert m.detectar_objecao_preco(texto), f"Deveria detectar objeção em: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 12-15. Detecção negativa
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccaoNegativa:

    @pytest.mark.parametrize("texto", [
        "não é caro",
        "bom preço",
        "aceito o valor",
        "tá ótimo",
        "gostei do preço",
        "",
        "quero agendar",
        "qual o horário disponível",
    ])
    def test_nao_detecta_falso_positivo(self, texto):
        m = _import()
        assert not m.detectar_objecao_preco(texto), f"Falso positivo em: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 16-22. Templates por contexto
# ─────────────────────────────────────────────────────────────────────────────

class TestTemplatesPorContexto:

    def test_pediatrico_contem_especialidade_karla(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", pediatrico=True, idade=8),
            user_text="está caro"
        )
        assert resp is not None
        assert "Dra. Karla Delalíbera" in resp
        assert any(k in resp.lower() for k in ("pediátrica", "pediatr", "bebê", "criança"))

    def test_pediatrico_contem_parcelamento_335(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", pediatrico=True, idade=3),
            user_text="achei caro"
        )
        assert resp is not None
        assert "335" in resp
        assert "2x" in resp.lower() or "2 x" in resp.lower() or "parcelamento" in resp.lower()

    def test_pediatrico_nao_fecha_conversa(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", pediatrico=True),
            user_text="muito caro"
        )
        assert resp is not None
        assert "encerramos" not in resp.lower()
        assert "encerro" not in resp.lower()

    def test_apv_menciona_duracao_avaliacao(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", motivo="processamento visual"),
            user_text="está caro"
        )
        assert resp is not None
        assert any(k in resp for k in ("2 a 3 horas", "2-3 horas", "435"))

    def test_karla_adulto_menciona_retina_e_parcelamento(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", motivo="rotina"),
            user_text="encontrei mais barato"
        )
        assert resp is not None
        assert "335" in resp
        assert any(k in resp.lower() for k in ("retina", "tonometria", "completa"))

    def test_fabricio_catarata_menciona_biometria(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Fabrício", motivo="catarata"),
            user_text="sai mais barato em outro lugar"
        )
        assert resp is not None
        assert "biometria" in resp.lower()
        assert "Dr. Fabrício Freitas" in resp

    def test_fabricio_catarata_parcelamento_235(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Fabrício", motivo="catarata"),
            user_text="não tenho esse valor"
        )
        assert resp is not None
        assert "235" in resp

    def test_fabricio_geral_menciona_saude_ocular(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Fabrício", motivo="rotina"),
            user_text="achei caro"
        )
        assert resp is not None
        assert "Dr. Fabrício Freitas" in resp
        assert any(k in resp.lower() for k in ("ocular", "saúde"))

    def test_sem_medico_retorna_resposta_geral(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(_ctx(), user_text="está caro")
        assert resp is not None
        assert "parcelamento" in resp.lower() or "2x" in resp.lower() or "335" in resp


# ─────────────────────────────────────────────────────────────────────────────
# 23-25. Âncora clínica
# ─────────────────────────────────────────────────────────────────────────────

class TestAncoraClinica:

    def test_sintoma_com_semanas_aparece_na_resposta(self):
        m = _import()
        notas = [{"text": "conjuntivite há 3 semanas"}]
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", pediatrico=True, notas=notas),
            user_text="caro"
        )
        assert resp is not None
        assert "3 semanas" in resp

    def test_sintoma_sem_tempo_aparece_genericamente(self):
        m = _import()
        notas = [{"text": "irritação ocular"}]
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", notas=notas),
            user_text="muito caro"
        )
        assert resp is not None
        assert "diagnóstico" in resp.lower() or "especializ" in resp.lower()

    def test_sem_sintoma_nao_tem_ancora(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", motivo="rotina"),
            user_text="caro"
        )
        assert resp is not None
        # Âncora clínica não deve aparecer (sem sintoma no ctx)
        assert "semanas" not in resp
        assert "diagnóstico correto" not in resp


# ─────────────────────────────────────────────────────────────────────────────
# 26-27. Toggle e fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestToggleEFallback:

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("OBJECAO_PRECO_ATIVADO", "0")
        m = _import()
        resp = m.deve_responder_objecao_preco(_ctx(medico="Karla"), user_text="está caro")
        assert resp is None

    def test_ctx_none_retorna_none(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(None, user_text="caro")
        assert resp is None


# ─────────────────────────────────────────────────────────────────────────────
# 28-30. Step 13 — enriquecimento_ctx
# ─────────────────────────────────────────────────────────────────────────────

class TestStep13EnriquecimentoCtx:

    def _enriquecer_step13(self, user_text, known=None):
        """Replica o step 13 de enriquecimento_ctx."""
        from voice_agent.objecao_preco import detectar_objecao_preco
        k = dict(known or {})
        if user_text and not k.get("objecao_preco"):
            if detectar_objecao_preco(user_text):
                k["objecao_preco"] = True
        return k

    def test_caro_injeta_flag(self):
        k = self._enriquecer_step13("está caro")
        assert k.get("objecao_preco") is True

    def test_texto_neutro_nao_injeta(self):
        k = self._enriquecer_step13("quero agendar")
        assert not k.get("objecao_preco")

    def test_flag_ja_true_nao_reprocessa(self):
        k = self._enriquecer_step13("caro", known={"objecao_preco": True, "medico": "Karla"})
        # Flag permanece True, não deve criar duplicidade
        assert k.get("objecao_preco") is True
        assert k.get("medico") == "Karla"  # ctx não corrompido


# ─────────────────────────────────────────────────────────────────────────────
# 31-33. Regras universais para todas as respostas
# ─────────────────────────────────────────────────────────────────────────────

class TestRegrasUniversais:

    @pytest.mark.parametrize("medico,motivo,pediatrico,idade", [
        ("Karla", "", True, 3),
        ("Karla", "apv", False, None),
        ("Karla", "rotina", False, None),
        ("Fabrício", "catarata", False, None),
        ("Fabrício", "rotina", False, None),
        ("", "", False, None),
    ])
    def test_nenhuma_resposta_dismisssa(self, medico, motivo, pediatrico, idade):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico=medico, motivo=motivo, pediatrico=pediatrico, idade=idade),
            user_text="está caro"
        )
        assert resp is not None
        # Não pode dismissar a objeção
        assert "preço é justo" not in resp.lower()
        assert "valor de mercado" not in resp.lower()
        assert "cobro o mínimo" not in resp.lower()

    @pytest.mark.parametrize("medico,motivo,pediatrico,idade", [
        ("Karla", "", True, 3),
        ("Karla", "apv", False, None),
        ("Karla", "rotina", False, None),
        ("Fabrício", "catarata", False, None),
    ])
    def test_nenhuma_resposta_usa_particular(self, medico, motivo, pediatrico, idade):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico=medico, motivo=motivo, pediatrico=pediatrico, idade=idade),
            user_text="muito caro"
        )
        assert resp is not None
        assert "consulta particular" not in resp.lower()
        assert "atendimento particular" not in resp.lower()

    @pytest.mark.parametrize("medico,motivo,pediatrico", [
        ("Karla", "", True),
        ("Karla", "rotina", False),
        ("Fabrício", "catarata", False),
        ("", "", False),
    ])
    def test_toda_resposta_tem_pergunta_final(self, medico, motivo, pediatrico):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico=medico, motivo=motivo, pediatrico=pediatrico),
            user_text="encontrei mais barato"
        )
        assert resp is not None
        # Deve terminar com pergunta (? no final do texto)
        assert resp.strip().endswith("?")


# ─────────────────────────────────────────────────────────────────────────────
# 34. Caso real — Gael lead 24436018
# ─────────────────────────────────────────────────────────────────────────────

class TestCasoRealGael:

    def test_gael_bebe_conjuntivite_3_semanas(self):
        """
        Lead 24436018: Gael, bebê 8 meses, conjuntivite 3 semanas, Karla, Asa Norte.
        Atendente humana ofereceu desconto do sábado por telefone — tarde demais.
        Python deve entregar o script antes de o paciente ir embora.
        """
        m = _import()
        notas = [{"text": "Ele está apresentando uma irritação que parece conjuntivite há 3 semanas"}]
        ctx = _ctx(
            medico="Karla",
            motivo="irritação ocular, conjuntivite",
            pediatrico=True,
            idade=0,  # bebê
            nome="Suely",
            notas=notas,
        )
        resp = m.deve_responder_objecao_preco(ctx, user_text="encontrei por 170 reais")
        assert resp is not None
        # Menciona Dra. Karla Delalíbera (nome completo)
        assert "Dra. Karla Delalíbera" in resp
        # Âncora clínica (3 semanas)
        assert "3 semanas" in resp
        # Especialidade pediátrica
        assert any(k in resp.lower() for k in ("pediatr", "bebê", "recém-nasc", "criança"))
        # Alternativas
        assert "335" in resp
        # Não fecha a conversa
        assert "encerramos" not in resp.lower()
        # Termina com pergunta
        assert resp.strip().endswith("?")


# ─────────────────────────────────────────────────────────────────────────────
# 35-37. Casos de borda
# ─────────────────────────────────────────────────────────────────────────────

class TestCasosDeBorda:

    def test_flag_known_ativa_sem_regex(self):
        """known.objecao_preco=True deve ativar mesmo sem objeção no user_text."""
        m = _import()
        ctx = {"known": {"medico": "Karla", "objecao_preco": True}, "name": "Maria"}
        resp = m.deve_responder_objecao_preco(ctx, user_text="quando tem horário?")
        assert resp is not None
        assert "Dra. Karla Delalíbera" in resp

    def test_pediatrico_nome_completo_karla(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Karla", pediatrico=True, idade=5),
            user_text="caro"
        )
        assert resp is not None
        assert "Dra. Karla Delalíbera" in resp

    def test_fabricio_catarata_nome_completo(self):
        m = _import()
        resp = m.deve_responder_objecao_preco(
            _ctx(medico="Fabrício", motivo="catarata"),
            user_text="está caro"
        )
        assert resp is not None
        assert "Dr. Fabrício Freitas" in resp
