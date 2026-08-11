"""Pytest da FSM da conversa Lia ↔ paciente.

Cobre:
 - estados enum
 - transições válidas/inválidas
 - inferência inicial pelo caller_context
 - manager Redis (com fake)
 - render_bloco_estado pro system prompt
 - degradação silenciosa quando Redis indisponível
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.fsm_conversa import (  # noqa: E402
    EstadoConversa,
    FSMManager,
    SnapshotFSM,
    inferir_estado_inicial,
    render_bloco_estado,
    transicao_valida,
)


# ----------------------------------------------------------------------
# Transições válidas
# ----------------------------------------------------------------------

class TestTransicoes:

    @pytest.mark.parametrize("origem,destino,ok", [
        # Fluxo feliz
        (EstadoConversa.TRIAGEM, EstadoConversa.DADOS, True),
        (EstadoConversa.DADOS, EstadoConversa.CONVENIO, True),
        (EstadoConversa.CONVENIO, EstadoConversa.AGENDA, True),
        (EstadoConversa.AGENDA, EstadoConversa.CONFIRMACAO, True),
        (EstadoConversa.CONFIRMACAO, EstadoConversa.GRAVACAO, True),
        (EstadoConversa.GRAVACAO, EstadoConversa.POS_GRAVACAO, True),
        # Repetir é OK
        (EstadoConversa.TRIAGEM, EstadoConversa.TRIAGEM, True),
        (EstadoConversa.AGENDA, EstadoConversa.AGENDA, True),
        # Atalhos
        (EstadoConversa.DADOS, EstadoConversa.AGENDA, True),
        (EstadoConversa.AGENDA, EstadoConversa.DADOS, True),  # volta coletar
        (EstadoConversa.POS_GRAVACAO, EstadoConversa.AGENDA, True),  # remarcação
        # PROIBIDAS
        (EstadoConversa.TRIAGEM, EstadoConversa.AGENDA, False),
        (EstadoConversa.TRIAGEM, EstadoConversa.GRAVACAO, False),
        (EstadoConversa.GRAVACAO, EstadoConversa.AGENDA, False),
        (EstadoConversa.GRAVACAO, EstadoConversa.TRIAGEM, False),
        (EstadoConversa.POS_GRAVACAO, EstadoConversa.TRIAGEM, False),
        (EstadoConversa.POS_GRAVACAO, EstadoConversa.DADOS, False),
    ])
    def test_validacao(self, origem, destino, ok):
        assert transicao_valida(origem, destino) is ok


# ----------------------------------------------------------------------
# Inferência inicial
# ----------------------------------------------------------------------

class TestInferirEstadoInicial:

    def test_contato_novo_vira_triagem(self):
        assert inferir_estado_inicial(None) == EstadoConversa.TRIAGEM
        assert inferir_estado_inicial({}) == EstadoConversa.TRIAGEM
        assert inferir_estado_inicial({"found": False}) == EstadoConversa.TRIAGEM

    def test_ja_agendado_vira_pos_gravacao(self):
        ctx = {"found": True, "ja_agendado": True}
        assert inferir_estado_inicial(ctx) == EstadoConversa.POS_GRAVACAO

    def test_status_agendado_vira_pos_gravacao(self):
        for sid in (101507507, 101109455, 106653499):
            ctx = {"found": True, "status_id": sid}
            assert inferir_estado_inicial(ctx) == EstadoConversa.POS_GRAVACAO

    def test_agendar_sem_dados_vai_para_DADOS(self):
        ctx = {
            "found": True, "status_id": 102560495,
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": False},
        }
        assert inferir_estado_inicial(ctx) == EstadoConversa.DADOS

    def test_agendar_com_dados_vai_para_AGENDA(self):
        ctx = {
            "found": True, "status_id": 102560495,
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": True},
        }
        assert inferir_estado_inicial(ctx) == EstadoConversa.AGENDA

    def test_reagendar_funciona_igual(self):
        ctx = {
            "found": True, "status_id": 106184631,  # REAGENDAR
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": False},
        }
        assert inferir_estado_inicial(ctx) == EstadoConversa.DADOS

    def test_etapa_entrada_vira_triagem(self):
        ctx = {"found": True, "status_id": 96441724}  # ENTRADA
        assert inferir_estado_inicial(ctx) == EstadoConversa.TRIAGEM


# ----------------------------------------------------------------------
# Snapshot serializa/desserializa
# ----------------------------------------------------------------------

class TestSnapshot:

    def test_roundtrip_json(self):
        snap = SnapshotFSM(
            estado=EstadoConversa.AGENDA,
            ultima_transicao_ts=1780000000.0,
            tentativas_no_estado=3,
            motivo_ultima_transicao="paciente recusou os 2",
        )
        s = json.dumps(snap.como_dict())
        recuperado = SnapshotFSM.de_dict(json.loads(s))
        assert recuperado.estado == EstadoConversa.AGENDA
        assert recuperado.tentativas_no_estado == 3
        assert recuperado.motivo_ultima_transicao == "paciente recusou os 2"

    def test_de_dict_default_triagem(self):
        snap = SnapshotFSM.de_dict({})
        assert snap.estado == EstadoConversa.TRIAGEM


# ----------------------------------------------------------------------
# FSMManager — com fake Redis
# ----------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.store[k] = v
        self.ttls[k] = ttl


class TestManager:

    def test_redis_none_degrada_silenciosa(self):
        mgr = FSMManager(None)
        assert mgr.get("x") is None
        # set não levanta
        mgr.set("x", SnapshotFSM(EstadoConversa.AGENDA, 0))
        # transicionar funciona, mas não persiste
        snap, ok = mgr.transicionar("x", EstadoConversa.DADOS)
        assert ok is True
        assert snap.estado == EstadoConversa.DADOS

    def test_primeira_transicao_cria_snapshot(self):
        mgr = FSMManager(FakeRedis())
        snap, ok = mgr.transicionar(
            "abc", EstadoConversa.TRIAGEM, motivo="boot",
        )
        assert ok is True
        assert snap.estado == EstadoConversa.TRIAGEM
        # Persistiu
        assert mgr.get("abc").estado == EstadoConversa.TRIAGEM

    def test_transicao_valida_atualiza(self):
        mgr = FSMManager(FakeRedis())
        mgr.transicionar("abc", EstadoConversa.TRIAGEM)
        snap, ok = mgr.transicionar(
            "abc", EstadoConversa.DADOS, motivo="paciente deu nome",
        )
        assert ok is True
        assert snap.estado == EstadoConversa.DADOS

    def test_transicao_invalida_mantem_estado(self):
        mgr = FSMManager(FakeRedis())
        mgr.transicionar("abc", EstadoConversa.TRIAGEM)
        snap, ok = mgr.transicionar("abc", EstadoConversa.GRAVACAO)
        assert ok is False
        assert snap.estado == EstadoConversa.TRIAGEM

    def test_repetir_estado_conta_tentativa(self):
        mgr = FSMManager(FakeRedis())
        mgr.transicionar("abc", EstadoConversa.AGENDA)
        mgr.transicionar("abc", EstadoConversa.AGENDA)
        mgr.transicionar("abc", EstadoConversa.AGENDA)
        snap = mgr.get("abc")
        assert snap.estado == EstadoConversa.AGENDA
        assert snap.tentativas_no_estado == 3


# ----------------------------------------------------------------------
# Bloco descritivo pro system prompt
# ----------------------------------------------------------------------

class TestBlocoEstado:

    def test_snap_none_retorna_vazio(self):
        assert render_bloco_estado(None) == ""

    @pytest.mark.parametrize("estado,must_have", [
        (EstadoConversa.TRIAGEM, ["TRIAGEM", "MOTIVO"]),
        (EstadoConversa.DADOS, ["COLETA", "checklist"]),
        (EstadoConversa.AGENDA, ["AGENDA", "2", "escassez"]),
        (EstadoConversa.CONFIRMACAO, ["CONFIRMAÇÃO", "gravação"]),
        (EstadoConversa.GRAVACAO, ["GRAVAÇÃO", "thread"]),
        (EstadoConversa.POS_GRAVACAO, ["PÓS", "remarcação"]),
    ])
    def test_bloco_menciona_palavras_chave(self, estado, must_have):
        snap = SnapshotFSM(estado, time.time(), 1)
        bloco = render_bloco_estado(snap)
        for kw in must_have:
            assert kw.lower() in bloco.lower(), \
                f"estado {estado.value} faltou '{kw}' no bloco"
