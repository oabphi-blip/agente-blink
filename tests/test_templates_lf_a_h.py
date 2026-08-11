"""Blindagem dos 8 templates LF (A-H) plugados em templates_meta.py (task #236).

Garante que:
- Catálogo TEMPLATES_LF tem 8 entradas (A-H)
- Cada TemplateMeta tem template_name + parametros_body coerentes
- resolver_template_lf() mapeia categoria + dados → (TemplateMeta, params)
- Validações: A sem convênio → None, D sem 2º paciente → None, H sem nada → OK
"""
from voice_agent.templates_meta import (
    TEMPLATES_LF,
    TEMPLATE_LF_A,
    TEMPLATE_LF_B,
    TEMPLATE_LF_C,
    TEMPLATE_LF_D,
    TEMPLATE_LF_E,
    TEMPLATE_LF_F,
    TEMPLATE_LF_G,
    TEMPLATE_LF_H,
    resolver_template_lf,
)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def test_catalogo_tem_8_entradas():
    assert set(TEMPLATES_LF.keys()) == {"A", "B", "C", "D", "E", "F", "G", "H"}


def test_template_a_tem_2_params_nome_e_convenio():
    assert TEMPLATE_LF_A.parametros_body == ["nome_paciente", "nome_convenio"]
    assert "convenio_aceito" in TEMPLATE_LF_A.template_name


def test_template_b_tem_1_param_nome():
    assert TEMPLATE_LF_B.parametros_body == ["nome_paciente"]
    assert "particular" in TEMPLATE_LF_B.template_name


def test_template_c_pediatrico():
    assert TEMPLATE_LF_C.parametros_body == ["nome_paciente"]
    assert "pediatrico" in TEMPLATE_LF_C.template_name


def test_template_d_familia_3_params():
    assert TEMPLATE_LF_D.parametros_body == [
        "nome_contato", "nome_paciente_1", "nome_paciente_2",
    ]


def test_template_e_pausa_2_params():
    assert TEMPLATE_LF_E.parametros_body == ["nome_paciente", "motivo_da_pausa"]


def test_template_f_catarata():
    assert "catarata" in TEMPLATE_LF_F.template_name
    assert TEMPLATE_LF_F.parametros_body == ["nome_paciente"]


def test_template_g_cliente_conhecido():
    assert "conhecido" in TEMPLATE_LF_G.template_name


def test_template_h_sem_params():
    assert TEMPLATE_LF_H.parametros_body == []


# ---------------------------------------------------------------------------
# resolver_template_lf — casos felizes
# ---------------------------------------------------------------------------

def test_resolver_a_com_convenio():
    res = resolver_template_lf(
        "A", nome_paciente="Maria", nome_convenio="Saúde Caixa",
    )
    assert res is not None
    tpl, params = res
    assert tpl.template_name == TEMPLATE_LF_A.template_name
    assert params == ["Maria", "Saúde Caixa"]


def test_resolver_b_particular():
    res = resolver_template_lf("B", nome_paciente="João")
    assert res is not None
    _, params = res
    assert params == ["João"]


def test_resolver_c_pediatrico():
    res = resolver_template_lf("C", nome_paciente="Pedro")
    assert res is not None
    _, params = res
    assert params == ["Pedro"]


def test_resolver_d_familia_completo():
    res = resolver_template_lf(
        "D",
        nome_contato="Ana",
        nome_paciente="Lucas",
        nome_paciente_2="Sofia",
    )
    assert res is not None
    _, params = res
    assert params == ["Ana", "Lucas", "Sofia"]


def test_resolver_e_pausa():
    res = resolver_template_lf(
        "E", nome_paciente="Carla", motivo_da_pausa="terminar tratamento",
    )
    assert res is not None
    _, params = res
    assert params == ["Carla", "terminar tratamento"]


def test_resolver_f_catarata():
    res = resolver_template_lf("F", nome_paciente="Seu João")
    assert res is not None
    _, params = res
    assert params == ["Seu João"]


def test_resolver_g_cliente_conhecido():
    res = resolver_template_lf("G", nome_paciente="Beatriz")
    assert res is not None
    _, params = res
    assert params == ["Beatriz"]


def test_resolver_h_sem_params():
    res = resolver_template_lf("H")
    assert res is not None
    tpl, params = res
    assert tpl.template_name == TEMPLATE_LF_H.template_name
    assert params == []


# ---------------------------------------------------------------------------
# Validações / fallbacks
# ---------------------------------------------------------------------------

def test_resolver_categoria_invalida_devolve_none():
    assert resolver_template_lf("Z", nome_paciente="X") is None
    assert resolver_template_lf("", nome_paciente="X") is None


def test_resolver_a_sem_convenio_devolve_none():
    """A exige convênio — sem ele, melhor cair em B externamente."""
    assert resolver_template_lf("A", nome_paciente="Maria") is None
    assert resolver_template_lf(
        "A", nome_paciente="Maria", nome_convenio="",
    ) is None


def test_resolver_d_sem_segundo_paciente_devolve_none():
    """Família exige 2 pacientes — sem o segundo, não dá pra mandar D."""
    assert resolver_template_lf(
        "D", nome_contato="Ana", nome_paciente="Lucas",
    ) is None


def test_resolver_b_aceita_nome_vazio_fallback_voce():
    res = resolver_template_lf("B", nome_paciente="")
    assert res is not None
    _, params = res
    assert params == ["você"]


def test_resolver_e_motivo_vazio_fallback():
    res = resolver_template_lf("E", nome_paciente="Carla")
    assert res is not None
    _, params = res
    assert params == ["Carla", "resolver isso"]


def test_resolver_case_insensitive_minuscula():
    res = resolver_template_lf(
        "a", nome_paciente="Maria", nome_convenio="Cassi",
    )
    assert res is not None


def test_resolver_case_insensitive_com_espacos():
    res = resolver_template_lf(" b ", nome_paciente="João")
    assert res is not None
