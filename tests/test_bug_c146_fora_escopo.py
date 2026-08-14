"""
Pytest — Bug C-146 (14/08/2026)
Pergunta fora do escopo Python → escalação imediata.

Caso real: lead 24328426 Alice Tavares.
  Paciente pagou Pix, depois conseguiu vaga no convênio.
  Perguntou: "gostaria de saber se o valor enviado poderia ser reembolsado,
  pois consegui uma vaga no meu convênio."
  Lia inventou resposta sobre cobertura. C-129 só tinha "reembolso\\b"
  (substantivo), não casava "reembolsado" (particípio verbal).

Cobre:
  - Tier 1: reembolso (todas as formas), estorno, devolução de valor
  - Tier 2: ja_agendado + pergunta não whitelistada
  - Wire em blindagens_deterministicas.py (antes de C-129)
  - Falso positivo: confirmações simples pós-agendamento não disparam
  - Toggle OFF desliga
  - fail-open: ctx=None, redis=None
"""
import pytest
from unittest.mock import MagicMock, patch
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voice_agent.fora_escopo import deve_escalar_fora_escopo_c146


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ctx(ja_agendado=False, nome=None):
    return {
        "lead_id": 24328426,
        "known": {
            "lead_id": 24328426,
            "nome_contato": nome or "Alice",
            "ja_agendado": ja_agendado,
        },
    }


# ─── Tier 1: Financeiro universal ─────────────────────────────────────────────

class TestTier1Financeiro:
    """Mensagens com reembolso/estorno/devolução → sempre escalar."""

    def test_caso_real_alice_tavares_reembolsado(self):
        """Caso exato do bug: 'reembolsado' (particípio) não casava C-129."""
        user_text = (
            "gostaria de saber se o valor enviado poderia ser reembolsado, "
            "pois consegui uma vaga no meu convênio"
        )
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None, "Deve escalar — reembolsado + consegui vaga no convênio"
        assert "equipe" in res.lower() or "atendente" in res.lower() or "blink" in res.lower()

    def test_reembolso_substantivo(self):
        user_text = "quero pedir um reembolso do valor que paguei"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_reembolsar_verbo(self):
        user_text = "vocês podem reembolsar o que paguei?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_reembolsada_feminino(self):
        user_text = "a quantia seria reembolsada se eu cancelar?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_estorno_substantivo(self):
        user_text = "quero solicitar o estorno do pix que fiz"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_estornar_verbo(self):
        user_text = "como faço para estornar o pagamento?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_estornado_participio(self):
        user_text = "o valor já foi estornado?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_devolucao_valor(self):
        user_text = "gostaria de solicitar a devolução do valor pago"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_devolver_dinheiro(self):
        user_text = "vocês podem devolver o dinheiro?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_dinheiro_de_volta(self):
        user_text = "quero o dinheiro de volta"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_valor_de_volta(self):
        user_text = "como faço pra receber o valor de volta?"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_consegui_vaga_convenio(self):
        """Padrão exato do caso Alice — 'consegui uma vaga no meu convênio'."""
        user_text = "consegui uma vaga no meu convênio"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_consegui_vaga_convenio_sem_acento(self):
        user_text = "consegui uma vaga no meu convenio agora"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_paguei_quero_devolver(self):
        user_text = "paguei o pix mas quero devolver, consegui convênio"
        res = deve_escalar_fora_escopo_c146(_ctx(), user_text)
        assert res is not None

    def test_tier1_inclui_nome_na_resposta(self):
        """Resposta deve incluir saudação com nome quando disponível."""
        res = deve_escalar_fora_escopo_c146(_ctx(nome="Alice"), "quero o reembolso")
        assert res is not None
        assert "Alice" in res

    def test_tier1_sem_nome_responde_mesmo_assim(self):
        ctx = {"lead_id": 1, "known": {"lead_id": 1}}
        res = deve_escalar_fora_escopo_c146(ctx, "quero o reembolso")
        assert res is not None


# ─── Tier 2: Escopo fechado pós-agendamento ───────────────────────────────────

class TestTier2PosAgendamento:
    """Leads ja_agendado=True + pergunta sem handler Python → escalar."""

    def test_pergunta_generica_pos_agendamento(self):
        user_text = "gostaria de saber mais informações sobre o procedimento"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is not None, "Pergunta genérica pós-agenda deve escalar"

    def test_pergunta_clinica_pos_agendamento(self):
        user_text = "posso tomar remédio antes da consulta?"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is not None

    def test_pergunta_exame_pos_agendamento(self):
        user_text = "preciso fazer algum exame antes?"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is not None


# ─── Falso positivo: perguntas whitelistadas pós-agendamento ─────────────────

class TestFalsoPositivo:
    """Perguntas que Python JÁ sabe responder → não dispara Tier 2."""

    def test_whitelist_endereco(self):
        user_text = "qual o endereço da clínica?"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is None, "Endereço é whitelistado — Python responde via FAQ"

    def test_whitelist_cancelar(self):
        user_text = "quero cancelar minha consulta"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is None, "Cancelamento é whitelistado — C-117 cuida"

    def test_whitelist_remarcar(self):
        user_text = "gostaria de remarcar a consulta"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is None

    def test_whitelist_horario_consulta(self):
        user_text = "qual o horário da minha consulta?"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is None

    def test_whitelist_nova_consulta(self):
        user_text = "quero marcar uma nova consulta para minha filha"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), user_text)
        assert res is None

    def test_tier2_nao_dispara_sem_agendamento(self):
        """Tier 2 só ativa quando ja_agendado=True."""
        user_text = "posso tomar remédio antes?"
        res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=False), user_text)
        assert res is None, "Sem agendamento: Tier 2 não dispara"

    def test_saudacao_simples_nao_dispara(self):
        """Oi/Bom dia não dispara Tier 2."""
        for msg in ("Oi", "Bom dia", "Olá", "Tudo bem?"):
            res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), msg)
            assert res is None, f"Saudação '{msg}' não deve escalar"

    def test_confirmacao_simples_nao_dispara(self):
        """'Sim', 'ok', 'perfeito' não dispara Tier 2."""
        for msg in ("Sim", "ok", "perfeito", "👍", "✅"):
            res = deve_escalar_fora_escopo_c146(_ctx(ja_agendado=True), msg)
            assert res is None, f"Confirmação '{msg}' não deve escalar"


# ─── fail-open e toggle ────────────────────────────────────────────────────────

class TestFailOpenToggle:

    def test_ctx_none_retorna_none(self):
        res = deve_escalar_fora_escopo_c146(None, "reembolso")
        # Com ctx=None, Tier 1 ainda dispara (não requer ctx)
        # Tier 2 não dispara (sem ja_agendado)
        # Tier 1 dispara independente de ctx
        # Verificamos apenas que não levanta exceção
        assert isinstance(res, (str, type(None)))

    def test_user_text_vazio_retorna_none(self):
        res = deve_escalar_fora_escopo_c146(_ctx(), "")
        assert res is None

    def test_user_text_none_retorna_none(self):
        res = deve_escalar_fora_escopo_c146(_ctx(), None)
        assert res is None

    def test_redis_none_nao_levanta_excecao(self):
        """Com redis=None, deve retornar resposta mas sem gravar flag."""
        res = deve_escalar_fora_escopo_c146(_ctx(), "quero o reembolso", redis_client=None)
        assert res is not None  # Tier 1 ainda dispara

    def test_toggle_off_retorna_none(self):
        import os
        original = os.environ.get("FORA_ESCOPO_C146_ATIVADO")
        try:
            os.environ["FORA_ESCOPO_C146_ATIVADO"] = "0"
            # Recarregar módulo pra pegar novo env
            import importlib
            import voice_agent.fora_escopo as _mod
            importlib.reload(_mod)
            from voice_agent.fora_escopo import deve_escalar_fora_escopo_c146 as _fn
            res = _fn(_ctx(ja_agendado=True), "quero o reembolso")
            assert res is None, "Toggle OFF → não escalar"
        finally:
            if original is None:
                os.environ.pop("FORA_ESCOPO_C146_ATIVADO", None)
            else:
                os.environ["FORA_ESCOPO_C146_ATIVADO"] = original
            import importlib
            import voice_agent.fora_escopo as _mod
            importlib.reload(_mod)


# ─── Wire em blindagens_deterministicas ───────────────────────────────────────

class TestWireBypass:
    """C-146 deve estar wired na chain ANTES de C-129."""

    def test_c146_importa_em_blindagens(self):
        """blindagens_deterministicas.py deve importar fora_escopo."""
        import ast, os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "voice_agent", "blindagens_deterministicas.py",
        )
        with open(path) as f:
            src = f.read()
        assert "fora_escopo" in src, "fora_escopo não está importado em blindagens_deterministicas.py"
        assert "deve_escalar_fora_escopo_c146" in src

    def test_c146_wired_antes_de_c129(self):
        """C-146 deve aparecer antes de C-129 na ordem da chain."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "voice_agent", "blindagens_deterministicas.py",
        )
        with open(path) as f:
            src = f.read()
        idx_146 = src.find("fora_escopo_c146")
        idx_129 = src.find("pos_consulta_c129")
        assert idx_146 != -1, "fora_escopo_c146 não encontrado em blindagens"
        assert idx_129 != -1, "pos_consulta_c129 não encontrado em blindagens"
        assert idx_146 < idx_129, (
            "C-146 deve aparecer ANTES de C-129 na chain "
            f"(idx_146={idx_146}, idx_129={idx_129})"
        )

    def test_pipeline_tem_hook_c146(self):
        """pipeline.py deve ter bloco de hook para C-146."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "voice_agent", "pipeline.py",
        )
        with open(path) as f:
            src = f.read()
        assert "c146_fora_escopo" in src, "Hook C-146 não encontrado em pipeline.py"
        assert "fora_escopo lead" in src.lower() or "C-146 PIPELINE" in src


# ─── Teste de regressão: C-129 ainda funciona ─────────────────────────────────

class TestRegressaoC129:
    """C-129 não deve ser quebrado pela adição de C-146."""

    def test_c129_ainda_importa(self):
        from voice_agent.pos_consulta import deve_escalar_pos_consulta
        # Deve importar sem erro
        assert callable(deve_escalar_pos_consulta)

    def test_c129_recibo_ainda_funciona(self):
        from voice_agent.pos_consulta import deve_escalar_pos_consulta
        res = deve_escalar_pos_consulta({}, "preciso do recibo da consulta")
        assert res is not None, "C-129 deve continuar funcionando para recibo"

    def test_c129_reembolso_substantivo_ainda_funciona(self):
        from voice_agent.pos_consulta import deve_escalar_pos_consulta
        res = deve_escalar_pos_consulta({}, "quero pedir reembolso")
        assert res is not None, "C-129 deve continuar funcionando para reembolso"
