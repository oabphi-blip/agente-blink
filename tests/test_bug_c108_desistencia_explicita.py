"""
Bug C-108 (11/08/2026) — Desistência explícita do paciente.

Cenários:
  1.  "desisti" → detectado
  2.  "não quero mais" → detectado
  3.  "vou em outro lugar" → detectado
  4.  "vou em outra clínica" → detectado
  5.  "já marquei em outro lugar" → detectado
  6.  "pode cancelar tudo" → detectado
  7.  "deixa pra lá" → detectado
  8.  "não vou mais marcar" → detectado
  9.  "encerrar o atendimento" → detectado
 10.  "não tenho interesse" → detectado
 11.  "não quero esse horário" → NÃO detectado (recusando slot, não desistindo)
 12.  "não quero de manhã" → NÃO detectado (preferência)
 13.  "vou tentar outro horário" → NÃO detectado (querendo outro slot)
 14.  texto vazio → NÃO detectado
 15.  Resposta contém "entendemos" ou equivalente (não rejeita)
 16.  Resposta sugere retorno futuro
 17.  Resposta NÃO pergunta "tem certeza?"
 18.  Resposta NÃO oferece desconto ou salvamento
 19.  Resposta termina com boa mensagem (não pergunta)
 20.  Toggle OFF → None
 21.  ctx=None → None
 22.  Step 14 enriquecimento: "desisti" → desistencia_explicita=True
 23.  Step 14: texto neutro → flag não injetado
 24.  flag known ativa sem regex no user_text
 25.  Bypass está ANTES de urgência na chain (primeira posição)
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def toggle_on(monkeypatch):
    monkeypatch.setenv("DESISTENCIA_ATIVADO", "1")
    yield


def _import():
    import importlib
    import voice_agent.desistencia as m
    importlib.reload(m)
    return m


def _ctx(nome="Ana", lead_id=99999):
    return {"name": nome, "lead_id": lead_id, "known": {}}


# ─────────────────────────────────────────────────────────────────────────────
# 1-10. Detecção positiva
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccaoPositiva:

    @pytest.mark.parametrize("texto", [
        "desisti",
        "desisto mesmo",
        "não quero mais",
        "não tenho mais interesse",
        "não preciso mais",
        "vou em outro lugar",
        "vou em outra clínica",
        "vou buscar outro médico",
        "já marquei em outro lugar",
        "já agendei em outra clínica",
        "pode cancelar tudo",
        "cancela tudo",
        "deixa pra lá",
        "não vou mais marcar",
        "não vou mais agendar",
        "pode encerrar o atendimento",
        "encerra a conversa",
        "não tenho interesse",
        "obrigada, mas não",
        "prefiro outro lugar",
    ])
    def test_detecta_desistencia(self, texto):
        m = _import()
        assert m.detectar_desistencia(texto), f"Deveria detectar em: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 11-14. Detecção negativa
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccaoNegativa:

    @pytest.mark.parametrize("texto", [
        "não quero esse horário",
        "não quero de manhã",
        "vou tentar outro horário",
        "não preciso do horário das 9h",
        "",
        "quero agendar",
        "qual o valor?",
        "não quero mais esse slot",
    ])
    def test_nao_detecta_falso_positivo(self, texto):
        m = _import()
        assert not m.detectar_desistencia(texto), f"Falso positivo em: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 15-19. Qualidade da resposta
# ─────────────────────────────────────────────────────────────────────────────

class TestQualidadeResposta:

    def _resp(self, texto="desisti"):
        m = _import()
        return m.deve_responder_desistencia(_ctx(), user_text=texto)

    def test_resposta_contem_reconhecimento(self):
        r = self._resp()
        assert r is not None
        assert any(k in r.lower() for k in ("entendemos", "entendo", "tudo bem", "claro"))

    def test_resposta_sugere_retorno_futuro(self):
        r = self._resp()
        assert r is not None
        assert any(k in r.lower() for k in ("quando precisar", "sempre que", "retornar", "estaremos aqui"))

    def test_resposta_nao_pergunta_tem_certeza(self):
        r = self._resp()
        assert r is not None
        assert "tem certeza" not in r.lower()
        assert "certeza" not in r.lower()

    def test_resposta_nao_oferece_desconto(self):
        r = self._resp()
        assert r is not None
        assert "desconto" not in r.lower()
        assert "oferta especial" not in r.lower()
        assert "promoção" not in r.lower()

    def test_resposta_nao_termina_com_pergunta(self):
        r = self._resp()
        assert r is not None
        # Não deve terminar com "?" — não é para prender o paciente
        assert not r.strip().endswith("?")


# ─────────────────────────────────────────────────────────────────────────────
# 20-21. Toggle e ctx=None
# ─────────────────────────────────────────────────────────────────────────────

class TestToggleEFallback:

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("DESISTENCIA_ATIVADO", "0")
        m = _import()
        assert m.deve_responder_desistencia(_ctx(), user_text="desisti") is None

    def test_ctx_none_retorna_none(self):
        m = _import()
        assert m.deve_responder_desistencia(None, user_text="desisti") is None


# ─────────────────────────────────────────────────────────────────────────────
# 22-24. Step 14 enriquecimento + flag known
# ─────────────────────────────────────────────────────────────────────────────

class TestStep14:

    def _enriquecer_step14(self, user_text, known=None):
        from voice_agent.desistencia import detectar_desistencia
        k = dict(known or {})
        if user_text and not k.get("desistencia_explicita"):
            if detectar_desistencia(user_text):
                k["desistencia_explicita"] = True
        return k

    def test_desisti_injeta_flag(self):
        k = self._enriquecer_step14("desisti")
        assert k.get("desistencia_explicita") is True

    def test_texto_neutro_nao_injeta(self):
        k = self._enriquecer_step14("qual o horário?")
        assert not k.get("desistencia_explicita")

    def test_flag_known_ativa_sem_regex(self):
        m = _import()
        ctx = {"name": "Maria", "lead_id": 123, "known": {"desistencia_explicita": True}}
        resp = m.deve_responder_desistencia(ctx, user_text="qual o horário?")
        assert resp is not None
        assert any(k in resp.lower() for k in ("entendemos", "tudo bem", "quando precisar"))


# ─────────────────────────────────────────────────────────────────────────────
# 25. Posição na chain of responsibility
# ─────────────────────────────────────────────────────────────────────────────

class TestPosicaoNaChain:

    def test_desistencia_antes_da_urgencia_no_codigo(self):
        """Verifica que C-108 está posicionado ANTES da chamada de deve_orientar_urgencia
        dentro da função tentar_bypass_deterministico."""
        with open("voice_agent/blindagens_deterministicas.py") as f:
            conteudo = f.read()

        # Encontrar o corpo da função tentar_bypass_deterministico
        inicio_func = conteudo.find("def tentar_bypass_deterministico(")
        assert inicio_func >= 0, "Função tentar_bypass_deterministico não encontrada"

        corpo = conteudo[inicio_func:]

        # Dentro do corpo, C-108 deve aparecer antes da chamada a deve_orientar_urgencia
        pos_c108 = corpo.find("C-108")
        # Procurar a chamada (não a definição) — "deve_orientar_urgencia(ctx" é a call site
        pos_urgencia_call = corpo.find("deve_orientar_urgencia(ctx")

        assert pos_c108 >= 0, "Bloco C-108 não encontrado em tentar_bypass_deterministico"
        assert pos_urgencia_call >= 0, "Chamada a deve_orientar_urgencia não encontrada em tentar_bypass_deterministico"
        assert pos_c108 < pos_urgencia_call, (
            f"C-108 (pos={pos_c108}) deve aparecer ANTES da chamada de "
            f"deve_orientar_urgencia (pos={pos_urgencia_call}) na chain"
        )
