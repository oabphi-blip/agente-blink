"""
Bug C-101 (10/08/2026) — Criança/bebê → roteia automaticamente para Dra. Karla

Caso real: lead 24438844 (Cinthia Mendes).
  Paciente: "Eu gostaria de saber o valor da consulta para 3 anos"
  Antes:  Lia mostrou tabela completa + perguntou "Qual médico é o seu atendimento?"
  Depois: Lia responde direto com valores da Dra. Karla (criança = Karla, sempre)

Cenários cobertos:
  A. intent_classifier._extract_pre_slots detecta criança → medico="Karla"
  B. blindagens_deterministicas.deve_responder_valor não mostra tabela geral
  C. Adultos (≥18 anos) NÃO são roteados para Karla (sem falso positivo)
  D. Caso real lead 24438844
"""

import pytest

# ─── A. intent_classifier._extract_pre_slots ────────────────────────────────

from voice_agent.intent_classifier import _extract_pre_slots


class TestExtractPreSlotsC101:

    def test_para_3_anos_inferido_karla(self):
        slots = _extract_pre_slots("Eu gostaria de saber o valor da consulta para 3 anos")
        assert slots.medico == "Karla"

    def test_para_5_anos_inferido_karla(self):
        slots = _extract_pre_slots("quero marcar para o meu filho de 5 anos")
        assert slots.medico == "Karla"

    def test_para_bebe_inferido_karla(self):
        slots = _extract_pre_slots("consulta para bebê")
        assert slots.medico == "Karla"

    def test_para_crianca_inferido_karla(self):
        slots = _extract_pre_slots("tem consulta para criança?")
        assert slots.medico == "Karla"

    def test_meu_filho_inferido_karla(self):
        slots = _extract_pre_slots("quero marcar consulta para meu filho")
        assert slots.medico == "Karla"

    def test_minha_filha_inferido_karla(self):
        slots = _extract_pre_slots("gostaria de agendar para minha filha")
        assert slots.medico == "Karla"

    def test_recem_nascido_inferido_karla(self):
        slots = _extract_pre_slots("para recém-nascido de 2 meses")
        assert slots.medico == "Karla"

    def test_meses_inferido_karla(self):
        slots = _extract_pre_slots("meu bebê tem 8 meses")
        assert slots.medico == "Karla"

    def test_17_anos_inferido_karla(self):
        """17 anos = ainda menor = Karla."""
        slots = _extract_pre_slots("para consulta com 17 anos")
        assert slots.medico == "Karla"

    def test_adulto_25_anos_nao_inferido(self):
        """Adulto de 25 anos não deve ser roteado para Karla."""
        slots = _extract_pre_slots("quero marcar para 25 anos")
        assert slots.medico is None

    def test_adulto_50_anos_nao_inferido_karla(self):
        """50 anos = adulto → None (Fabrício seria inferido por outra lógica)."""
        slots = _extract_pre_slots("consulta para 50 anos")
        assert slots.medico is None

    def test_filho_adulto_45_anos_nao_karla(self):
        """'meu filho de 45 anos' — idade prevalece, não roteia pra Karla."""
        slots = _extract_pre_slots("para meu filho de 45 anos")
        assert slots.medico is None  # 45 ≥ 18 → adulto

    def test_karla_explicita_preservada(self):
        """Menção explícita de Karla não é afetada pelo C-101."""
        slots = _extract_pre_slots("quero consulta com a Karla para meu filho")
        assert slots.medico == "Karla"

    def test_sem_crianca_nao_altera(self):
        """Mensagem sem indicação de criança não injeta medico."""
        slots = _extract_pre_slots("boa tarde, quero marcar uma consulta")
        assert slots.medico is None


# ─── B. deve_responder_valor — resposta específica Karla ────────────────────

from voice_agent.blindagens_deterministicas import deve_responder_valor


def _ctx_sem_medico(nome="Cinthia") -> dict:
    return {
        "found": True,
        "name": nome,
        "status_id": 102560495,
        "known": {
            "nome_paciente": nome,
            "medico": "",
            "motivo": "",
            "convenio": "",
        },
    }


class TestDeveResponderValorC101:

    def test_caso_real_lead_24438844(self):
        """Lead 24438844: 'valor da consulta para 3 anos' → Karla, sem tabela geral."""
        ctx = _ctx_sem_medico("Cinthia")
        resp = deve_responder_valor(ctx, "Eu gostaria de saber o valor da consulta para 3 anos")
        assert resp is not None
        # Deve conter Karla
        assert "Karla" in resp or "karla" in resp.lower()
        # NÃO deve perguntar qual médico (tabela geral)
        assert "Qual médico" not in resp
        assert "qual médico" not in resp.lower()

    def test_para_bebe_retorna_karla(self):
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "qual o valor para bebê?")
        assert resp is not None
        assert "Karla" in resp
        assert "Qual médico" not in resp

    def test_para_crianca_retorna_karla(self):
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "quanto custa para criança?")
        assert resp is not None
        assert "Karla" in resp
        assert "Qual médico" not in resp

    def test_para_meu_filho_retorna_karla(self):
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "qual o valor para meu filho?")
        assert resp is not None
        assert "Karla" in resp
        assert "Qual médico" not in resp

    def test_para_minha_filha_retorna_karla(self):
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "quanto fica para minha filha?")
        assert resp is not None
        assert "Karla" in resp
        assert "Qual médico" not in resp

    def test_para_8_meses_retorna_karla(self):
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "minha bebê tem 8 meses, qual o valor?")
        assert resp is not None
        assert "Karla" in resp
        assert "Qual médico" not in resp

    def test_adulto_sem_medico_mostra_tabela_geral(self):
        """Adulto sem medico definido → ainda mostra tabela geral + pergunta médico."""
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "quanto custa a consulta?")
        assert resp is not None
        # Sem criança detectada → tabela geral
        assert "Qual médico" in resp or "Karla" in resp  # tabela geral tem ambos

    def test_filho_adulto_45_anos_tabela_geral(self):
        """'meu filho de 45 anos' → adulto → tabela geral."""
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "qual o valor para meu filho de 45 anos?")
        assert resp is not None
        # 45 ≥ 18 → não infere Karla → tabela geral
        assert "Qual médico" in resp

    def test_crianca_valor_contem_611_pix(self):
        """Karla consulta particular = R$ 611 Pix."""
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "qual o valor para 3 anos?")
        assert resp is not None
        assert "611" in resp

    def test_medico_ja_definido_no_ctx_preservado(self):
        """Se médico já definido no ctx, C-101 não altera."""
        ctx = {
            "found": True,
            "name": "Teste",
            "known": {
                "nome_paciente": "Teste",
                "medico": "Fabrício",
                "motivo": "catarata",
                "convenio": "",
            },
        }
        resp = deve_responder_valor(ctx, "qual o valor para meu filho de 3 anos?")
        assert resp is not None
        # Médico Fabrício já definido → resposta de Fabrício
        assert "Fabr" in resp


# ─── C. Regressão: comportamentos existentes preservados ────────────────────

class TestC101Regressao:

    def test_frase_sem_valor_retorna_none(self):
        """Mensagem sem pergunta de valor → deve_responder_valor retorna None."""
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "quero agendar para 3 anos")
        # "agendar" não é uma pergunta de valor → None
        assert resp is None

    def test_crianca_sem_pergunta_valor_retorna_none(self):
        """Criança detectada, mas sem padrão de pergunta de valor → None."""
        ctx = _ctx_sem_medico()
        resp = deve_responder_valor(ctx, "meu filho de 5 anos quer consulta")
        # Sem trigger de valor → None (não ativa o bypass)
        assert resp is None

    def test_valor_adulto_karla_no_ctx(self):
        """Karla já no ctx + adulto pergunta valor → resposta específica Karla."""
        ctx = {
            "found": True,
            "name": "Adulto",
            "known": {
                "nome_paciente": "Adulto",
                "medico": "Karla",
                "motivo": "rotina",
                "convenio": "",
            },
        }
        resp = deve_responder_valor(ctx, "quanto custa?")
        assert resp is not None
        assert "Karla" in resp
        assert "611" in resp
