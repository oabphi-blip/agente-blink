"""
tests/test_bug_c94_especialidade_motivo.py
Bug C-94 (05/08/2026) — Auto-inferência de especialidade + médico + checklist médico/unidade
"""
import pytest
from voice_agent.intent_classifier import (
    calcular_idade_anos,
    inferir_especialidade,
    inferir_medico,
)
from voice_agent.checklist_dados_minimos import (
    verificar_dados_minimos,
    medico_ok,
    unidade_ok,
)


# ---------------------------------------------------------------------------
# calcular_idade_anos
# ---------------------------------------------------------------------------

class TestCalcularIdade:
    def test_timestamp_unix_bebe(self):
        """Bebê de 1 mês: timestamp recente"""
        import time
        import datetime
        ts_1m_atras = int(time.time() - 30 * 86400)
        age = calcular_idade_anos(ts_1m_atras)
        assert age == 0

    def test_timestamp_unix_adulto(self):
        import datetime
        import calendar
        dt = datetime.date(1990, 6, 15)
        ts = calendar.timegm(dt.timetuple())
        age = calcular_idade_anos(ts)
        assert age >= 34  # 2026 - 1990

    def test_string_iso(self):
        age = calcular_idade_anos("2015-03-20")
        assert 9 <= age <= 12

    def test_string_br(self):
        age = calcular_idade_anos("20/03/2015")
        assert 9 <= age <= 12

    def test_none_retorna_none(self):
        assert calcular_idade_anos(None) is None

    def test_string_invalida_retorna_none(self):
        assert calcular_idade_anos("invalido") is None


# ---------------------------------------------------------------------------
# inferir_especialidade
# ---------------------------------------------------------------------------

class TestInferirEspecialidade:
    def test_bebe_sem_motivo(self):
        assert inferir_especialidade(0, "") == "Oftalmopediatria"

    def test_crianca_8_anos(self):
        assert inferir_especialidade(8, "rotina") == "Oftalmopediatria"

    def test_apv_adulto(self):
        result = inferir_especialidade(30, "cansaço ao ler, cefaleia")
        assert result == "Avaliação do Processamento Visual"

    def test_sdp_adulto(self):
        result = inferir_especialidade(25, "sdp dificuldade concentração")
        assert result == "Avaliação do Processamento Visual"

    def test_processamento_visual(self):
        result = inferir_especialidade(20, "processamento visual")
        assert result == "Avaliação do Processamento Visual"

    def test_estrabismo(self):
        result = inferir_especialidade(None, "estrabismo")
        assert result == "Oftalmopediatria"

    def test_catarata_retorna_none(self):
        # Catarata vai pra Fabrício — não tem enum de especialidade
        result = inferir_especialidade(65, "catarata")
        assert result is None

    def test_pterigio_retorna_none(self):
        result = inferir_especialidade(45, "pterígio")
        assert result is None

    def test_adulto_rotina(self):
        result = inferir_especialidade(35, "rotina de óculos")
        assert result == "Oftalmologia Geral"

    def test_fabricio_retorna_none(self):
        # Se médico já é Fabrício, não inferir especialidade
        result = inferir_especialidade(60, "avaliação", medico_known="Fabrício")
        assert result is None

    def test_sem_dados_retorna_none(self):
        assert inferir_especialidade(None, None) is None

    def test_pediatrico_por_motivo(self):
        result = inferir_especialidade(None, "bebê de 3 meses")
        assert result == "Oftalmopediatria"


# ---------------------------------------------------------------------------
# inferir_medico
# ---------------------------------------------------------------------------

class TestInferirMedico:
    def test_bebe_karla(self):
        assert inferir_medico(0, "rotina") == "Karla"

    def test_crianca_karla(self):
        assert inferir_medico(7, "check-up") == "Karla"

    def test_catarata_fabricio(self):
        assert inferir_medico(65, "catarata") == "Fabrício"

    def test_pterigio_fabricio(self):
        assert inferir_medico(40, "pterígio / carne no olho") == "Fabrício"

    def test_cornea_fabricio(self):
        assert inferir_medico(50, "ceratocone córnea") == "Fabrício"

    def test_apv_karla(self):
        assert inferir_medico(28, "sdp, cansaço ao ler") == "Karla"

    def test_estrabismo_karla(self):
        assert inferir_medico(12, "estrabismo olho torto") == "Karla"

    def test_adulto_sem_sinal_retorna_none(self):
        # Adulto rotina sem sinal claro → não inferir
        assert inferir_medico(40, "rotina") is None

    def test_sem_dados_retorna_none(self):
        assert inferir_medico(None, None) is None

    def test_pediatrico_por_motivo(self):
        assert inferir_medico(None, "bebê recém-nascido") == "Karla"


# ---------------------------------------------------------------------------
# checklist agora exige médico + unidade
# ---------------------------------------------------------------------------

class TestChecklistMedicoUnidade:
    _base = {
        "nome_paciente": "Ana Paula Silva",
        "data_nascimento": "2010-05-10",
        "convenio": "Saúde Caixa",
    }

    def test_sem_medico_nao_pronto(self):
        r = verificar_dados_minimos({**self._base, "unidade": "Asa Norte"})
        assert not r.pronto_para_oferecer_slot
        assert not r.medico_ok
        assert any("médico" in p for p in r.campos_pendentes)

    def test_sem_unidade_nao_pronto(self):
        r = verificar_dados_minimos({**self._base, "medico": "Karla"})
        assert not r.pronto_para_oferecer_slot
        assert not r.unidade_ok
        assert any("unidade" in p for p in r.campos_pendentes)

    def test_completo_pronto(self):
        r = verificar_dados_minimos({
            **self._base,
            "medico": "Karla",
            "unidade": "Asa Norte",
        })
        assert r.pronto_para_oferecer_slot
        assert r.medico_ok
        assert r.unidade_ok

    def test_fabricio_aguas_claras_pronto(self):
        r = verificar_dados_minimos({
            **self._base,
            "medico": "Fabrício",
            "unidade": "Águas Claras",
        })
        assert r.pronto_para_oferecer_slot

    def test_sem_tudo_4_pendentes(self):
        r = verificar_dados_minimos({})
        # nome + data + convenio + medico + unidade = 5 pendentes mínimos
        assert len(r.campos_pendentes) >= 4

    def test_retrocompat_medico_ok_default_true(self):
        """ChecklistResultado criado sem medico_ok ainda funciona."""
        from voice_agent.checklist_dados_minimos import ChecklistResultado
        r = ChecklistResultado(
            nome_completo_ok=True, data_nascimento_ok=True,
            cpf_ok=False, convenio_definido_ok=True, cpf_exigido=False,
        )
        # default medico_ok=True e unidade_ok=True → pronto_para_oferecer_slot=True
        assert r.pronto_para_oferecer_slot is True


# ---------------------------------------------------------------------------
# medico_ok / unidade_ok
# ---------------------------------------------------------------------------

class TestValidacoesIndividuais:
    def test_medico_ok_karla(self):
        assert medico_ok("Karla") is True

    def test_medico_ok_fabricio(self):
        assert medico_ok("Fabrício") is True

    def test_medico_ok_none(self):
        assert medico_ok(None) is False

    def test_medico_ok_vazio(self):
        assert medico_ok("") is False

    def test_unidade_ok_asa_norte(self):
        assert unidade_ok("Asa Norte") is True

    def test_unidade_ok_aguas_claras(self):
        assert unidade_ok("Águas Claras") is True

    def test_unidade_ok_none(self):
        assert unidade_ok(None) is False
