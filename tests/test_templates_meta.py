"""Pytest do template Meta 1039 + decisor de estratégia.

Cobre:
  - normalização E.164 (BR)
  - builder do payload Cloud API (estrutura exata)
  - sanitização do nome do contato (sem newline, < 120 chars)
  - decisor: 5 cenários de estratégia
"""
from __future__ import annotations

import pytest

from voice_agent.templates_meta import (
    TEMPLATE_1039,
    TEMPLATE_ATIVAR_URGENCIA_NAME,
    build_template_ativar_urgencia,
    decidir_estrategia,
    normalizar_telefone_e164,
)


# ---------------------------------------------------------------------------
# Normalização E.164
# ---------------------------------------------------------------------------

class TestNormalizarE164:

    def test_com_55_passa(self):
        assert normalizar_telefone_e164("5561999990000") == "5561999990000"

    def test_so_ddd_e_numero_assume_55(self):
        assert normalizar_telefone_e164("61999990000") == "5561999990000"

    def test_remove_mascara(self):
        assert normalizar_telefone_e164("(61) 99999-0000") == "5561999990000"

    def test_remove_mais(self):
        assert normalizar_telefone_e164("+55 61 99999-0000") == "5561999990000"

    def test_aceita_fixo_10_digitos(self):
        assert normalizar_telefone_e164("6133331005") == "556133331005"

    def test_vazio_devolve_none(self):
        assert normalizar_telefone_e164("") is None
        assert normalizar_telefone_e164(None) is None

    def test_curto_devolve_none(self):
        assert normalizar_telefone_e164("123") is None

    def test_longo_demais_devolve_none(self):
        assert normalizar_telefone_e164("9" * 20) is None


# ---------------------------------------------------------------------------
# Builder do payload
# ---------------------------------------------------------------------------

class TestBuilderTemplate1039:

    def test_payload_basico(self):
        p = build_template_ativar_urgencia(
            to_telefone="5561999990000",
            nome_contato="Maria Soares",
        )
        assert p["messaging_product"] == "whatsapp"
        assert p["to"] == "5561999990000"
        assert p["type"] == "template"
        assert p["template"]["name"] == TEMPLATE_ATIVAR_URGENCIA_NAME
        assert p["template"]["language"]["code"] == "pt_BR"
        body = p["template"]["components"][0]
        assert body["type"] == "body"
        assert body["parameters"][0]["text"] == "Maria Soares"

    def test_normaliza_telefone(self):
        p = build_template_ativar_urgencia(
            to_telefone="(61) 99999-0000",
            nome_contato="X",
        )
        assert p["to"] == "5561999990000"

    def test_telefone_invalido_devolve_none(self):
        assert build_template_ativar_urgencia(
            to_telefone="abc", nome_contato="X",
        ) is None

    def test_nome_vazio_devolve_none(self):
        assert build_template_ativar_urgencia(
            to_telefone="5561999990000", nome_contato="",
        ) is None

    def test_nome_com_newline_e_sanitizado(self):
        # Cloud API rejeita texto com \n no parâmetro.
        p = build_template_ativar_urgencia(
            to_telefone="5561999990000",
            nome_contato="Maria\nSoares\nde Oliveira",
        )
        nome = p["template"]["components"][0]["parameters"][0]["text"]
        assert "\n" not in nome
        assert nome == "Maria Soares de Oliveira"

    def test_nome_longo_truncado_em_120(self):
        nome_longo = "A" * 500
        p = build_template_ativar_urgencia(
            to_telefone="5561999990000", nome_contato=nome_longo,
        )
        nome = p["template"]["components"][0]["parameters"][0]["text"]
        assert len(nome) <= 120

    def test_template_name_pode_ser_sobrescrito(self):
        p = build_template_ativar_urgencia(
            to_telefone="5561999990000", nome_contato="Ana",
            template_name="outro_template",
        )
        assert p["template"]["name"] == "outro_template"


class TestMetadataTemplate:

    def test_tem_3_botoes_quick_reply(self):
        assert len(TEMPLATE_1039.botoes_quick_reply) == 3
        assert "1ª Opção" in TEMPLATE_1039.botoes_quick_reply

    def test_tem_1_parametro_body(self):
        assert TEMPLATE_1039.parametros_body == ["nome_contato"]


# ---------------------------------------------------------------------------
# Decisor de estratégia
# ---------------------------------------------------------------------------

class TestDecidirEstrategia:

    def test_janela_aberta_usa_free_form(self):
        elig = {"elegivel": True, "razao": None, "delta_seg": 82800}
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=True)
        assert r.tipo == "free_form"

    def test_janela_morta_e_ja_respondeu_usa_template(self):
        elig = {
            "elegivel": False,
            "razao": "janela_expirou_so_template",
            "delta_seg": 30 * 3600,
        }
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=True)
        assert r.tipo == "template_1039"
        assert r.detalhe["template_name"] == TEMPLATE_ATIVAR_URGENCIA_NAME

    def test_lead_frio_puro_usa_template(self):
        elig = {
            "elegivel": False,
            "razao": "paciente_nunca_falou",
            "delta_seg": None,
        }
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=False)
        assert r.tipo == "template_1039"

    def test_status_pos_agendado_nao_dispara(self):
        elig = {
            "elegivel": False,
            "razao": "status_pos_agendado",
            "delta_seg": None,
        }
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=True)
        assert r.tipo == "nao_disparar"

    def test_ainda_cedo_nao_dispara(self):
        elig = {
            "elegivel": False,
            "razao": "ainda_dentro_da_janela_confortavel",
            "delta_seg": 5 * 3600,
        }
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=True)
        assert r.tipo == "nao_disparar"

    def test_razao_desconhecida_nao_dispara(self):
        elig = {"elegivel": False, "razao": None, "delta_seg": None}
        r = decidir_estrategia(elig, paciente_ja_respondeu_na_vida=True)
        assert r.tipo == "nao_disparar"
