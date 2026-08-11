"""
Pytest — Bug C-111: Re-verificar slot antes de gravar agendamento (agendamento.py).

Causa raiz: tools_lia.py::handle_gravar_agendamento_medware já tinha a verificação
de slot (slot_ainda_disponivel) antes de criar_agendamento. Mas agendamento.py::
executar_agendamento é o segundo caminho pro Medware — e NÃO tinha essa checagem.

Resultado: race condition — Lia oferecia slot 18h atrás, outro paciente confirmava
entretanto, mas executar_agendamento gravava no slot ocupado sem reclamar.

Fix (C-111): adicionado bloco antes de criar_agendamento em agendamento.py.
Fail-open: se medware.slot_ainda_disponivel levantar exceção → prossegue normalmente.
"""
from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision(
    data_iso="2026-08-15",
    hora="10:00",
    medico="Karla",
    unidade="Asa Norte",
    cod_medico=12080,
    cod_unidade=5,
    cod_agenda=100,
    data_hora="2026-08-15 10:00:00",
):
    return {
        "data_iso": data_iso,
        "hora": hora,
        "medico": medico,
        "unidade": unidade,
        "cod_medico": cod_medico,
        "cod_unidade": cod_unidade,
        "cod_agenda": cod_agenda,
        "data_hora": data_hora,
    }


def _known(**kwargs):
    base = {
        "nome_completo": "Maria Silva",
        "cpf": "52998224725",
        "data_nasc": "2000-01-01",
        "telefone": "61999887766",
        "convenio": "Saúde Caixa",
        "cod_medico": 12080,
        "cod_unidade": 5,
    }
    base.update(kwargs)
    return base


def _caller_context(lead_id=5001, **overrides):
    ctx = {"lead_id": lead_id, "known": _known(), "agenda": []}
    ctx.update(overrides)
    return ctx


def _medware_ok():
    """Medware mock que retorna agendamento criado com sucesso."""
    m = MagicMock()
    m.criar_agendamento.return_value = {"ok": True, "cod_agendamento": 99999}
    return m


def _medware_slot_livre():
    """Medware com slot_ainda_disponivel retornando livre."""
    m = _medware_ok()
    m.slot_ainda_disponivel.return_value = (True, [])
    return m


def _medware_slot_ocupado(alternativas=None):
    """Medware com slot_ainda_disponivel retornando ocupado."""
    m = _medware_ok()
    alts = alternativas or [
        {"data_br": "16/08/2026", "dia_semana": "Segunda", "hora": "09:00", "data_iso": "2026-08-16"},
        {"data_br": "17/08/2026", "dia_semana": "Terça", "hora": "14:00", "data_iso": "2026-08-17"},
    ]
    m.slot_ainda_disponivel.return_value = (False, alts)
    return m


def _medware_sem_metodo():
    """Medware sem o método slot_ainda_disponivel (versão antiga)."""
    m = _medware_ok()
    if hasattr(m, "slot_ainda_disponivel"):
        del m.slot_ainda_disponivel
    # Garante que hasattr retorna False
    spec_m = MagicMock(spec=[
        "criar_agendamento",
        "buscar_paciente_por_cpf",
        "listar_horarios_disponiveis",
    ])
    spec_m.criar_agendamento.return_value = {"ok": True, "cod_agendamento": 99999}
    return spec_m


# ---------------------------------------------------------------------------
# Importar executar_agendamento
# ---------------------------------------------------------------------------

def _importar():
    from voice_agent.agendamento import executar_agendamento
    return executar_agendamento


def _kommo():
    """Kommo mock simples para satisfazer assinatura de executar_agendamento."""
    return MagicMock()


# ---------------------------------------------------------------------------
# 1. Slot ainda disponível → prossegue e grava normalmente
# ---------------------------------------------------------------------------

class TestSlotDisponivel:
    def test_slot_livre_chama_criar_agendamento(self):
        ea = _importar()
        med = _medware_slot_livre()
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert med.criar_agendamento.called
        assert result.get("ok") is True

    def test_slot_livre_verifica_antes_de_gravar(self):
        """A verificação deve PRECEDER a criação — confirma pela ordem de calls."""
        ea = _importar()
        med = _medware_slot_livre()
        call_order = []
        med.slot_ainda_disponivel.side_effect = lambda **kw: (call_order.append("verificar"), (True, []))[1]
        med.criar_agendamento.side_effect = lambda **kw: (call_order.append("gravar"), {"ok": True, "cod_agendamento": 1})[1]
        ea(_decision(), _caller_context(), med, _kommo())
        assert call_order.index("verificar") < call_order.index("gravar")

    def test_slot_livre_passa_args_corretos(self):
        ea = _importar()
        med = _medware_slot_livre()
        dec = _decision(data_iso="2026-09-10", hora="14:30", medico="Fabrício", unidade="Águas Claras")
        ea(dec, _caller_context(), med, _kommo())
        # Verifica que slot_ainda_disponivel foi chamado com data_iso e hora corretos
        call_kwargs = med.slot_ainda_disponivel.call_args
        assert call_kwargs is not None
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        assert kwargs.get("data_iso") == "2026-09-10"
        assert kwargs.get("hora") == "14:30"


# ---------------------------------------------------------------------------
# 2. Slot ocupado → retorna erro com msg e alternativas
# ---------------------------------------------------------------------------

class TestSlotOcupado:
    def test_retorna_ok_false(self):
        ea = _importar()
        med = _medware_slot_ocupado()
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert result.get("ok") is False

    def test_motivo_race_condition(self):
        ea = _importar()
        med = _medware_slot_ocupado()
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert result.get("motivo") == "slot_ocupado_race_condition"

    def test_nao_chama_criar_agendamento(self):
        """Quando slot está ocupado, NÃO deve tentar criar o agendamento."""
        ea = _importar()
        med = _medware_slot_ocupado()
        ea(_decision(), _caller_context(), med, _kommo())
        assert not med.criar_agendamento.called

    def test_retorna_msg_para_paciente(self):
        ea = _importar()
        med = _medware_slot_ocupado()
        result = ea(_decision(), _caller_context(), med, _kommo())
        msg = result.get("msg_para_paciente", "")
        assert "horário" in msg.lower() or "slot" in msg.lower() or "preenchido" in msg.lower()

    def test_retorna_slots_alternativos(self):
        ea = _importar()
        alts = [{"data_br": "20/08/2026", "hora": "10:00", "dia_semana": "Quinta", "data_iso": "2026-08-20"}]
        med = _medware_slot_ocupado(alternativas=alts)
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert isinstance(result.get("slots_alternativos"), list)
        assert len(result["slots_alternativos"]) >= 1

    def test_msg_contem_alternativas(self):
        """Mensagem para paciente deve incluir os slots alternativos."""
        ea = _importar()
        alts = [
            {"data_br": "16/08/2026", "dia_semana": "Segunda", "hora": "09:00", "data_iso": "2026-08-16"},
            {"data_br": "17/08/2026", "dia_semana": "Terça", "hora": "14:00", "data_iso": "2026-08-17"},
        ]
        med = _medware_slot_ocupado(alternativas=alts)
        result = ea(_decision(), _caller_context(), med, _kommo())
        msg = result.get("msg_para_paciente", "")
        # Deve mencionar ao menos um slot alternativo
        assert "09:00" in msg or "14:00" in msg or "1️⃣" in msg

    def test_slot_sem_alternativas_retorna_msg_padrao(self):
        """Sem alternativas, deve retornar mensagem útil ao paciente."""
        ea = _importar()
        med = _medware_slot_ocupado(alternativas=[])
        result = ea(_decision(), _caller_context(), med, _kommo())
        msg = result.get("msg_para_paciente", "")
        assert len(msg) > 10  # Mensagem não deve ser vazia


# ---------------------------------------------------------------------------
# 3. Fail-open: exceção na verificação → prossegue normalmente
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_excecao_na_verificacao_nao_bloqueia(self):
        """Se slot_ainda_disponivel levantar exceção → fail-open: cria agendamento mesmo assim."""
        ea = _importar()
        med = _medware_ok()
        med.slot_ainda_disponivel.side_effect = RuntimeError("Medware timeout")
        result = ea(_decision(), _caller_context(), med, _kommo())
        # Deve ter prosseguido para criar_agendamento
        assert med.criar_agendamento.called
        assert result.get("ok") is True

    def test_timeout_nao_bloqueia(self):
        """Simula timeout de rede na verificação."""
        ea = _importar()
        med = _medware_ok()
        med.slot_ainda_disponivel.side_effect = TimeoutError("timeout")
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert result.get("ok") is True

    def test_medware_sem_metodo_prossegue(self):
        """Medware sem slot_ainda_disponivel (versão antiga) → compatibilidade retroativa."""
        ea = _importar()
        med = _medware_sem_metodo()
        result = ea(_decision(), _caller_context(), med, _kommo())
        assert result.get("ok") is True


# ---------------------------------------------------------------------------
# 4. Sem data_iso ou hora → não chama verificação (guard)
# ---------------------------------------------------------------------------

class TestSemDadosHorario:
    def test_sem_data_iso_nao_verifica(self):
        ea = _importar()
        med = _medware_slot_livre()
        dec = _decision(data_iso="", hora="10:00")
        result = ea(dec, _caller_context(), med, _kommo())
        # Sem data_iso — verificação não deve ocorrer
        assert not med.slot_ainda_disponivel.called

    def test_sem_hora_nao_verifica(self):
        ea = _importar()
        med = _medware_slot_livre()
        dec = _decision(data_iso="2026-08-15", hora="")
        result = ea(dec, _caller_context(), med, _kommo())
        assert not med.slot_ainda_disponivel.called


# ---------------------------------------------------------------------------
# 5. Bloco C-111 existe no arquivo (estrutura)
# ---------------------------------------------------------------------------

class TestEstruturaArquivo:
    def test_c111_presente_em_agendamento_py(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/agendamento.py").read_text(encoding="utf-8")
        assert "C-111" in conteudo, "Bloco C-111 não encontrado em agendamento.py"

    def test_c111_antes_de_criar_agendamento(self):
        """C-111 deve vir ANTES da chamada a criar_agendamento."""
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/agendamento.py").read_text(encoding="utf-8")
        pos_c111 = conteudo.find("C-111")
        pos_criar = conteudo.find("result = medware.criar_agendamento")
        assert pos_c111 >= 0, "C-111 não encontrado"
        assert pos_criar >= 0, "criar_agendamento não encontrado"
        assert pos_c111 < pos_criar, "C-111 deve vir antes de criar_agendamento"

    def test_fail_open_em_agendamento_py(self):
        """Deve ter bloco except que garante fail-open."""
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/agendamento.py").read_text(encoding="utf-8")
        assert "fail-open" in conteudo.lower() or "fail_open" in conteudo.lower() or "fail open" in conteudo.lower()
