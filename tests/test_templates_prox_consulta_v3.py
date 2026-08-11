"""Testes pros 2 templates prox_consulta v3 aprovados no Meta em 04/07/2026.

Cobre:
  - Sluggs dos 2 templates aprovados (+ override via env)
  - Builder de payload build_template_prox_consulta
  - _sanitizar_param (edge cases)
  - Roteador rotear_pacientes_para_disparo
  - normalizar_cadencia

Fixture principal: um lead com 6 pacientes (família) cobrindo variantes reais.
"""
from __future__ import annotations

from datetime import date

import pytest

from voice_agent.templates_meta import (
    LANGUAGE_BR,
    TEMPLATE_PROX_CONSULTA_1ANO_KARLA,
    TEMPLATE_PROX_CONSULTA_6M_KARLA,
    DecisaoRetornoProgramado,
    PacienteDoLead,
    _sanitizar_param,
    build_template_prox_consulta,
    normalizar_cadencia,
    rotear_pacientes_para_disparo,
)


# ---------------------------------------------------------------------------
# Slugs dos 2 templates aprovados
# ---------------------------------------------------------------------------

class TestSlugsAprovados:

    def test_default_6m_matches_meta_approved(self):
        assert TEMPLATE_PROX_CONSULTA_6M_KARLA.template_name == "blink_prox_consulta_6m_karla_v3"

    def test_default_1ano_matches_meta_approved(self):
        assert TEMPLATE_PROX_CONSULTA_1ANO_KARLA.template_name == "blink_prox_consulta_1ano_karla_v3"

    def test_language_e_ptbr(self):
        assert TEMPLATE_PROX_CONSULTA_6M_KARLA.language_code == "pt_BR"
        assert TEMPLATE_PROX_CONSULTA_1ANO_KARLA.language_code == "pt_BR"

    def test_params_body_tem_7_variaveis_em_ordem(self):
        esperados = [
            "nome_contato",
            "nome_paciente",
            "data_ultima_consulta",
            "data_prox_prevista",
            "unidade",
            "slot_1",
            "slot_2",
        ]
        assert TEMPLATE_PROX_CONSULTA_6M_KARLA.parametros_body == esperados
        assert TEMPLATE_PROX_CONSULTA_1ANO_KARLA.parametros_body == esperados

    def test_sem_botoes_quick_reply(self):
        """Templates aprovados são só body — sem botões."""
        assert TEMPLATE_PROX_CONSULTA_6M_KARLA.botoes_quick_reply == []
        assert TEMPLATE_PROX_CONSULTA_1ANO_KARLA.botoes_quick_reply == []


# ---------------------------------------------------------------------------
# _sanitizar_param
# ---------------------------------------------------------------------------

class TestSanitizarParam:

    def test_none_retorna_none(self):
        assert _sanitizar_param(None) is None

    def test_string_vazia_retorna_none(self):
        assert _sanitizar_param("") is None

    def test_so_espacos_retorna_none(self):
        assert _sanitizar_param("   ") is None

    def test_quebra_linha_vira_espaco(self):
        assert _sanitizar_param("linha1\nlinha2") == "linha1 linha2"

    def test_tab_vira_espaco(self):
        assert _sanitizar_param("a\tb") == "a b"

    def test_espacos_multiplos_colapsam(self):
        assert _sanitizar_param("a    b     c") == "a b c"

    def test_trunca_em_max_chars(self):
        entrada = "x" * 200
        assert len(_sanitizar_param(entrada, max_chars=60)) == 60

    def test_aceita_emojis(self):
        assert _sanitizar_param("Fábio 👋") == "Fábio 👋"

    def test_aceita_numeros_como_string(self):
        assert _sanitizar_param(1234) == "1234"


# ---------------------------------------------------------------------------
# build_template_prox_consulta
# ---------------------------------------------------------------------------

class TestBuildTemplateProxConsulta:

    def _kwargs_validos(self, cadencia="6m"):
        return dict(
            to_telefone="61999990000",
            cadencia=cadencia,
            nome_contato="Carol",
            nome_paciente="João",
            data_ultima_consulta="10/07/2025",
            data_prox_prevista="10/01/2026",
            unidade="Asa Norte",
            slot_1="12/01/2026 às 09h",
            slot_2="15/01/2026 às 14h",
        )

    def test_payload_6m_bate_slug_aprovado(self):
        p = build_template_prox_consulta(**self._kwargs_validos("6m"))
        assert p["template"]["name"] == "blink_prox_consulta_6m_karla_v3"

    def test_payload_1ano_bate_slug_aprovado(self):
        p = build_template_prox_consulta(**self._kwargs_validos("1ano"))
        assert p["template"]["name"] == "blink_prox_consulta_1ano_karla_v3"

    def test_language_pt_br(self):
        p = build_template_prox_consulta(**self._kwargs_validos("6m"))
        assert p["template"]["language"] == {"code": "pt_BR"}

    def test_recipient_e164_com_prefixo_55(self):
        p = build_template_prox_consulta(**self._kwargs_validos("6m"))
        assert p["to"] == "5561999990000"

    def test_7_parametros_no_body_em_ordem(self):
        p = build_template_prox_consulta(**self._kwargs_validos("6m"))
        params = p["template"]["components"][0]["parameters"]
        assert len(params) == 7
        assert params[0] == {"type": "text", "text": "Carol"}
        assert params[1] == {"type": "text", "text": "João"}
        assert params[2] == {"type": "text", "text": "10/07/2025"}
        assert params[3] == {"type": "text", "text": "10/01/2026"}
        assert params[4] == {"type": "text", "text": "Asa Norte"}
        assert params[5] == {"type": "text", "text": "12/01/2026 às 09h"}
        assert params[6] == {"type": "text", "text": "15/01/2026 às 14h"}

    def test_telefone_invalido_retorna_none(self):
        k = self._kwargs_validos("6m")
        k["to_telefone"] = "abc"
        assert build_template_prox_consulta(**k) is None

    def test_nome_paciente_vazio_retorna_none(self):
        k = self._kwargs_validos("6m")
        k["nome_paciente"] = ""
        assert build_template_prox_consulta(**k) is None

    def test_unidade_vazia_retorna_none(self):
        k = self._kwargs_validos("6m")
        k["unidade"] = "   "
        assert build_template_prox_consulta(**k) is None

    def test_cadencia_invalida_retorna_none(self):
        k = self._kwargs_validos("6m")
        k["cadencia"] = "3m"
        assert build_template_prox_consulta(**k) is None

    def test_cadencia_aceita_variantes_6m(self):
        for v in ["6m", "6meses", "6_meses", "6-meses"]:
            k = self._kwargs_validos(v)
            p = build_template_prox_consulta(**k)
            assert p is not None
            assert p["template"]["name"] == "blink_prox_consulta_6m_karla_v3"

    def test_cadencia_aceita_variantes_1ano(self):
        for v in ["1ano", "anual", "1_ano", "1-ano", "12m"]:
            k = self._kwargs_validos(v)
            p = build_template_prox_consulta(**k)
            assert p is not None
            assert p["template"]["name"] == "blink_prox_consulta_1ano_karla_v3"

    def test_override_template_name_via_arg(self):
        k = self._kwargs_validos("6m")
        p = build_template_prox_consulta(**k, template_name="custom_slug")
        assert p["template"]["name"] == "custom_slug"

    def test_quebra_linha_no_slot_e_sanitizada(self):
        k = self._kwargs_validos("6m")
        k["slot_1"] = "12/01/2026\nàs 09h"
        p = build_template_prox_consulta(**k)
        assert p["template"]["components"][0]["parameters"][5]["text"] == "12/01/2026 às 09h"


# ---------------------------------------------------------------------------
# normalizar_cadencia
# ---------------------------------------------------------------------------

class TestNormalizarCadencia:

    def test_6m_variantes(self):
        for v in ["6m", "6 meses", "6-meses", "6_meses", "6MESES", "seis meses"]:
            assert normalizar_cadencia(v) == "6m"

    def test_1ano_variantes(self):
        for v in ["1ano", "1 ano", "anual", "ANUAL", "12m", "12 meses"]:
            assert normalizar_cadencia(v) == "1ano"

    def test_invalido_retorna_none(self):
        assert normalizar_cadencia("") is None
        assert normalizar_cadencia(None) is None
        assert normalizar_cadencia("3 meses") is None
        assert normalizar_cadencia("bimestral") is None


# ---------------------------------------------------------------------------
# rotear_pacientes_para_disparo — fixture família 6 pacientes
# ---------------------------------------------------------------------------

@pytest.fixture
def familia_6_pacientes():
    """Lead família com 6 pacientes cobrindo casos reais."""
    return [
        PacienteDoLead(
            indice=1,
            nome="João (5a)",
            dia_consulta=date(2025, 1, 10),
            mes_prox_consulta=date(2026, 1, 10),   # anual
            unidade="Asa Norte",
            cadencia="1ano",
        ),
        PacienteDoLead(
            indice=2,
            nome="Maria (1a)",
            dia_consulta=date(2025, 7, 15),
            mes_prox_consulta=date(2026, 1, 15),   # 6m
            unidade="Asa Norte",
            cadencia="6m",
        ),
        PacienteDoLead(
            indice=3,
            nome="Pedro (adulto)",
            dia_consulta=date(2025, 8, 20),
            mes_prox_consulta=date(2026, 8, 20),   # anual — longe
            unidade="Asa Norte",
            cadencia="1ano",
        ),
        PacienteDoLead(
            indice=4,
            nome="Bebê Sofia (0a)",
            dia_consulta=date(2025, 12, 5),
            mes_prox_consulta=date(2026, 6, 5),    # 6m — meio de julho
            unidade="Águas Claras",
            cadencia="6m",
        ),
        PacienteDoLead(
            indice=5,
            nome="Cadastro incompleto",
            dia_consulta=None,
            mes_prox_consulta=None,
            unidade=None,
            cadencia=None,
        ),
        PacienteDoLead(
            indice=6,
            nome="Cadencia invalida",
            dia_consulta=date(2025, 1, 1),
            mes_prox_consulta=date(2026, 3, 1),
            unidade="Asa Norte",
            cadencia="3 meses",                    # inválida
        ),
    ]


class TestRoteadorPacientes:

    def test_paciente_sem_cadencia_ou_data_e_descartado(self, familia_6_pacientes):
        decisoes = rotear_pacientes_para_disparo(
            familia_6_pacientes,
            hoje=date(2026, 1, 5),
        )
        indices = {d.paciente.indice for d in decisoes}
        assert 5 not in indices                    # cadastro incompleto
        assert 6 not in indices                    # cadência inválida

    def test_paciente_muito_longe_no_futuro_descartado(self, familia_6_pacientes):
        decisoes = rotear_pacientes_para_disparo(
            familia_6_pacientes,
            hoje=date(2026, 1, 5),
        )
        indices = {d.paciente.indice for d in decisoes}
        # Pedro vence só em agosto de 2026 — 7 meses = fora janela 30d
        assert 3 not in indices

    def test_paciente_dentro_janela_antecedencia_incluido(self, familia_6_pacientes):
        # hoje = 05/01/2026, João vence 10/01/2026 (5 dias) e Maria 15/01/2026 (10 dias)
        decisoes = rotear_pacientes_para_disparo(
            familia_6_pacientes,
            hoje=date(2026, 1, 5),
        )
        indices = {d.paciente.indice for d in decisoes}
        assert 1 in indices                        # João anual
        assert 2 in indices                        # Maria 6m

    def test_ordenacao_por_urgencia(self, familia_6_pacientes):
        decisoes = rotear_pacientes_para_disparo(
            familia_6_pacientes,
            hoje=date(2026, 1, 5),
        )
        # João (5 dias) antes de Maria (10 dias)
        assert decisoes[0].paciente.indice == 1
        assert decisoes[1].paciente.indice == 2

    def test_template_correto_por_cadencia(self, familia_6_pacientes):
        decisoes = rotear_pacientes_para_disparo(
            familia_6_pacientes,
            hoje=date(2026, 1, 5),
        )
        d_joao = next(d for d in decisoes if d.paciente.indice == 1)
        assert d_joao.template_name == "blink_prox_consulta_1ano_karla_v3"
        assert d_joao.cadencia_normalizada == "1ano"

        d_maria = next(d for d in decisoes if d.paciente.indice == 2)
        assert d_maria.template_name == "blink_prox_consulta_6m_karla_v3"
        assert d_maria.cadencia_normalizada == "6m"

    def test_paciente_atrasado_dentro_janela_atraso_incluido(self):
        pacientes = [
            PacienteDoLead(
                indice=1,
                nome="Atrasado",
                dia_consulta=date(2025, 1, 1),
                mes_prox_consulta=date(2025, 7, 1),
                unidade="Asa Norte",
                cadencia="6m",
            ),
        ]
        # hoje é 90 dias depois — no limite
        decisoes = rotear_pacientes_para_disparo(pacientes, hoje=date(2025, 9, 29))
        assert len(decisoes) == 1
        assert decisoes[0].dias_ate_prox == -90
        assert "vencido_ha_90_dias" == decisoes[0].motivo

    def test_paciente_atrasado_alem_janela_atraso_descartado(self):
        pacientes = [
            PacienteDoLead(
                indice=1,
                nome="Muito atrasado",
                dia_consulta=date(2024, 1, 1),
                mes_prox_consulta=date(2024, 7, 1),
                unidade="Asa Norte",
                cadencia="6m",
            ),
        ]
        decisoes = rotear_pacientes_para_disparo(pacientes, hoje=date(2026, 1, 1))
        assert decisoes == []

    def test_lead_vazio_devolve_lista_vazia(self):
        assert rotear_pacientes_para_disparo([]) == []

    def test_motivo_vence_hoje(self):
        pacientes = [
            PacienteDoLead(
                indice=1,
                nome="Hoje",
                dia_consulta=date(2025, 1, 1),
                mes_prox_consulta=date(2026, 1, 5),
                unidade="Asa Norte",
                cadencia="6m",
            ),
        ]
        decisoes = rotear_pacientes_para_disparo(pacientes, hoje=date(2026, 1, 5))
        assert decisoes[0].motivo == "vence_hoje"

    def test_janela_configuravel(self):
        pacientes = [
            PacienteDoLead(
                indice=1,
                nome="60 dias no futuro",
                dia_consulta=date(2025, 1, 1),
                mes_prox_consulta=date(2026, 3, 5),
                unidade="Asa Norte",
                cadencia="6m",
            ),
        ]
        # janela padrão 30d antecipação → descarta
        assert rotear_pacientes_para_disparo(pacientes, hoje=date(2026, 1, 5)) == []
        # janela expandida pra 90d → aceita
        decisoes = rotear_pacientes_para_disparo(
            pacientes,
            hoje=date(2026, 1, 5),
            janela_antecedencia_dias=90,
        )
        assert len(decisoes) == 1
