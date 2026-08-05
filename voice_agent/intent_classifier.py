"""
voice_agent/intent_classifier.py
Bug C-81 — Classificador de intenção pré-LLM (02/08/2026)

Problema: pipeline monolítico de 120K chars carregado em CADA turno.
Resultado: Isabella (22335902) teve "olhos inchados e remelando" e
recebeu triagem normal de convênio em vez de encaixe urgente.

Solução: classificação determinística (regex) ANTES do LLM.
• Detecta urgência (critical / priority / routine) por vocabulário oftalmológico.
• Pré-extrai unidade, n_pacientes, dia_preferência, turno, médico da primeira
  mensagem — reduz perguntas de coleta de 3-4 turnos para 0-1.
• Resultado injetado em caller_context["known"] antes do Medware lookup
  (pipeline.py ~linha 482) — Medware já recebe parâmetros corretos.

Custo: ZERO chamadas de API — só regex. Haiku fallback opcional para
casos verdadeiramente ambíguos (toggle INTENT_HAIKU_FALLBACK=1).
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class PreSlots:
    """Campos pré-extraídos da mensagem do paciente."""
    unidade: Optional[str] = None          # "Asa Norte" | "Águas Claras"
    n_patients: Optional[int] = None       # 1, 2, 3 …
    day_pref: Optional[str] = None         # "segunda" | "semana que vem" | "amanhã" …
    turno: Optional[str] = None            # "manhã" | "tarde"
    medico: Optional[str] = None           # "Karla" | "Fabrício"


@dataclass
class IntentResult:
    """Saída do classificador de intenção."""
    urgency_level: str = "routine"         # "critical" | "priority" | "routine"
    intent: str = "agendamento"            # ver _INTENTS
    pre_slots: PreSlots = field(default_factory=PreSlots)
    # Descrição resumida do que foi detectado (para log / nota Kommo)
    reasoning: str = ""
    # True se deve pular coleta de convênio e ir direto para encaixe
    skip_convenio: bool = False
    # True se deve escalar humano imediatamente (critical)
    escalate_human: bool = False

# ---------------------------------------------------------------------------
# Padrões de urgência oftalmológica
# ---------------------------------------------------------------------------

# CRÍTICO — perda de função / trauma físico.
# Ação: resposta canônica imediata + escalar humano + sem LLM.
_CRITICAL_PATTERNS = re.compile(
    r"""
    perda\s+de\s+vis[aã]o                 # perda de visão
    | perdeu\s+a\s+vis[aã]o               # perdeu a visão
    | n[aã]o\s+(?:est[aá]\s+)?enxerga     # não enxerga
    | n[aã]o\s+v[eê]                      # não vê
    | ficou\s+ceg[ao]                     # ficou cego/a
    | cegueira                            # cegueira
    | trauma\s+ocular                     # trauma ocular
    | bateu.{0,10}olho                    # bateu no/o olho
    | baten?d[oa].{0,10}olho            # batendo no/o olho
    | machucou.{0,10}olho               # machucou o/no olho
    | feriu.{0,10}olho                  # feriu o/no olho
    | cortou.{0,10}olho                 # cortou o/no olho
    | perfura[çc][aã]o                   # perfuração
    | corpo\s+estranho                   # corpo estranho
    | caiu\s+(?:algo|alguma\s+coisa)?\s*(?:n[oa]\s+)?olho  # caiu algo no olho
    | descolamento                       # descolamento de retina
    | olho\s+(?:est[aá]\s+)?saindo      # olho saindo
    | olho\s+saltando                    # olho saltando
    | queimadura\s+(?:n[oa]\s+)?olho    # queimadura no olho
    | produto\s+qu[íi]mico              # produto químico
    | [áa]cido\s+(?:n[oa]\s+)?olho     # ácido no olho
    """,
    re.VERBOSE | re.IGNORECASE,
)

# PRIORITÁRIO — sintoma ativo que precisa de encaixe, mas não PS imediato.
# Ação: oferecer encaixe imediatamente + pular coleta de convênio +
# alerta paralelo ao humano.
_PRIORITY_PATTERNS = re.compile(
    r"""
    olho\s+(?:(?:est[aá]|ficou)\s+)?inchad[oa]   # olho inchado
    | incha[çc][aã]o\s+(?:n[oa]\s+)?olho          # inchaço no olho
    | remela(?:ndo)?                               # remela / remelando
    | rem[eê]la                                    # remela (acento)
    | secre[çc][aã]o\s+(?:n[oa]\s+)?olho         # secreção no olho
    | olho\s+vermelho                             # olho vermelho
    | vermelhid[aã]o\s+(?:n[oa]\s+)?olho         # vermelhidão no olho
    | olho\s+(?:est[aá]\s+)?ardendo              # olho ardendo
    | ardor\s+(?:n[oa]\s+)?olho                  # ardor no olho
    | arde\s+(?:o\s+)?olho                       # arde o olho
    | dor\s+(?:forte\s+)?(?:n[oa]\s+)?olho       # dor no olho
    | olho\s+(?:est[aá]\s+)?doendo               # olho doendo
    | dói\s+(?:muito\s+)?(?:o\s+)?olho           # dói o olho
    | lacrimejando\s+muito                        # lacrimejando muito
    | cho?rand[oa]\s+muito\s+(?:d[oa]\s+)?olho   # chorando muito do olho
    | coceira\s+(?:intensa\s+)?(?:n[oa]\s+)?olho  # coceira no olho
    | olho\s+(?:com\s+)?co[çc]ando              # olho coçando
    | vis[aã]o\s+emba[çc]ada                    # visão embaçada
    | vis[aã]o\s+dupla                          # visão dupla
    | sensibilidade\s+(?:à|a)\s+luz             # sensibilidade à luz
    | fotofobia                                  # fotofobia
    | alergia\s+(?:n[oa]\s+)?olho               # alergia no olho
    | olho\s+(?:com\s+)?alergia                 # olho com alergia
    | conjuntivite                               # conjuntivite
    | urg[eê]ncia\s+(?:oftalm)?                 # urgência (com ou sem "oftalm")
    | urgente                                    # urgente
    | preciso.{0,30}hoje                       # preciso (de consulta) hoje
    | (?:o\s+mais\s+r[áa]pido|o\s+quanto\s+antes)  # o mais rápido / o quanto antes
    | t[êe]m\s+horário\s+(?:hoje|agora)         # tem horário hoje/agora
    | sangue\s+(?:n[oa]\s+)?olho                # sangue no olho (pode ser priority)
    | pus\s+(?:n[oa]\s+)?olho                   # pus no olho
    | olho\s+(?:com\s+)?pus                     # olho com pus
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Padrões de intenção
# ---------------------------------------------------------------------------

_INTENT_FAQ_VALOR = re.compile(
    r"quanto\s+custa|qual\s+(?:o\s+)?(?:valor|pre[çc]o)|caro|barato|pagar|gratuito|de\s+gra[çc]a",
    re.IGNORECASE,
)

_INTENT_FAQ_LOCAL = re.compile(
    r"onde\s+fica|endere[çc]o|localiza[çc][aã]o|como\s+chegar|est[áa]\s+localiza|como\s+ir|mapa",
    re.IGNORECASE,
)

_INTENT_CANCELAMENTO = re.compile(
    r"cancelar|desmarcar|cancelamento|n[aã]o\s+(?:vou\s+)?(?:poder|conseguir)\s+ir|n[aã]o\s+vou\s+mais",
    re.IGNORECASE,
)

_INTENT_AGENDAMENTO = re.compile(
    r"agendar|marcar|consulta|horário|disponib|vaga|atend|médic[oa]|dra\.|dr\.",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Padrões de pré-extração de slots
# ---------------------------------------------------------------------------

# Unidade
_UNIDADE_ASA_NORTE = re.compile(
    r"\basa\s+norte\b|\bnorte\b(?!\s+(?:de|do|da))|(?:cl[íi]nica\s+)?asa\s+norte",
    re.IGNORECASE,
)
_UNIDADE_AGUAS_CLARAS = re.compile(
    r"\b[aá]guas\s+claras\b|\baguas\s+claras\b|\bclaras\b|\bac\b",
    re.IGNORECASE,
)

# Número de pacientes
_N_PATIENTS_PATTERNS = [
    # "2 filhos", "dois filhos", "minhas 2 filhas"
    (re.compile(r"\b([23456]|dois|tr[êe]s|quatro)\s+(?:filh[oa]s?|crian[çc]as?|pacientes?|pessoas?|irmã[os]?|sobrinh[oa]s?)\b", re.IGNORECASE), {
        "dois": 2, "três": 3, "tres": 3, "quatro": 4,
    }),
    # "eu e minha filha", "minha filha e eu"
    (re.compile(r"\beu\s+e\s+(?:minha?|meu|meus)\b|\b(?:minha?|meu|meus).{0,20}\s+e\s+eu\b", re.IGNORECASE), None),
    # "nós dois", "somos dois"
    (re.compile(r"\bn[oó]s\s+(?:dois|duas)\b|\bsomos\s+(?:dois|duas)\b", re.IGNORECASE), None),
]

_N_DIGITS = re.compile(r"\b([23456])\b")

# Dia da semana / preferência temporal
_DAY_PREFS = {
    "segunda": re.compile(r"\bsegunda(?:-feira)?\b", re.IGNORECASE),
    "terça": re.compile(r"\bter[çc]a(?:-feira)?\b", re.IGNORECASE),
    "quarta": re.compile(r"\bquarta(?:-feira)?\b", re.IGNORECASE),
    "quinta": re.compile(r"\bquinta(?:-feira)?\b", re.IGNORECASE),
    "sexta": re.compile(r"\bsexta(?:-feira)?\b", re.IGNORECASE),
    "sábado": re.compile(r"\bs[aá]bado\b", re.IGNORECASE),
    "amanhã": re.compile(r"\bamanh[aã]\b", re.IGNORECASE),
    "hoje": re.compile(r"\bhoje\b", re.IGNORECASE),
    "semana_que_vem": re.compile(r"\bsemana\s+(?:que\s+vem|pr[oó]xima)\b|\bpr[oó]xima\s+semana\b", re.IGNORECASE),
    "essa_semana": re.compile(r"\bessa\s+semana\b|\besta\s+semana\b", re.IGNORECASE),
}

# Turno
_TURNO_MANHA = re.compile(r"\bmanh[aã]\b", re.IGNORECASE)
_TURNO_TARDE = re.compile(r"\btarde\b", re.IGNORECASE)

# Médico
_MEDICO_KARLA = re.compile(r"\bkarla\b|\bdra\.?\s*karla\b", re.IGNORECASE)
_MEDICO_FABRICIO = re.compile(r"\bfabr[íi]cio\b|\bfabricio\b|\bdr\.?\s*fabr[íi]cio\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Funções de classificação
# ---------------------------------------------------------------------------


def _classify_urgency(text: str) -> tuple[str, str]:
    """
    Retorna (urgency_level, reasoning) para o texto.
    urgency_level: "critical" | "priority" | "routine"
    """
    if _CRITICAL_PATTERNS.search(text):
        matched = _CRITICAL_PATTERNS.search(text)
        return "critical", f"critical keyword: '{matched.group()[:40]}'"

    if _PRIORITY_PATTERNS.search(text):
        matched = _PRIORITY_PATTERNS.search(text)
        return "priority", f"priority keyword: '{matched.group()[:40]}'"

    return "routine", "no urgency keywords detected"


def _classify_intent(text: str, urgency_level: str) -> str:
    """Classifica a intenção principal da mensagem."""
    if urgency_level in ("critical", "priority"):
        return "urgencia"
    if _INTENT_FAQ_VALOR.search(text):
        return "faq_valor"
    if _INTENT_FAQ_LOCAL.search(text):
        return "faq_local"
    if _INTENT_CANCELAMENTO.search(text):
        return "cancelamento"
    # Default: agendamento (a maioria das primeiras mensagens)
    return "agendamento"


def _extract_pre_slots(text: str) -> PreSlots:
    """
    Extrai campos de agendamento pre-preenchidos da mensagem.
    Evita perguntas de coleta desnecessárias.
    """
    slots = PreSlots()

    # --- Unidade ---
    if _UNIDADE_ASA_NORTE.search(text):
        slots.unidade = "Asa Norte"
    elif _UNIDADE_AGUAS_CLARAS.search(text):
        slots.unidade = "Águas Claras"

    # --- Número de pacientes ---
    # Tenta padrão composto primeiro
    for pattern, word_map in _N_PATIENTS_PATTERNS:
        m = pattern.search(text)
        if m:
            if word_map is not None:
                # Grupo 1 é o número/palavra
                raw = m.group(1).lower()
                slots.n_patients = word_map.get(raw, 2)
            else:
                slots.n_patients = 2
            break

    # Fallback: dígito isolado (2, 3…) antes de "pacientes"
    if slots.n_patients is None:
        m = _N_DIGITS.search(text)
        if m:
            slots.n_patients = int(m.group(1))

    # --- Dia de preferência ---
    for day_name, pattern in _DAY_PREFS.items():
        if pattern.search(text):
            slots.day_pref = day_name
            break

    # --- Turno ---
    if _TURNO_MANHA.search(text):
        slots.turno = "manhã"
    elif _TURNO_TARDE.search(text):
        slots.turno = "tarde"

    # --- Médico explicitamente mencionado ---
    if _MEDICO_KARLA.search(text):
        slots.medico = "Karla"
    elif _MEDICO_FABRICIO.search(text):
        slots.medico = "Fabrício"

    return slots


# ---------------------------------------------------------------------------
# Função pública principal
# ---------------------------------------------------------------------------


def classify_intent(
    user_text: str,
    caller_context: Optional[dict] = None,
    *,
    is_first_message: bool = False,
) -> IntentResult:
    """
    Classifica a intenção da mensagem do paciente.

    Args:
        user_text: Texto da mensagem recebida.
        caller_context: Contexto do lead (Kommo). Usado para verificar se
            já há unidade/médico definidos (não sobrescreve campos já conhecidos).
        is_first_message: True quando é o primeiro contato do lead (sem histórico
            Redis). Quando True, aplica pré-extração completa mesmo sem palavras-
            chave de agendamento explícitas.

    Returns:
        IntentResult com urgency_level, intent, pre_slots, reasoning,
        skip_convenio, escalate_human.
    """
    if not user_text:
        return IntentResult(reasoning="empty message")

    text = user_text.strip()
    urgency_level, urgency_reason = _classify_urgency(text)
    intent = _classify_intent(text, urgency_level)
    pre_slots = _extract_pre_slots(text)

    # Não sobrescrever campos já definidos no caller_context
    if caller_context:
        known = caller_context.get("known") or {}
        if known.get("unidade") and pre_slots.unidade is None:
            pass  # mantém o que já existe no ctx
        if known.get("unidade") and pre_slots.unidade:
            # ctx já tem unidade definida — não limpar, mas logar discrepância
            if known["unidade"] != pre_slots.unidade:
                log.debug(
                    "[IntentClassifier] unidade no ctx=%r difere da extraída=%r — mantendo ctx",
                    known["unidade"], pre_slots.unidade,
                )
                pre_slots.unidade = None  # não sobrescrever
        if known.get("medico") and pre_slots.medico:
            pre_slots.medico = None  # médico já definido no ctx

    # Flags derivadas de urgência
    skip_convenio = urgency_level in ("critical", "priority")
    escalate_human = urgency_level == "critical"

    # Log estruturado para diagnóstico
    reasons = [urgency_reason]
    if pre_slots.unidade:
        reasons.append(f"unidade={pre_slots.unidade}")
    if pre_slots.n_patients:
        reasons.append(f"n_patients={pre_slots.n_patients}")
    if pre_slots.day_pref:
        reasons.append(f"day_pref={pre_slots.day_pref}")
    if pre_slots.turno:
        reasons.append(f"turno={pre_slots.turno}")
    if pre_slots.medico:
        reasons.append(f"medico={pre_slots.medico}")

    reasoning = f"[C-81] urgency={urgency_level} intent={intent} | " + " | ".join(reasons)

    log.info(reasoning)

    return IntentResult(
        urgency_level=urgency_level,
        intent=intent,
        pre_slots=pre_slots,
        reasoning=reasoning,
        skip_convenio=skip_convenio,
        escalate_human=escalate_human,
    )


# ---------------------------------------------------------------------------
# Mensagens canônicas de urgência
# ---------------------------------------------------------------------------

_MSG_CRITICAL_TEMPLATE = (
    "{nome_prefix}isso parece uma emergência ocular — por favor, vá AGORA ao "
    "pronto-socorro mais próximo ou ligue 192 (SAMU). "
    "Enquanto isso, estou chamando nossa equipe para te apoiar. 🚨"
)

_MSG_PRIORITY_TEMPLATE = (
    "{nome_prefix}consegui ver que você está com um sintoma que precisa de "
    "atenção rápida. Vou verificar um encaixe urgente agora mesmo — "
    "um momento! 🙏"
)


def gerar_msg_urgencia(result: IntentResult, nome_contato: str = "") -> str:
    """Gera a mensagem de resposta canônica para casos urgentes."""
    nome_prefix = f"{nome_contato.split()[0]}, " if nome_contato else ""
    if result.urgency_level == "critical":
        return _MSG_CRITICAL_TEMPLATE.format(nome_prefix=nome_prefix)
    if result.urgency_level == "priority":
        return _MSG_PRIORITY_TEMPLATE.format(nome_prefix=nome_prefix)
    return ""


# ---------------------------------------------------------------------------
# Injeção de pre_slots no caller_context
# ---------------------------------------------------------------------------


def injetar_pre_slots(caller_context: dict, result: IntentResult) -> dict:
    """
    Injeta os campos pré-extraídos em caller_context["known"].
    Não sobrescreve campos já preenchidos.
    Retorna o caller_context modificado (in-place).
    """
    if caller_context is None:
        return caller_context

    known = caller_context.setdefault("known", {})
    slots = result.pre_slots

    if slots.unidade and not known.get("unidade"):
        known["unidade"] = slots.unidade
        log.debug("[C-81] injetou unidade=%r no ctx.known", slots.unidade)

    if slots.n_patients and not known.get("n_patients"):
        known["n_patients"] = slots.n_patients
        log.debug("[C-81] injetou n_patients=%s no ctx.known", slots.n_patients)

    if slots.day_pref and not known.get("dia_turno"):
        known["dia_turno"] = slots.day_pref
        log.debug("[C-81] injetou dia_turno=%r no ctx.known", slots.day_pref)

    if slots.turno and not known.get("turno_preferido"):
        known["turno_preferido"] = slots.turno
        log.debug("[C-81] injetou turno_preferido=%r no ctx.known", slots.turno)

    if slots.medico and not known.get("medico"):
        known["medico"] = slots.medico
        log.debug("[C-81] injetou medico=%r no ctx.known", slots.medico)

    # Flag de urgência para o responder.py adaptar o system prompt
    if result.urgency_level != "routine":
        known["urgency_level"] = result.urgency_level
        known["skip_convenio"] = result.skip_convenio

    return caller_context


# ---------------------------------------------------------------------------
# Bug C-94 (05/08/2026) — Inferência determinística de especialidade + médico
# Resolve: agente qualifica médico + unidade ANTES de oferecer slots
# ---------------------------------------------------------------------------

import datetime as _dt


def calcular_idade_anos(data_nasc) -> Optional[int]:
    """Calcula idade em anos a partir de data de nascimento (int/date/str).

    Aceita:
    - int: timestamp Unix (formato Kommo)
    - date/datetime: diretamente
    - str: ISO "YYYY-MM-DD" ou BR "DD/MM/YYYY" ou "DD/MM/YY"
    Retorna None se não conseguir calcular.
    """
    today = _dt.date.today()
    try:
        if isinstance(data_nasc, (int, float)) and data_nasc > 0:
            dt = _dt.datetime.utcfromtimestamp(float(data_nasc)).date()
        elif hasattr(data_nasc, "year"):
            dt = data_nasc if (isinstance(data_nasc, _dt.date) and not isinstance(data_nasc, _dt.datetime)) else (
                data_nasc.date() if isinstance(data_nasc, _dt.datetime) else data_nasc
            )
        elif isinstance(data_nasc, str):
            s = data_nasc.strip()
            if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", s):
                y, m, d = (int(x) for x in s.split("-"))
                dt = _dt.date(y, m, d)
            elif re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", s):
                parts = s.split("/")
                d2, m2, y2 = int(parts[0]), int(parts[1]), int(parts[2])
                if y2 < 100:
                    y2 += 2000
                dt = _dt.date(y2, m2, d2)
            else:
                return None
        else:
            return None
        age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
        return age if 0 <= age <= 120 else None
    except Exception:
        return None


# Padrões de motivo para especialidade/médico
_MOT_CATARATA = re.compile(r"\bcatarata\b", re.IGNORECASE)
_MOT_CORNEA = re.compile(
    r"\bpt[eé]r[íi]gio\b|\bcarne\s+no\s+olho\b|\bc[oó]rnea\b|\bceratocone\b",
    re.IGNORECASE,
)
_MOT_ESTRABISMO = re.compile(
    r"\bestrabismo\b|\bolho\s+torto\b|\bolhos?\s+desviado[as]?\b",
    re.IGNORECASE,
)
_MOT_APV = re.compile(
    r"\bsdp\b|\bapv\b|\bprocessamento\s+visual\b|\bprisma\b"
    r"|\bcansac[eo]\s+(?:ao\s+)?ler\b|\bcansac[eo]\s+(?:com\s+)?tela\b"
    r"|\bcefalei[a]\b|\bdificuldade\s+de\s+concentra[çc][aã]o\b"
    r"|\bdificuldade\s+(?:de\s+)?leitura\b|\btontura\b",
    re.IGNORECASE,
)
_MOT_PEDIATRICO = re.compile(
    r"\bbeb[êe]\b|\bnasceu\b|\brec[eé]m[-\s]?nascid[oa]\b"
    r"|\bfilh[oa]\s+(?:tem|de)\s+\d+\s+(?:m[eê]s|ano)\b"
    r"|\b\d+\s+(?:m[eê]ses?|meses)\s+de\s+(?:vida|idade)\b",
    re.IGNORECASE,
)


def inferir_especialidade(
    age_years: Optional[int],
    motivo_text: Optional[str],
    medico_known: Optional[str] = None,
) -> Optional[str]:
    """Infere especialidade Kommo por idade + motivo + médico.

    Retorna um dos 3 valores válidos do FIELD_ESPECIALIDADE:
    - "Oftalmopediatria"
    - "Oftalmologia Geral"
    - "Avaliação do Processamento Visual"
    - None se catarata/córnea (Fabrício) ou incerteza

    Regras (em ordem de prioridade):
    1. Fabrício → None (catarata/córnea não têm enum neste campo)
    2. Idade < 13 → Oftalmopediatria
    3. APV/SDP/Processamento → APV
    4. Estrabismo → Oftalmopediatria (Karla faz estrabismo)
    5. Catarata / Córnea → None (Fabrício, sem enum de especialidade)
    6. Adulto definido → Oftalmologia Geral
    7. Incerto → None
    """
    motivo = (motivo_text or "").lower()
    medico = (medico_known or "").lower()

    # Fabrício já definido → não inferir especialidade pelo enum
    if "fabr" in medico:
        return None

    # Pediátrico por idade
    if age_years is not None and age_years < 13:
        return "Oftalmopediatria"

    # APV/SDP
    if _MOT_APV.search(motivo):
        return "Avaliação do Processamento Visual"

    # Estrabismo
    if _MOT_ESTRABISMO.search(motivo):
        return "Oftalmopediatria"

    # Catarata ou Córnea → Fabrício, sem enum de especialidade
    if _MOT_CATARATA.search(motivo) or _MOT_CORNEA.search(motivo):
        return None

    # Adulto com idade definida
    if age_years is not None and age_years >= 13:
        return "Oftalmologia Geral"

    # Pediátrico por motivo (sem data de nascimento)
    if _MOT_PEDIATRICO.search(motivo):
        return "Oftalmopediatria"

    return None


def inferir_medico(
    age_years: Optional[int],
    motivo_text: Optional[str],
    especialidade: Optional[str] = None,
) -> Optional[str]:
    """Infere médico por idade + motivo + especialidade.

    Retorna "Karla" | "Fabrício" | None (incerto → agent vai perguntar).

    Regras:
    - Catarata / Pterígio / Córnea / Ceratocone → Fabrício
    - Bebê/criança < 13 → Karla
    - APV / SDP / Processamento → Karla
    - Estrabismo → Karla
    - Default: None (não inferir para não errar)
    """
    motivo = (motivo_text or "").lower()
    esp = (especialidade or "").lower()

    # Por especialidade já inferida
    if "processamento" in esp or "oftalmopediatria" in esp:
        return "Karla"

    # Por motivo — Fabrício
    if _MOT_CATARATA.search(motivo) or _MOT_CORNEA.search(motivo):
        return "Fabrício"

    # Pediátrico — Karla
    if age_years is not None and age_years < 13:
        return "Karla"
    if _MOT_PEDIATRICO.search(motivo):
        return "Karla"

    # APV / Estrabismo → Karla
    if _MOT_APV.search(motivo) or _MOT_ESTRABISMO.search(motivo):
        return "Karla"

    # Adulto sem sinal claro → não inferir
    return None
