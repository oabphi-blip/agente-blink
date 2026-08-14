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
    r"1(?:\W|$)|2(?:\W|$)|3(?:\W|$)"  # 1️⃣ 2️⃣ 3️⃣ ou "1)" "2." ou "1" fim de string
    r"|primeir[oa]|segund[oa]|terceir[oa]"
    r"|op[cç][aã]o\s*[123]"
    r"|primeir[oa]\s*op[cç][aã]o|segund[oa]\s*op[cç][aã]o"
    r"|(?:fica|serve|prefiro|melhor|pego|topo|aceito)"
    r")",
    re.IGNORECASE,
)

# C-119 (11/08/2026): Paciente aceita slot E confirma inline ("1, pode marcar").
# Quando ambos os padrões batem no mesmo turno, Python pula CONFIRMACAO e injeta
# ctx["known"]["c119_slot_para_gravar"] = slot para pipeline hook gravar no Medware.
_PADRAO_PODE_MARCAR_INLINE = re.compile(
    r"(?:"
    r"pode\s+(?:marcar|agendar|confirmar|registrar|fechar|reservar)"
    r"|quero\s+(?:marcar|agendar|confirmar|fechar|reservar)"
    r"|t[aá]\s*(?:bom|ok|[oó]timo|certo)\s*[,!]?\s*(?:pode\s+(?:marcar|agendar|confirmar))?"
    r"|sim[,!\s]+(?:pode|confirma|agenda|marca|reserva)"
    r"|(?:confirma|fecha|marca|agenda|reserva)(?:\s+(?:esse|este|aquele|o)\s*hor[aá]rio)?"
    r"|fica(?:r)?\s+(?:com\s+esse|marcado|confirmado|reservado)"
    r"|peg[ao]\s+esse"
    r"|v[aá]\s+(?:marcar|agendar)"
    r"|f[ei]cha[!]?"
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

    # C-118 (11/08/2026): ctx["slots_ofertados"] nunca foi populado em prod —
    # C-105/enriquecimento_ctx escreve em ctx["known"]["slots_selecionados"].
    # Fallback added so aceite bypass actually fires.
    slots = (
        ctx.get("slots_ofertados")
        or (ctx.get("known") or {}).get("slots_selecionados")
        or []
    )
    if not slots:
        return None

    # Descobre qual slot foi aceito
    slot_aceito = _identificar_slot_aceito(user_text, slots)
    if not slot_aceito:
        return None

    # C-119 (11/08/2026): paciente aceitou slot E confirmou inline ("1, pode marcar").
    # Injeta flag no ctx.known → pipeline hook em pipeline.py grava Medware e
    # avança FSM para POS_GRAVACAO, saltando o turno de CONFIRMACAO.
    if _PADRAO_PODE_MARCAR_INLINE.search(user_text):
        if isinstance(ctx, dict) and isinstance(ctx.get("known"), dict):
            ctx["known"]["c119_slot_para_gravar"] = slot_aceito
            log.info(
                "[C-119] slot_para_gravar injetado ctx.known: %s %s",
                slot_aceito.get("data_iso"), slot_aceito.get("hora"),
            )
        return _montar_texto_reserva_imediata(slot_aceito, ctx)

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

    # C-118 fix: texto de CONFIRMAÇÃO (não de registro).
    # Antes dizia "Já estou registrando" sem gravar no Medware — arquiteturalmente errado.
    # Agora pede confirmação do paciente; pipeline hook C-119 grava quando houver
    # "pode marcar" inline (via _montar_texto_reserva_imediata).
    return (
        f"{saudacao}✅ Confirmando: {dia_semana} ({data_br}) — "
        f"{intervalo} — com {medico}{unidade_frase}{convenio_frase}. "
        "Está tudo certo pra você?"
    )


def _montar_texto_reserva_imediata(slot: dict, ctx: Optional[dict]) -> str:
    """C-119: texto enviado quando paciente confirmou inline ('1, pode marcar').

    Pipeline hook em pipeline.py lê ctx["known"]["c119_slot_para_gravar"] e
    executa a gravação no Medware logo após o envio desta mensagem.
    """
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
        f"{saudacao}✅ Perfeito! Reservando {dia_semana} ({data_br}) — "
        f"{intervalo} — com {medico}{unidade_frase}{convenio_frase}. "
        "Em seguida te mando o endereço e as orientações. 🏥"
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
    # ── Frases compostas ──────────────────────────────────────────────
    r"(?:quanto|qual|qto)\s+(?:custa|é|e|vale|fica|sai|paga)"
    r"|(?:qual|qto|quanto)\s+(?:o\s+)?(?:valor|pre[cç]o|custo)"
    r"|quanto\s+(?:eu\s+)?(?:vou\s+)?pag(?:o|ar|amos)"
    r"|(?:tem|qual)\s+desconto"
    r"|(?:tem|qual|como)\s+(?:[eé]\s+)?(?:o\s+)?pix"   # "tem pix?", "qual o pix?"
    r"|aceita[m]?\s+cart[aã]o"                          # "aceitam cartão?"
    r"|aceita[m]?\s+(?:todas?\s+)?as\s+bandeiras"       # "aceita as bandeiras?"
    r"|cobr[ao]\s+quanto"                               # "cobram quanto?"
    r"|me\s+passa\s+(?:o\s+)?(?:valor|pre[cç]o|tabela)" # "me passa o valor"
    r"|qual\s+(?:a\s+)?tabela"                          # "qual a tabela?"
    # ── Standalone — Bug C-86 ─────────────────────────────────────────
    r"|\bvalor(?:es)?\b"      # "Valor"/"Valores"
    r"|\bpre[cç]os?\b"        # "Preço"/"Preços"
    r"|\bpagamento\b"         # "pagamento"
    # ── Sinônimos PT-BR informal — Bug C-86b ─────────────────────────
    r"|\bcusto[s]?\b"         # "custo"/"custos"
    r"|\binvestimento\b"       # "investimento" (comum em clínicas premium)
    r"|\bcobr[ao]m?\b"         # "cobra"/"cobro"/"cobram"
    r"|\btabela\b"             # "tabela" (tabela de preços)
    r"|\bpromo[cç][aã]o\b"   # "promoção"
    r"|\bparcela(?:[rs]|d[oa])?\b"  # "parcela/s/r/do/da"
    r"|\b[àa]\s*vista\b"     # "à vista"/"a vista"
    r"|\bpix\b"               # "pix" standalone
    r"|\bcart[aã]o\b"        # "cartão"
    r"|\bboleto\b"            # "boleto"
    r"|\bgratuito\b"          # "gratuito?"
    r"|\bgr[áa]tis\b"        # "grátis?"
    r"|\bbarato\b"            # "é barato?"
    r"|\bcaro\b"              # "é caro?"
    r"|\bform[as]?\s+de\s+pag"      # "forma(s) de pagamento"
    r"|\bmeio\s+de\s+pagamento\b"   # "meio de pagamento"
    r")",
    re.IGNORECASE,
)

_VALORES_CANONICOS = {
    "karla_particular": "R$ 611",
    "karla_apv": "R$ 800",
    "fabricio_catarata": "R$ 297",
    "fabricio_50plus": "R$ 611",
}


def _inferir_medico_por_motivo(known: dict) -> str:
    """Tenta deduzir médico pelo motivo/especialidade/perfil etário do ctx.known.

    Retorna 'karla', 'fabricio' ou '' (não foi possível inferir).
    Usado quando ctx.known.medico está vazio mas a pergunta de valor chegou.
    """
    motivo = str(known.get("motivo") or known.get("especialidade") or "").lower()

    # Pediátrico / crianças → Karla Delalíbera
    for kw in (
        "criança", "bebê", "bebe", "pediátri", "pediatri", "infantil",
        "filho", "filha", "recém-nascido", "recem-nascido",
    ):
        if kw in motivo:
            return "karla"

    # Estrabismo, APV, rotina, óculos → Karla
    for kw in (
        "estrabismo", "olho torto", "desvio", "ambliopia", "preguiça",
        "apv", "processamento visual", "sdp",
        "rotina", "óculos", "oculos", "grau", "refração", "refracao",
        "oftalmopediatria",
    ):
        if kw in motivo:
            return "karla"

    # Catarata, córnea, adulto 50+ → Fabrício
    for kw in (
        "catarata", "córnea", "cornea", "pterígio", "pterigio",
        "ceratocone", "cirurgia", "transplante",
    ):
        if kw in motivo:
            return "fabricio"

    # Idade registrada no ctx
    try:
        idade = int(str(known.get("idade") or known.get("age") or 0).split()[0])
        if 0 < idade < 18:
            return "karla"
        if idade >= 50:
            return "fabricio"
    except (ValueError, TypeError, IndexError):
        pass

    return ""  # não foi possível inferir — mostrar tabela geral


# Bug C-101 (10/08/2026) — detecta criança/bebê no texto do paciente
# Usado por deve_responder_valor quando ctx.known.motivo ainda está vazio
_PEDIATRIC_USR_KW = re.compile(
    r"\b(?:beb[eê]|crian[çc]a|crian[çc]as|beb[eê]s|rec[eé]m[- ]?nascido|infantil)\b"
    r"|\bmeu\s+(?:beb[eê]|filho|filhinho)\b"
    r"|\bminha\s+(?:beb[eê]|filha|filhinha)\b"
    r"|\bpara\s+(?:(?:meu|minha|um|uma|o|a)\s+)?(?:beb[eê]|crian[çc]a|filho|filha|rec[eé]m[- ]?nascido)\b",
    re.IGNORECASE,
)
_PEDIATRIC_USR_AGE = re.compile(
    r"\bpara\s+(?:\w+\s+){0,2}(\d{1,2})\s+anos?\b"
    r"|\bde\s+(\d{1,2})\s+anos?\b"
    r"|\bcom\s+(\d{1,2})\s+anos?\b"
    r"|\b(\d{1,2})\s+anos?\s+de\s+(?:idade|vida)\b",
    re.IGNORECASE,
)
_PEDIATRIC_USR_MESES = re.compile(r"\b\d{1,2}\s+meses?\b", re.IGNORECASE)


def _inferir_medico_por_user_text(user_text: str) -> str:
    """Bug C-101 — infere médico pelo texto do paciente quando ctx.known.motivo está vazio.

    Prioridade:
      1. Idade numérica encontrada: ≥18 → não infere; <18 → 'karla'
      2. 'X meses' → bebê → 'karla'
      3. Palavras-chave (bebê, criança, meu filho, minha filha) → 'karla'
    Retorna '' se não conseguir inferir.
    """
    if not user_text:
        return ""
    # 1. Idade numérica tem prioridade — evita "meu filho de 45 anos" → Karla
    m = _PEDIATRIC_USR_AGE.search(user_text)
    if m:
        age_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if age_str:
            age = int(age_str)
            if age >= 18:
                return ""      # adulto → não forçar Karla
            return "karla"     # criança/adolescente
    # 2. Bebê em meses
    if _PEDIATRIC_USR_MESES.search(user_text):
        return "karla"
    # 3. Palavras-chave diretas
    if _PEDIATRIC_USR_KW.search(user_text):
        return "karla"
    return ""


def _resposta_tabela_geral_valores(nome: str) -> str:
    """Retorna tabela geral de valores (ambos médicos) quando médico não é conhecido.

    C-106: usa "sem convênio" (nunca "particular"). Nunca retorna None.
    """
    # C-106: delega para oferta_valor_contextualizado que já tem tabela correta
    try:
        from voice_agent.oferta_valor_contextualizado import _tabela_sem_convenio
        return _tabela_sem_convenio(nome)
    except Exception:
        pass
    # Fallback inline (caso import falhe)
    saudacao = f"Olá, {nome}!\n\n" if nome else ""
    return (
        f"{saudacao}"
        "Nossos valores para consulta sem convênio:\n\n"
        "👩‍⚕️ *Dra. Karla Delalíbera* — Oftalmopediatria, estrabismo, rotina\n"
        "💰 Pix: *R$ 611* · 💳 Cartão 1x: *R$ 670*\n\n"
        "👨‍⚕️ *Dr. Fabrício Freitas* — Saúde ocular adulto 50+, catarata, córnea\n"
        "💰 Pix: *R$ 445* (catarata) · *R$ 611* (outros)\n"
        "💳 Cartão 1x: *R$ 470* (catarata) · *R$ 670* (outros)\n\n"
        "Com qual médico seria a consulta?"
    )


def _escuta_universal(user_text: str, ctx: Optional[dict]) -> str:
    """C-127 Fix 3 (12/08/2026) — Prova de escuta leve para qualquer bypass.

    Extrai 1-2 elementos informativos do que o paciente acabou de mandar e
    retorna um prefixo de acknowledgment curto.

    Ex: "meu filho tem 5 anos, quero saber o valor"
        → "Entendido! "  (se já tem médico/motivo em ctx)
        → "Anotado — filho de 5 anos! " (se extrai algo novo)

    Retorna "" se não extraiu nada relevante (sem prefixo).
    Fail-open: qualquer exceção → "".
    """
    try:
        if not user_text:
            return ""
        known = (ctx or {}).get("known") or {}
        partes: list[str] = []

        # Filho/bebê com idade (não foi parseado ainda em known)
        if not known.get("data_nasc"):
            m = re.search(
                r"(?:filho|filha|beb[êe]|crian[çc]a)[^\d]{0,10}(\d+)\s*(anos?|meses?|m[êe]s)",
                user_text, re.IGNORECASE
            )
            if m:
                n, unid = m.group(1), m.group(2).lower()
                if "ano" in unid:
                    partes.append(f"filho de {n} {'ano' if n == '1' else 'anos'}")
                else:
                    partes.append(f"bebê de {n} {'mês' if n == '1' else 'meses'}")

        # Convênio mencionado mas não parseado
        if not known.get("convenio"):
            m2 = re.search(
                r"\b(bacen|saúde caixa|serpro|omint|care plus|fascal|sis senado"
                r"|pf saúde|afego|proasa|casec|conab)\b",
                user_text, re.IGNORECASE
            )
            if m2:
                partes.append(f"plano {m2.group(1).title()}")

        # Unidade mencionada mas não parseada
        if not known.get("unidade"):
            if re.search(r"asa\s+norte", user_text, re.IGNORECASE):
                partes.append("Asa Norte")
            elif re.search(r"águas?\s+claras?", user_text, re.IGNORECASE):
                partes.append("Águas Claras")

        if not partes:
            return ""
        return "Anotado — " + ", ".join(partes) + "! "
    except Exception:
        return ""


def deve_responder_valor(ctx: Optional[dict], user_text: str) -> Optional[str]:
    """Se paciente perguntou valor, retorna resposta canônica.

    Fluxo C-106 (11/08/2026):
      0. Tenta resposta contextualizada (valor antes do preço, sem convênio)
         via oferta_valor_contextualizado.gerar_valor_contextualizado().
         Se retornar texto → usa diretamente (caminho principal).
      1. ctx.known.medico definido → resposta específica (convênio ou valor exato).
      2. Sem médico → tenta inferir por motivo/idade → resposta específica.
      3. Não conseguiu inferir → tabela geral sem convênio (NUNCA retorna None).

    Regras C-106:
      - Pergunta de valor pressupõe SEM CONVÊNIO — não perguntar convênio/particular.
      - Usar "sem convênio" (nunca "particular").
      - Valor SEMPRE precedido por proposição de valor (especialidade, o que inclui).
      - Contexto pediátrico → resposta focada em oftalmopediatria + ambiente criança.

    IMPORTANTE: qualquer pergunta de valor DEVE ser respondida deterministicamente.
    Retornar None significa jogar para o LLM, que pode ignorar ou inventar valor.
    """
    if not _ativado("BLINDAGEM_VALOR_ATIVADO"):
        return None
    if not user_text:
        return None
    if not _PADROES_PERGUNTA_VALOR.search(user_text):
        return None

    # ── C-106: caminho principal — valor contextualizado (sem convênio, sem tabela genérica) ──
    try:
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        resp_c106 = gerar_valor_contextualizado(ctx, user_text)
        if resp_c106:
            return resp_c106
    except Exception as _e106:
        log.warning("[C-106] gerar_valor_contextualizado falhou, fallback legado: %s", _e106)

    known = (ctx or {}).get("known") or {}
    nome = _nome_paciente(ctx)

    # ── C-104: usa valor já derivado pelo enriquecimento_ctx (C-103) ─────────
    # Se C-103 rodou, valor_consulta já está em known — zero reprocessamento.
    valor_precomputado = known.get("valor_consulta")
    if valor_precomputado is not None or "valor_consulta" in known:
        # None = coberto por convênio; tuple = (pix, cartao_1x, cartao_2x)
        if "valor_consulta" in known:
            medico = _nome_medico_canonico(ctx)
            convenio_k = _convenio_str(ctx)
            conv_aceito_ctx = known.get("convenio_aceito")
            saudacao = f"{nome}, " if nome else ""
            if valor_precomputado is None and conv_aceito_ctx is True:
                # Coberto por convênio — não dar valor particular
                return (
                    f"{saudacao}a consulta é coberta pelo **{convenio_k.title()}**! 👍\n\n"
                    "Qual unidade fica melhor para você: **Asa Norte** ou **Águas Claras**?"
                )
            if isinstance(valor_precomputado, (tuple, list)) and len(valor_precomputado) >= 2:
                pix, cartao_1x = float(valor_precomputado[0]), float(valor_precomputado[1])
                servico = "consulta"
                motivo_k = (known.get("motivo") or known.get("especialidade") or "").lower()
                if "apv" in motivo_k or "processamento visual" in motivo_k or "sdp" in motivo_k:
                    servico = "avaliação do processamento visual"
                elif "catarata" in motivo_k:
                    servico = "avaliação de catarata"
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
                    f"**Primeira Opção: R$ {pix:.0f} Pix**, "
                    f"**Segunda Opção: R$ {cartao_1x:.0f} (1x Cartão)**.\n\n"
                    "Qual a sua escolha?"
                )
        # Fall through to full inference below if valor_precomputado is unexpected type

    # ── Resolve médico: ctx → motivo → user_text (C-101) → tabela geral ────
    medico_raw = (known.get("medico") or "").strip()
    if not medico_raw:
        medico_raw = _inferir_medico_por_motivo(known)
    if not medico_raw:
        # Bug C-101: tenta detectar criança/bebê no próprio user_text
        # Ex: "valor para 3 anos" → Karla sem perguntar
        medico_raw = _inferir_medico_por_user_text(user_text)
    if not medico_raw:
        # NUNCA retornar None em pergunta de valor — sempre responder
        return _resposta_tabela_geral_valores(nome)

    # Garante nome canônico mesmo quando medico_raw veio da inferência
    # (ex: "karla" → "Dra. Karla Delalíbera")
    medico = _nome_medico_canonico(ctx)
    if medico == "a médica":
        # ctx.known.medico estava vazio; usamos o nome do inferido
        if "karla" in medico_raw.lower():
            medico = "Dra. Karla Delalíbera"
        elif "fabricio" in medico_raw.lower() or "fabrício" in medico_raw.lower():
            medico = "Dr. Fabrício Freitas"

    convenio = _convenio_str(ctx).lower()
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
        # Médico não reconhecido (não deve chegar aqui após os fixes acima)
        return _resposta_tabela_geral_valores(nome)

    # C-68 v2 (Fábio 21/07/2026, modelo humano lead Layssa):
    # Copia formato usado pelo atendimento humano — mais claro, mais rico.
    # Estrutura: intro → exames descritos → especialistas → voucher → valor inline → CTA.
    # C-127 Fix 3: prova de escuta antes do corpo (ex: "Anotado — filho de 3 meses!")
    nome_apenas = nome.rstrip(",").strip() if nome else ""
    _escuta_valor = _escuta_universal(user_text, ctx)
    abertura = (f"{_escuta_valor}\n\n" if _escuta_valor else "") + (
        f"Olá, {nome_apenas}\n\n" if nome_apenas else ""
    )
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

# ── Bug C-87 (05/08/2026): FAQ endereço ────────────────────────────────
_FAQ_ENDERECO = re.compile(
    r"("
    r"onde\s+fica"
    r"|qual\s+(?:é\s+o?\s*|o\s+)?endere[cç]o"
    r"|fica\s+no\s+felicit{1,2}[aá]?"
    r"|felicit{1,2}[aá]?\s+shopping"
    r"|\bendere[cç]o\b"
    r"|\blocali(?:za[çc][aã]o|dade)\b"
    r"|como\s+(?:ch[ae]g[ao]r?|ir)\b"
    r"|tem\s+estacionamento"
    r"|onde\s+(?:é|fica)\s+(?:a|o)\s+(?:cl[íi]nica|consultório|unidade)"
    r"|qual\s+(?:é\s+)?(?:a\s+)?unidade"
    r"|shin\s+qi"
    r"|lago\s+norte"
    r"|(?:a\s+)?cl[íi]nica\s+(?:é|fica)\s+(?:aonde|onde)"
    r")",
    re.IGNORECASE,
)


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
# Bug C-87 (05/08/2026) — FAQ ENDEREÇO
# ═══════════════════════════════════════════════════════════════════════
_ENDERECO_ASA_NORTE = (
    "nossa unidade Asa Norte fica na "
    "SHIN QI 5 Bloco J Loja 22, Lago Norte 📍\n"
    "https://maps.app.goo.gl/jPfjSsXA1bHhsyw56"
)
_ENDERECO_AGUAS_CLARAS = (
    "nossa unidade Águas Claras fica no Felicittá Shopping — "
    "R. 36 Norte, 05 - Bloco 11, Loja 48, 1º Andar 📍\n"
    "https://maps.app.goo.gl/FRbkUtg4U4xG55q18"
)
_ENDERECO_AMBAS = (
    "Temos 2 unidades 📍\n\n"
    "🏥 *Asa Norte* — SHIN QI 5 Bloco J Loja 22, Lago Norte\n"
    "https://maps.app.goo.gl/jPfjSsXA1bHhsyw56\n\n"
    "🏥 *Águas Claras* — Felicittá Shopping, R. 36 Norte, Bloco 11, Loja 48\n"
    "https://maps.app.goo.gl/FRbkUtg4U4xG55q18\n\n"
    "Qual fica mais perto de você?"
)


def deve_responder_faq_endereco(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """Resposta determinística para perguntas de endereço/localização.

    Usa ctx.known.unidade para escolher qual endereço mostrar.
    Se unidade desconhecida, mostra as duas e pergunta qual é mais perto.
    Toggle: BLINDAGEM_FAQ_ENDERECO_ATIVADO (default ON).
    """
    if not _ativado("BLINDAGEM_FAQ_ENDERECO_ATIVADO"):
        return None
    if not user_text or not _FAQ_ENDERECO.search(user_text.strip()):
        return None

    try:
        known = (ctx or {}).get("known") or {}
        unidade_raw = str(known.get("unidade") or "").lower()
        e_asa_norte = "asa norte" in unidade_raw or "lago norte" in unidade_raw
        e_aguas_claras = (
            ("água" in unidade_raw and "clara" in unidade_raw)
            or "aguas claras" in unidade_raw
            or "felicit" in unidade_raw
        )

        nome = _nome_paciente(ctx)
        saud = f"{nome}, " if nome else ""

        if e_asa_norte and not e_aguas_claras:
            return f"{saud}{_ENDERECO_ASA_NORTE}"
        elif e_aguas_claras and not e_asa_norte:
            return f"{saud}{_ENDERECO_AGUAS_CLARAS}"
        else:
            # unidade não definida ou ambas → mostra as duas
            return (f"{saud}{_ENDERECO_AMBAS}" if not nome else
                    f"{nome}, {_ENDERECO_AMBAS}")

    except Exception as e:  # noqa: BLE001
        log.warning("[C-87] faq_endereco falhou: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Bug C-104 (11/08/2026) — FAQ CONVÊNIO ACEITO usando ctx.known enriquecido
# ═══════════════════════════════════════════════════════════════════════
# Paciente pergunta "vocês aceitam meu plano?", "funciona com X?" etc.
# Se C-103 já enriqueceu ctx.known.convenio_aceito → resposta imediata.
# Caso contrário: extrai convênio do user_text e chama _convenio_aceito().
# Zero LLM. Zero Medware.
# Toggle: BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO (default ON)
# ═══════════════════════════════════════════════════════════════════════

# Padrões que indicam paciente está perguntando se convênio é aceito
_FAQ_CONVENIO_ACEITO_RE = re.compile(
    r"("
    r"voc[êe]s?\s+aceitam?"
    r"|aceitam?\s+(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r"|atendem?\s+(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r"|funciona\s+(?:com\s+)?(?:o\s+)?(?:meu\s+)?(?:conv[êe]nio|plano)"
    r"|(?:meu|o)\s+(?:conv[êe]nio|plano)\s+(?:é\s+)?(?:aceito|válido|cobre|funciona)"
    r"|tem\s+conv[êe]nio"
    r"|aceita\s+conv[êe]nio"
    r"|atende\s+(?:pelo\s+)?conv[êe]nio"
    r"|qual(?:is)?\s+conv[êe]nios?\s+(?:aceitam?|atendem?)"
    r")",
    re.IGNORECASE,
)

# Padrão para extrair nome do convênio do user_text quando não está no ctx
_CONV_NOME_INTEXT_RE = re.compile(
    r"(?:conv[êe]nio|plano)\s+(?:de\s+sa[uú]de\s+)?([A-Za-zÀ-ú\s\-/\.]+?)(?:\??$|\s+(?:funciona|é aceito|cobre))",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# C-123 (11/08/2026) — Tom canônico + escolha pós-recusa de convênio
# ─────────────────────────────────────────────────────────────────────────────
# Paciente pergunta se atende Bradesco → resposta correta:
#   "ainda estamos em processo de credenciamento. Qual sua preferência?
#    1️⃣ Somente com Convênio  2️⃣ Seguir Sem Convênio"
#
# Quando paciente responde escolhendo opção 2 → injeta ctx.known.convenio
# = "Não se aplica" + flag c123_marcar_sem_convenio para pipeline gravar Kommo.
# ─────────────────────────────────────────────────────────────────────────────

_RE_ESCOLHA_SEM_CONVENIO_C123 = re.compile(
    r"(?:^|\s)"
    r"(?:"
    r"1️⃣|"                          # C-128: Seguir sem convênio é agora opção 1
    r"1\s*[.,)✔]?(?:\s|$)|"
    r"seguir\s+sem\s+conv[eê]nio|"
    r"sem\s+conv[eê]nio\b|"
    r"prefiro\s+sem|"
    r"pode\s+ser\s+sem|"
    r"vou\s+sem\s+conv[eê]nio|"
    r"seguir\s+sem\b|"
    r"sem\s+plano\b"
    r")",
    re.IGNORECASE,
)

_RE_ESCOLHA_SO_CONVENIO_C123 = re.compile(
    r"(?:^|\s)"
    r"(?:"
    r"2️⃣|"                          # C-128: Somente com convênio é agora opção 2
    r"2\s*[.,)✔]?(?:\s|$)|"
    r"somente\s+com\s+conv[eê]nio|"
    r"s[oó]\s+com\s+conv[eê]nio|"
    r"somente\s+conv[eê]nio|"
    r"preciso\s+de\s+conv[eê]nio|"
    r"s[oó]\s+(?:com\s+)?conv[eê]nio\b"
    r")",
    re.IGNORECASE,
)


def _montar_recusa_convenio(
    conv_display: str,
    saud: str = "",
    escuta_pfx: str = "",
    ctx: Optional[dict] = None,
) -> str:
    """Tom amistoso para convênio não credenciado — C-123 / C-128.

    C-128 (12/08/2026): tom empático personalizado:
    - Abre "Entendi, {nome_contato}." quando nome disponível
    - "não quero deixar o {nome_paciente} sem solução"
    - "incentivos especiais" (era "condições diferenciadas")
    - "Como prefere seguir?" (era "Qual a sua preferência?")
    - Ordem: 1️⃣ Seguir sem convênio (conversão) / 2️⃣ Somente com convênio

    Regras mantidas do C-123:
    - NÃO usa "particular" (usar "sem convênio")
    - NÃO oferece valor (não sabe motivo/médico ainda)

    Args:
        conv_display: Nome do convênio para exibição (ex: "Amil")
        saud: (legado, ignorado) mantido para compatibilidade de assinatura
        escuta_pfx: prova de escuta C-127 Fix 3 (ex: "Anotado — bebê 7 meses!")
        ctx: caller context para extrair nome_contato e nome_paciente
    """
    pfx = f"{escuta_pfx}\n\n" if escuta_pfx else ""

    # Extrai nomes do ctx ─────────────────────────────────────────────────────
    try:
        known = (ctx or {}).get("known") or {}
        # nome_contato: quem está no WhatsApp (pode ser responsável/mãe/pai)
        _nc_raw = (
            known.get("nome_contato")
            or known.get("nome_paciente")
            or known.get("nome_completo_paciente")
            or known.get("nome")
            or ""
        ).strip()
        nome_contato = _nc_raw.split()[0] if _nc_raw else ""

        # nome_paciente: quem vai consultar (pode diferir do contato)
        _np_raw = (
            known.get("nome_paciente")
            or known.get("nome_completo_paciente")
            or ""
        ).strip()
        nome_paciente = _np_raw.split()[0] if _np_raw else ""
    except Exception:
        nome_contato = ""
        nome_paciente = ""

    # Monta mensagem ──────────────────────────────────────────────────────────
    abertura = f"Entendi, {nome_contato}. " if nome_contato else ""
    ref_paciente = f"o {nome_paciente}" if nome_paciente else "você"

    return (
        f"{pfx}{abertura}O **{conv_display}** ainda não está credenciado na nossa rede.\n\n"
        f"Mas não quero deixar {ref_paciente} sem solução — temos incentivos especiais "
        "para pacientes com convênios que ainda não cobrimos. "
        "Como prefere seguir?\n\n"
        "1️⃣ Seguir sem convênio\n"
        "2️⃣ Somente com convênio"
    )


def _ultima_msg_era_recusa_convenio(ctx: Optional[dict]) -> bool:
    """Verifica se o último outbound da Lia apresentou as 2 opções de convênio.

    C-128: usa regex case-insensitive — funciona com formato legado (C-123) e
    novo (C-128) independente de capitalização ou ordem das opções.
    """
    ultima = (((ctx or {}).get("known") or {}).get("ultima_msg_outbound") or "").strip()
    tem_sem = bool(re.search(r"seguir\s+sem\s+conv[eê]nio", ultima, re.IGNORECASE))
    tem_so = bool(re.search(r"somente\s+com\s+conv[eê]nio", ultima, re.IGNORECASE))
    return tem_sem and tem_so


def deve_responder_escolha_convenio(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """C-123: Detecta escolha do paciente após apresentação das 2 opções de convênio.

    Gate: última outbound contém ambas as opções ("Somente com Convênio" e
    "Seguir Sem Convênio"). Só age quando estamos neste contexto específico.

    Opção 2 (Seguir Sem Convênio):
        - Injeta ctx.known.convenio = "Não se aplica"
        - Injeta ctx.known.c123_marcar_sem_convenio = True (pipeline atualiza Kommo)
        - Retorna mensagem pedindo motivo da consulta

    Opção 1 (Somente com Convênio):
        - Injeta ctx.known.c123_encerrar_so_convenio = True
        - Retorna mensagem de encerramento gentil

    Toggle: BLINDAGEM_ESCOLHA_CONVENIO_ATIVADO (default ON)
    Fail-open: exceção → None
    """
    if not _ativado("BLINDAGEM_ESCOLHA_CONVENIO_ATIVADO"):
        return None
    if not user_text or not ctx:
        return None
    if not _ultima_msg_era_recusa_convenio(ctx):
        return None

    try:
        nome = _nome_paciente(ctx)
        saud = f"{nome.split()[0]}, " if nome else ""
        known = ctx.get("known") or {}

        if _RE_ESCOLHA_SEM_CONVENIO_C123.search(user_text):
            # Paciente escolheu Seguir Sem Convênio
            if isinstance(ctx, dict) and isinstance(ctx.get("known"), dict):
                ctx["known"]["convenio"] = "Não se aplica"
                ctx["known"]["c123_marcar_sem_convenio"] = True
                # Preservar nome do convênio recusado para Ñ ACEITO CONVÊNIO
                conv_recusado = known.get("convenio_nao_aceito_nome") or known.get("convenio") or ""
                if conv_recusado and conv_recusado.lower() not in ("não se aplica", "nao se aplica"):
                    ctx["known"]["c123_convenio_recusado"] = conv_recusado
            log.info("[C-123] Paciente escolheu Seguir Sem Convênio")
            return (
                f"{saud}ótimo! ✅ Seguiremos sem convênio.\n\n"
                "Para prosseguir, me conta: qual é o motivo da consulta?"
            )

        if _RE_ESCOLHA_SO_CONVENIO_C123.search(user_text):
            # Paciente insiste em só com convênio
            if isinstance(ctx, dict) and isinstance(ctx.get("known"), dict):
                ctx["known"]["c123_encerrar_so_convenio"] = True
            log.info("[C-123] Paciente escolheu Somente com Convênio — encerrando")
            return (
                f"{saud}entendo! 😊 Assim que concluirmos o credenciamento, "
                "te avisamos.\n\n"
                "Qualquer dúvida, é só chamar aqui. Até mais! 🌟"
            )

        return None

    except Exception as exc:
        log.warning("[C-123] deve_responder_escolha_convenio falhou (fail-open): %s", exc)
        return None


def deve_responder_faq_convenio_aceito(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """Resposta determinística para perguntas sobre convênio aceito/não aceito.

    Dois caminhos de detecção (C-104):

    Caminho A — ctx.known.convenio_aceito já derivado (C-103):
        Qualquer user_text que mencione o nome do convênio OU contenha padrão FAQ
        é suficiente para responder — a resposta já está computada.

    Caminho B — convenio não em ctx.known:
        Exige padrão FAQ no user_text + deriva aceito inline.

    Toggle: BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO (default ON)
    """
    if not _ativado("BLINDAGEM_FAQ_CONVENIO_ACEITO_ATIVADO"):
        return None
    if not user_text:
        return None

    try:
        known = (ctx or {}).get("known") or {}
        nome = _nome_paciente(ctx)
        saud = f"{nome}, " if nome else ""

        aceito = known.get("convenio_aceito")  # True / False / None / ausente
        convenio_nome = (known.get("convenio") or "").strip()

        user_lower = user_text.lower()
        tem_padrao_faq = bool(_FAQ_CONVENIO_ACEITO_RE.search(user_text))

        # ── Caminho A: resposta já computada em ctx.known.convenio_aceito ────
        # Gatilho: menciona o nome do convênio OU tem padrão FAQ genérico
        if "convenio_aceito" in known and aceito is not None:
            conv_lower = convenio_nome.lower()
            menciona_convenio = conv_lower and conv_lower in user_lower
            if not tem_padrao_faq and not menciona_convenio:
                return None  # user_text irrelevante
            # Responde com o resultado derivado
            conv_display = convenio_nome.title() if convenio_nome else "esse convênio"
            if aceito is True:
                return (
                    f"{saud}sim, atendemos o **{conv_display}**! 👍\n\n"
                    "Posso já verificar os horários disponíveis — "
                    "qual unidade fica melhor para você: **Asa Norte** ou **Águas Claras**?"
                )
            else:
                # C-123: tom canônico — processo de credenciamento + sem "particular" + sem valor prematuro
                if isinstance(ctx, dict) and isinstance(ctx.get("known"), dict):
                    ctx["known"]["convenio_nao_aceito_nome"] = conv_display
                return _montar_recusa_convenio(
                    conv_display,
                    escuta_pfx=_escuta_universal(user_text, ctx),  # C-127 Fix 3
                    ctx=ctx,  # C-128: nomes para tom personalizado
                )

        # ── Caminho B: convenio_aceito não computado ─────────────────────────
        # Gatilho: padrão FAQ genérico OU ctx.known.convenio aparece no user_text
        conv_lower_b = convenio_nome.lower()
        menciona_conv_known = conv_lower_b and conv_lower_b in user_lower
        if not tem_padrao_faq and not menciona_conv_known:
            return None

        # Fonte B1: ctx.known.convenio como nome → deriva inline
        if aceito is None and convenio_nome:
            try:
                from voice_agent.enriquecimento_ctx import _convenio_aceito as _ca
                aceito = _ca(convenio_nome)
            except Exception:  # noqa: BLE001
                pass

        # Fonte B2: extrai nome do user_text → deriva inline
        if aceito is None:
            m = _CONV_NOME_INTEXT_RE.search(user_text)
            if m:
                candidato = m.group(1).strip().rstrip("?").strip()
                if candidato and len(candidato) >= 3:
                    try:
                        from voice_agent.enriquecimento_ctx import _convenio_aceito as _ca
                        aceito = _ca(candidato)
                        if not convenio_nome:
                            convenio_nome = candidato.title()
                    except Exception:  # noqa: BLE001
                        pass

        if aceito is None:
            return None  # não mapeado — LLM decide

        conv_display = convenio_nome.title() if convenio_nome else "esse convênio"
        if aceito is True:
            return (
                f"{saud}sim, atendemos o **{conv_display}**! 👍\n\n"
                "Posso já verificar os horários disponíveis — "
                "qual unidade fica melhor para você: **Asa Norte** ou **Águas Claras**?"
            )
        else:
            # C-123 / C-128: tom amistoso + sem "particular" + sem valor prematuro
            if isinstance(ctx, dict) and isinstance(ctx.get("known"), dict):
                ctx["known"]["convenio_nao_aceito_nome"] = conv_display
            return _montar_recusa_convenio(
                conv_display,
                escuta_pfx=_escuta_universal(user_text, ctx),  # C-127 Fix 3
                ctx=ctx,  # C-128: nomes para tom personalizado
            )

    except Exception as e:  # noqa: BLE001
        log.warning("[C-104] faq_convenio_aceito falhou: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA — chain of responsibility
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# BYPASS C-120 — DADOS PENDENTES: Python gera pergunta, salva 1 LLM call
# ═══════════════════════════════════════════════════════════════════════
# C-120 (11/08/2026): substitui render_bloco_pre_agenda + LLM por bypass Python
# que emite a pergunta de dados faltantes diretamente — sem chamar LLM.
#
# Impacto: ~40% dos fluxos tinham CONVENIO como turno extra separado.
# C-120 pergunta nome + data_nasc + convênio em 1 mensagem só.
# Toggle: BLINDAGEM_DADOS_PENDENTES_ATIVADO (default ON).

_SAUDACAO_PURA_C120 = re.compile(
    r"^[\s]*(?:oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|hey|hi|hello"
    r"|boas|e\s*[aí]|eae)\W*[\s]*$",
    re.IGNORECASE,
)

_INTENT_AGENDAR_C120 = re.compile(
    r"(?:quero|queria|preciso|gostaria|pode(?:ria)?|tentar)\s+"
    r"(?:de\s+)?(?:agendar|marcar|consultar|uma\s+consulta|uma\s+avalia[cç][aã]o"
    r"|horário|atend|retorno)",
    re.IGNORECASE,
)

_CAMPOS_COLETADOS_C120 = (
    "nome_paciente", "nome", "motivo", "convenio", "medico",
    "unidade", "data_nasc_iso", "data_nascimento_iso",
    "urgency_level", "unidade_detectada", "medico_detectado",
)

# ─── C-130: Anti-loop "resposta ao C-125 não reconhecida" (12/08/2026) ─────────
# Causa raiz: C-125 pergunta "Qual a data de nascimento?" e paciente responde
# "27/012/2024" (typo) → data_nascimento_ok() falha (regex não aceita "012") →
# C-125 volta a pedir → loop 3x (lead 24447784 Bento).
# Fix: detectar quando inbound é resposta à última pergunta C-125 → return None
# → LLM extrai e armazena o valor com tolerância a typos.
_RE_DATA_RESP_C130 = re.compile(
    r"\b\d{1,2}[/\-\.]\d{1,3}[/\-\.]\d{2,4}\b"  # "27/012/2024", "27/12/2024"
    r"|\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b",   # ISO: "2024-12-27"
    re.IGNORECASE,
)
_RE_CPF_RESP_C130 = re.compile(
    r"\b\d{3}[\.\- ]?\d{3}[\.\- ]?\d{3}[\.\- ]?\d{2}\b|\b\d{11}\b"
)
_RE_ULTIMA_PERGUNTOU_DATA_C130 = re.compile(r"data de nascimento", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_NOME_C130 = re.compile(r"nome completo", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_CPF_C130 = re.compile(r"\bcpf\b", re.IGNORECASE)
_RE_ULTIMA_PERGUNTOU_CONV_C130 = re.compile(
    r"conv[eê]nio\s+ou\s+sem|por\s+conv[eê]nio", re.IGNORECASE
)


_RE_IMAGEM_SINTETICA_C134 = re.compile(
    r"\[O paciente enviou uma imagem",
    re.IGNORECASE,
)


def _inbound_responde_ultima_pergunta_c130(ctx: Optional[dict], user_text: str) -> bool:
    """True quando o inbound parece ser resposta à última pergunta de dado do C-125.

    Se True → return None em deve_perguntar_dados_pendentes → LLM extrai o valor.

    Casos cobertos:
    - data de nascimento pedida + inbound tem padrão de data (aceita typos: "27/012/2024")
    - CPF pedido + inbound tem 11 dígitos
    - nome completo pedido + inbound parece nome curto (sem interrogação, sem data)
    - convênio pedido + inbound tem sim/não/nome de convênio
    - Bug C-134 (13/08/2026): paciente enviou IMAGEM → não repetir pergunta de texto
      LLM reconhece a imagem e decide o próximo passo sem re-perguntar o mesmo dado.
    """
    ut = user_text.strip()
    if not ut:
        return False

    # C-134 (13/08/2026): imagem sintética — nunca perguntar dado de texto de novo.
    # Verificado ANTES do guard `ultima` porque imagem deve suprimir C-125 mesmo
    # que ultima_msg_outbound ainda não tenha sido gravada no Redis/Kommo
    # (race condition: webhook chega antes do PATCH Kommo terminar).
    # Caso real: lead 21933605 Giovana — paciente enviou carteirinha 3x, Lia
    # repetiu "Qual a data de nascimento de Giovana?" a cada imagem.
    if _RE_IMAGEM_SINTETICA_C134.search(ut):
        log.debug("[C-134] inbound=imagem sintética → suprime C-125, LLM trata")
        return True

    ultima = ((ctx or {}).get("known") or {}).get("ultima_msg_outbound") or ""
    if not ultima:
        return False

    # Data de nascimento pedida → inbound parece data (tolera typos como "012")
    if _RE_ULTIMA_PERGUNTOU_DATA_C130.search(ultima):
        return bool(_RE_DATA_RESP_C130.search(ut))

    # CPF pedido → inbound tem 11 dígitos (com ou sem máscara)
    if _RE_ULTIMA_PERGUNTOU_CPF_C130.search(ultima):
        return bool(_RE_CPF_RESP_C130.search(ut))

    # Nome completo pedido → inbound parece nome (sem data, >= 2 palavras, sem "?")
    if _RE_ULTIMA_PERGUNTOU_NOME_C130.search(ultima):
        palavras = [p for p in ut.split() if p.isalpha()]
        return len(palavras) >= 2 and "?" not in ut and not _RE_DATA_RESP_C130.search(ut)

    # Convênio pedido → qualquer resposta substantiva (≥3 chars, sem "?")
    # Cobre: "sim", "não", "particular", "Saúde Caixa", "Bacen", etc.
    # LLM extrai o plano/intenção — não precisamos casar o nome exato.
    if _RE_ULTIMA_PERGUNTOU_CONV_C130.search(ultima):
        return len(ut) >= 3 and "?" not in ut

    return False


def deve_perguntar_dados_pendentes(ctx: Optional[dict], user_text: str) -> Optional[str]:
    """C-120: Python gera a pergunta de dados pendentes sem chamar o LLM.

    Dispara quando:
      - FSM em TRIAGEM / DADOS / CONVENIO (ou None = início)
      - checklist com >= 1 campo pendente para gravar no Medware
      - paciente demonstrou intenção de agendar OU algum dado já foi coletado
      - user_text não é saudação pura (ex: "Oi")

    Retorna: string com pergunta concatenada ex. "Me passa nome completo,
    data de nascimento e convênio?" — uma mensagem única, sem LLM.
    Retorna None → fail-open, LLM continua fluxo normal.

    Toggle: BLINDAGEM_DADOS_PENDENTES_ATIVADO (default ON).
    """
    if not _ativado("BLINDAGEM_DADOS_PENDENTES_ATIVADO"):
        return None
    if not ctx or not user_text or not user_text.strip():
        return None

    # Saudação pura: LLM humaniza o primeiro contato
    if _SAUDACAO_PURA_C120.match(user_text.strip()):
        return None

    # FSM: não disparar após o paciente já estar escolhendo slots ou pós-agendamento
    fsm_estado = ((ctx.get("fsm") or {}).get("estado") or "").upper()
    if fsm_estado in {"AGENDA", "CONFIRMACAO", "GRAVACAO", "POS_GRAVACAO"}:
        return None

    # Sem agendamento já realizado
    known = ctx.get("known") or {}
    if ctx.get("ja_agendado") or known.get("ja_agendado"):
        return None

    # C-126 FIX-1 (11/08/2026): se convênio não aceito e paciente ainda não escolheu,
    # aguardar resposta à oferta C-123 ("1️⃣ Somente / 2️⃣ Seguir sem convênio").
    # Caso real: lead 24442314 Rafael — após C-123 recusar GDF, paciente mandou
    # "Asa norte" e C-120 voltou a perguntar convênio (que já era impossível).
    # INATIVAÇÃO AUTOMÁTICA: após >= 2 turnos sem escolha → escalada + desativa IA.
    if known.get("convenio_nao_aceito_nome") and not known.get(
        "c123_marcar_sem_convenio"
    ) and not known.get("c123_encerrar_so_convenio"):
        # Contador Redis — quantos turnos sem escolha neste estado
        _lead_id_c126_f1 = (
            known.get("lead_id")
            or ctx.get("lead_id")
            or (ctx.get("lead") or {}).get("id")
        )
        _loop_count = 0
        try:
            from voice_agent.redis_client import get_redis as _get_redis_c126f1
            _r_f1 = _get_redis_c126f1()
            if _r_f1 and _lead_id_c126_f1:
                _key_cnt = f"blink:c126_convenio_loop:{_lead_id_c126_f1}"
                _loop_count = int(_r_f1.incr(_key_cnt) or 1)
                _r_f1.expire(_key_cnt, 3600)  # TTL 1h — reseta se conversa esfria
        except Exception:
            pass

        if _loop_count >= 2:
            # Loop confirmado: INATIVAR IA AUTOMATICAMENTE → escalar para humano
            log.error(
                "[C-126] LOOP CONVENIO count=%d lead=%s — "
                "escalando para 1-ATENDIMENTO HUMANO + desativando IA",
                _loop_count, _lead_id_c126_f1,
            )
            try:
                from voice_agent.redis_client import get_redis as _get_redis_c126esc
                _r_esc = _get_redis_c126esc()
                if _r_esc and _lead_id_c126_f1:
                    # Reutiliza flag C-84: pipeline move lead + desativa IA
                    _r_esc.setex(
                        f"blink:c84_pede_atendente:{_lead_id_c126_f1}", 86400, "1"
                    )
            except Exception:
                pass
            _nome_f1 = str(
                known.get("nome_contato") or known.get("nome_paciente") or ""
            ).strip()
            _saud_f1 = (f"{_nome_f1.split()[0]}, " if _nome_f1 else "")
            return (
                f"{_saud_f1}vou conectar você com nossa equipe que pode te orientar "
                "melhor sobre as opções de atendimento. "
                "Em instantes alguém da Blink responde! 🤝"
            )

        log.debug(
            "[C-126] convenio_nao_aceito_nome=%r loop_count=%d — aguardando C-123",
            known.get("convenio_nao_aceito_nome"), _loop_count,
        )
        return None  # C-126: aguardar paciente responder 1️⃣ ou 2️⃣

    # Verificar checklist
    try:
        from voice_agent.checklist_dados_minimos import verificar_dados_minimos
        resultado = verificar_dados_minimos(known)
        if resultado.pronto_para_oferecer_slot or resultado.total_pendentes < 1:
            return None  # checklist completo ou vazio: não agir
    except Exception as _exc_c120:
        log.warning("[C-120] checklist falhou (fail-open): %s", _exc_c120)
        return None

    # Gate: algum dado já coletado OU intenção explícita de agendar
    # Evita interceptar perguntas de FAQ/serviços antes do paciente expressar intenção
    has_data = any(known.get(f) for f in _CAMPOS_COLETADOS_C120)
    has_intent = bool(_INTENT_AGENDAR_C120.search(user_text))
    if not has_data and not has_intent:
        return None  # LLM lida com FAQ, curiosos, perguntas de serviço

    # C-130 (12/08/2026): Anti-loop — se paciente está respondendo à última pergunta
    # de dado do C-125, deixar o LLM extrair e armazenar o valor.
    # Caso real: lead 24447784 Bento — "27/012/2024" (typo) → C-125 disparava 3x
    # porque a data não passava na regex e nunca chegava ao LLM para extração.
    if _inbound_responde_ultima_pergunta_c130(ctx, user_text):
        log.debug("[C-130] inbound responde ultima pergunta C-125 — fall-through para LLM")
        return None

    return _montar_pergunta_dados_c125(resultado, ctx, user_text)


def _montar_pergunta_dados_c120(resultado, ctx) -> str:
    """Monta a pergunta dos dados pendentes em linguagem natural (C-120).

    DEPRECATED: substituído por _montar_pergunta_dados_c125 (Bug C-125 11/08/2026).
    Mantido por compatibilidade com testes legados.
    """
    pendentes = resultado.campos_pendentes
    if not pendentes:
        return ""

    nome = _nome_paciente(ctx)
    saud = f"{nome}, " if nome else ""

    if len(pendentes) == 1:
        campo = pendentes[0]
        if "cpf" in campo.lower():
            nome_pac = (
                (ctx or {}).get("known", {}).get("nome_paciente") or nome or "do paciente"
            )
            return f"{saud}me passa o CPF de {nome_pac}?"
        return f"{saud}me passa {campo}?"

    if len(pendentes) == 2:
        lista = f"{pendentes[0]} e {pendentes[1]}"
    else:
        lista = ", ".join(pendentes[:-1]) + f" e {pendentes[-1]}"

    return f"{saud}antes de garantir o horário, me passa: {lista}?"


# ═══════════════════════════════════════════════════════════════════════
# C-125 — PROVA DE ESCUTA + UMA PERGUNTA POR TURNO (Bug C-125 11/08/2026)
# ═══════════════════════════════════════════════════════════════════════
# Causa raiz de C-120: despejava TODOS os campos pendentes num formulário
# sem reconhecer o que o paciente acabou de dizer (lead 24441434 Janaina).
# C-125 corrige: (1) prova de escuta — acknowledge o que o paciente disse;
#               (2) UMA só pergunta por turno em ordem de prioridade.
#               (3) NUNCA pede médico — Python deriva via C-101/enriquecimento.
# Mesmo toggle: BLINDAGEM_DADOS_PENDENTES_ATIVADO.

_RE_KARLA_C125 = re.compile(r"\bkarla\b", re.IGNORECASE)
_RE_FABRICIO_C125 = re.compile(r"\bfabr[ií]c[io]o?\b|\bfreitas\b", re.IGNORECASE)
_RE_BEBE_C125 = re.compile(r"\bb[eê]b[eê]\b|\brecém[- ]nasc\w*", re.IGNORECASE)
_RE_FILHO_IDADE_C125 = re.compile(
    r"(?:filho|filha|menino|menina|crian[cç]a|bebê|bebe)\s+de\s+(\d+)\s*(m[eê]s(?:es)?|anos?)",
    re.IGNORECASE,
)
_RE_ROTINA_C125 = re.compile(r"\brotina\b|\bcheck[- ]?up\b|\bpreventiv\w+\b", re.IGNORECASE)
_RE_RETORNO_C125 = re.compile(r"\bretorno\b|\bvolta\s+(?:ao|para|pra)\b|\bseguimento\b", re.IGNORECASE)
_RE_ENCAMINHAMENTO_C125 = re.compile(
    r"\bencaminh\w+\b|\bpedi[aá]tra\b|\bm[eé]dico\s+de\s+fam[ií]lia\b",
    re.IGNORECASE,
)


def _prova_de_escuta_c125(user_text: str, known: dict) -> str:
    """Extrai o que o paciente disse e retorna string de acknowledgment (C-125).

    Ex: "Anotado — Dra. Karla Delalíbera, bebê de 7 meses, consulta de rotina"
    Retorna "" se não houver elementos identificáveis o suficiente.
    """
    partes: list[str] = []

    # Médico mencionado explicitamente pelo paciente
    if _RE_KARLA_C125.search(user_text):
        partes.append("Dra. Karla Delalíbera")
    elif _RE_FABRICIO_C125.search(user_text):
        partes.append("Dr. Fabrício Freitas")

    # Perfil do paciente: filho/bebê com idade
    m_filho = _RE_FILHO_IDADE_C125.search(user_text)
    if m_filho:
        num = m_filho.group(1)
        unid = m_filho.group(2)
        if "ano" in unid.lower():
            s = "s" if int(num) != 1 else ""
            partes.append(f"criança de {num} ano{s}")
        else:
            s = "s" if int(num) != 1 else ""
            partes.append(f"bebê de {num} mês{s}" if int(num) == 1 else f"bebê de {num} meses")
    elif _RE_BEBE_C125.search(user_text):
        partes.append("bebê")

    # Motivo da consulta
    if _RE_RETORNO_C125.search(user_text):
        partes.append("retorno")
    elif _RE_ROTINA_C125.search(user_text):
        partes.append("consulta de rotina")

    # Encaminhamento / pediatra
    if _RE_ENCAMINHAMENTO_C125.search(user_text):
        partes.append("com encaminhamento")

    if not partes:
        return ""

    return "Anotado — " + ", ".join(partes)


def _campo_prioritario_c125(pendentes: tuple) -> Optional[str]:
    """Retorna APENAS o campo mais prioritário (um só), filtrando 'médico' (C-125).

    Nunca pede médico via C-125 — Python deriva via C-101/enriquecimento_ctx.
    Prioridade natural: nome → data_nasc → convênio → cpf → unidade.
    """
    for campo in pendentes:
        if "médico" in campo.lower():
            continue  # Python's job — never ask patient to choose médico
        return campo
    return None  # só médico restava → fail-open, LLM continua


def _montar_pergunta_dados_c125(resultado, ctx, user_text: str) -> str:
    """Monta pergunta com prova de escuta + 1 campo prioritário (C-125).

    Formato quando escuta presente:
        "Anotado — Dra. Karla Delalíbera, bebê de 7 meses, consulta de rotina! 😊
         Qual o nome completo do bebê?"

    Formato sem escuta (paciente só disse "sim"):
        "João, o atendimento vai ser por convênio ou sem convênio?"
    """
    known = (ctx or {}).get("known") or {}
    campo = _campo_prioritario_c125(resultado.campos_pendentes)
    if not campo:
        return ""  # só médico pendente — Python resolve via C-101

    # Prova de escuta: extrai o que o paciente disse
    escuta = _prova_de_escuta_c125(user_text, known)

    # Detectar perfil (bebê/criança) para personalizar pronomes
    eh_bebe = bool(
        _RE_BEBE_C125.search(user_text) or _RE_FILHO_IDADE_C125.search(user_text)
    )

    nome_pac = (
        known.get("nome_paciente")
        or known.get("nome_completo_paciente")
        or known.get("nome")
    )
    nome_primeiro = _nome_paciente(ctx)  # primeiro nome (para saudação)

    # Pergunta específica por campo (atômica — apenas 1)
    if "cpf" in campo.lower():
        ref = nome_pac or ("do bebê" if eh_bebe else "do paciente")
        pergunta = f"me passa o CPF de {ref}?"
    elif "nome completo" in campo.lower():
        ref = "do bebê" if eh_bebe else "do paciente"
        pergunta = f"qual o nome completo {ref}?"
    elif "data de nascimento" in campo.lower():
        if nome_pac:
            primeiro_pac = nome_pac.strip().split()[0]
            pergunta = f"qual a data de nascimento de {primeiro_pac}?"
        elif eh_bebe:
            pergunta = "qual a data de nascimento do bebê?"
        else:
            pergunta = "qual a data de nascimento do paciente?"
    elif "convênio" in campo.lower():
        pergunta = "o atendimento vai ser por convênio ou sem convênio?"
    elif "unidade" in campo.lower():
        pergunta = "prefere Asa Norte ou Águas Claras?"
    else:
        pergunta = f"me passa {campo}?"

    p = pergunta[0].upper() + pergunta[1:]

    # Montar resposta final
    if escuta:
        return f"{escuta}! 😊 {p}"
    elif nome_primeiro and nome_primeiro.lower() in pergunta.lower():
        # Nome já aparece no corpo da pergunta — evita "Beatriz, Qual a data de Beatriz?"
        return p
    else:
        saud = f"{nome_primeiro}, " if nome_primeiro else ""
        return f"{saud}{p}"


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
        # === Bug C-126 FIX-2 (11/08/2026): C-84 na chain ANTES de qualquer bypass ===
        # C-84b em _scrub_prohibited (pós-LLM) nunca roda quando C-120 bypassa o LLM.
        # Caso real: lead 24442314 Rafael — "Quem está me atendendo é um Robô, ou atendente?"
        # foi ignorado 3x porque C-120 curto-circuitava o LLM inteiro.
        # Solução: detectar pedido de atendente/robô AQUI TAMBÉM, antes de qualquer bypass.
        # Usa mesmos padrões e flag Redis de C-84b (blink:c84_pede_atendente:{lead_id}).
        try:
            _C126_PEDE_ATENDENTE = re.compile(
                r"\batendente\b|falar\s+com\s+(um\s+)?atendente|"
                r"quero\s+atendente|chamar\s+atendente|"
                r"falar\s+com\s+(um\s+)?humano|falar\s+com\s+pessoa|"
                r"me\s+passa\s+pra\s+(uma?\s+)?pessoa|"
                r"quero\s+falar\s+com\s+algu[eé]m|"
                r"me\s+passa\s+pra\s+(um\s+)?atendente|"
                r"\bhumano\b.*\bpor\s+favor\b|\bpor\s+favor\b.*\bhumano\b|"
                # C-131 12/08/2026 — lead 24448016 Lorena disse "atendimento humano."
                # \batendente\b não casava com "atendimento" (palavra diferente)
                r"\batendimento\s+humano\b|quero\s+atendimento\s+humano|"
                r"transfere?\s+(?:para?\s+)?(?:um\s+)?atendimento\s+humano|"
                r"\brob[oô]\b|est[aá]\s+me\s+atendendo|quem\s+[eé]\s+voc[eê]",
                re.IGNORECASE | re.UNICODE,
            )
            if user_text and _C126_PEDE_ATENDENTE.search(user_text):
                _known_c126 = (ctx or {}).get("known") or {}
                _nome_c126 = str(
                    _known_c126.get("nome_contato") or _known_c126.get("nome_paciente") or ""
                ).strip()
                _saud_c126 = (f"{_nome_c126.split()[0]}, " if _nome_c126 else "")
                _resp_c126 = (
                    f"{_saud_c126}entendido! Vou passar para um dos nossos atendentes "
                    "agora. Em instantes alguém da Blink responde por aqui. 🤝"
                )
                # Grava flag Redis — pipeline hook moverá lead pra 1-ATENDIMENTO HUMANO
                try:
                    _lid_c126 = (
                        _known_c126.get("lead_id")
                        or (ctx or {}).get("lead_id")
                        or ((ctx or {}).get("lead") or {}).get("id")
                    )
                    if _lid_c126:
                        from voice_agent.redis_client import get_redis as _get_redis_c126
                        _r_c126 = _get_redis_c126()
                        if _r_c126:
                            _r_c126.setex(
                                f"blink:c84_pede_atendente:{_lid_c126}", 86400, "1"
                            )
                except Exception:  # noqa: BLE001
                    pass
                log.error(
                    "[C-126/C-84] PACIENTE PEDIU ATENDENTE (bypass chain) user=%r",
                    user_text[:60],
                )
                return ("pede_atendente_c126", _resp_c126)
        except Exception as _e126_c84:
            log.warning("[C-126/C-84] bypass atendente falhou: %s", _e126_c84)

        # === Bug C-127 Fix 2 (12/08/2026): Anti-repetição universal ===
        # Problema: bypasses ignoram o histórico recente. Se o paciente já recebeu
        # "Qual o nome do paciente?" como última outbound, e algo leva ao mesmo bypass,
        # a mesma pergunta é enviada de novo → parece robô de disco travado.
        #
        # Solução: ANTES de qualquer bypass, armazenar a última outbound e, após gerar
        # a resposta candidata, verificar se ela seria repetição substancial.
        # Se sim → return None (LLM tenta uma variação diferente).
        #
        # Implementado como closure: _guard_repeticao(candidata) → bool
        # Fail-open: qualquer exceção → não bloqueia.
        _ultima_outbound_c127 = ""
        try:
            _ultima_outbound_c127 = str(
                ((ctx or {}).get("known") or {}).get("ultima_msg_outbound") or ""
            ).strip().lower()
        except Exception:
            pass

        def _repete_ultima_outbound(candidata: str) -> bool:
            """True se a candidata é repetição substancial da última outbound."""
            if not _ultima_outbound_c127 or not candidata:
                return False
            try:
                cand_lower = candidata.strip().lower()
                # Extrai palavras-chave da candidata (3+ chars, sem stop words)
                _stop = {"que", "com", "para", "por", "uma", "seu", "sua", "qual",
                         "como", "mais", "não", "sim", "ok", "ola", "oi", "bom",
                         "dia", "tarde", "boa", "noite", "tudo"}
                palavras_cand = {
                    w for w in re.findall(r"\b\w{3,}\b", cand_lower, re.UNICODE)
                    if w not in _stop
                }
                palavras_ult = {
                    w for w in re.findall(r"\b\w{3,}\b", _ultima_outbound_c127, re.UNICODE)
                    if w not in _stop
                }
                if not palavras_cand or not palavras_ult:
                    return False
                intersecao = palavras_cand & palavras_ult
                # Repetição se > 70% das palavras-chave coincidem
                overlap = len(intersecao) / min(len(palavras_cand), len(palavras_ult))
                if overlap >= 0.70:
                    log.debug(
                        "[C-127/ANTI-REP] suprimindo repetição overlap=%.0f%% "
                        "cand=%r ult=%r",
                        overlap * 100, candidata[:60], _ultima_outbound_c127[:60],
                    )
                    return True
                return False
            except Exception:
                return False

        # Bug C-129 (12/08/2026): Pós-consulta → escalar para humano.
        # Qualquer paciente que pergunta sobre recibo, reembolso, laudo, resultado,
        # atestado ou qualquer questão administrativa pós-consulta deve ir para
        # atendente humana — Lia não tem acesso a esses dados.
        # Camada A: pedido de documento (sempre escalar).
        # Camada B: ctx.known.a_fazer_pos_consulta=True + msg não é novo agendamento.
        # Vem ANTES de C-117 (cancelamento) — se o paciente está em pós-consulta,
        # qualquer comunicação que não seja "quero marcar nova consulta" vai ao humano.
        try:
            from voice_agent.pos_consulta import deve_escalar_pos_consulta
            t = deve_escalar_pos_consulta(ctx, user_text)
            if t:
                return ("pos_consulta_c129", t)
        except Exception as _e129:
            log.warning("[C-129] bypass pos_consulta falhou: %s", _e129)

        # Bug C-117 (11/08/2026): Cancelamento < 24h → informa política de sinal.
        # Vem PRIMEIRO na chain — se paciente tem consulta em < 24h e quer cancelar,
        # Python calcula o delta, informa a política de sinal (50% não devolvido)
        # e abre para reagendamento. Gate: ctx.known.dia_consulta_iso preenchido.
        # Fail-open: sem iso → None → próximos bypasses continuam.
        try:
            from voice_agent.cancelamento_24h import deve_informar_politica_cancelamento_24h as _cancel_24h
            t = _cancel_24h(ctx, user_text)
            if t:
                if _repete_ultima_outbound(t):
                    pass  # não bloqueia C-117 (política de sinal nunca deve ser suprimida)
                else:
                    return ("cancelamento_24h", t)
        except Exception as _e117:
            log.warning("[C-117] bypass cancelamento_24h falhou: %s", _e117)

        # Bug C-108 (11/08/2026): desistência explícita — "desisti", "não quero mais",
        # "vou em outro lugar". Vem DEPOIS de C-117 — se há consulta < 24h o C-117
        # prioriza a política; se não há consulta ou está > 24h, C-108 encerra.
        try:
            from voice_agent.desistencia import deve_responder_desistencia
            t = deve_responder_desistencia(ctx, user_text)
            if t:
                return ("desistencia", t)
        except Exception as _e108:
            log.warning("[C-108] bypass desistencia falhou: %s", _e108)

        # Bug C-109 (11/08/2026): NO-SHOW COUNT >= 2 → sinal Pix obrigatório antes do slot.
        # Vem DEPOIS de desistência (C-108) e ANTES de urgência — se o paciente está
        # desistindo, não precisamos cobrar sinal; mas se está querendo agendar E tem
        # histórico de no-show, a política de sinal vem antes de qualquer oferta de slot.
        try:
            from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
            t = deve_exigir_sinal_noshow(ctx, user_text)
            if t:
                return ("sinal_noshow", t)
        except Exception as _e109:
            log.warning("[C-109] bypass sinal_noshow falhou: %s", _e109)

        # Bug C-110 (11/08/2026): CPF matematicamente inválido → pedir correção.
        # Vem DEPOIS de desistência/sinal (não pedimos CPF pra quem está desistindo)
        # e ANTES de urgência — CPF errado bloqueia gravação Medware de qualquer forma.
        # Só age quando há padrão de CPF no texto E é matematicamente inválido.
        try:
            from voice_agent.validacao_cpf import deve_validar_cpf as _validar_cpf_c110
            t = _validar_cpf_c110(ctx, user_text)
            if t:
                return ("cpf_invalido", t)
        except Exception as _e110:
            log.warning("[C-110] bypass validacao_cpf falhou: %s", _e110)

        # Bug C-113 (11/08/2026): Múltiplos pacientes — bifurcar para 2 agendamentos.
        # Detecta "2 filhos", "nós dois", "para mim e minha filha" → orienta bifurcação.
        # Vem ANTES de protocolo_retorno e urgência: quando há múltiplos pacientes,
        # precisamos resolver a bifurcação antes de verificar protocolo do primeiro.
        try:
            from voice_agent.multiplos_pacientes import deve_orientar_multiplos_pacientes as _orientar_multi
            _redis_c113 = getattr(ctx, "_redis", None) if not isinstance(ctx, dict) else None
            t = _orientar_multi(ctx, user_text, _redis_c113)
            if t:
                return ("multiplos_pacientes", t)
        except Exception as _e113:
            log.warning("[C-113] bypass multiplos_pacientes falhou: %s", _e113)

        # Bug C-112 (11/08/2026): Protocolo retorno — bloquear oferta prematura.
        # Dra. Karla define janela de retorno na consulta. Se 1.MÊS PRÓX CONSULTA
        # ainda está no futuro OU 1.DIA CONSULTA < janela mínima atrás, não oferecer slot.
        # Roda ANTES de urgência: protocolo médico definido vence oferta nova.
        try:
            from voice_agent.protocolo_retorno import deve_bloquear_oferta_retorno as _bloquear_retorno
            t = _bloquear_retorno(ctx)
            if t:
                return ("protocolo_retorno", t)
        except Exception as _e112:
            log.warning("[C-112] bypass protocolo_retorno falhou: %s", _e112)

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

        # Bug C-115 (11/08/2026): FAQ consulta marcada — "quando é minha consulta?"
        # Python lê ctx.known.dia_consulta_iso (campo Kommo 1255723) e formata
        # a resposta com dia-da-semana + data + hora + médico + unidade.
        # Zero Medware, zero LLM. Fail-open se sem dia_consulta_iso.
        try:
            from voice_agent.faq_consulta_marcada import deve_responder_faq_consulta_marcada as _faq_consulta
            t = _faq_consulta(ctx, user_text)
            if t:
                return ("faq_consulta_marcada", t)
        except Exception as _e115:
            log.warning("[C-115] bypass faq_consulta_marcada falhou: %s", _e115)

        # Bug C-116 (11/08/2026): Comprovante Pix — fecha loop da política de comparecimento.
        # Paciente enviou imagem → webhook gerou texto sintético.
        # Se blink:politica_aguardando_comprovante:{lead_id} ativo → confirma recebimento.
        # Grava blink:c116_comprovante_detectado:{lead_id} para pipeline fazer
        # nota Kommo + limpeza de flags. Fail-open: sem Redis → None.
        try:
            from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix as _comprovante
            t = _comprovante(ctx, user_text)
            if t:
                return ("comprovante_pix_c116", t)
        except Exception as _e116:
            log.warning("[C-116] bypass comprovante_pix falhou: %s", _e116)

        # Bug C-87 (05/08/2026): FAQ endereço — "onde fica?", "qual o endereço?"
        # Resposta determinística com link Maps. Zero Medware, zero LLM.
        t = deve_responder_faq_endereco(ctx, user_text)
        if t and not _repete_ultima_outbound(t):
            return ("faq_endereco", t)

        # Bug C-74 (26/07/2026): FAQ especialidade/médico — resposta KB pura,
        # zero LLM. Evita circuit breaker C-56 em perguntas simples.
        t = deve_responder_faq_especialidade(ctx, user_text)
        if t and not _repete_ultima_outbound(t):
            return ("faq_especialidade", t)

        # Bug C-123 (11/08/2026): Escolha pós-recusa de convênio.
        # Se o último outbound da Lia apresentou "1️⃣ Somente com Convênio /
        # 2️⃣ Seguir Sem Convênio", detecta a escolha do paciente e injeta
        # ctx.known.convenio = "Não se aplica" + flag c123_marcar_sem_convenio.
        # Vem ANTES de faq_convenio_aceito — o paciente está respondendo a uma
        # oferta já apresentada, não fazendo uma pergunta nova de FAQ.
        t = deve_responder_escolha_convenio(ctx, user_text)
        if t:
            # Escolha de convênio nunca suprimida — é ação, não FAQ
            return ("escolha_convenio_c123", t)

        # Bug C-104 (11/08/2026): FAQ convênio aceito usando ctx.known.convenio_aceito
        # (derivado por C-103). "Vocês aceitam meu plano?" → resposta imediata
        # sem LLM e sem Medware. Vem ANTES do classificador_convenio para usar
        # o ctx.known já enriquecido quando disponível.
        t = deve_responder_faq_convenio_aceito(ctx, user_text)
        if t and not _repete_ultima_outbound(t):
            return ("faq_convenio_aceito", t)

        # Bug C-60 (20/07/2026): classificador convênio ANTES do valor,
        # pra pegar CBMDF, GDF, Amil etc antes de LLM inventar "deixa eu verificar"
        try:
            from voice_agent.classificador_convenio import deve_responder_convenio
            t = deve_responder_convenio(ctx, user_text)
            if t and not _repete_ultima_outbound(t):
                return ("convenio", t)
        except Exception as e:  # noqa: BLE001
            log.warning("bypass convênio falhou: %s", e)

        # Bug C-107 (11/08/2026): objeção de preço — "caro", "encontrei mais barato".
        # Vem ANTES de deve_responder_valor para capturar pacientes que já sabem
        # o preço e estão objectionando, não apenas pedindo o valor pela primeira vez.
        # Entrega script contextualizado: diferencial especialidade + alternativas.
        try:
            from voice_agent.objecao_preco import deve_responder_objecao_preco
            t = deve_responder_objecao_preco(ctx, user_text)
            if t and not _repete_ultima_outbound(t):
                return ("objecao_preco", t)
        except Exception as _e107:
            log.warning("[C-107] bypass objecao_preco falhou: %s", _e107)

        t = deve_responder_valor(ctx, user_text)
        if t and not _repete_ultima_outbound(t):
            return ("valor", t)

        t = deve_gerar_confirmacao_aceite(ctx, user_text)
        if t:
            # Aceite de slot nunca suprimido — é ação crítica de agendamento
            return ("aceite_slot", t)

        t = deve_enviar_endereco_pos_agenda(ctx)
        if t and not _repete_ultima_outbound(t):
            return ("endereco_pos_agenda", t)

        # Bug C-114 (11/08/2026): Política de comparecimento — sinal 50% para PARTICULAR.
        # Quando paciente confirma dados da conclusão de agendamento ("sim dados corretos")
        # e é particular (sem convênio aceito), Lia apresenta 2 opções:
        #   1️⃣ Reserva garantida → Pix 50% do valor
        #   2️⃣ Fila de encaixe → sem pagamento, sem exclusividade
        # Análogo à poltrona de avião: você comprou o bilhete (agendou), e DEPOIS
        # vem a opção de garantir o assento (sinal). Leve, não coercitivo.
        # Vem DEPOIS de endereco_pos_agenda — é a última ação no fluxo de agendamento.
        try:
            from voice_agent.politica_comparecimento import deve_solicitar_sinal_particular as _solicitar_sinal
            _redis_c114 = getattr(ctx, "_redis", None) if not isinstance(ctx, dict) else None
            t = _solicitar_sinal(ctx, user_text, _redis_c114)
            if t and not _repete_ultima_outbound(t):
                return ("sinal_particular_c114", t)
        except Exception as _e114:
            log.warning("[C-114] bypass sinal_particular falhou: %s", _e114)

        # C-120 (11/08/2026): dados pendentes — Python gera pergunta, salva 1 LLM call.
        # Fica NO FIM da chain: todos os bypasses específicos (FAQ, valor, aceite, etc.)
        # têm prioridade. Só chega aqui quando nenhum outro bypass quis o turno.
        try:
            t = deve_perguntar_dados_pendentes(ctx, user_text)
            if t and not _repete_ultima_outbound(t):
                return ("dados_pendentes_c120", t)
        except Exception as _e120:
            log.warning("[C-120] bypass dados_pendentes falhou: %s", _e120)

    except Exception as e:  # noqa: BLE001
        log.warning("bypass determinístico falhou: %s", e)
        return None

    return None
