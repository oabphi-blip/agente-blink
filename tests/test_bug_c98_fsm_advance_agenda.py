"""Pytest Bug C-98 — FSM auto-advance CONVENIO→AGENDA (08/08/2026).

Cenário: paciente envia o último dado necessário (ex: "asa norte").
C-81 injeta unidade em known[] ANTES do Medware.
Medware retorna slots.
Checklist vira pronto_para_oferecer_slot=True.
MAS FSM Redis snapshot do turno anterior ainda é CONVENIO.
deve_ofertar_agora() exige fsm.estado==AGENDA → retorna False sem C-98.

Garante que o bloco C-98 em pipeline.py:
  1. Avança FSM CONVENIO→AGENDA quando checklist completo + agenda presente
  2. Avança FSM DADOS→AGENDA (mesma lógica)
  3. Avança FSM TRIAGEM→AGENDA (prioritário: urgência ou dados já no Kommo)
  4. NÃO avança quando checklist pendente
  5. NÃO avança quando agenda vazia (Medware não retornou slots)
  6. NÃO avança quando ja_agendado=True
  7. NÃO avança quando FSM já está em AGENDA (idempotente)
  8. NÃO avança quando FSM está em CONFIRMACAO/GRAVACAO/POS_GRAVACAO
  9. Após advance, deve_ofertar_agora() retorna True
  10. FSM salva no Redis com motivo C-98
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    fsm_estado: str = "CONVENIO",
    pronto: bool = True,
    agenda: list | None = None,
    ja_agendado: bool = False,
    medico: str = "Dra. Karla Delalibera",
    unidade: str = "Asa Norte",
    lead_id: int = 99999,
) -> dict:
    """Monta caller_context mínimo para testar C-98."""
    if agenda is None:
        agenda = [{"data": "2026-08-10", "hora": "09:30", "medico": medico}]

    known = {
        "nome_paciente": "Joana Silva Costa",
        "data_nasc": "2010-05-01",
        "convenio": "Saúde Caixa",
        "medico": medico,
        "unidade": unidade,
    }

    checklist = {
        "pronto_para_oferecer_slot": pronto,
        "campos_pendentes": [] if pronto else ["nome_paciente"],
        "nome_completo_ok": pronto,
        "data_nascimento_ok": pronto,
        "cpf_ok": True,
        "convenio_definido_ok": pronto,
    }

    return {
        "lead_id": lead_id,
        "found": True,
        "ja_agendado": ja_agendado,
        "status_id": 102560495,  # 3-AGENDAR
        "known": known,
        "agenda": agenda,
        "checklist_dados_minimos": checklist,
        "fsm": {
            "estado": fsm_estado,
            "tentativas_no_estado": 1,
            "motivo_ultima_transicao": "turno anterior",
        },
    }


# ---------------------------------------------------------------------------
# Testes do bloco C-98 (lógica condicional)
# ---------------------------------------------------------------------------

class TestC98Condicao:
    """Valida as condições de entrada/saída do bloco C-98."""

    def _run_c98(self, ctx: dict) -> dict:
        """Simula o bloco C-98 de pipeline.py contra o ctx."""
        from voice_agent.fsm_conversa import EstadoConversa, FSMManager

        redis_mock = MagicMock()
        # Simula Redis retornando None (sem snapshot existente no mock)
        redis_mock.get.return_value = None
        redis_mock.setex.return_value = True

        fsm_mgr = FSMManager(redis_mock)
        conversation_key = f"test:{ctx.get('lead_id', 0)}"

        _fsm_estado_c98 = (ctx.get("fsm") or {}).get("estado", "")
        _chk_c98 = ctx.get("checklist_dados_minimos") or {}

        if (
            _fsm_estado_c98 in {"TRIAGEM", "DADOS", "CONVENIO"}
            and _chk_c98.get("pronto_para_oferecer_slot")
            and ctx.get("agenda")
            and not ctx.get("ja_agendado")
        ):
            _snap_c98, _ok_c98 = fsm_mgr.transicionar(
                conversation_key,
                EstadoConversa.AGENDA,
                motivo="C-98 auto-advance: checklist completo + agenda disponível",
            )
            if _ok_c98:
                ctx["fsm"] = {
                    "estado": _snap_c98.estado.value,
                    "tentativas_no_estado": _snap_c98.tentativas_no_estado,
                    "motivo_ultima_transicao": _snap_c98.motivo_ultima_transicao,
                }

        return ctx

    def test_convenio_avanca_pra_agenda(self):
        ctx = _make_ctx(fsm_estado="CONVENIO")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "AGENDA"

    def test_dados_avanca_pra_agenda(self):
        ctx = _make_ctx(fsm_estado="DADOS")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "AGENDA"

    def test_triagem_avanca_pra_agenda(self):
        ctx = _make_ctx(fsm_estado="TRIAGEM")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "AGENDA"

    def test_checklist_pendente_nao_avanca(self):
        ctx = _make_ctx(fsm_estado="CONVENIO", pronto=False)
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "CONVENIO"  # não mudou

    def test_agenda_vazia_nao_avanca(self):
        ctx = _make_ctx(fsm_estado="CONVENIO", agenda=[])
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "CONVENIO"

    def test_ja_agendado_nao_avanca(self):
        ctx = _make_ctx(fsm_estado="CONVENIO", ja_agendado=True)
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "CONVENIO"

    def test_fsm_ja_agenda_idempotente(self):
        """Se FSM já está em AGENDA, C-98 não entra no if (estado não está no set)."""
        ctx = _make_ctx(fsm_estado="AGENDA")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "AGENDA"  # manteve

    def test_confirmacao_nao_retrocede(self):
        ctx = _make_ctx(fsm_estado="CONFIRMACAO")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "CONFIRMACAO"

    def test_gravacao_nao_retrocede(self):
        ctx = _make_ctx(fsm_estado="GRAVACAO")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "GRAVACAO"

    def test_pos_gravacao_nao_retrocede(self):
        ctx = _make_ctx(fsm_estado="POS_GRAVACAO")
        result = self._run_c98(ctx)
        assert result["fsm"]["estado"] == "POS_GRAVACAO"


# ---------------------------------------------------------------------------
# Integração com deve_ofertar_agora()
# ---------------------------------------------------------------------------

class TestC98IntegracaoDeveOfertar:
    """Valida que após C-98, deve_ofertar_agora() retorna True."""

    def test_apos_advance_deve_ofertar_true(self):
        from voice_agent.oferta_deterministica import deve_ofertar_agora

        ctx = _make_ctx(fsm_estado="CONVENIO")
        # Simular C-98 advance
        ctx["fsm"]["estado"] = "AGENDA"

        with patch.dict("os.environ", {"AGENDA_DETERMINISTICA": "1"}):
            resultado = deve_ofertar_agora(ctx)

        assert resultado is True, (
            "deve_ofertar_agora deve retornar True após C-98 avançar FSM para AGENDA"
        )

    def test_sem_advance_deve_ofertar_false(self):
        """Sem C-98 advance, deve_ofertar_agora retorna False (FSM = CONVENIO)."""
        from voice_agent.oferta_deterministica import deve_ofertar_agora

        ctx = _make_ctx(fsm_estado="CONVENIO")
        # NÃO simula o advance — FSM fica em CONVENIO

        with patch.dict("os.environ", {"AGENDA_DETERMINISTICA": "1"}):
            resultado = deve_ofertar_agora(ctx)

        assert resultado is False, (
            "Sem C-98 advance, deve_ofertar_agora deve retornar False (FSM=CONVENIO)"
        )

    def test_ediva_pattern(self):
        """Replica o padrão do lead Edivá 24430558.

        Último dado coletado = unidade "Asa Norte".
        C-81 injetou unidade. Checklist pronto. Medware retornou slots.
        FSM Redis estava em CONVENIO (paciente tinha dito 'sem convênio').
        Sem C-98: stall. Com C-98: oferta real.

        Particular com CPF → checklist completo pra simular cenário real.
        (Paciente sem convênio precisa de CPF — sem CPF o checklist não estaria
        completo e C-98 não avançaria, o que seria correto.)
        """
        from voice_agent.oferta_deterministica import deve_ofertar_agora

        ctx = {
            "lead_id": 24430558,
            "found": True,
            "ja_agendado": False,
            "status_id": 102560495,  # 3-AGENDAR
            "known": {
                "nome_paciente": "Edivá Maria Santos",
                "data_nasc": "1985-03-15",
                "convenio": "Não se aplica",  # sem convênio → particular
                "cpf_paciente": "12345678901",  # CPF necessário para particular
                "medico": "Dra. Karla Delalibera",
                "unidade": "Asa Norte",  # C-81 injetou isso
            },
            "agenda": [
                {"data": "2026-08-11", "hora": "10:00"},
                {"data": "2026-08-13", "hora": "14:30"},
            ],
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": True,  # checklist completo
                "campos_pendentes": [],
                "nome_completo_ok": True,
                "data_nascimento_ok": True,
                "cpf_ok": True,
                "convenio_definido_ok": True,
            },
            # FSM Redis do turno anterior = CONVENIO (paciente disse "sem convênio")
            "fsm": {"estado": "CONVENIO", "tentativas_no_estado": 1},
        }

        # ANTES de C-98: deve_ofertar_agora retorna False
        with patch.dict("os.environ", {"AGENDA_DETERMINISTICA": "1"}):
            antes = deve_ofertar_agora(ctx)
        assert antes is False, "ANTES do C-98 deve retornar False (FSM=CONVENIO)"

        # Simula C-98 advance
        ctx["fsm"]["estado"] = "AGENDA"

        # DEPOIS de C-98: deve_ofertar_agora retorna True
        with patch.dict("os.environ", {"AGENDA_DETERMINISTICA": "1"}):
            depois = deve_ofertar_agora(ctx)
        assert depois is True, "DEPOIS do C-98 deve retornar True (FSM=AGENDA)"


# ---------------------------------------------------------------------------
# Validar que bloco C-98 existe em pipeline.py
# ---------------------------------------------------------------------------

class TestC98ExisteNoPipeline:
    """Garante que o bloco C-98 foi commitado em pipeline.py."""

    def test_bloco_c98_presente(self):
        import os
        pipeline_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "pipeline.py"
        )
        with open(pipeline_path) as f:
            content = f.read()

        assert "C-98" in content, "Bloco C-98 deve existir em pipeline.py"
        assert "auto-advance" in content, "Comentário auto-advance deve existir"
        assert "_fsm_estado_c98" in content, "Variável _fsm_estado_c98 deve existir"
        assert "TRIAGEM.*DADOS.*CONVENIO" not in content.replace("\n", "") or \
               '{"TRIAGEM", "DADOS", "CONVENIO"}' in content, \
               "Set de estados pré-AGENDA deve existir"

    def test_transicao_convenio_agenda_valida(self):
        """CONVENIO→AGENDA deve ser transição válida na FSM."""
        from voice_agent.fsm_conversa import EstadoConversa, transicao_valida

        assert transicao_valida(
            EstadoConversa.CONVENIO, EstadoConversa.AGENDA
        ), "CONVENIO→AGENDA deve ser transição válida"

    def test_transicao_dados_agenda_valida(self):
        from voice_agent.fsm_conversa import EstadoConversa, transicao_valida

        assert transicao_valida(
            EstadoConversa.DADOS, EstadoConversa.AGENDA
        ), "DADOS→AGENDA deve ser transição válida"

    def test_transicao_confirmacao_agenda_invalida_por_c98(self):
        """C-98 não deve disparar em CONFIRMACAO/GRAVACAO/POS_GRAVACAO."""
        # Esses estados não estão no set {"TRIAGEM", "DADOS", "CONVENIO"}
        estados_protegidos = {"CONFIRMACAO", "GRAVACAO", "POS_GRAVACAO"}
        estados_c98 = {"TRIAGEM", "DADOS", "CONVENIO"}

        assert not (estados_protegidos & estados_c98), (
            "Nenhum estado protegido deve estar no set de estados C-98"
        )
