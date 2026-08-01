"""Bypasses determinísticos — Nível 3 do framework anti-invenção da Lia.

Origem: Fábio 12/07/2026 — após bug C-43 (Mariana Lopes) e C-44 (Clarice),
decisão de expandir bypass Python (`oferta_deterministica.py`) pra outros
pontos onde LLM erra sistematicamente.

Cada função exposta aqui:
    1. Recebe (ctx, user_text)
    2. Detecta se está no ponto crítico coberto por bypass
    3. Retorna string canônica pronta OU None (LLM continua)

Se retorna string, `responder.reply()` NÃO chama LLM naquele turno.
Zero probabilidade de invenção nos 4 pontos cobertos:

    1. Confirmação de horário aceito (paciente disse "1️⃣" ou "Segunda 13/07")
    2. Envio de endereço + resumo pós-agenda (agenda gravada mas endereço não enviado)
    3. Orientação de urgência médica (paciente citou dor forte / trauma / não enxerga)
    4. Resposta de valor consulta (paciente perguntou "quanto custa?")

Contrato de segurança:
    - Nunca inventa data/hora/valor/médico — usa apenas ctx
    - Nunca menciona cargo inexistente (regra C-44)
    - Zero LLM no ponto coberto
    - Fail-open: erro/exceção → retorna None, LLM continua fluxo normal
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# TOGGLE PADRÃO ON — rollback = env=0
# ═══════════════════════════════════════════════════════════════════════

def _ativado(env_name: str) -> bool:
    """Default ON. Set env=0/false/no/off pra desligar."""
    return (os.getenv(env_name) or "1").lower() not in (
        "0", "false", "no", "off", "",
    )


def _nome_paciente(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    nome = (
        known.get("nome_paciente")
        or known.get("nome_completo_paciente")
        or known.get("nome")
        or ""
    )
    primeiro = str(nome).strip().split()[0] if str(nome).strip() else ""
    return primeiro


def _nome_medico_canonico(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    m = known.get("medico") or known.get("medicos") or ""
    if isinstance(m, (list, tuple)):
        m = m[0] if m else ""
    ml = str(m).lower()
    if "karla" in ml or "delalíbera" in ml or "delalibera" in ml:
        return "Dra. Karla Delalíbera"
    if "fabrício" in ml or "fabricio" in ml or "freitas" in ml:
        return "Dr. Fabrício Freitas"
    return "a médica"


def _unidade_str(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    u = known.get("unidade") or known.get("unidades") or ""
    if isinstance(u, (list, tuple)):
        u = u[0] if u else ""
    return str(u)


def _convenio_str(ctx: Optional[dict]) -> str:
    known = (ctx or {}).get("known") or {}
    return str(known.get("convenio") or "").strip()


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 1 — CONFIRMAÇÃO DE HORÁRIO ACEITO
# ═══════════════════════════════════════════════════════════════════════
# Paciente respondeu "1️⃣" ou "1" ou "opção 1" ou "segunda 13/07 17h30"
# depois que Lia ofereceu 2 slots. Em vez do LLM improvisar texto de
# confirmação (que às vezes é vazio, às vezes já grava sem confirmar,
# às vezes inventa "vou passar pra remarcação"), Python monta o texto
# canônico exato.
# ═══════════════════════════════════════════════════════════════════════

_PADRAO_ACEITE_SLOT = re.compile(
    r"(?:^|\W)("
    r"1[\W]|2[\W]|3[\W]"  # 1️⃣ 2️⃣ 3️⃣ ou "1)" "2." etc
    r"|primeir[oa]|segund[oa]|terceir[oa]"
    r"|op[cç][aã]o\s*[123]"
    r"|primeir[oa]\s*op[cç][aã]o|segund[oa]\s*op[cç][aã]o"
    r"|(?:fica|serve|prefiro|melhor|pego|topo|aceito)"
    r")",
    re.IGNORECASE,
)


def deve_gerar_confirmacao_aceite(ctx: Optional[dict], user_text: str) -> Optional[str]:
    """Retorna texto canônico se paciente aceitou um dos slots ofertados.

    Requer no ctx:
        - fsm.estado == 'AGENDA' ou 'CONFIRMACAO'
        - ctx.slots_ofertados: lista com pelo menos 1 slot que Lia ofertou
        - ctx.known preenchido (nome, médico, unidade)

    Retorna None se:
        - Não tem sinal claro de aceite no user_text
        - ctx sem slots ofertados
        - Toggle BLINDAGEM_ACEITE_ATIVADO=0
    """
    if not _ativado("BLINDAGEM_ACEITE_ATIVADO"):
        return None
    if not ctx or not user_text:
        return None
    if not _PADRAO_ACEITE_SLOT.search(user_text or ""):
        return None

    slots = ctx.get("slots_ofertados") or []
    if not slots:
        return None

    # Descobre qual slot foi aceito
    slot_aceito = _identificar_slot_aceito(user_text, slots)
    if not slot_aceito:
        return None

    return _montar_texto_confirmacao(slot_aceito, ctx)


def _identificar_slot_aceito(user_text: str, slots: list[dict]) -> Optional[dict]:
    """Extrai qual slot o paciente aceitou.

    Tenta em ordem:
        1. Referência posicional (1️⃣ / 2 / primeira opção)
        2. Data literal (13/07 / segunda-feira)
        3. Hora literal (17h30 / 15h)
    """
    t = user_text.lower().strip()

    # 1. Data literal (prioridade — dado objetivo do paciente)
    for slot in slots:
        try:
            dt = datetime.strptime(str(slot.get("data_iso", ""))[:10], "%Y-%m-%d")
            data_br = dt.strftime("%d/%m")
            if data_br in t:
                return slot
        except (ValueError, TypeError):
            continue

    # 2. Hora literal (segunda prioridade — também objetivo)
    for slot in slots:
        hora = str(slot.get("hora") or "")[:5]
        if not hora:
            continue
        hora_h = hora.replace(":", "h")
        # Word boundary evita falso positivo tipo "11h30" casando "1h30"
        if re.search(rf"\b{re.escape(hora_h)}\b", t) or re.search(rf"\b{re.escape(hora)}\b", t):
            return slot

    # 3. Posicional (último fallback — "primeira" / emoji 1️⃣ isolado)
    # Padrão estrito: só isolado como token, NÃO como parte de "11h30" etc
    if re.search(r"(?:^|\s)(?:1️⃣|[1](?![0-9h:]))", t) or re.search(r"\bprimeir[oa]\b", t) or "opção 1" in t or "opcao 1" in t:
        return slots[0] if slots else None
    if re.search(r"(?:^|\s)(?:2️⃣|[2](?![0-9h:]))", t) or re.search(r"\bsegund[oa]\b", t) or "opção 2" in t or "opcao 2" in t:
        return slots[1] if len(slots) > 1 else None
    if re.search(r"(?:^|\s)(?:3️⃣|[3](?![0-9h:]))", t) or re.search(r"\bterceir[oa]\b", t) or "opção 3" in t or "opcao 3" in t:
        return slots[2] if len(slots) > 2 else None

    return None


def _montar_texto_confirmacao(slot: dict, ctx: Optional[dict]) -> str:
    """Texto canônico pós-aceite. Zero invenção — só ctx + slot."""
    from voice_agent.mensagens_ciclo import (
        _DIAS_SEMANA_PT,
        formatar_intervalo_consulta,
    )

    try:
        dt = datetime.strptime(str(slot.get("data_iso", ""))[:10], "%Y-%m-%d")
        dia_semana = _DIAS_SEMANA_PT[dt.weekday()].capitalize()
        data_br = dt.strftime("%d/%m")
    except (ValueError, TypeError):
        return ""

    hora_inicio = str(slot.get("hora") or "")[:5]
    medico_ctx = (ctx or {}).get("known", {}).get("medico") or ""
    intervalo = formatar_intervalo_consulta(hora_inicio, medico_ctx)

    nome = _nome_paciente(ctx)
    medico = _nome_medico_canonico(ctx)
    unidade = _unidade_str(ctx)
    convenio = _convenio_str(ctx)

    saudacao = f"{nome}, " if nome else ""
    unidade_frase = f" na unidade {unidade}" if unidade else ""
    convenio_frase = (
        f" pelo {convenio}"
        if convenio and convenio.lower() not in (
            "não se aplica", "nao se aplica", "particular",
        )
        else ""
    )

    return (
        f"{saudacao}fechado! Vou reservar {dia_semana} ({data_br}) — "
        f"{intervalo} — com {medico}{unidade_frase}{convenio_frase}.\n\n"
        "Já estou registrando no sistema — em instantes te envio a "
        "confirmação com o endereço e as orientações."
    )


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 2 — ENDEREÇO + RESUMO PÓS-AGENDAMENTO
# ═══════════════════════════════════════════════════════════════════════
# Após slot gravado no Medware, Lia às vezes esquece de enviar o resumo +
# endereço + link maps (bug C-40 Marcela). Python força sempre.
# Reusa `mensagens_ciclo.montar_resumo_agendamento` + endereço fixo.
# ═══════════════════════════════════════════════════════════════════════

def deve_enviar_endereco_pos_agenda(ctx: Optional[dict]) -> Optional[str]:
    """Retorna resumo + endereço + maps se agenda foi gravada mas envio pendente.

    Requer no ctx:
        - ctx.agenda_gravada == True (setado pelo handle_gravar_agendamento_medware)
        - ctx.endereco_ja_enviado != True (Redis flag setada após primeiro envio)
        - ctx.known com nome, médico, unidade, dia_hora, convenio

    Retorna None se:
        - Agenda não foi gravada nesse turno
        - Endereço já foi enviado
        - Toggle BLINDAGEM_ENDERECO_ATIVADO=0
    """
    if not _ativado("BLINDAGEM_ENDERECO_ATIVADO"):
        return None
    if not ctx:
        return None
    if not ctx.get("agenda_gravada"):
        return None
    if ctx.get("endereco_ja_enviado"):
        return None

    known = ctx.get("known") or {}
    if not (known.get("nome_paciente") and known.get("medico") and known.get("unidade")):
        return None

    return _montar_endereco_pos_agenda(ctx)


def _montar_endereco_pos_agenda(ctx: dict) -> str:
    """Resumo + endereço + link maps + orientação de chegada."""
    from voice_agent.mensagens_ciclo import (
        _info_unidade,
        montar_resumo_agendamento,
    )

    known = ctx.get("known") or {}
    nome = known.get("nome_paciente") or ""
    dia_hora = known.get("dia_hora_confirmado") or known.get("dia_consulta") or ""
    medico = _nome_medico_canonico(ctx)
    unidade_str = _unidade_str(ctx)
    unidade_info = _info_unidade(unidade_str)
    convenio = _convenio_str(ctx)
    convenio_ou_valor = (
        convenio if convenio and convenio.lower() not in (
            "não se aplica", "nao se aplica", "particular",
        ) else "Particular"
    )

    resumo = montar_resumo_agendamento(
        paciente=nome,
        dia_hora=dia_hora,
        medico=medico,
        unidade=unidade_info["label"],
        convenio_ou_valor=convenio_ou_valor,
    )

    endereco = unidade_info["endereco"]
    maps = unidade_info["maps"]
    maps_frase = f"\n\n📍 Mapa: {maps}" if maps else ""

    return (
        f"{resumo}\n\n"
        f"📍 Endereço: {endereco}"
        f"{maps_frase}\n\n"
        "Chegue 15 min antes pra fazer o cadastro. "
        "Se precisar remarcar, é só me avisar por aqui."
    )


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 3 — ORIENTAÇÃO DE URGÊNCIA MÉDICA
# ═══════════════════════════════════════════════════════════════════════
# Paciente relatou trauma agudo / dor forte / perda de visão / olho
# fechado. Lia às vezes minimiza ou desvia pra agenda regular.
# Python força orientação PS + oferta de horário próximo em paralelo.
# ═══════════════════════════════════════════════════════════════════════

_PADROES_URGENCIA = re.compile(
    r"("
    r"trauma\s+(?:na\s+|no\s+)?(?:c[oó]rnea|olho|vis[aã]o)"
    r"|dor\s+forte\s+(?:no\s+|de\s+)?olho"
    r"|n[aã]o\s+consigo\s+abrir\s+o\s+olho"
    r"|n[aã]o\s+(?:consigo|estou\s+conseguindo)\s+enxergar"
    r"|olho\s+(?:muito\s+)?vermelho\s+(?:e\s+)?doendo"
    r"|perdi\s+a\s+vis[aã]o"
    r"|caiu\s+(?:algo\s+)?no\s+olho"
    r"|corpo\s+estranho\s+no\s+olho"
    r"|fura(?:ram)?\s+o\s+olho"
    r"|batida\s+forte\s+no\s+olho"
    r"|acidente\s+(?:no\s+)?olho"
    r"|queimadura\s+(?:no\s+)?olho"
    r"|c[eé]gu(?:a|o)"
    r")",
    re.IGNORECASE,
)


def deve_orientar_urgencia(ctx: Optional[dict], user_text: str) -> Optional[str]:
    """Retorna orientação PS + oferta de antecipação se paciente relatou urgência.

    Toggle: BLINDAGEM_URGENCIA_ATIVADO (default ON).
    """
    if not _ativado("BLINDAGEM_URGENCIA_ATIVADO"):
        return None
    if not user_text:
        return None
    if not _PADROES_URGENCIA.search(user_text):
        return None

    nome = _nome_paciente(ctx)
    saudacao = f"{nome}, " if nome else ""

    return (
        f"{saudacao}pelo que você descreveu, é uma situação clínica "
        "que precisa de avaliação médica AGORA — não dá pra esperar "
        "próxima consulta agendada.\n\n"
        "**Procure imediatamente o pronto-socorro oftalmológico "
        "mais próximo.** Se estiver em Brasília, o HBDF (Hospital de "
        "Base) e o HRAN têm PS oftalmológico 24h.\n\n"
        "Assim que passar pelo atendimento de urgência, me avisa por "
        "aqui — se a Dra. Karla ou o Dr. Fabrício precisarem te "
        "receber pra acompanhamento, agendo imediatamente com "
        "prioridade."
    )


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 4 — RESPOSTA DE VALOR DE CONSULTA
# ═══════════════════════════════════════════════════════════════════════
# Paciente perguntou "quanto custa?" / "qual o valor?" — LLM às vezes
# inventa valor errado. Python responde canônico usando ctx.
# ═══════════════════════════════════════════════════════════════════════

_PADROES_PERGUNTA_VALOR = re.compile(
    r"("
    r"(?:quanto|qual|qto)\s+(?:custa|é|e|vale|fica|sai|paga)"
    r"|(?:qual|qto|quanto)\s+(?:o\s+)?(?:valor|pre[cç]o|custo)"
    r"|quanto\s+(?:eu\s+)?(?:vou\s+)?pag(?:o|ar|amos)"  # relaxado: "eu" opcional
    r"|(?:tem|qual)\s+desconto"
    r")",
    re.IGNORECASE,
)

_VALORES_CANONICOS = {
    "karla_particular": "R$ 611",
    "karla_apv": "R$ 800",
    "fabricio_catarata": "R$ 297",
    "fabricio_50plus": "R$ 611",
}


def deve_responder_valor(ctx: Optional[dict], user_text: str) -> Optional[str]:
    """Se paciente perguntou valor, retorna resposta canônica.

    Se convênio aceito no ctx: fala "coberta pelo seu plano".
    Se particular: fala valor exato da tabela.
    Se não tem médico definido: retorna None (LLM triaga primeiro).
    """
    if not _ativado("BLINDAGEM_VALOR_ATIVADO"):
        return None
    if not user_text:
        return None
    if not _PADROES_PERGUNTA_VALOR.search(user_text):
        return None

    known = (ctx or {}).get("known") or {}
    if not known.get("medico"):
        return None  # Sem médico, LLM triaga

    medico = _nome_medico_canonico(ctx)
    convenio = _convenio_str(ctx).lower()
    nome = _nome_paciente(ctx)
    saudacao = f"{nome}, " if nome else ""

    # Convênio aceito → confirma sem falar em cobertura (Bug C-61)
    conv_aceito = (
        convenio and
        convenio not in ("não se aplica", "nao se aplica", "particular", "") and
        "não aceit" not in convenio and
        "nao aceit" not in convenio
    )
    if conv_aceito:
        return (
            f"{saudacao}sim, atendemos o {convenio.title()}! 👍\n\n"
            "Qual unidade fica melhor para você — **Asa Norte** ou **Águas Claras**?"
        )

    # Particular — determina valor + rótulo do serviço
    motivo = str(known.get("motivo") or known.get("especialidade") or "").lower()

    if "karla" in medico.lower():
        if "apv" in motivo or "processamento visual" in motivo or "sdp" in motivo:
            valor_pix = "R$ 800"
            valor_cartao = "R$ 870"
            valor_2x = "R$ 435"
            servico = "avaliação do processamento visual"
        else:
            valor_pix = "R$ 611"
            valor_cartao = "R$ 670"
            valor_2x = "R$ 335"
            servico = "consulta"
    elif "fabrício" in medico.lower() or "fabricio" in medico.lower():
        if "catarata" in motivo:
            valor_pix = "R$ 445"
            valor_cartao = "R$ 470"
            valor_2x = "R$ 235"
            servico = "avaliação de catarata"
        else:
            valor_pix = "R$ 611"
            valor_cartao = "R$ 670"
            valor_2x = "R$ 335"
            servico = "consulta"
    else:
        return None  # Médico desconhecido, LLM

    # C-68 v2 (Fábio 21/07/2026, modelo humano lead Layssa):
    # Copia formato usado pelo atendimento humano — mais claro, mais rico.
    # Estrutura: intro → exames descritos → especialistas → voucher → valor inline → CTA.
    nome_apenas = nome.rstrip(",").strip() if nome else ""
    abertura = f"Olá, {nome_apenas}\n\n" if nome_apenas else ""
    return (
        f"{abertura}"
        f"Para entender exatamente o que está incluso na {servico}, segue um resumo:\n\n"
        "✅ **Incluso na consulta os seguintes exames:**\n"
        "👁️ Tonometria (medir a pressão ocular)\n"
        "🔍 Avaliação do alinhamento e coordenação dos olhos\n"
        "🩺 Exame detalhado do fundo do olho (mapeamento de retina)\n\n"
        "➕ **Se houver indicação do médico, também está incluso:**\n"
        "👩‍⚕️ Avaliação com especialistas do corpo clínico "
        "(Catarata, Refrativa, Plástica Ocular, Retina e Vítreo).\n\n"
        "🪪 **E, se necessário:**\n"
        "🕶️ voucher para aquisição de óculos.\n\n"
        f"💳 **O valor da {servico} com a {medico}** tem as seguintes opções: "
        f"**Primeira Opção: {valor_pix} Pix**, "
        f"**Segunda Opção: {valor_cartao} (1x Cartão)**, "
        f"**Terceira Opção: {valor_cartao} (2x Cartão)**, "
        "para o primeiro paciente.\n\n"
        "Qual a sua escolha?"
    )


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 6 — FAQ ESPECIALIDADE / MÉDICO (Bug C-74, 26/07/2026)
# ═══════════════════════════════════════════════════════════════════════
# Paciente perguntou "tem oftalmologista pediátrico?", "faz estrabismo?",
# "faz catarata?" etc. — resposta é COMPLETAMENTE determinística (KB).
# Zero motivo pra chamar LLM. Circuit breaker C-56 nunca será ativado
# nessas perguntas simples.
# Toggle: BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO (default ON)
# ═══════════════════════════════════════════════════════════════════════

# ── padrões por especialidade ──────────────────────────────────────────

_V = r"(?:tem|têm|temos?|faz(?:em)?|trata(?:m)?|opera(?:m)?(?:[çc][aã]o\s+de)?)"

_FAQ_PEDIATRIA = re.compile(
    r"("
    r"(?:tem|têm)\s+oftalmo(?:logista)?[\s\-]*(?:pedi[aá]tri[cao]{1,2}|infantil)"
    r"|(?:tem|têm)\s+pediatra"
    r"|atendem?\s+(?:crian[çc]as?|beb[êes]+|crian[çc]inha)"
    r"|faz(?:em)?\s+(?:consulta\s+)?(?:pedi[aá]tri[cao]{1,2}|infantil)"
    r"|(?:pedi[aá]tri[cao]{1,2}|infantil).*oftalmo"
    r"|oftalmo.*(?:pedi[aá]tri[cao]{1,2}|infantil)"
    r"|(?:consulta|retorno)\s+(?:pra\s+)?(?:crian[çc]a|beb[êe]|minha\s+filha|meu\s+filho)"
    r")",
    re.IGNORECASE,
)

_FAQ_ESTRABISMO = re.compile(
    r"("
    + _V + r"\s+estrabismo"
    r"|estrabismo"
    r"|olho\s+(?:torto|desviado|cruzado|virando)"
    r"|olhos?\s+(?:tortos?|desviados?|cruzados?)"
    r"|desvio\s+(?:do\s+)?ocular"
    r")",
    re.IGNORECASE,
)

_FAQ_CATARATA = re.compile(
    r"("
    + _V + r"\s+catarata"
    r"|cirurgia\s+(?:de\s+)?catarata"
    r"|opera[çc][aã]o\s+(?:de\s+)?catarata"
    r")",
    re.IGNORECASE,
)

_FAQ_CORNEA = re.compile(
    r"("
    + _V + r"\s+pter[íi]gio"
    r"|carne\s+no\s+olho"
    r"|(?:tem|têm|faz(?:em)?|trata(?:m)?)\s+(?:c[oó]rnea|ceratocone|transplante\s+(?:de\s+)?c[oó]rnea)"
    r"|ceratocone"
    r")",
    re.IGNORECASE,
)

# Perguntas gerais sobre "tem oftalmologista" / "tem médico" → não interceptar,
# deixa LLM responder (pode querer coletar contexto)


def deve_responder_faq_especialidade(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """Retorna resposta canônica para perguntas FAQ sobre especialidades.

    Detecta pergunta → mapeia pra médico correto → retorna texto pronto.
    Nunca chama LLM. Fail-open (exceção → None).

    Toggle: BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO (default ON).
    """
    if not _ativado("BLINDAGEM_FAQ_ESPECIALIDADE_ATIVADO"):
        return None
    if not user_text:
        return None

    txt = user_text.strip()

    # ── Pediatria → Dra. Karla ─────────────────────────────────────────
    if _FAQ_PEDIATRIA.search(txt):
        return (
            "Sim! 😊 A Dra. Karla Delalíbera é nossa especialista em oftalmopediatria "
            "e atende crianças de todas as idades.\n\n"
            "Pra agendar, me passa o nome e a data de nascimento do paciente?"
        )

    # ── Estrabismo → Dra. Karla ────────────────────────────────────────
    if _FAQ_ESTRABISMO.search(txt):
        return (
            "Sim! A Dra. Karla Delalíbera é nossa especialista em estrabismo. 👁️\n\n"
            "Me passa o nome e a data de nascimento do paciente pra eu verificar "
            "os horários disponíveis?"
        )

    # ── Catarata → Dr. Fabrício ────────────────────────────────────────
    if _FAQ_CATARATA.search(txt):
        return (
            "Sim! O Dr. Fabrício Freitas é nosso especialista em catarata "
            "(avaliação e cirurgia). 🏥\n\n"
            "Me passa o nome e a data de nascimento do paciente?"
        )

    # ── Córnea / Pterígio → Dr. Fabrício ──────────────────────────────
    if _FAQ_CORNEA.search(txt):
        return (
            "Sim! O Dr. Fabrício Freitas é nosso especialista em córnea e pterígio "
            "(a 'carne no olho'). 👁️\n\n"
            "Me passa o nome e a data de nascimento do paciente?"
        )

    return None


# ═══════════════════════════════════════════════════════════════════════
# BUG C-78 (01/08/2026) — FAQ DISPONIBILIDADE HOJE
#
# Causa raiz lead 23456132: paciente perguntou "A Dra Karla está atendendo hj?"
# num sábado. Bot foi ao Medware → vazio (sábado = sem agenda) → ctx.agenda=[] →
# C-30 não dispara (has_agenda=False) → C-30A trocou por "Medware instável" (ERRADO)
# → LLM entrou em loop stall 3x com "reconferir os horários exatos".
#
# Fix: interceptar ANTES de chegar ao Medware. Resposta 100% determinística
# baseada em dia-da-semana + escala de atendimento. Zero LLM.
#
# Toggle: BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO (default ON)
# ═══════════════════════════════════════════════════════════════════════

_TZ_BRT = ZoneInfo("America/Sao_Paulo")

# weekday(): 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom
_KARLA_ASA_NORTE_DIAS  = frozenset({0, 2, 4})   # seg / qua / sex
_KARLA_AGUAS_CLARAS_DIAS = frozenset({1, 3})     # ter / qui
_KARLA_TODOS_DIAS      = frozenset({0, 1, 2, 3, 4})  # fallback sem unidade
_FABRICIO_DIAS         = frozenset({1, 3})        # ter / qui

_NOMES_DIAS_PT = {
    0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
    3: "quinta-feira",  4: "sexta-feira", 5: "sábado",       6: "domingo",
}

_FAQ_DISP_HOJE = re.compile(
    r"("
    r"est[áa]\s+atendendo\s+(?:hoje|hj|agora)"
    r"|tem\s+(?:hor[áa]rio|vaga|consulta|atendimento)\s+(?:hoje|hj)"
    r"|atende\s+(?:hoje|hj)"
    r"|(?:hoje|hj)\s+tem\s+(?:hor[áa]rio|vaga|consulta|atendimento)"
    r"|(?:hoje|hj)\s+est[áa]\s+atendendo"
    r"|atende\s+(?:s[áa]bado|domingo|nesse\s+s[áa]bado|nesse\s+domingo)"
    r"|tem\s+(?:hor[áa]rio|vaga)\s+(?:s[áa]bado|domingo|amanh[ãa])"
    r"|(?:s[áa]bado|domingo)\s+tem\s+(?:hor[áa]rio|vaga|atendimento)"
    r")",
    re.IGNORECASE,
)


def _proxima_data_no_plano(
    hoje: date, dias_plano: frozenset,
) -> tuple[date, str]:
    """Retorna (data, nome_dia) do próximo atendimento no conjunto de dias."""
    for delta in range(1, 8):
        prox = hoje + timedelta(days=delta)
        if prox.weekday() in dias_plano:
            return prox, _NOMES_DIAS_PT[prox.weekday()]
    return hoje + timedelta(days=1), "segunda-feira"  # fallback defensivo


def deve_responder_faq_disponibilidade_hoje(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """Resposta determinística para perguntas de disponibilidade no dia.

    Detecta "está atendendo hoje/hj?", "tem horário hoje?", "atende sábado?"
    e responde baseado no dia-da-semana atual (fuso BRT) + escala dos médicos.

    NUNCA chama Medware. Fail-open (exceção → None, LLM continua).

    Toggle: BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO (default ON).
    """
    if not _ativado("BLINDAGEM_FAQ_DISPONIBILIDADE_ATIVADO"):
        return None
    if not user_text or not _FAQ_DISP_HOJE.search(user_text.strip()):
        return None

    try:
        hoje = datetime.now(_TZ_BRT).date()
        wd = hoje.weekday()
        nome_hoje = _NOMES_DIAS_PT[wd]

        known = (ctx or {}).get("known") or {}
        medico_raw  = (known.get("medico") or "").lower()
        unidade_raw = (known.get("unidade") or "").lower()

        # ── Identificar médico ─────────────────────────────────────────
        e_karla    = "karla"  in medico_raw
        e_fabricio = "fabr"   in medico_raw
        if not e_karla and not e_fabricio:
            return None   # médico desconhecido — deixa o LLM lidar

        # ── Identificar unidade ────────────────────────────────────────
        e_asa_norte    = "asa norte" in unidade_raw or "asa_norte" in unidade_raw
        e_aguas_claras = (
            "águas claras" in unidade_raw
            or "aguas claras" in unidade_raw
            or ("agua" in unidade_raw and "clara" in unidade_raw)
        )

        if e_karla:
            medico_str = "Dra. Karla Delalíbera"
            if e_asa_norte:
                dias_plano  = _KARLA_ASA_NORTE_DIAS
                unidade_str: Optional[str] = "Asa Norte"
            elif e_aguas_claras:
                dias_plano  = _KARLA_AGUAS_CLARAS_DIAS
                unidade_str = "Águas Claras"
            else:
                dias_plano  = _KARLA_TODOS_DIAS
                unidade_str = None
        else:
            medico_str  = "Dr. Fabrício Freitas"
            dias_plano  = _FABRICIO_DIAS
            unidade_str = None

        atende_hoje = (wd in dias_plano)

        if atende_hoje:
            # Inferir unidade pelo dia quando Karla sem unidade definida
            if e_karla and not unidade_str:
                unidade_str = (
                    "Asa Norte" if wd in _KARLA_ASA_NORTE_DIAS else "Águas Claras"
                )
            unidade_msg = f" em {unidade_str}" if unidade_str else ""
            return (
                f"Sim! 😊 Hoje é {nome_hoje} — a {medico_str} tem atendimento"
                f"{unidade_msg}. Me passa o nome e a data de nascimento do "
                f"paciente pra eu verificar os horários disponíveis?"
            )

        # ── Não atende hoje — mostrar próxima(s) data(s) ──────────────
        if e_karla and not unidade_str:
            # Mostrar ambas as unidades (paciente não definiu)
            prox_an, prox_an_dia = _proxima_data_no_plano(hoje, _KARLA_ASA_NORTE_DIAS)
            prox_ac, prox_ac_dia = _proxima_data_no_plano(hoje, _KARLA_AGUAS_CLARAS_DIAS)
            return (
                f"Hoje é {nome_hoje} — a {medico_str} não tem atendimento neste dia. 😊\n\n"
                f"As próximas disponibilidades são:\n"
                f"• Asa Norte: {prox_an_dia} ({prox_an.strftime('%d/%m')})\n"
                f"• Águas Claras: {prox_ac_dia} ({prox_ac.strftime('%d/%m')})\n\n"
                f"Qual unidade fica mais perto de você?"
            )
        else:
            prox, prox_dia = _proxima_data_no_plano(hoje, dias_plano)
            unidade_msg = f" em {unidade_str}" if unidade_str else ""
            return (
                f"Hoje é {nome_hoje} — a {medico_str} não tem atendimento neste dia. 😊\n\n"
                f"A próxima consulta disponível{unidade_msg} é na "
                f"{prox_dia} ({prox.strftime('%d/%m')}). "
                f"Quer que eu verifique os horários?"
            )

    except Exception as e:  # noqa: BLE001
        log.warning("[C-78] faq_disponibilidade_hoje falhou: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA — chain of responsibility
# ═══════════════════════════════════════════════════════════════════════

def tentar_bypass_deterministico(
    ctx: Optional[dict], user_text: str,
) -> Optional[tuple[str, str]]:
    """Tenta cada bypass em ordem. Retorna (nome_bypass, texto) do primeiro
    que responder. None se todos passaram.

    Ordem tem propósito:
        1. urgência (prioridade absoluta — segurança clínica)
        2. faq_especialidade (C-74: perguntas simples KB sem LLM)
        3. convênio (C-60: pegar CBMDF/GDF/Amil antes do LLM)
        4. valor (rápido, curto)
        5. aceite de slot (fluxo agenda)
        6. endereço pós-agenda (segunda mensagem obrigatória)
    """
    try:
        t = deve_orientar_urgencia(ctx, user_text)
        if t:
            return ("urgencia", t)

        # Bug C-78 (01/08/2026): FAQ disponibilidade hoje — "está atendendo hj?"
        # Resposta determinística por dia-da-semana. Zero Medware, zero LLM.
        # Deve vir ANTES de faq_especialidade para evitar que C-30A diga
        # "Medware instável" quando a realidade é "não atende neste dia".
        t = deve_responder_faq_disponibilidade_hoje(ctx, user_text)
        if t:
            return ("faq_disponibilidade_hoje", t)

        # Bug C-74 (26/07/2026): FAQ especialidade/médico — resposta KB pura,
        # zero LLM. Evita circuit breaker C-56 em perguntas simples.
        t = deve_responder_faq_especialidade(ctx, user_text)
        if t:
            return ("faq_especialidade", t)

        # Bug C-60 (20/07/2026): classificador convênio ANTES do valor,
        # pra pegar CBMDF, GDF, Amil etc antes de LLM inventar "deixa eu verificar"
        try:
            from voice_agent.classificador_convenio import deve_responder_convenio
            t = deve_responder_convenio(ctx, user_text)
            if t:
                return ("convenio", t)
        except Exception as e:  # noqa: BLE001
            log.warning("bypass convênio falhou: %s", e)

        t = deve_responder_valor(ctx, user_text)
        if t:
            return ("valor", t)

        t = deve_gerar_confirmacao_aceite(ctx, user_text)
        if t:
            return ("aceite_slot", t)

        t = deve_enviar_endereco_pos_agenda(ctx)
        if t:
            return ("endereco_pos_agenda", t)
    except Exception as e:  # noqa: BLE001
        log.warning("bypass determinístico falhou: %s", e)
        return None

    return None
