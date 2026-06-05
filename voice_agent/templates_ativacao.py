"""Templates de ativação aprovados (Fábio 03/06/2026).

Cobre dois fluxos:

  1) **Reativação de LEAD FRIO** (status_id=101508307) — modelos A-H
     Disparados manualmente ou via campanha XLSX.

  2) **Ciclo confirmação + pós-consulta** — modelos I, J1/J2, K1/K2, L
     Disparados via cron (I, J, L) ou webhook Kommo (K).

Regras herdadas dos docs MODELOS_LEAD_FRIO_PARA_APROVAR.md e
SEQUENCIA_CONFIRMACAO_E_POS_CONSULTA.md:

  - Médico SEMPRE nome+sobrenome ("Dra. Karla Delalibera" / "Dr. Fabrício Freitas")
  - Pix Asa Norte: karladelaliberaoftalmo@gmail.com
  - Pix Águas Claras: CNPJ 52.303.729/0001-30
  - Valor Karla particular: R$ 611 (sinal 50% = R$ 305,50)
  - Valor Fabrício avaliação catarata: R$ 297 (sinal 50% = R$ 148,50)
  - Janela 24h WhatsApp Cloud: se passou → usar template Meta aprovado
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Constantes oficiais (allowlist Pix — qualquer outra é alucinação)
# ---------------------------------------------------------------------------

PIX_ASA_NORTE = "karladelaliberaoftalmo@gmail.com"
PIX_AGUAS_CLARAS = "52.303.729/0001-30"

VALOR_KARLA_PARTICULAR = "R$ 611"
SINAL_KARLA_50 = "R$ 305,50"
VALOR_FABRICIO_AVALIACAO = "R$ 297"
SINAL_FABRICIO_50 = "R$ 148,50"

ENDERECO_AGUAS_CLARAS = (
    "Felicittá Shopping — Rua 36 Norte, Lote 05 sn, Bloco 11, "
    "Loja 48 — Águas Claras, Brasília DF"
)
ENDERECO_ASA_NORTE = (
    "SGAN 607, Asa Norte, Bloco A Sala 123, "
    "Ed. Brasília Medical Center, CEP 70830-300"
)

MAPS_AGUAS_CLARAS = "https://maps.app.goo.gl/FRbkUtg4U4xG55q18"
MAPS_ASA_NORTE = "https://maps.app.goo.gl/jPfjSsXA1bHhsyw56"

REVIEW_GOOGLE_AGUAS_CLARAS = "https://g.page/r/CdTrhQ8o4DYaEAE/review"
REVIEW_GOOGLE_ASA_NORTE = "https://g.page/r/CZYHYwv6CgYcEAE/review"

MEDICOS_COMPLETOS = {
    "karla": "Dra. Karla Delalibera",
    "fabricio": "Dr. Fabrício Freitas",
    "katia": "Dra. Kátia Delalibera",
}


# ---------------------------------------------------------------------------
# FLUXO 1 — Reativação de LEAD FRIO (modelos A-H)
# ---------------------------------------------------------------------------

def modelo_a_convenio_aceito(nome_paciente: str, nome_convenio: str) -> str:
    """A — Convênio aceito (Plan Assiste, SIS Senado, TJDFT, etc.)"""
    return (
        f"Olá, {nome_paciente}!\n\n"
        f"Aqui é a Blink Oftalmologia. Seu convênio {nome_convenio} cobre "
        f"consulta com a Dra. Karla Delalibera — sem sair do bolso.\n\n"
        f"Tenho horário pra essa semana ainda. Como prefere?\n\n"
        f"1️⃣ Asa Norte\n"
        f"2️⃣ Águas Claras\n"
        f"3️⃣ Prefiro que vocês me liguem\n\n"
        f"Responde com 1, 2 ou 3 que eu já organizo. 🌿"
    )


def modelo_b_particular(
    nome_paciente: str,
    convenio_nao_aceito: Optional[str] = None,
) -> str:
    """B — Particular (convênio não cobre ou paciente sem convênio)"""
    if convenio_nao_aceito:
        primeira_linha = (
            f"Aqui é a Blink Oftalmologia. Sei que o {convenio_nao_aceito} "
            f"não cobre aqui — mas temos uma condição particular com sinal "
            f"de 50% via Pix pra reservar o horário."
        )
    else:
        primeira_linha = (
            "Aqui é a Blink Oftalmologia. Pra você que vai consulta "
            "particular, temos condição com sinal de 50% via Pix pra "
            "reservar o horário."
        )
    return (
        f"Olá, {nome_paciente}!\n\n"
        f"{primeira_linha}\n\n"
        f"Valor consulta Dra. Karla Delalibera: {VALOR_KARLA_PARTICULAR} "
        f"(sinal {SINAL_KARLA_50}). Vale a tranquilidade de fechar com a melhor.\n\n"
        f"Como prefere seguir?\n\n"
        f"1️⃣ Agendar essa semana (Asa Norte ou Águas Claras)\n"
        f"2️⃣ Agendar pra próximas 2 semanas\n"
        f"3️⃣ Receber só o link de avaliação online primeiro\n\n"
        f"Me responde 1, 2 ou 3. 🌿"
    )


def modelo_c_pediatrico(nome_paciente: str) -> str:
    """C — Pediátrico (bebê 0-2 ou criança 3-12)"""
    return (
        f"Olá! Aqui é a Blink Oftalmologia, sobre a consulta do(a) "
        f"{nome_paciente}.\n\n"
        f"Avaliação oftalmológica precoce na infância é o que evita "
        f"problemas de aprendizado e desenvolvimento depois. "
        f"A Dra. Karla Delalibera é oftalmopediatra — atende criança "
        f"calminha, sem demora.\n\n"
        f"Como podemos seguir?\n\n"
        f"1️⃣ Marcar essa semana\n"
        f"2️⃣ Marcar nas próximas 2 semanas\n"
        f"3️⃣ Me passa só info sobre como é a consulta primeiro\n\n"
        f"Responde 1, 2 ou 3. 🌿"
    )


def modelo_d_familia(
    nome_contato: str,
    nome_paciente_1: str,
    nome_paciente_2: str,
) -> str:
    """D — Família (2+ pacientes no mesmo lead)"""
    return (
        f"Olá, {nome_contato}!\n\n"
        f"Aqui é a Blink Oftalmologia. Vi que vocês querem consulta pra "
        f"{nome_paciente_1} e {nome_paciente_2} — posso encaixar os dois "
        f"no mesmo dia, em horários seguidos, pra você não voltar duas vezes.\n\n"
        f"Como prefere?\n\n"
        f"1️⃣ Mesmo dia essa semana (Asa Norte ou Águas Claras)\n"
        f"2️⃣ Mesmo dia nas próximas 2 semanas\n"
        f"3️⃣ Em datas separadas mesmo\n\n"
        f"Responde 1, 2 ou 3. 🌿"
    )


def modelo_e_pausa_paciente(
    nome_paciente: str,
    motivo_da_pausa: str,
) -> str:
    """E — Pausa do próprio paciente ('vou tirar siso', 'tô em viagem')"""
    return (
        f"Olá, {nome_paciente}!\n\n"
        f"Aqui é a Blink. Lembrei de você — da última vez você comentou "
        f"que ia {motivo_da_pausa}.\n\n"
        f"Sem pressão. Só quero deixar reservado um espaço quando você "
        f"estiver pronta. Me avisa:\n\n"
        f"1️⃣ Já resolvi, pode agendar essa semana\n"
        f"2️⃣ Ainda preciso de mais 2-3 semanas\n"
        f"3️⃣ Te aviso eu mesma quando estiver\n\n"
        f"Responde 1, 2 ou 3. 🌿"
    )


def modelo_f_catarata(nome_paciente: str) -> str:
    """F — Catarata / Dr. Fabrício Freitas"""
    return (
        f"Olá, {nome_paciente}!\n\n"
        f"Aqui é a Blink Oftalmologia. Vi que você tinha interesse em "
        f"avaliar a catarata com o Dr. Fabrício Freitas, especialista em "
        f"cirurgia refrativa e de catarata.\n\n"
        f"A avaliação completa é {VALOR_FABRICIO_AVALIACAO} — define se "
        f"tem indicação cirúrgica e qual a melhor lente. Quanto antes a "
        f"avaliação, mais opções de tratamento.\n\n"
        f"Como prefere?\n\n"
        f"1️⃣ Avaliação essa semana\n"
        f"2️⃣ Avaliação nas próximas 2 semanas\n"
        f"3️⃣ Quero entender melhor antes (me liguem)\n\n"
        f"Responde 1, 2 ou 3. 🌿"
    )


def modelo_g_cliente_conhecido(nome_paciente: str) -> str:
    """G — Cliente conhecido / retorno anual"""
    return (
        f"Olá, {nome_paciente}!\n\n"
        f"Aqui é a Blink Oftalmologia. Já faz mais de um ano da sua "
        f"última consulta com a Dra. Karla Delalibera — está na hora do "
        f"check-up anual pra acompanhar o grau e a saúde dos olhos.\n\n"
        f"Já reservei essa janela pra você. Como prefere?\n\n"
        f"1️⃣ Marcar essa semana\n"
        f"2️⃣ Marcar nas próximas 2 semanas\n"
        f"3️⃣ Me avisa um dia antes pra eu confirmar\n\n"
        f"Responde 1, 2 ou 3. 🌿"
    )


def modelo_h_sem_nome() -> str:
    """H — Lead sem nome do paciente preenchido"""
    return (
        "Olá! Aqui é a Blink Oftalmologia.\n\n"
        "Vi que você entrou em contato sobre consulta com a gente e "
        "acabou ficando pendente — estou retomando pra fechar.\n\n"
        "Pra eu te oferecer o horário certo:\n\n"
        "1️⃣ A consulta é pra você ou pra outra pessoa? (me passa o nome)\n"
        "2️⃣ É por convênio ou particular?\n"
        "3️⃣ Prefere Asa Norte ou Águas Claras?\n\n"
        "Responde 1, 2 e 3 em uma mensagem só que eu já organizo o horário. 🌿"
    )


# ---------------------------------------------------------------------------
# FLUXO 2 — Confirmação + pós-consulta (modelos I, J1/J2, K1/K2, L)
# ---------------------------------------------------------------------------

def modelo_i_confirmacao_d1(
    nome_contato: str,
    dia_hora_consulta: str,
    nome_paciente: str,
    nome_medico_completo: str,
) -> str:
    """I — Confirmação D-1 véspera (1/2/3 = Confirmo / Antecipar / Fila espera)"""
    return (
        f"Olá! {nome_contato},\n\n"
        f"✨ Em continuidade ao atendimento!\n\n"
        f"Informamos os dados para confirmar consulta.\n\n"
        f"🔍 Detalhes do Agendamento:\n"
        f"📅 Dia/Hora: {dia_hora_consulta}\n"
        f"👤 Paciente(s): {nome_paciente}\n"
        f"👩‍⚕️ Médica: {nome_medico_completo}\n\n"
        f"⏳ Se não recebermos confirmação em até 2 horas após esta "
        f"mensagem, chamaremos outro paciente da fila de espera. ⏰\n\n"
        f"🔄 Caso isso aconteça, entraremos em contato para remarcar "
        f"seu atendimento para você e sua família. Obrigado! 🙏\n\n"
        f"1️⃣ Confirmo\n"
        f"2️⃣ Quero antecipar ⏩\n"
        f"3️⃣ Entrar na fila de espera (próx. 30 dias) ⏳"
    )


def modelo_j1_localizacao_aguas_claras(
    nome_contato: str,
    dia_hora_consulta: str,
) -> str:
    """J1 — Link localização D-0 06h Águas Claras"""
    return (
        f"Olá, {nome_contato}!\n\n"
        f"Para consulta prevista para data {dia_hora_consulta}\n\n"
        f"🔗 Para facilitar o acesso à Blink Oftalmologia, "
        f"unidade Águas Claras, segue o endereço e o link de localização:\n\n"
        f"📍 Endereço: {ENDERECO_AGUAS_CLARAS}\n\n"
        f"{MAPS_AGUAS_CLARAS}\n\n"
        f"✅ Estaremos à disposição para atender! 😊"
    )


def modelo_j2_localizacao_asa_norte(
    nome_contato: str,
    dia_hora_consulta: str,
) -> str:
    """J2 — Link localização D-0 06h Asa Norte"""
    return (
        f"Olá, {nome_contato}!\n\n"
        f"Para consulta prevista para data {dia_hora_consulta}\n\n"
        f"🔗 Para facilitar o acesso à Blink Oftalmologia, "
        f"unidade Asa Norte, segue o endereço e o link de localização:\n\n"
        f"📍 Endereço: {ENDERECO_ASA_NORTE}\n\n"
        f"{MAPS_ASA_NORTE}\n\n"
        f"✅ Estaremos à disposição para atender! 😊"
    )


def modelo_k1_avaliacao_google_asa_norte(
    nome_contato: str,
    nome_medico_completo: str,
    especialidade: str,
) -> str:
    """K1 — Pós-consulta avaliação Google Asa Norte (dispara em evento 8-REALIZADO)"""
    return (
        f"Olá, {nome_contato}!\n\n"
        f"😊 Obrigado por confiar na {nome_medico_completo}, "
        f"especialista em {especialidade}.\n\n"
        f"📢 Sua opinião é muito importante para ampliar nossa visão!\n\n"
        f"Por isso, buscamos saber: como foi sua experiência na Blink "
        f"Oftalmologia unidade Asa Norte clicando aqui ⬇️\n\n"
        f"{REVIEW_GOOGLE_ASA_NORTE}"
    )


def modelo_k2_avaliacao_google_aguas_claras(
    nome_contato: str,
    nome_medico_completo: str,
    especialidade: str,
) -> str:
    """K2 — Pós-consulta avaliação Google Águas Claras (dispara em evento 8-REALIZADO)"""
    return (
        f"Olá, {nome_contato}!\n\n"
        f"😊 Obrigado por confiar na {nome_medico_completo}, "
        f"especialista em {especialidade}.\n\n"
        f"📢 Sua opinião é muito importante para ampliar nossa visão!\n\n"
        f"Por isso, buscamos saber: como foi sua experiência na Blink "
        f"Oftalmologia unidade Águas Claras clicando aqui ⬇️\n\n"
        f"{REVIEW_GOOGLE_AGUAS_CLARAS}"
    )


def modelo_l_lembrete_proxima_consulta(
    nome_contato: str,
    dia_hora_consulta_anterior: str,
    nome_paciente: str,
    intervalo: str,
    intervalo_curto: Optional[str] = None,
) -> str:
    """L — Lembrete próxima consulta (D+1m / 3m / 6m / 1 ano).

    `intervalo`: "1 mês", "3 meses", "6 meses", "1 (um) ano"
    `intervalo_curto`: usado na opção 2 (ex: "1 mês" se intervalo for "3 meses")
    """
    if not intervalo_curto:
        intervalo_curto = intervalo
    return (
        f"Olá, {nome_contato}!\n\n"
        f"Agradecemos pela realização da consulta na data de "
        f"{dia_hora_consulta_anterior}.\n\n"
        f"A próxima consulta de {nome_paciente} está prevista para "
        f"daqui {intervalo}.\n\n"
        f"Quer que eu já reserve um horário?\n\n"
        f"1️⃣ Sim, agendar essa semana\n"
        f"2️⃣ Sim, mas só daqui {intervalo_curto} (me lembre depois)\n"
        f"3️⃣ Vou entrar em contato eu mesma quando estiver pronta"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolver_modelo_localizacao(
    unidade: str,
    nome_contato: str,
    dia_hora_consulta: str,
) -> str:
    """Escolhe J1 ou J2 conforme a unidade. Case-insensitive."""
    if unidade.strip().lower() in ("águas claras", "aguas claras"):
        return modelo_j1_localizacao_aguas_claras(nome_contato, dia_hora_consulta)
    if unidade.strip().lower() in ("asa norte",):
        return modelo_j2_localizacao_asa_norte(nome_contato, dia_hora_consulta)
    raise ValueError(f"Unidade desconhecida: {unidade!r}")


def resolver_modelo_avaliacao_google(
    unidade: str,
    nome_contato: str,
    nome_medico_completo: str,
    especialidade: str,
) -> str:
    """Escolhe K1 (Asa Norte) ou K2 (Águas Claras). Case-insensitive."""
    u = unidade.strip().lower()
    if u in ("asa norte",):
        return modelo_k1_avaliacao_google_asa_norte(
            nome_contato, nome_medico_completo, especialidade
        )
    if u in ("águas claras", "aguas claras"):
        return modelo_k2_avaliacao_google_aguas_claras(
            nome_contato, nome_medico_completo, especialidade
        )
    raise ValueError(f"Unidade desconhecida: {unidade!r}")
