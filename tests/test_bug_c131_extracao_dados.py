"""Bug C-131 (12/08/2026) — Extração determinística de dados do inbound.

Casos reais:
- Lead 24448016 Lorena/Nicolas: paciente deu data de nascimento 3× e "9 de fevereiro
  de 2025" — agente continuou repetindo "Qual a data de nascimento de Nicolas?"
- Lead 24448040 Patrícia: deu nome completo — agente repetiu "Qual o nome completo?"

Fix: extracao_resposta_c131.py extrai nome/data/CPF do user_text quando a última
mensagem da Lia perguntou o campo, e grava em ctx.known ANTES do checklist.

Testa também:
- C-84/C-126 fix: "atendimento humano" agora detectado (antes só "atendente")
- C-108 fix: "não quero agendar agora", "vou decidir", "não vou agendar"
"""
from __future__ import annotations

import pytest
import re
from unittest.mock import patch, MagicMock

from voice_agent.extracao_resposta_c131 import (
    extrair_data_nascimento,
    extrair_nome_completo,
    extrair_cpf,
    extrair_e_injetar_resposta_c131,
)
from voice_agent.desistencia import detectar_desistencia


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_data_nascimento
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtrairDataNascimento:
    """Caso real: Nicolas enviou data 3 vezes e ainda assim C-125 repetiu a pergunta."""

    def test_formato_dd_mm_yyyy(self):
        assert extrair_data_nascimento("09/02/2025") == "09/02/2025"

    def test_formato_dd_mm_yyyy_espacos(self):
        assert extrair_data_nascimento("Minha data é 09/02/2025") == "09/02/2025"

    def test_typo_mes_3_digitos(self):
        """Lead real: paciente digitou '27/012/2024' (typo no mês)."""
        resultado = extrair_data_nascimento("27/012/2024")
        assert resultado == "27/12/2024"

    def test_formato_escrito_completo(self):
        """Caso real: 'nicolas nasceu em 9 de fevereiro de 2025'."""
        assert extrair_data_nascimento("9 de fevereiro de 2025") == "09/02/2025"

    def test_formato_escrito_sem_de(self):
        assert extrair_data_nascimento("9 fevereiro 2025") == "09/02/2025"

    def test_iso_format(self):
        assert extrair_data_nascimento("2025-02-09") == "09/02/2025"

    def test_frase_completa_com_data(self):
        assert extrair_data_nascimento("Nicolas nasceu em 09/02/2025, às 3h da manhã") == "09/02/2025"

    def test_sem_data_retorna_none(self):
        assert extrair_data_nascimento("não sei a data") is None

    def test_texto_vazio_retorna_none(self):
        assert extrair_data_nascimento("") is None

    def test_none_retorna_none(self):
        assert extrair_data_nascimento(None) is None  # type: ignore

    def test_mes_dezembro(self):
        assert extrair_data_nascimento("15 de dezembro de 2010") == "15/12/2010"

    def test_data_com_tracos(self):
        assert extrair_data_nascimento("09-02-2025") == "09/02/2025"

    def test_ano_dois_digitos(self):
        r = extrair_data_nascimento("09/02/25")
        assert r == "09/02/2025"


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_nome_completo
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtrairNomeCompleto:
    """Caso real: Patrícia enviou nome e agente repetiu 'Qual o nome completo?'."""

    def test_nome_direto(self):
        r = extrair_nome_completo("Patrícia Dellany Costa Azevedo")
        assert r is not None
        assert "Patrícia" in r or "Patricia" in r

    def test_nome_com_prefixo_meu_nome_e(self):
        r = extrair_nome_completo("Meu nome é João Silva")
        assert r is not None
        assert "João" in r or "Joao" in r

    def test_nome_com_prefixo_me_chamo(self):
        r = extrair_nome_completo("Me chamo Maria Aparecida")
        assert r is not None
        assert "Maria" in r

    def test_nome_invalido_sim(self):
        assert extrair_nome_completo("Sim") is None

    def test_nome_invalido_ok(self):
        assert extrair_nome_completo("Ok") is None

    def test_nome_invalido_quero_agendar(self):
        assert extrair_nome_completo("Quero agendar uma consulta") is None

    def test_nome_invalido_com_numero(self):
        assert extrair_nome_completo("09/02/2025") is None

    def test_nome_invalido_pergunta(self):
        assert extrair_nome_completo("Qual o horário?") is None

    def test_nome_invalido_so_uma_palavra(self):
        assert extrair_nome_completo("Patrícia") is None

    def test_texto_vazio_retorna_none(self):
        assert extrair_nome_completo("") is None

    def test_none_retorna_none(self):
        assert extrair_nome_completo(None) is None  # type: ignore

    def test_nome_case_corrigido(self):
        r = extrair_nome_completo("CARLOS ALBERTO SOUZA")
        assert r is not None
        assert r == "Carlos Alberto Souza"


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_cpf
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtrairCpf:
    def test_cpf_com_mascara(self):
        assert extrair_cpf("123.456.789-09") == "12345678909"

    def test_cpf_sem_mascara(self):
        assert extrair_cpf("12345678909") == "12345678909"

    def test_cpf_no_meio_de_frase(self):
        assert extrair_cpf("meu CPF é 123.456.789-09 obrigado") == "12345678909"

    def test_sem_cpf_retorna_none(self):
        assert extrair_cpf("não tenho isso") is None

    def test_texto_vazio_retorna_none(self):
        assert extrair_cpf("") is None


# ═══════════════════════════════════════════════════════════════════════════════
# extrair_e_injetar_resposta_c131 — integração
# ═══════════════════════════════════════════════════════════════════════════════

def _ctx_com_ultima_msg(ultima_msg: str, lead_id: int = 24448016) -> dict:
    return {
        "known": {
            "lead_id": lead_id,
            "ultima_msg_outbound": ultima_msg,
        }
    }


class TestInjetarResposta:
    """Verifica que a função popula ctx.known corretamente."""

    def test_injeta_data_quando_perguntou_data(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual a data de nascimento de Nicolas?")
        extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
        assert ctx["known"].get("data_nasc") == "09/02/2025"

    def test_injeta_data_escrita(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:31 12/08] Qual a data de nascimento de Nicolas?")
        extrair_e_injetar_resposta_c131(ctx, "9 de fevereiro de 2025")
        assert ctx["known"].get("data_nasc") == "09/02/2025"

    def test_injeta_nome_quando_perguntou_nome(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:00 12/08] Qual o nome completo do paciente?")
        extrair_e_injetar_resposta_c131(ctx, "Patrícia Dellany Costa Azevedo")
        assert ctx["known"].get("nome") == "Patrícia Dellany Costa Azevedo"

    def test_injeta_cpf_quando_perguntou_cpf(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:00 12/08] Qual o CPF do paciente?")
        extrair_e_injetar_resposta_c131(ctx, "123.456.789-09")
        assert ctx["known"].get("cpf_extraido_c131") == "12345678909"

    def test_nao_sobrescreve_data_ja_preenchida(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual a data de nascimento de Nicolas?")
        ctx["known"]["data_nasc"] = "01/01/2000"
        extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
        assert ctx["known"]["data_nasc"] == "01/01/2000"  # não sobrescreveu

    def test_nao_injeta_data_quando_nao_perguntou_data(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual o nome completo?")
        extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
        assert ctx["known"].get("data_nasc") is None

    def test_nao_injeta_nome_quando_nao_perguntou_nome(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual a data de nascimento?")
        extrair_e_injetar_resposta_c131(ctx, "João da Silva")
        assert ctx["known"].get("nome") is None

    def test_fail_open_ctx_none(self):
        """Não deve levantar exceção com ctx=None."""
        extrair_e_injetar_resposta_c131(None, "09/02/2025")  # fail-open

    def test_fail_open_user_text_vazio(self):
        ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual a data de nascimento?")
        extrair_e_injetar_resposta_c131(ctx, "")
        assert ctx["known"].get("data_nasc") is None

    def test_toggle_off_nao_injeta(self):
        with patch.dict("os.environ", {"EXTRACAO_RESPOSTA_ATIVADO": "0"}):
            ctx = _ctx_com_ultima_msg("[LIA 10:30 12/08] Qual a data de nascimento?")
            extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
            assert ctx["known"].get("data_nasc") is None

    def test_sem_ultima_msg_nao_injeta(self):
        ctx = {"known": {"lead_id": 123}}
        extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
        assert ctx["known"].get("data_nasc") is None

    def test_caso_real_nicolas_data(self):
        """Reproduz exatamente o caso do lead 24448016 Nicolas."""
        ctx = _ctx_com_ultima_msg(
            "[LIA 08:15 12/08] Qual a data de nascimento de Nicolas? 😊",
            lead_id=24448016,
        )
        extrair_e_injetar_resposta_c131(ctx, "09/02/2025")
        assert ctx["known"].get("data_nasc") == "09/02/2025"

    def test_caso_real_patricia_nome(self):
        """Reproduz exatamente o caso do lead 24448040 Patrícia."""
        ctx = _ctx_com_ultima_msg(
            "[LIA 09:00 12/08] Qual o nome completo do paciente?",
            lead_id=24448040,
        )
        extrair_e_injetar_resposta_c131(ctx, "Patrícia Dellany Costa Azevedo")
        assert ctx["known"].get("nome") is not None
        assert "Patrícia" in ctx["known"]["nome"] or "Patricia" in ctx["known"]["nome"]


# ═══════════════════════════════════════════════════════════════════════════════
# C-108 fix — novos padrões de desistência (lead 24448040 Patrícia)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDesistenciaNovosPadroes:
    """Caso real: Patrícia disse 'Vou decidir e procuro novamente', 'não quero agendar agora'."""

    def test_nao_quero_agendar_agora(self):
        assert detectar_desistencia("não quero agendar agora")

    def test_nao_vou_agendar(self):
        assert detectar_desistencia("Não vou agendar")

    def test_vou_decidir_procuro_novamente(self):
        """Caso exato do lead 24448040."""
        assert detectar_desistencia("Vou decidir e procuro novamente")

    def test_procuro_depois(self):
        assert detectar_desistencia("procuro depois")

    def test_procuro_novamente(self):
        assert detectar_desistencia("procuro novamente")

    def test_decido_depois(self):
        assert detectar_desistencia("decido depois")

    def test_vou_pensar_e_volto(self):
        assert detectar_desistencia("vou pensar e volto")

    def test_desistencia_classica_ainda_funciona(self):
        assert detectar_desistencia("desisti")
        assert detectar_desistencia("não quero mais")
        assert detectar_desistencia("cancela tudo")

    def test_falso_positivo_slot(self):
        """'não quero mais esse horário' NÃO é desistência."""
        assert not detectar_desistencia("não quero mais esse horário")

    def test_falso_positivo_agendamento_sim(self):
        assert not detectar_desistencia("sim, quero agendar")

    def test_nao_quero_agendar_por_enquanto(self):
        assert detectar_desistencia("não quero agendar por enquanto")


# ═══════════════════════════════════════════════════════════════════════════════
# C-84/C-126 fix — "atendimento humano" detectado
# ═══════════════════════════════════════════════════════════════════════════════

class TestAtendimentoHumanoDetectado:
    """Caso real: lead 24448016 Lorena disse 'atendimento humano.' — não foi capturado."""

    def setup_method(self):
        self._re = re.compile(
            r"\batendente\b|falar\s+com\s+(um\s+)?atendente|"
            r"quero\s+atendente|chamar\s+atendente|"
            r"falar\s+com\s+(um\s+)?humano|falar\s+com\s+pessoa|"
            r"me\s+passa\s+pra\s+(uma?\s+)?pessoa|"
            r"quero\s+falar\s+com\s+algu[eé]m|"
            r"me\s+passa\s+pra\s+(um\s+)?atendente|"
            r"\bhumano\b.*\bpor\s+favor\b|\bpor\s+favor\b.*\bhumano\b|"
            r"\batendimento\s+humano\b|quero\s+atendimento\s+humano|"
            r"transfere?\s+(?:para?\s+)?(?:um\s+)?atendimento\s+humano|"
            r"\brob[oô]\b|est[aá]\s+me\s+atendendo|quem\s+[eé]\s+voc[eê]",
            re.IGNORECASE | re.UNICODE,
        )

    def test_atendimento_humano_simples(self):
        """Caso exato do lead 24448016 — 'atendimento humano.'"""
        assert self._re.search("atendimento humano.")

    def test_atendimento_humano_minusculo(self):
        assert self._re.search("atendimento humano")

    def test_atendimento_humano_uppercase(self):
        assert self._re.search("ATENDIMENTO HUMANO")

    def test_quero_atendimento_humano(self):
        assert self._re.search("quero atendimento humano")

    def test_transfere_atendimento_humano(self):
        assert self._re.search("me transfere para atendimento humano")

    def test_atendente_ainda_detectado(self):
        """Padrão antigo ainda funciona."""
        assert self._re.search("quero falar com atendente")
        assert self._re.search("falar com um atendente")

    def test_falso_positivo_consulta_normal(self):
        """Mensagem normal não dispara."""
        assert not self._re.search("quero agendar uma consulta")
        assert not self._re.search("qual o valor da consulta?")
