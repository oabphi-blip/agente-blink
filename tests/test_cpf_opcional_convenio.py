"""Blindagem da regra: CPF é dispensável quando o paciente tem
convênio aceito; obrigatório APENAS para Particular.

Origem (02/06/2026): Fábio + lead Eva Massimo Agrelis 22527166.
Lia coletou nome, data nasc, médica, unidade, convênio (Plan Assiste
MPF) e MOTIVO, mas ainda pediu o CPF e ficou travada nele. Mudança:

  - Convênio == Particular / "Não se aplica" → CPF OBRIGATÓRIO
  - Convênio == qualquer plano aceito (Plan Assiste, TJDFT, STM, …)
    → CPF OPCIONAL (não bloqueia oferta de slot)

Esses testes garantem que `checklist_dados_minimos.verificar_dados_minimos`
NÃO inclui "CPF" como pendente quando há convênio aceito.
"""
from voice_agent.checklist_dados_minimos import verificar_dados_minimos


def _dados_base_completos_sem_cpf(convenio: str) -> dict:
    return {
        "nome_paciente": "Eva Massimo Agrelis",
        "data_nasc_iso": "2021-11-23",
        "convenio": convenio,
        # cpf intencionalmente ausente
    }


# ---------------------------------------------------------------------------
# Caso Eva Massimo: Plan Assiste MPF, todos os outros dados OK
# ---------------------------------------------------------------------------

def test_convenio_plan_assiste_mpf_sem_cpf_libera_slot():
    """Cenário real lead 22527166: Plan Assiste MPF + dados completos → libera."""
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("Plan Assiste - MPF (MPU)")
    )
    assert res.cpf_exigido is False
    assert res.pronto_para_oferecer_slot is True
    assert "CPF" not in " ".join(res.campos_pendentes)


def test_convenio_tjdft_sem_cpf_libera_slot():
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("TJDFT Pró-Saúde")
    )
    assert res.cpf_exigido is False
    assert res.pronto_para_oferecer_slot is True


def test_convenio_stf_med_sem_cpf_libera_slot():
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("STF-Med")
    )
    assert res.cpf_exigido is False
    assert res.pronto_para_oferecer_slot is True


def test_convenio_saude_caixa_sem_cpf_libera_slot():
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("Saúde Caixa")
    )
    assert res.cpf_exigido is False
    assert res.pronto_para_oferecer_slot is True


# ---------------------------------------------------------------------------
# Particular continua exigindo CPF
# ---------------------------------------------------------------------------

def test_particular_sem_cpf_NAO_libera_slot():
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("Particular")
    )
    assert res.cpf_exigido is True
    assert res.cpf_ok is False
    assert res.pronto_para_oferecer_slot is False
    assert any("CPF" in c for c in res.campos_pendentes)


def test_nao_se_aplica_sem_cpf_NAO_libera_slot():
    """Kommo grava 'Não se aplica' pra particular; mesma regra."""
    res = verificar_dados_minimos(
        _dados_base_completos_sem_cpf("Não se aplica")
    )
    assert res.cpf_exigido is True
    assert res.pronto_para_oferecer_slot is False


def test_particular_com_cpf_valido_libera_slot():
    dados = _dados_base_completos_sem_cpf("Particular")
    dados["cpf_paciente"] = "529.982.247-25"  # CPF de teste matemático válido
    res = verificar_dados_minimos(dados)
    assert res.cpf_exigido is True
    assert res.cpf_ok is True
    assert res.pronto_para_oferecer_slot is True


# ---------------------------------------------------------------------------
# Edge cases: convênio em branco / indefinido
# ---------------------------------------------------------------------------

def test_convenio_vazio_NAO_libera_slot():
    dados = {
        "nome_paciente": "Eva Massimo Agrelis",
        "data_nasc_iso": "2021-11-23",
        "convenio": "",
    }
    res = verificar_dados_minimos(dados)
    assert res.convenio_definido_ok is False
    assert res.pronto_para_oferecer_slot is False
    # CPF ainda não é exigido (porque o convênio nem foi definido)
    assert res.cpf_exigido is False


def test_falta_nome_mesmo_com_convenio_NAO_libera_slot():
    dados = {
        "nome_paciente": "Eva",  # 1 token só
        "data_nasc_iso": "2021-11-23",
        "convenio": "Plan Assiste - MPF (MPU)",
    }
    res = verificar_dados_minimos(dados)
    assert res.nome_completo_ok is False
    assert res.pronto_para_oferecer_slot is False
    # Continua não exigindo CPF (convênio aceito), mas falta o nome
    assert res.cpf_exigido is False
    assert any("nome" in c.lower() for c in res.campos_pendentes)


def test_falta_data_nascimento_NAO_libera_slot():
    dados = {
        "nome_paciente": "Eva Massimo Agrelis",
        "convenio": "Plan Assiste - MPF (MPU)",
    }
    res = verificar_dados_minimos(dados)
    assert res.data_nascimento_ok is False
    assert res.pronto_para_oferecer_slot is False


# ---------------------------------------------------------------------------
# Lista de pendentes NÃO menciona CPF quando convênio aceito
# ---------------------------------------------------------------------------

def test_pendentes_nao_lista_cpf_quando_convenio_aceito():
    dados = {
        "nome_paciente": "Eva",  # falta nome
        "convenio": "Plan Assiste - MPF (MPU)",
    }
    res = verificar_dados_minimos(dados)
    pendentes_joined = " ".join(res.campos_pendentes)
    assert "CPF" not in pendentes_joined
    assert "nome" in pendentes_joined.lower()
    assert "nascimento" in pendentes_joined.lower()
