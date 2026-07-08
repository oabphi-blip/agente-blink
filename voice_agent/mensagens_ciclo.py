"""Ciclo completo de comunicação pós-agendamento (task #89).

Sequência:
  E1  — Conversa pré-agendamento → ping 24h (já em mensagens_janela.py)
  D-3 — Confirmação prévia (documentos + sinal se aplicável)
  D-1 — Localização (link Maps) + instruções específicas por médico
  D-0 — Lembrete matinal
  D+0 +30min — Check no-show ("está a caminho?")
  D+15 — Pós-consulta (já regra 15 do MASTER_INSTRUCTION)

REGRAS BLINK CARREGADAS:
  - Vocabulário vetado igual aos outros módulos (sem "particular",
    "infelizmente", "rapidinho", etc.)
  - Personalização obrigatória: primeiro nome do paciente, médico,
    unidade, data com dia da semana, hora.
  - Cada gerador devolve string pronta + valida com
    validar_mensagem_renovacao (do mensagens_janela).
  - Pré-op catarata, pediatria e SDP ganham nota específica.

JANELA WHATSAPP:
  D-3, D-1, D-0 e no-show check tipicamente estão FORA da janela 24h
  → no envio real, o pipeline tem que usar TEMPLATE aprovado no Meta
  Business. Os textos aqui servem como conteúdo do template (a parte
  variável vai como parâmetro).
"""
from __future__ import annotations

import re
from datetime import date, datetime

from voice_agent.mensagens_janela import (
    _PALAVRAS_VETADAS,
    _primeiro_nome,
    validar_mensagem_renovacao,
)

# ===========================================================================
# Bug C-40 (Fábio 01/07/2026, lead 24232988 Marcela) — resumo pós-agendamento
# ===========================================================================

def montar_resumo_agendamento(
    paciente: str,
    dia_hora: str,
    medico: str,
    unidade: str,
    convenio_ou_valor: str,
) -> str:
    """Resumo canônico pós-agendamento (mensagem #1 do fluxo FE.2).

    Formato exigido pelo prompt FE.2:
        📋 Resumo:
         · {paciente}
         · {dia_hora}
         · {medico}
         · Unidade {unidade}
         · Pagamento: {convenio_ou_valor}
    """
    return (
        "📋 Resumo:\n"
        f" · {paciente}\n"
        f" · {dia_hora}\n"
        f" · {medico}\n"
        f" · Unidade {unidade}\n"
        f" · Pagamento: {convenio_ou_valor}"
    )


# ===========================================================================
# Unidades — fonte de verdade
# ===========================================================================

ENDERECO_ASA_NORTE = (
    "Medical Center — SHC/N CL Quadra 102, Bloco F, sala 305, Asa Norte"
)
ENDERECO_AGUAS_CLARAS = (
    "Felicittá Shopping — Av. das Araucárias 1750, Águas Claras"
)

# URLs de busca Google Maps — funcionam sem chave de API e sem encurtador.
MAPS_ASA_NORTE = (
    "https://www.google.com/maps/search/?api=1&"
    "query=Blink+Oftalmologia+Asa+Norte+Brasilia"
)
MAPS_AGUAS_CLARAS = (
    "https://www.google.com/maps/search/?api=1&"
    "query=Blink+Oftalmologia+Aguas+Claras+Brasilia"
)

UNIDADES = {
    "asa norte": {
        "label": "Asa Norte",
        "endereco": ENDERECO_ASA_NORTE,
        "maps": MAPS_ASA_NORTE,
    },
    "águas claras": {
        "label": "Águas Claras",
        "endereco": ENDERECO_AGUAS_CLARAS,
        "maps": MAPS_AGUAS_CLARAS,
    },
    "aguas claras": {  # variante sem acento
        "label": "Águas Claras",
        "endereco": ENDERECO_AGUAS_CLARAS,
        "maps": MAPS_AGUAS_CLARAS,
    },
}


def _info_unidade(unidade: str) -> dict:
    key = (unidade or "").strip().lower()
    return UNIDADES.get(key, {
        "label": unidade or "Blink Oftalmologia",
        "endereco": "Confirme o endereço com a equipe.",
        "maps": "",
    })


# ===========================================================================
# Dia da semana em PT-BR — sem depender de locale
# ===========================================================================

_DIAS_SEMANA_PT = {
    0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
    3: "quinta-feira", 4: "sexta-feira", 5: "sábado", 6: "domingo",
}


# ===========================================================================
# Duração do slot na agenda por médico — fonte: Medware (Fábio, 31/05/2026)
# ===========================================================================
# Esta é a DURAÇÃO DO SLOT como está configurada no Medware AGORA. O slot já
# contempla triagem + médico + orientações.
#
# Karla Delalíbera ........ 30 min
#   • cobre TODOS os tipos: oftalmopediatria, SDP/Prisma, estrabismo, rotina.
#     Decisão Fábio 31/05/2026: avaliação SDP também segue 30 min — não
#     existe slot separado para SDP.
#
# Fabrício Freitas ........ 40 min
#   • cobre avaliação inicial E acompanhamento pós-operatório de catarata.
#     Mesmo slot Medware para os dois fluxos — sem distinção.
#
# Kátia Delalíbera ........ 30 min (default — NÃO está atendendo agora)
#   • Decisão Fábio 31/05/2026: Dra. Kátia está em pausa. Ao retornar,
#     reabrir esta entrada pra confirmar duração real no Medware.
#
# Não confundir com tempo do AGRUPADOR DE EXAMES (procedimentos.py): exames
# complementares são agendados em slot separado quando necessário.
#
# IMPORTANTE: se a duração mudar no Medware, atualizar AQUI e rodar pytest.
# Sentinela em `tests/test_mensagens_ciclo.py::TestDuracaoSlot` blinda
# regressão acidental.

DURACAO_SLOT_MIN_POR_MEDICO = {
    "karla": 30,
    "fabricio": 40,
    "fabrício": 40,
    # Kátia em pausa — manter default; revisar quando voltar a atender.
    "katia": 30,
    "kátia": 30,
}

DURACAO_SLOT_PADRAO_MIN = 30


def duracao_slot_min(medico: str | None) -> int:
    """Devolve duração do slot em minutos para o médico dado.

    Match case-insensitive por substring do primeiro nome no nome completo.
    """
    if not medico:
        return DURACAO_SLOT_PADRAO_MIN
    baixo = medico.lower()
    for chave, minutos in DURACAO_SLOT_MIN_POR_MEDICO.items():
        if chave in baixo:
            return minutos
    return DURACAO_SLOT_PADRAO_MIN


def hora_termino_estimada(hora_inicio: str, duracao_min: int) -> str | None:
    """'14:30' + 30 → '15:00'. Aceita 'HH:MM' ou 'HHhMM'. None se inválido."""
    if not hora_inicio or duracao_min <= 0:
        return None
    s = hora_inicio.replace("h", ":").strip()
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    total = h * 60 + m + duracao_min
    h_out, m_out = divmod(total % (24 * 60), 60)
    return f"{h_out:02d}:{m_out:02d}"


def formatar_intervalo_consulta(hora_inicio: str, medico: str | None) -> str:
    """'14:30 às 15:00 (30 min)' — usado nas mensagens do ciclo."""
    dur = duracao_slot_min(medico)
    fim = hora_termino_estimada(hora_inicio, dur)
    if fim:
        return f"{hora_inicio} às {fim} ({dur} min)"
    return f"{hora_inicio} ({dur} min)"


def _parse_data(data) -> date | None:
    """Aceita date, datetime, ou string ISO/BR ('YYYY-MM-DD' ou 'DD/MM/YYYY')."""
    if isinstance(data, datetime):
        return data.date()
    if isinstance(data, date):
        return data
    if isinstance(data, str) and data.strip():
        s = data.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


def formatar_data_completa(data) -> str:
    """'sexta-feira, 06/06/2026' — usa fallback se data inválida."""
    d = _parse_data(data)
    if not d:
        return str(data) if data else ""
    dia_semana = _DIAS_SEMANA_PT[d.weekday()]
    return f"{dia_semana}, {d.strftime('%d/%m/%Y')}"


def formatar_data_curta(data) -> str:
    """'sexta, 06/06' — versão compacta."""
    d = _parse_data(data)
    if not d:
        return str(data) if data else ""
    return f"{_DIAS_SEMANA_PT[d.weekday()].split('-')[0]}, {d.strftime('%d/%m')}"


# ===========================================================================
# Detecção de contexto médico → instruções específicas
# ===========================================================================

def _orientacao_pre_op(medico: str, motivo: str | None) -> str:
    """Orientações pré-consulta — VAZIO POR DEFAULT.

    PRINCÍPIO COSMOÉTICA (anti-padrão #2 do CLAUDE.md): NUNCA inventar
    orientação clínica. Tudo que a Lia disser ao paciente sobre o que
    fazer/trazer/evitar antes da consulta precisa ter fonte VERIFICADA
    (KB Blink ou orientação direta da equipe médica).

    Tentativas que foram REMOVIDAS em 31/05/2026 (task #92) por serem
    invenção da IA:
      - "trazer brinquedo ou lanche para a criança" (pediatria)
      - "venha acompanhada por pessoa maior de idade" (catarata pré-op)
      - "se a equipe pediu jejum ou pausa de medicamento" (catarata pré-op)
      - "exame de retina pode envolver dilatação da pupila" (Kátia)
      - "visão pode ficar embaçada por algumas horas" (qualquer)

    Para ADICIONAR uma orientação aqui no futuro, é preciso:
      1. Fonte na KB (`voice_agent/knowledge_base/`) ou
      2. Confirmação direta da equipe clínica (Karla / Fabrício / Kátia)
         REGISTRADA em `lia-atendimento-blink/memoria/bugs-licoes/`.
      3. Pytest que confirme a presença da orientação SOMENTE para o
         médico/motivo correto (não vazar pra outros casos).
    """
    return ""


# ===========================================================================
# Geradores de mensagem por etapa
# ===========================================================================

def render_d3_confirmacao(
    *,
    primeiro_nome_contato: str,
    nome_paciente: str,
    medico: str,
    unidade: str,
    data,
    hora: str,
    convenio: str | None = None,
    convenio_documentos_pendentes: bool = False,
    sinal_pendente: bool = False,
    valor_sinal: str | None = None,
) -> str:
    """D-3: confirmação prévia. Pede documentos / sinal se pendentes."""
    saudacao = (
        f"Olá, {_primeiro_nome(primeiro_nome_contato)}!"
        if _primeiro_nome(primeiro_nome_contato) else "Olá!"
    )
    data_str = formatar_data_completa(data)

    intervalo = formatar_intervalo_consulta(hora, medico)
    linhas = [
        f"{saudacao} Aqui é a Lia, da Blink Oftalmologia ✨",
        "",
        "Estamos confirmando o atendimento daqui a 3 dias:",
        f"📋 *Paciente:* {nome_paciente}",
        f"👩‍⚕️ *Médico(a):* {medico}",
        f"📅 *Dia/Hora:* {data_str} — {intervalo}",
        f"📍 *Unidade:* {_info_unidade(unidade)['label']}",
    ]
    if convenio and convenio.strip().lower() not in ("", "sem convênio", "sem convenio", "não se aplica"):
        linhas.append(f"🏥 *Convênio:* {convenio}")

    pendencias = []
    if convenio_documentos_pendentes:
        pendencias.append(
            "envie a foto da carteirinha do convênio e de um documento "
            "de identidade com foto"
        )
    if sinal_pendente:
        if valor_sinal:
            pendencias.append(
                f"finalize o sinal de R$ {valor_sinal} (Reserva Imediata) "
                "ou avise se prefere a Fila de Encaixe"
            )
        else:
            pendencias.append(
                "finalize o sinal pra manter a Reserva Imediata, ou avise "
                "se prefere a Fila de Encaixe"
            )

    if pendencias:
        linhas.append("")
        linhas.append("*Para manter sua reserva confirmada, falta:*")
        for p in pendencias:
            linhas.append(f"• {p}")

    linhas.append("")
    linhas.append("Tudo certo pra seguir com esse dia? Me responde aqui.")
    return "\n".join(linhas)


def render_d1_localizacao(
    *,
    primeiro_nome_contato: str,
    nome_paciente: str,
    medico: str,
    unidade: str,
    data,
    hora: str,
    motivo: str | None = None,
    convenio_documentos_pendentes: bool = False,
) -> str:
    """D-1: localização + Maps + instruções específicas por médico."""
    saudacao = (
        f"Olá, {_primeiro_nome(primeiro_nome_contato)}!"
        if _primeiro_nome(primeiro_nome_contato) else "Olá!"
    )
    info_unid = _info_unidade(unidade)
    data_str = formatar_data_completa(data)

    intervalo = formatar_intervalo_consulta(hora, medico)
    linhas = [
        f"{saudacao} Aqui é a Lia, da Blink Oftalmologia 👋",
        "",
        f"Amanhã é o dia da consulta:",
        f"📋 *Paciente:* {nome_paciente}",
        f"👩‍⚕️ *Médico(a):* {medico}",
        f"📅 *Dia/Hora:* {data_str} — {intervalo}",
        f"📍 *Unidade:* {info_unid['label']}",
        f"🏥 *Endereço:* {info_unid['endereco']}",
    ]
    if info_unid["maps"]:
        linhas.append(f"🗺️ *Como chegar:* {info_unid['maps']}")

    orientacao = _orientacao_pre_op(medico, motivo)
    if orientacao:
        linhas.append("")
        linhas.append(orientacao)

    if convenio_documentos_pendentes:
        linhas.append("")
        linhas.append(
            "*Lembrete:* traga a carteirinha do convênio e um documento "
            "de identidade com foto."
        )

    linhas.append("")
    linhas.append(
        "Pra confirmar a presença, responda *1 — confirmo*. "
        "Caso precise reagendar, responda *2 — reagendar*."
    )
    return "\n".join(linhas)


def render_d0_lembrete(
    *,
    primeiro_nome_contato: str,
    nome_paciente: str,
    medico: str,
    unidade: str,
    hora: str,
) -> str:
    """D-0: lembrete matinal do dia mesmo."""
    saudacao = (
        f"Bom dia, {_primeiro_nome(primeiro_nome_contato)}!"
        if _primeiro_nome(primeiro_nome_contato) else "Bom dia!"
    )
    info_unid = _info_unidade(unidade)

    intervalo = formatar_intervalo_consulta(hora, medico)
    return (
        f"{saudacao} Aqui é a Lia, da Blink Oftalmologia ✨\n\n"
        f"Hoje é o dia da consulta de *{nome_paciente}* com "
        f"*{medico}*, *{intervalo}*, na unidade *{info_unid['label']}*.\n\n"
        f"Chegando entre 10 e 15 minutos antes, nossa equipe agradece. "
        f"Qualquer imprevisto no caminho, me avisa por aqui."
    )


def render_noshow_check(
    *,
    primeiro_nome_contato: str,
    nome_paciente: str,
    medico: str,
    hora: str,
) -> str:
    """D+0 +30min: paciente não compareceu — pergunta se está a caminho."""
    saudacao = (
        f"Olá, {_primeiro_nome(primeiro_nome_contato)}!"
        if _primeiro_nome(primeiro_nome_contato) else "Olá!"
    )
    return (
        f"{saudacao} Aqui é a Lia, da Blink Oftalmologia 👋\n\n"
        f"A consulta de *{nome_paciente}* com *{medico}* estava marcada "
        f"para *{hora}* e ainda não registramos sua chegada na recepção.\n\n"
        f"Está a caminho? Houve algum imprevisto?\n"
        f"Responda *1 — chegando* / *2 — preciso reagendar* / "
        f"*3 — não posso comparecer*."
    )


# ===========================================================================
# Validação cruzada — toda mensagem passa pelo validador Blink
# ===========================================================================

def validar_todas(renderizadas: dict[str, str]) -> dict[str, dict]:
    """Aplica validar_mensagem_renovacao em cada saída.

    Aceita falhas esperadas: D-3/D-1/D-0 não precisam de "oi" nem
    "outro momento" (essas regras eram só pro ping 24h). Filtra essas
    violações sintaticamente.
    """
    out = {}
    for chave, txt in renderizadas.items():
        v = validar_mensagem_renovacao(txt)
        # Estas duas regras são exclusivas do ping 24h — outras mensagens
        # não precisam delas. Mantém só violações de vocabulário / tamanho.
        v["violacoes"] = [
            x for x in v["violacoes"]
            if "'oi'" not in x and "retomar depois" not in x
        ]
        v["ok"] = not v["violacoes"]
        out[chave] = v
    return out


def gerar_sequencia_completa(
    *,
    primeiro_nome_contato: str,
    nome_paciente: str,
    medico: str,
    unidade: str,
    data,
    hora: str,
    convenio: str | None = None,
    motivo: str | None = None,
    convenio_documentos_pendentes: bool = False,
    sinal_pendente: bool = False,
    valor_sinal: str | None = None,
) -> dict[str, str]:
    """Atalho — devolve as 4 mensagens prontas pro mesmo lead/consulta."""
    return {
        "D-3": render_d3_confirmacao(
            primeiro_nome_contato=primeiro_nome_contato,
            nome_paciente=nome_paciente, medico=medico,
            unidade=unidade, data=data, hora=hora, convenio=convenio,
            convenio_documentos_pendentes=convenio_documentos_pendentes,
            sinal_pendente=sinal_pendente, valor_sinal=valor_sinal,
        ),
        "D-1": render_d1_localizacao(
            primeiro_nome_contato=primeiro_nome_contato,
            nome_paciente=nome_paciente, medico=medico,
            unidade=unidade, data=data, hora=hora, motivo=motivo,
            convenio_documentos_pendentes=convenio_documentos_pendentes,
        ),
        "D-0": render_d0_lembrete(
            primeiro_nome_contato=primeiro_nome_contato,
            nome_paciente=nome_paciente, medico=medico,
            unidade=unidade, hora=hora,
        ),
        "no-show": render_noshow_check(
            primeiro_nome_contato=primeiro_nome_contato,
            nome_paciente=nome_paciente, medico=medico, hora=hora,
        ),
    }
