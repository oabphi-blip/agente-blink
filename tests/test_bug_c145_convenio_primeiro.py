"""pytest — Bug C-145 (14/08/2026): Convênio verificado ANTES dos dados do paciente.

Lead 24456884 (Beatriz/Amil): paciente perguntou "Vocês aceitam o plano de
saúde Amil?" na 1ª mensagem. C-136 disparou antes e perguntou perfil.
5 turnos desperdiçados. Amil não é aceito.

Fix: C-145 pergunta convênio primeiro quando desconhecido, C-136 tem guard.
"""
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voice_agent.convenio_primeiro import deve_perguntar_convenio_primeiro_c145
from voice_agent.pergunta_perfil import deve_perguntar_perfil


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(known=None, *, lead_id=24456884):
    return {
        "lead_id": lead_id,
        "known": known or {},
    }


def _ctx_com_convenio(conv="Bacen"):
    """Ctx com convênio já definido — C-145 não deve disparar."""
    return _ctx({"convenio": conv})


def _ctx_convenio_aceito(aceito=True):
    """Ctx com convenio_aceito já derivado."""
    return _ctx({"convenio_aceito": aceito})


def _ctx_sem_convenio():
    """Ctx com paciente sem convênio (escolheu Seguir Sem Convênio)."""
    return _ctx({"sem_convenio": True})


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 1 — deve_perguntar_convenio_primeiro_c145
# ═══════════════════════════════════════════════════════════════════════════


class TestC145ConvenioPrimeiro:
    """Testes do módulo convenio_primeiro.py."""

    # --- Caso feliz: dispara quando convênio desconhecido ---

    def test_dispara_quando_convenio_desconhecido_saudacao(self):
        """'Boa tarde' → convênio desconhecido → pergunta convênio primeiro."""
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "Boa tarde")
        assert res is not None
        assert "plano de saúde ou sem convênio" in res.lower()

    def test_dispara_quando_convenio_desconhecido_pedido_generrico(self):
        """'Quero marcar uma consulta' → sem convênio → pergunta."""
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "Quero marcar uma consulta")
        assert res is not None
        assert "plano de saúde ou sem convênio" in res.lower()

    def test_resposta_inclui_nome_contato_quando_disponivel(self):
        """Quando nome_contato disponível, pergunta começa com o nome."""
        ctx = _ctx({"nome_contato": "Beatriz Silva"})
        res = deve_perguntar_convenio_primeiro_c145(ctx, "Quero agendar")
        assert res is not None
        assert res.startswith("Beatriz,")

    def test_resposta_sem_nome_quando_nao_disponivel(self):
        """Sem nome_contato → sem saudação."""
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "Oi quero consulta")
        assert res is not None
        assert not res.startswith(",")

    # --- Caso do bug real: "Vocês aceitam Amil?" ---

    def test_nao_dispara_quando_nome_plano_mencionado_amil(self):
        """'Vocês aceitam Amil?' — menciona Amil → faq_convenio_aceito trata."""
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Vocês aceitam o plano de saúde Amil?"
        )
        assert res is None, "faq_convenio_aceito deve tratar, não C-145"

    def test_nao_dispara_quando_nome_plano_mencionado_bacen(self):
        """'Vocês aceitam Bacen?' → C-145 não dispara."""
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Quero saber se vocês aceitam Bacen"
        )
        assert res is None

    def test_nao_dispara_quando_nome_plano_unimed(self):
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Atende pelo Unimed?"
        )
        assert res is None

    def test_nao_dispara_quando_nome_plano_bradesco(self):
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Tenho Bradesco, aceita?"
        )
        assert res is None

    # --- Não dispara quando FAQ genérico de convênio ---

    def test_nao_dispara_quando_faq_convenio_generico_aceitam(self):
        """'Vocês aceitam convênio?' → faq_convenio_aceito trata."""
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Vocês aceitam convênio?"
        )
        assert res is None

    def test_nao_dispara_quando_faq_tem_convenio(self):
        """'Tem convênio?' → faq_convenio_aceito trata."""
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "Tem convênio?")
        assert res is None

    # --- Não dispara quando convênio já resolvido ---

    def test_nao_dispara_quando_convenio_ja_definido(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx_com_convenio("Bacen"), "Oi")
        assert res is None

    def test_nao_dispara_quando_convenio_aceito_derivado(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx_convenio_aceito(True), "Oi")
        assert res is None

    def test_nao_dispara_quando_convenio_recusado_derivado(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx_convenio_aceito(False), "Oi")
        assert res is None

    def test_nao_dispara_quando_sem_convenio_flag(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx_sem_convenio(), "Quero agendar")
        assert res is None

    # --- Não dispara quando paciente disse "sem convênio" no texto ---

    def test_nao_dispara_quando_paciente_diz_sem_convenio(self):
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Quero agendar sem convênio"
        )
        assert res is None

    def test_nao_dispara_quando_paciente_diz_pagar_direto(self):
        res = deve_perguntar_convenio_primeiro_c145(
            _ctx(), "Vou pagar direto, sem plano"
        )
        assert res is None

    # --- Anti-loop ---

    def test_nao_dispara_quando_ja_perguntou_convenio(self):
        """Anti-loop: última outbound já perguntou sobre convênio."""
        ctx = _ctx(
            {"ultima_msg_outbound": "a consulta seria pelo seu plano de saúde ou sem convênio? 😊"}
        )
        res = deve_perguntar_convenio_primeiro_c145(ctx, "Oi")
        assert res is None

    # --- Outros guards ---

    def test_nao_dispara_quando_ja_agendado(self):
        ctx = _ctx({"ja_agendado": True})
        res = deve_perguntar_convenio_primeiro_c145(ctx, "Quero remarcar")
        assert res is None

    def test_nao_dispara_quando_texto_muito_curto(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "hi")
        assert res is None

    def test_nao_dispara_quando_texto_vazio(self):
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "")
        assert res is None

    def test_nao_dispara_quando_ctx_none(self):
        res = deve_perguntar_convenio_primeiro_c145(None, "Quero agendar")
        assert res is None

    # --- Toggle ---

    def test_toggle_off_nao_dispara(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_CONVENIO_PRIMEIRO_C145_ATIVADO", "0")
        from voice_agent import convenio_primeiro
        monkeypatch.setattr(convenio_primeiro, "_ativado", lambda: False)
        res = deve_perguntar_convenio_primeiro_c145(_ctx(), "Quero agendar")
        assert res is None


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 2 — Guard em deve_perguntar_perfil (C-136 com C-145)
# ═══════════════════════════════════════════════════════════════════════════


class TestC136GuardC145:
    """Guard em pergunta_perfil.py: C-136 retorna None quando convênio desconhecido."""

    def test_c136_nao_dispara_quando_convenio_desconhecido(self):
        """C-136 não deve perguntar perfil quando convênio ainda desconhecido."""
        ctx = _ctx()  # sem convenio, sem convenio_aceito, sem sem_convenio
        res = deve_perguntar_perfil(ctx, "Quero marcar uma consulta")
        assert res is None, (
            "C-136 deve retornar None quando convenio desconhecido — C-145 pergunta primeiro"
        )

    def test_c136_nao_dispara_saudacao_simples(self):
        """'Boa tarde' → sem convênio no ctx → C-136 retorna None."""
        ctx = _ctx()
        res = deve_perguntar_perfil(ctx, "Boa tarde")
        assert res is None

    def test_c136_dispara_quando_convenio_definido(self):
        """Convênio definido → C-136 pode perguntar perfil normalmente."""
        ctx = _ctx({"convenio": "Bacen"})
        res = deve_perguntar_perfil(ctx, "Quero consulta para minha filha")
        # Pode ser None (perfil detectado no texto) mas NÃO deve ser None pelo guard
        # "filha" → _RE_PERFIL_JA_DADO matches → retorna None
        # Vamos usar texto sem pista de perfil
        res = deve_perguntar_perfil(ctx, "Quero agendar uma consulta")
        assert res is not None, "Com convênio definido, C-136 deve disparar normalmente"
        assert "bebê" in res.lower() or "criança" in res.lower()

    def test_c136_dispara_quando_convenio_aceito_true(self):
        """convenio_aceito=True → convênio resolvido → C-136 pode disparar."""
        ctx = _ctx({"convenio_aceito": True, "convenio": "Bacen"})
        res = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res is not None

    def test_c136_dispara_quando_sem_convenio_flag(self):
        """sem_convenio=True → paciente escolheu sem conv → C-136 pode disparar."""
        ctx = _ctx({"sem_convenio": True})
        res = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res is not None
        assert "bebê" in res.lower() or "criança" in res.lower()

    def test_c136_nao_dispara_quando_texto_tem_faixa_etaria(self):
        """Faixa etária no texto → _RE_PERFIL_JA_DADO → C-136 retorna None (mesmo com conv)."""
        ctx = _ctx({"convenio": "Bacen"})
        res = deve_perguntar_perfil(ctx, "minha filha tem 3 anos")
        assert res is None


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 3 — Integração: fluxo completo lead 24456884 Beatriz/Amil
# ═══════════════════════════════════════════════════════════════════════════


class TestFluxoCompletoC145:
    """Simula o fluxo real do lead 24456884."""

    def test_turno1_amil_perguntado_c145_nao_dispara_c136_nao_dispara(self):
        """Turno 1: 'Vocês aceitam o plano de saúde Amil?'
        → C-145 não dispara (nome de plano no texto)
        → faq_convenio_aceito deve tratar (recusa)
        → C-136 não dispara (guard)
        """
        user_text = "Vocês aceitam o plano de saúde Amil?"
        ctx = _ctx()

        # C-145 não interfere (faq_convenio_aceito deve tratar)
        res_c145 = deve_perguntar_convenio_primeiro_c145(ctx, user_text)
        assert res_c145 is None, "C-145 não deve disparar quando Amil mencionado"

        # C-136 também não interfere (convênio desconhecido)
        res_c136 = deve_perguntar_perfil(ctx, user_text)
        assert res_c136 is None, "C-136 não deve disparar quando convênio desconhecido"

    def test_turno1_generico_c145_dispara(self):
        """Turno 1: 'Boa tarde, quero agendar'
        → C-145 dispara → pergunta convênio primeiro
        → C-136 não dispara (guard)
        """
        user_text = "Boa tarde, quero agendar uma consulta"
        ctx = _ctx()

        res_c145 = deve_perguntar_convenio_primeiro_c145(ctx, user_text)
        assert res_c145 is not None, "C-145 deve perguntar convênio primeiro"
        assert "plano de saúde ou sem convênio" in res_c145.lower()

        # C-136 com guard retorna None
        res_c136 = deve_perguntar_perfil(ctx, user_text)
        assert res_c136 is None, "C-136 não deve disparar enquanto convênio desconhecido"

    def test_turno2_paciente_responde_sem_convenio_c136_dispara(self):
        """Turno 2: após C-145 perguntar, paciente diz 'sem convênio'
        → C-145 não dispara (sem_convenio=True)
        → C-136 dispara → pergunta perfil
        """
        # Simulando ctx após pipeline enriquecer com sem_convenio=True
        ctx = _ctx({"sem_convenio": True})
        user_text = "Sem convênio mesmo"

        res_c145 = deve_perguntar_convenio_primeiro_c145(ctx, user_text)
        assert res_c145 is None, "sem_convenio=True → C-145 não dispara"

        res_c136 = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res_c136 is not None, "sem_convenio=True → C-136 pode disparar"
        assert "bebê" in res_c136.lower() or "criança" in res_c136.lower()

    def test_turno2_paciente_informa_plano_aceito_c136_dispara(self):
        """Turno 2: paciente diz 'Bacen' (aceito)
        → enriquecimento_ctx seta convenio='Bacen'
        → C-145 não dispara (convenio definido)
        → C-136 dispara → pergunta perfil
        """
        ctx = _ctx({"convenio": "Bacen", "convenio_aceito": True})

        res_c145 = deve_perguntar_convenio_primeiro_c145(ctx, "É pelo Bacen")
        assert res_c145 is None

        res_c136 = deve_perguntar_perfil(ctx, "É pelo Bacen")
        assert res_c136 is not None
        assert "bebê" in res_c136.lower() or "criança" in res_c136.lower()

    def test_ordem_chain_c145_antes_c136(self):
        """Verifica indiretamente que C-145 dispara ANTES de C-136.
        Quando convenio desconhecido: C-145=resposta, C-136=None.
        Isso implica C-145 vir primeiro na chain e C-136 ter guard.
        """
        ctx = _ctx()
        ut = "Quero agendar"

        r145 = deve_perguntar_convenio_primeiro_c145(ctx, ut)
        r136 = deve_perguntar_perfil(ctx, ut)

        assert r145 is not None, "C-145 deve disparar (convênio desconhecido)"
        assert r136 is None, "C-136 deve retornar None (guard: convênio desconhecido)"
        # A chain em blindagens retorna C-145 primeiro — comportamento correto


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 4 — Regressão C-136 (casos que C-136 deve continuar cobrindo)
# ═══════════════════════════════════════════════════════════════════════════


class TestRegressaoC136:
    """Garante que o guard C-145 não quebrou casos legítimos de C-136."""

    def test_c136_dispara_com_convenio_nao_se_aplica(self):
        """Convênio = 'Não se aplica' → considerado resolvido → C-136 pode disparar."""
        ctx = _ctx({"convenio": "Não se aplica"})
        res = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res is not None

    def test_c136_nao_repete_quando_ultima_outbound_tem_pergunta(self):
        """Anti-loop C-136: se já perguntou 'bebê, criança', não repete."""
        ctx = _ctx({
            "convenio": "Bacen",
            "ultima_msg_outbound": "pode me contar se a consulta é para um bebê, criança, adolescente ou adulto?",
        })
        res = deve_perguntar_perfil(ctx, "Oi")
        assert res is None

    def test_c136_nao_dispara_quando_perfil_ja_no_ctx(self):
        """perfil_paciente já definido → C-136 não dispara."""
        ctx = _ctx({"convenio": "Bacen", "perfil_paciente": "criança"})
        res = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res is None

    def test_c136_nao_dispara_quando_medico_ja_derivado(self):
        """Médico já derivado → C-136 não dispara."""
        ctx = _ctx({"convenio": "Bacen", "medico": "Karla"})
        res = deve_perguntar_perfil(ctx, "Quero agendar")
        assert res is None


# ═══════════════════════════════════════════════════════════════════════════
# PARTE 5 — Smoke: módulo importa sem erro
# ═══════════════════════════════════════════════════════════════════════════


def test_importa_sem_erro():
    from voice_agent.convenio_primeiro import deve_perguntar_convenio_primeiro_c145  # noqa: F401
    assert True


def test_fail_open_ctx_none():
    """ctx=None → fail-open: retorna None (deixar LLM decidir)."""
    res = deve_perguntar_convenio_primeiro_c145(None, "Quero agendar")
    # ctx=None → módulo retorna None pra fail-open (não entrar na triagem sem ctx)
    assert res is None


def test_fail_open_user_text_none():
    """user_text=None nunca explode."""
    res = deve_perguntar_convenio_primeiro_c145(_ctx(), None)
    assert res is None
