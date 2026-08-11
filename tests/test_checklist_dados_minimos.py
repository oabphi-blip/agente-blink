"""Pytest do checklist de dados mínimos pra gravar agendamento Medware.

Origem: lead 24053159 Juliene (31/05/2026). Lia ofereceu slot sem ter
nome completo do Daniel nem CPF — agendamento físico era impossível.
Checklist defende preventivamente: sem dados, sem slot.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.checklist_dados_minimos import (  # noqa: E402
    cpf_ok,
    convenio_definido_ok,
    data_nascimento_ok,
    nome_completo_ok,
    render_bloco_pre_agenda,
    verificar_dados_minimos,
)


# ----------------------------------------------------------------------
# Validações individuais
# ----------------------------------------------------------------------

class TestNomeCompleto:

    @pytest.mark.parametrize("nome,esperado", [
        # Caso Juliene — pediátrico, nome só do filho
        ("Daniel", False),
        ("Maria", False),
        # Nomes incompletos
        ("Maria Silva", False),  # 2 tokens fortes
        ("Maria da Silva", False),  # 2 fortes ("da" conector)
        # Nomes válidos
        ("Maria da Silva Souza", True),
        ("João Pedro Costa Santos", True),
        ("Ana Carolina Silva", True),
        # Edge cases
        ("", False),
        (None, False),
        ("AB CD EF", False),  # tokens < 3 letras
        ("José de Almeida Pereira", True),  # "de" conector mas tem 3 fortes
    ])
    def test_avalia(self, nome, esperado):
        assert nome_completo_ok(nome) is esperado


class TestDataNascimento:

    @pytest.mark.parametrize("data,esperado", [
        # ISO
        ("2023-02-09", True),
        ("1986-02-09", True),
        # BR
        ("09/02/2023", True),
        ("09/02/86", True),
        # Timestamp Kommo
        (1675911600, True),  # Daniel 09/02/2023
        # Inválidos
        ("", False),
        (None, False),
        (0, False),
        ("ontem", False),
        ("não sei", False),
    ])
    def test_avalia(self, data, esperado):
        assert data_nascimento_ok(data) is esperado


class TestCPF:

    @pytest.mark.parametrize("cpf,esperado", [
        # Válidos (11 dígitos, não-repetidos)
        ("01305472633", True),
        ("013.054.726-33", True),
        ("123.456.789-09", True),
        # Inválidos
        ("", False),
        (None, False),
        ("123", False),  # curto
        ("11111111111", False),  # todos repetidos
        ("00000000000", False),  # todos zero
        ("abc.def.ghi-jk", False),  # sem dígitos
    ])
    def test_avalia(self, cpf, esperado):
        assert cpf_ok(cpf) is esperado


class TestConvenioDefinido:

    @pytest.mark.parametrize("conv,esperado", [
        ("Não se aplica", True),  # particular OK
        ("Amil", True),
        ("STJ", True),
        ("Pro ser STJ", True),
        # Vazio / placeholder
        ("", False),
        (None, False),
        ("Selecionar", False),
        ("(vazio)", False),
        ("—", False),
    ])
    def test_avalia(self, conv, esperado):
        assert convenio_definido_ok(conv) is esperado


# ----------------------------------------------------------------------
# Checklist agregado — cenários reais
# ----------------------------------------------------------------------

class TestVerificarDadosMinimos:

    def test_caso_juliene_lead_24053159(self):
        """Cenário REAL do bug. Conhecemos: nome curto 'Daniel', data nasc
        OK, convênio OK ('Não se aplica'). Falta: nome completo + CPF.
        Resultado esperado: bloqueia oferta de slot."""
        known = {
            "nome_paciente": "Daniel",
            "data_nasc_iso": "2023-02-09",
            "convenio": "Não se aplica",
            # cpf NÃO presente
        }
        r = verificar_dados_minimos(known)
        assert r.pronto_para_oferecer_slot is False
        assert r.nome_completo_ok is False
        assert r.data_nascimento_ok is True
        assert r.cpf_ok is False
        assert r.convenio_definido_ok is True
        assert "nome completo do paciente" in r.campos_pendentes
        assert any("CPF" in c for c in r.campos_pendentes)
        # 2 pendentes
        assert r.total_pendentes == 2

    def test_lead_completo_libera_slot(self):
        known = {
            "nome_paciente": "Daniel Silva Souza",
            "data_nasc_iso": "2023-02-09",
            "cpf_responsavel": "012.345.678-90",
            "convenio": "Não se aplica",
        }
        r = verificar_dados_minimos(known)
        assert r.pronto_para_oferecer_slot is True
        assert r.total_pendentes == 0

    def test_lead_vazio_4_pendentes(self):
        r = verificar_dados_minimos({})
        assert r.pronto_para_oferecer_slot is False
        assert r.total_pendentes == 4

    def test_known_None(self):
        r = verificar_dados_minimos(None)
        assert r.pronto_para_oferecer_slot is False

    def test_nomes_alternativos_de_chave(self):
        # Tolera nome diferente do campo
        known = {
            "nome": "João Pedro Silva",  # ao invés de "nome_paciente"
            "data_nascimento": "1985-05-20",  # alt
            "cpf": "98765432100",  # alt
            "convenio": "Amil",
        }
        r = verificar_dados_minimos(known)
        assert r.pronto_para_oferecer_slot is True


# ----------------------------------------------------------------------
# Bloco PRÉ-AGENDA — formato pro prompt
# ----------------------------------------------------------------------

class TestRenderBlocoPreAgenda:

    def test_pronto_retorna_vazio(self):
        from voice_agent.checklist_dados_minimos import ChecklistResultado
        r = ChecklistResultado(True, True, True, True, ())
        assert render_bloco_pre_agenda(r) == ""

    def test_pendente_injeta_bloco(self):
        from voice_agent.checklist_dados_minimos import ChecklistResultado
        r = ChecklistResultado(
            nome_completo_ok=False,
            data_nascimento_ok=True,
            cpf_ok=False,
            convenio_definido_ok=True,
            campos_pendentes=("nome completo do paciente",
                              "CPF do paciente (ou do responsável, se for menor)"),
        )
        bloco = render_bloco_pre_agenda(r)
        assert "DADOS PENDENTES" in bloco
        assert "PROIBIDO oferecer dia/hora" in bloco
        assert "nome completo do paciente" in bloco
        assert "CPF" in bloco
        assert "CAMINHO CORRETO" in bloco

    def test_bloco_NAO_repergunta_campo_ok(self):
        """Se nome completo OK, bloco não deve mencionar 'nome completo'
        como pendente."""
        from voice_agent.checklist_dados_minimos import ChecklistResultado
        r = ChecklistResultado(
            nome_completo_ok=True,
            data_nascimento_ok=True,
            cpf_ok=False,
            convenio_definido_ok=True,
            campos_pendentes=("CPF do paciente (ou do responsável, se for menor)",),
        )
        bloco = render_bloco_pre_agenda(r)
        assert "CPF" in bloco
        # Não deve listar nome completo como pendente (não está em
        # campos_pendentes, só na lista enumerada)
        # Conta ocorrências relevantes
        pendentes_block = bloco.split("PROIBIDO")[1].split("Motivo")[0]
        assert "nome completo do paciente" not in pendentes_block


# ----------------------------------------------------------------------
# Integração com responder._caller_context_block
# ----------------------------------------------------------------------

class TestIntegracaoComResponder:

    def test_caller_context_block_injeta_pre_agenda_quando_falta_dado(self):
        """Verifica que o responder.py injeta o bloco quando
        ctx['checklist_dados_minimos'] indica pendência."""
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "Juliene",
            "lead_id": 24053159,
            "known": {
                "nome_paciente": "Daniel",
                "convenio": "Não se aplica",
            },
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": False,
                "campos_pendentes": [
                    "nome completo do paciente",
                    "data de nascimento",
                    "CPF do paciente (ou do responsável, se for menor)",
                ],
                "nome_completo_ok": False,
                "data_nascimento_ok": False,
                "cpf_ok": False,
                "convenio_definido_ok": True,
            },
            "agenda": [],  # vazio pra ver só pre-agenda
        }
        bloco = _caller_context_block(ctx)
        # Pre-agenda deve aparecer
        assert "DADOS PENDENTES" in bloco
        assert "nome completo do paciente" in bloco
        assert "CPF" in bloco

    def test_caller_context_block_NAO_injeta_pre_agenda_quando_pronto(self):
        from voice_agent.responder import _caller_context_block
        ctx = {
            "found": True,
            "name": "João",
            "lead_id": 1,
            "known": {"nome_paciente": "João Silva Souza"},
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": True,
                "campos_pendentes": [],
                "nome_completo_ok": True,
                "data_nascimento_ok": True,
                "cpf_ok": True,
                "convenio_definido_ok": True,
            },
            "agenda": [],
        }
        bloco = _caller_context_block(ctx)
        assert "DADOS PENDENTES" not in bloco
