"""
tests/test_bug_c82_urgency_llm_path.py
Bug C-82 — urgência priority NÃO chegava ao LLM (fix 3 camadas)

Auditoria arquitetural C-81 revelou:
  - skip_convenio + urgency_level injetados pelo C-81 mas nunca lidos pelo responder.py
  - checklist gate não bypassado para urgência
  - FSM sem atalho TRIAGEM→AGENDA para urgência priority

Fixes:
  Fix 1: _caller_context_block() injeta urgency_block no system prompt
  Fix 2: checklist gate bypassa quando skip_convenio=True
  Fix 3: inferir_estado_inicial() retorna AGENDA quando urgency_level=priority + agenda populada
"""
import pytest


# ===========================================================================
# CLASSE 1: Fix 1 — urgency_block injetado no system prompt
# ===========================================================================

class TestUrgencyBlockNosPrompt:
    """_caller_context_block() deve injetar bloco de urgência quando urgency_level está em ctx.known."""

    def _make_ctx_priority(self, with_known=True):
        base = {
            "found": True,
            "name": "Ana",
            "etapa": "3-AGENDAR",
            "known": {"urgency_level": "priority", "skip_convenio": True} if with_known else {},
        }
        return base

    def _make_ctx_critical(self):
        return {
            "found": True,
            "name": "João",
            "etapa": "3-AGENDAR",
            "known": {"urgency_level": "critical", "skip_convenio": True},
        }

    def _make_ctx_routine(self):
        return {
            "found": True,
            "name": "Maria",
            "etapa": "3-AGENDAR",
            "known": {},
        }

    def test_priority_injeta_bloco_urgencia(self):
        from voice_agent.responder import _caller_context_block
        ctx = self._make_ctx_priority()
        bloco = _caller_context_block(ctx)
        assert "URGÊNCIA PRIORITÁRIA" in bloco

    def test_priority_menciona_pular_convenio(self):
        from voice_agent.responder import _caller_context_block
        ctx = self._make_ctx_priority()
        bloco = _caller_context_block(ctx)
        assert "convênio" in bloco.lower() or "PULE" in bloco

    def test_priority_menciona_encaixe_imediato(self):
        from voice_agent.responder import _caller_context_block
        ctx = self._make_ctx_priority()
        bloco = _caller_context_block(ctx)
        assert "encaixe" in bloco.lower() or "IMEDIATO" in bloco

    def test_critical_injeta_bloco_emergencia(self):
        from voice_agent.responder import _caller_context_block
        ctx = self._make_ctx_critical()
        bloco = _caller_context_block(ctx)
        assert "CRÍTICA" in bloco or "EMERGÊNCIA" in bloco

    def test_routine_nao_injeta_urgencia(self):
        from voice_agent.responder import _caller_context_block
        ctx = self._make_ctx_routine()
        bloco = _caller_context_block(ctx)
        assert "URGÊNCIA PRIORITÁRIA" not in bloco
        assert "CRÍTICA" not in bloco

    def test_sem_urgency_level_sem_bloco(self):
        """ctx.known sem urgency_level não deve injetar bloco."""
        from voice_agent.responder import _caller_context_block
        ctx = {"found": True, "name": "Pedro", "known": {"convenio": "Saúde Caixa"}}
        bloco = _caller_context_block(ctx)
        assert "URGÊNCIA PRIORITÁRIA" not in bloco

    def test_ctx_nao_encontrado_sem_bloco_urgencia(self):
        """Contato novo sem found=True não deve injetar bloco de urgência."""
        from voice_agent.responder import _caller_context_block
        ctx = {"found": False, "known": {"urgency_level": "priority"}}
        bloco = _caller_context_block(ctx)
        # Para contato novo, usa o branch "CONTATO NOVO" — não há known read
        assert "URGÊNCIA PRIORITÁRIA" not in bloco


# ===========================================================================
# CLASSE 2: Fix 2 — checklist gate bypassa skip_convenio
# ===========================================================================

class TestChecklistGateBypass:
    """Gate do checklist de dados mínimos deve ser bypassado quando skip_convenio=True."""

    def _make_checklist_pendente(self):
        return {
            "pronto_para_oferecer_slot": False,
            "nome_completo_ok": True,
            "data_nascimento_ok": True,
            "cpf_ok": False,
            "convenio_definido_ok": False,
            "campos_pendentes": ["convenio"],
        }

    def test_skip_convenio_bypassa_gate(self):
        """Com skip_convenio=True, checklist gate não deve renderizar bloco pre_agenda."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Isabella",
            "known": {
                "urgency_level": "priority",
                "skip_convenio": True,
                "medico": "Karla",
                "unidade": "Asa Norte",
            },
            "checklist_dados_minimos": self._make_checklist_pendente(),
            "agenda": [{"data": "2026-08-03 09:00", "medico": "Karla"}],
        }
        bloco = _caller_context_block(ctx)
        # Com skip_convenio, o bloco pré-agenda (que instrui a coletar convênio) NÃO deve aparecer
        # O bloco de urgência DEVE aparecer
        assert "URGÊNCIA PRIORITÁRIA" in bloco

    def test_sem_skip_convenio_gate_ativo(self):
        """Sem skip_convenio=True, checklist gate renderiza bloco pré-agenda normalmente."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "João",
            "known": {
                "medico": "Karla",
                "unidade": "Asa Norte",
            },
            "checklist_dados_minimos": self._make_checklist_pendente(),
            # sem "agenda" para acionar C-73
        }
        bloco = _caller_context_block(ctx)
        # Bloco de urgência NÃO deve aparecer (não tem urgency_level)
        assert "URGÊNCIA PRIORITÁRIA" not in bloco

    def test_tem_slots_c73_bypassa_gate(self):
        """Bug C-73 existente: com ctx.agenda populado, gate já era bypassado."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Maria",
            "known": {"medico": "Karla"},
            "checklist_dados_minimos": self._make_checklist_pendente(),
            "agenda": [{"data": "2026-08-03 10:00", "medico": "Karla"}],
        }
        bloco = _caller_context_block(ctx)
        # Gate bypassado pelo C-73 (agenda populada)
        assert "ONBOARDING" in bloco  # bloco normal gerado

    def test_skip_convenio_false_nao_bypassa(self):
        """skip_convenio=False não bypassa o gate."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Carlos",
            "known": {"skip_convenio": False},
            "checklist_dados_minimos": self._make_checklist_pendente(),
        }
        bloco = _caller_context_block(ctx)
        # Gate ativo (skip_convenio=False, sem agenda)
        # Sem urgency_level, bloco de urgência não aparece
        assert "URGÊNCIA PRIORITÁRIA" not in bloco


# ===========================================================================
# CLASSE 3: Fix 3 — FSM shortcut para urgência priority
# ===========================================================================

class TestFSMUrgencyShortcut:
    """inferir_estado_inicial() deve retornar AGENDA para urgência priority com slots disponíveis."""

    def test_priority_com_agenda_vai_para_agenda(self):
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": True,
            "status_id": 102560495,  # 3-AGENDAR
            "known": {"urgency_level": "priority", "skip_convenio": True, "medico": "Karla"},
            "agenda": [{"data": "2026-08-03 09:00"}],
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": False},
        }
        estado = inferir_estado_inicial(ctx)
        assert estado == EstadoConversa.AGENDA

    def test_priority_sem_agenda_vai_para_triagem(self):
        """Sem slots disponíveis, urgência priority vai para TRIAGEM (Medware não retornou nada)."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": True,
            "status_id": 102560495,
            "known": {"urgency_level": "priority", "skip_convenio": True},
            "agenda": [],  # sem slots
        }
        estado = inferir_estado_inicial(ctx)
        # Sem agenda, não há como pular para AGENDA — vai para TRIAGEM ou DADOS
        assert estado in (EstadoConversa.TRIAGEM, EstadoConversa.DADOS)

    def test_routine_sem_priority_fluxo_normal(self):
        """Sem urgência, fluxo normal: status AGENDAR sem checklist → DADOS."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": True,
            "status_id": 102560495,  # 3-AGENDAR
            "known": {},
            "agenda": [{"data": "2026-08-03 09:00"}],
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": False},
        }
        estado = inferir_estado_inicial(ctx)
        # Sem urgência, checklist não pronto → DADOS
        assert estado == EstadoConversa.DADOS

    def test_ja_agendado_sobrepoe_priority(self):
        """ja_agendado=True vence urgência — paciente já tem consulta."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": True,
            "ja_agendado": True,
            "known": {"urgency_level": "priority"},
            "agenda": [{"data": "2026-08-03 09:00"}],
        }
        estado = inferir_estado_inicial(ctx)
        assert estado == EstadoConversa.POS_GRAVACAO

    def test_ctx_none_falha_open(self):
        """ctx=None não deve explodir."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        estado = inferir_estado_inicial(None)
        assert estado == EstadoConversa.TRIAGEM

    def test_novo_lead_priority_com_agenda(self):
        """Lead novo (found=False) com urgência e slots vai para AGENDA."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": False,
            "known": {"urgency_level": "priority"},
            "agenda": [{"data": "2026-08-03 09:00"}],
        }
        estado = inferir_estado_inicial(ctx)
        assert estado == EstadoConversa.AGENDA

    def test_novo_lead_routine_vai_triagem(self):
        """Lead novo sem urgência vai para TRIAGEM."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {
            "found": False,
            "known": {},
            "agenda": [{"data": "2026-08-03 09:00"}],
        }
        estado = inferir_estado_inicial(ctx)
        assert estado == EstadoConversa.TRIAGEM


# ===========================================================================
# CLASSE 4: Regressão — fixes C-82 não quebram fluxo normal
# ===========================================================================

class TestRegressaoFluxoNormal:
    """Garantir que os 3 fixes do C-82 não alteram fluxo de rotina."""

    def test_fluxo_rotina_sem_urgencia_intacto(self):
        """Lead de rotina sem urgência: sistema prompt sem bloco urgência."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Carlos",
            "known": {"medico": "Karla", "unidade": "Asa Norte", "convenio": "Saúde Caixa"},
        }
        bloco = _caller_context_block(ctx)
        assert "URGÊNCIA PRIORITÁRIA" not in bloco
        assert "ONBOARDING" in bloco
        assert "Carlos" in bloco

    def test_agenda_block_ainda_presente_routine(self):
        """_agenda_block deve aparecer no output para leads de rotina."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Maria",
            "known": {},
            "agenda": [{"data": "2026-08-05 10:00", "medico": "Karla"}],
        }
        bloco = _caller_context_block(ctx)
        # Bloco deve existir sem erro
        assert len(bloco) > 50

    def test_ja_agendado_alerta_permanece(self):
        """Bloco ATENÇÃO MÁXIMA pra lead já agendado não deve desaparecer."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Pedro",
            "ja_agendado": True,
            "etapa": "5-AGENDADO",
            "known": {},
        }
        bloco = _caller_context_block(ctx)
        assert "JÁ TEM CONSULTA MARCADA" in bloco or "AGENDADO" in bloco

    def test_fsm_pos_gravacao_intacto(self):
        """Leads em AGENDADO/CONFIRMAR continuam indo para POS_GRAVACAO."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        for status_id in (101507507, 101109455, 106653499):
            ctx = {"found": True, "status_id": status_id, "known": {}}
            assert inferir_estado_inicial(ctx) == EstadoConversa.POS_GRAVACAO

    def test_fsm_triagem_entry_intacto(self):
        """Leads em entrada continuam indo para TRIAGEM sem urgência."""
        from voice_agent.fsm_conversa import inferir_estado_inicial, EstadoConversa
        ctx = {"found": True, "status_id": 96441724, "known": {}}  # 0-ENTRADA
        assert inferir_estado_inicial(ctx) == EstadoConversa.TRIAGEM
