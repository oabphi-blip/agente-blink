"""Blindagem dos 12 templates aprovados pelo Fábio (03/06/2026).

Garante:
  - Médico sempre nome+sobrenome ("Dra. Karla Delalibera", "Dr. Fabrício Freitas")
  - Pix oficiais nas mensagens de pagamento (allowlist)
  - Links Google e Maps exatos por unidade
  - Opções 1/2/3 presentes nos modelos de campanha
  - Variáveis injetadas corretamente
"""
import pytest

from voice_agent.templates_ativacao import (
    PIX_ASA_NORTE,
    PIX_AGUAS_CLARAS,
    VALOR_KARLA_PARTICULAR,
    SINAL_KARLA_50,
    VALOR_FABRICIO_AVALIACAO,
    MAPS_AGUAS_CLARAS,
    MAPS_ASA_NORTE,
    REVIEW_GOOGLE_AGUAS_CLARAS,
    REVIEW_GOOGLE_ASA_NORTE,
    modelo_a_convenio_aceito,
    modelo_b_particular,
    modelo_c_pediatrico,
    modelo_d_familia,
    modelo_e_pausa_paciente,
    modelo_f_catarata,
    modelo_g_cliente_conhecido,
    modelo_h_sem_nome,
    modelo_i_confirmacao_d1,
    modelo_j1_localizacao_aguas_claras,
    modelo_j2_localizacao_asa_norte,
    modelo_k1_avaliacao_google_asa_norte,
    modelo_k2_avaliacao_google_aguas_claras,
    modelo_l_lembrete_proxima_consulta,
    resolver_modelo_localizacao,
    resolver_modelo_avaliacao_google,
)


# ---------------------------------------------------------------------------
# Constantes oficiais
# ---------------------------------------------------------------------------

def test_pix_asa_norte_eh_email_karla():
    assert PIX_ASA_NORTE == "karladelaliberaoftalmo@gmail.com"


def test_pix_aguas_claras_eh_cnpj():
    assert PIX_AGUAS_CLARAS == "52.303.729/0001-30"


def test_valor_karla_e_sinal_50():
    assert VALOR_KARLA_PARTICULAR == "R$ 611"
    assert SINAL_KARLA_50 == "R$ 305,50"


def test_valor_fabricio_avaliacao():
    assert VALOR_FABRICIO_AVALIACAO == "R$ 297"


# ---------------------------------------------------------------------------
# Modelo A — Convênio aceito
# ---------------------------------------------------------------------------

def test_modelo_a_menciona_medico_completo_e_convenio():
    msg = modelo_a_convenio_aceito("Maria Teresa", "Plan Assiste - MPF (MPU)")
    assert "Dra. Karla Delalibera" in msg
    assert "Plan Assiste - MPF (MPU)" in msg
    assert "Maria Teresa" in msg
    assert "1️⃣" in msg and "2️⃣" in msg and "3️⃣" in msg


def test_modelo_a_NUNCA_so_dra_karla_sem_sobrenome():
    msg = modelo_a_convenio_aceito("X", "Y")
    # Não pode aparecer "Dra. Karla" sem "Delalibera" em seguida
    import re
    # Captura "Dra. Karla" não seguido de " Delalibera"
    matches = re.findall(r"Dra\. Karla(?! Delalibera)", msg)
    assert matches == [], f"Encontrou Dra. Karla sem sobrenome: {matches}"


# ---------------------------------------------------------------------------
# Modelo B — Particular
# ---------------------------------------------------------------------------

def test_modelo_b_com_convenio_nao_aceito():
    msg = modelo_b_particular("Beatriz", convenio_nao_aceito="Inas GDF")
    assert "Inas GDF" in msg
    assert "Dra. Karla Delalibera" in msg
    assert VALOR_KARLA_PARTICULAR in msg
    assert SINAL_KARLA_50 in msg


def test_modelo_b_sem_convenio_nao_aceito_omite_linha():
    msg = modelo_b_particular("Beatriz")
    assert "não cobre aqui" not in msg
    assert "particular" in msg.lower()


# ---------------------------------------------------------------------------
# Modelo C — Pediátrico
# ---------------------------------------------------------------------------

def test_modelo_c_menciona_oftalmopediatra_e_medico_completo():
    msg = modelo_c_pediatrico("Helena Maria")
    assert "oftalmopediatra" in msg
    assert "Dra. Karla Delalibera" in msg
    assert "Helena Maria" in msg


# ---------------------------------------------------------------------------
# Modelo D — Família
# ---------------------------------------------------------------------------

def test_modelo_d_familia_lista_2_pacientes():
    msg = modelo_d_familia(
        nome_contato="Luana",
        nome_paciente_1="Helena Maria",
        nome_paciente_2="Vicente",
    )
    assert "Luana" in msg
    assert "Helena Maria" in msg
    assert "Vicente" in msg
    assert "mesmo dia" in msg.lower()


# ---------------------------------------------------------------------------
# Modelo E — Pausa
# ---------------------------------------------------------------------------

def test_modelo_e_repete_motivo_do_paciente():
    msg = modelo_e_pausa_paciente("Circe", "tirar o siso")
    assert "tirar o siso" in msg
    assert "Sem pressão" in msg


# ---------------------------------------------------------------------------
# Modelo F — Catarata Fabrício
# ---------------------------------------------------------------------------

def test_modelo_f_menciona_fabricio_completo_e_valor_catarata():
    msg = modelo_f_catarata("João da Silva")
    assert "Dr. Fabrício Freitas" in msg
    assert VALOR_FABRICIO_AVALIACAO in msg


def test_modelo_f_NUNCA_so_dr_fabricio_sem_sobrenome():
    msg = modelo_f_catarata("X")
    import re
    matches = re.findall(r"Dr\. Fabrício(?! Freitas)", msg)
    assert matches == []


# ---------------------------------------------------------------------------
# Modelo G — Cliente conhecido
# ---------------------------------------------------------------------------

def test_modelo_g_menciona_um_ano_e_check_up_anual():
    msg = modelo_g_cliente_conhecido("Circe")
    assert "mais de um ano" in msg
    assert "Dra. Karla Delalibera" in msg
    assert "check-up anual" in msg


# ---------------------------------------------------------------------------
# Modelo H — Sem nome
# ---------------------------------------------------------------------------

def test_modelo_h_saudacao_neutra_sem_personalizacao():
    msg = modelo_h_sem_nome()
    assert "Olá!" in msg
    # Não deve ter placeholder de nome
    assert "{{" not in msg
    assert "{" not in msg.replace("Responde 1, 2 e 3", "")


# ---------------------------------------------------------------------------
# Modelo I — Confirmação D-1
# ---------------------------------------------------------------------------

def test_modelo_i_confirmacao_tem_3_opcoes_e_medico_completo():
    msg = modelo_i_confirmacao_d1(
        nome_contato="Kaliana",
        dia_hora_consulta="20/04/2026 13:30",
        nome_paciente="Valentina Raulino Coelho Vilaça",
        nome_medico_completo="Dra. Karla Delalibera",
    )
    assert "1️⃣ Confirmo" in msg
    assert "2️⃣ Quero antecipar" in msg
    assert "3️⃣ Entrar na fila de espera" in msg
    assert "Dra. Karla Delalibera" in msg
    assert "Valentina Raulino Coelho Vilaça" in msg
    assert "20/04/2026 13:30" in msg
    assert "2 horas" in msg


# ---------------------------------------------------------------------------
# Modelo J — Localização D-0
# ---------------------------------------------------------------------------

def test_modelo_j1_aguas_claras_endereco_e_link():
    msg = modelo_j1_localizacao_aguas_claras("Kaliana", "20/04/2026 13:30")
    assert "Águas Claras" in msg
    assert "Felicittá Shopping" in msg
    assert MAPS_AGUAS_CLARAS in msg
    assert "20/04/2026 13:30" in msg


def test_modelo_j2_asa_norte_endereco_e_link():
    msg = modelo_j2_localizacao_asa_norte("Kaliana", "20/04/2026 13:30")
    assert "Asa Norte" in msg
    assert "SGAN 607" in msg
    assert MAPS_ASA_NORTE in msg


def test_resolver_modelo_localizacao_escolhe_unidade_correta():
    msg_ac = resolver_modelo_localizacao("Águas Claras", "X", "data")
    assert MAPS_AGUAS_CLARAS in msg_ac
    msg_an = resolver_modelo_localizacao("Asa Norte", "X", "data")
    assert MAPS_ASA_NORTE in msg_an
    msg_an_lower = resolver_modelo_localizacao("asa norte", "X", "data")
    assert MAPS_ASA_NORTE in msg_an_lower
    with pytest.raises(ValueError):
        resolver_modelo_localizacao("Lago Sul", "X", "data")


# ---------------------------------------------------------------------------
# Modelo K — Avaliação Google
# ---------------------------------------------------------------------------

def test_modelo_k1_asa_norte_link_google():
    msg = modelo_k1_avaliacao_google_asa_norte(
        nome_contato="Kaliana",
        nome_medico_completo="Dra. Karla Delalibera",
        especialidade="Oftalmopediatria",
    )
    assert REVIEW_GOOGLE_ASA_NORTE in msg
    assert "Dra. Karla Delalibera" in msg
    assert "Oftalmopediatria" in msg
    assert "Asa Norte" in msg


def test_modelo_k2_aguas_claras_link_google():
    msg = modelo_k2_avaliacao_google_aguas_claras(
        nome_contato="Kaliana",
        nome_medico_completo="Dra. Karla Delalibera",
        especialidade="Oftalmologia Geral",
    )
    assert REVIEW_GOOGLE_AGUAS_CLARAS in msg
    assert "Águas Claras" in msg


def test_resolver_modelo_avaliacao_google_escolhe_unidade():
    msg_an = resolver_modelo_avaliacao_google(
        "Asa Norte", "X", "Dra. Karla Delalibera", "Oftalmopediatria"
    )
    assert REVIEW_GOOGLE_ASA_NORTE in msg_an
    msg_ac = resolver_modelo_avaliacao_google(
        "Águas Claras", "X", "Dra. Karla Delalibera", "Oftalmologia Geral"
    )
    assert REVIEW_GOOGLE_AGUAS_CLARAS in msg_ac


# ---------------------------------------------------------------------------
# Modelo L — Próxima consulta
# ---------------------------------------------------------------------------

def test_modelo_l_intervalo_personalizado():
    msg = modelo_l_lembrete_proxima_consulta(
        nome_contato="Kaliana",
        dia_hora_consulta_anterior="20/04/2026 13:30",
        nome_paciente="Benicio Raulino Coelho Vilaça",
        intervalo="1 (um) ano",
    )
    assert "1 (um) ano" in msg
    assert "Benicio Raulino Coelho Vilaça" in msg
    assert "20/04/2026 13:30" in msg


def test_modelo_l_intervalo_curto_default_igual_intervalo():
    msg = modelo_l_lembrete_proxima_consulta(
        nome_contato="X",
        dia_hora_consulta_anterior="data",
        nome_paciente="Y",
        intervalo="6 meses",
    )
    # intervalo_curto não informado → usa o próprio intervalo
    assert msg.count("6 meses") >= 2


def test_modelo_l_intervalo_curto_independente():
    msg = modelo_l_lembrete_proxima_consulta(
        nome_contato="X",
        dia_hora_consulta_anterior="data",
        nome_paciente="Y",
        intervalo="3 meses",
        intervalo_curto="1 mês",
    )
    assert "3 meses" in msg
    assert "1 mês" in msg


# ---------------------------------------------------------------------------
# Regra invariante — nenhum template menciona Pix falso
# ---------------------------------------------------------------------------

def test_nenhum_template_menciona_pix_invalido():
    """Allowlist: só Pix Asa Norte (email Karla) ou Águas Claras (CNPJ Blink)."""
    todas_msgs = [
        modelo_a_convenio_aceito("X", "Y"),
        modelo_b_particular("X", "Inas"),
        modelo_b_particular("X"),
        modelo_c_pediatrico("X"),
        modelo_d_familia("X", "Y", "Z"),
        modelo_e_pausa_paciente("X", "viagem"),
        modelo_f_catarata("X"),
        modelo_g_cliente_conhecido("X"),
        modelo_h_sem_nome(),
        modelo_i_confirmacao_d1("X", "data", "Y", "Dra. Karla Delalibera"),
        modelo_j1_localizacao_aguas_claras("X", "data"),
        modelo_j2_localizacao_asa_norte("X", "data"),
        modelo_k1_avaliacao_google_asa_norte("X", "Dra. Karla Delalibera", "Y"),
        modelo_k2_avaliacao_google_aguas_claras("X", "Dra. Karla Delalibera", "Y"),
        modelo_l_lembrete_proxima_consulta("X", "data", "Y", "1 mês"),
    ]
    import re
    chaves_pix_validas = {PIX_ASA_NORTE, PIX_AGUAS_CLARAS}
    for msg in todas_msgs:
        # Procura qualquer email
        emails = re.findall(r"[\w.-]+@[\w.-]+\.\w+", msg)
        for email in emails:
            assert email in chaves_pix_validas or "blinkoftalmologia" in email, (
                f"Email não-allowlist encontrado: {email}"
            )
