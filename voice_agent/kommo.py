"""Cliente Kommo CRM para auto-preenchimento de leads.

Usa Long-Lived JWT como Bearer. Endpoints v4:
- GET /api/v4/leads?query=<phone>   → busca lead por telefone do contato
- PATCH /api/v4/leads/{id}          → atualiza custom_fields_values

Mapeamento dos campos custom segue o ID/enum do Kommo univeja
(descobertos via list_custom_fields). Esse mapa é fixo no código —
se algum campo for renomeado no Kommo, atualizar aqui também.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Bug C-47 (02/07/2026) — timezone BRT pra formatar 1.DIA CONSULTA.
# Container do Easypanel roda em UTC; datetime.fromtimestamp(ts) sem tz
# devolvia hora UTC (10/07 19:30 UTC = 16:30 BRT). Lia lia e exibia 19:30.
# Manoela (lead 22838100) recebeu "consulta 10/07 às 19:30" 5x seguidas.
_TZ_BR = ZoneInfo("America/Sao_Paulo")
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


# Chaos test gate — module-level redis ref set externamente (webhook startup).
# Quando vazio (default), o gate é inerte e zero overhead.
_CHAOS_REDIS = None


def set_chaos_redis(redis_client) -> None:  # noqa: D401
    """Setter pra o webhook injetar o redis_client após boot."""
    global _CHAOS_REDIS
    _CHAOS_REDIS = redis_client


def _chaos_ativo_kommo() -> bool:
    """Retorna True se chaos test estiver ativo pra serviço kommo."""
    if _CHAOS_REDIS is None:
        return False
    try:
        from voice_agent import chaos as _chaos  # noqa: WPS433
        return _chaos.esta_em_chaos(_CHAOS_REDIS, "kommo")
    except Exception:  # noqa: BLE001
        return False


# ============================================================
# Mapa de campos (univeja.kommo.com)
# ============================================================

# Tipo SELECT (única opção) — id do campo + dict {valor → enum_id}
FIELD_CONVENIO = (853206, {
    "Pro ser STJ": 908265, "Pro Ser STJ": 908265, "STJ": 908265, "Pro Ser": 908265,
    "Bacen": 610306, "Casec": 610316, "Codevasf": 610316,
    "Casembrapa": 610318, "Embrapa": 610318,
    "Conab": 610324,
    "E-vida": 610326, "Luminar": 610326, "E-Vida": 610326,
    "Fascal": 610334,
    "Omint": 610348,
    "PF Saúde": 610356, "PF Saude": 610356, "Polícia Federal": 610356,
    "Plan Assiste": 610358, "MPF": 610358, "MPU": 610358, "MPT": 610358, "MPDFT": 610358,
    "ProSaúde": 610362, "Pro-Saúde": 610362, "Câmara dos Deputados": 610362,
    "Proasa": 610364,
    "Saúde Caixa": 610368, "Caixa": 610368,
    "Petrobrás": 610370, "Petrobras": 610370,
    "Serpro": 610372,
    "SIS Senado": 610374, "Senado": 610374,
    "STF-Med": 610376, "STF": 610376,
    "TRE": 610384, "TRE Saúde": 610384,
    "TRF": 610386, "Pro-social TRF": 610386,
    "TRT": 610388, "TRT Saúde": 610388,
    "TST": 610392, "TST Saúde": 610392,
    "TJDFT": 905132, "TJ DFT": 905132,
    "Care Plus": 908653, "CarePlus": 908653,
    "Anafe": 914499,
    "Plas/JMU": 924924, "STM": 924924, "STM Plas": 924924,
    "Inas GDF": 925312,
    "Não se aplica": 906979, "Particular": 906979, "Sem convênio": 906979,
})

FIELD_UNIDADE = (1245125, {
    "Asa Norte": 905963,
    "Águas Claras": 905961, "Aguas Claras": 905961,
    "Asa Sul": 925828,
})

FIELD_NUMERO_PACIENTES = (1259118, {
    "1": 923818, "2": 923820, "3": 923822, "4": 923824, "5": 923826,
    "6": 925218, "7": 925220, "8": 925222, "9": 925224, "10": 925226,
})

# Tipo MULTISELECT (lista) — mesma forma, ids
FIELD_MEDICOS = (1256257, {
    "Dra. Karla Delalibera": 919833, "Dra Karla": 919833, "Karla Delalibera": 919833,
    "Karla Delalíbera": 919833, "Dra Karla Delalíbera": 919833,
    "Dr. Fabrício Freitas": 919835, "Dr Fabricio": 919835, "Fabricio Freitas": 919835,
    "Fabrício Freitas": 919835, "Dr Fabrício": 919835, "Dr. Fabricio": 919835,
    "Dra. Kátia Delalibera": 919837, "Dra Katia": 919837, "Katia Delalibera": 919837,
    "Kátia Delalíbera": 919837, "Dra Kátia": 919837,
    "Dr. Marcelo Paraíba": 925166,
    "Dra. Isabela Nacarato": 925256,
})

FIELD_ESPECIALIDADE = (1259130, {
    "Oftalmopediatria": 923858, "Pediatria": 923858, "Oftalmopediatra": 923858,
    "Oftalmologia Geral": 923860, "Rotina": 923860, "Check-up": 923860,
    "Avaliação do Processamento Visual": 923862, "Avaliacao do Processamento Visual": 923862,
    "Processamento Visual": 923862,
    # Aliases retrocompatibilidade — termo antigo (SDP) ainda aparece em dados Kommo:
    "SDP": 923862, "Síndrome Deficiência Postural": 923862, "Postural": 923862,
    "Estrabismo": 923864,
    "Retina": 923868, "Retina e vítreo": 923868, "Retina e Vítreo": 923868,
    "Uveíte": 923870,
    "Plástica": 923872,
    "Refrativa": 924832,
    "Catarata": 924930,
    "Lentes": 924934, "Lentes de contato": 924934,
    "Consulta Domiciliar": 925894, "Domiciliar": 925894,
})

# ⚠️ DESATIVADO — o campo "Tipo de agendamento" (id 1260438) NÃO existe na
# conta univeja.kommo.com. Enviá-lo fazia o Kommo rejeitar o PATCH inteiro
# com HTTP 400 (NotSupportedChoice em custom_fields_values.N.field_id).
# Mantido só como referência; não é mais usado em update_lead_fields.
FIELD_TIPO_AGENDAMENTO = (1260438, {
    "Fixo": 926254, "Fixo/Definido": 926254, "Definido": 926254,
    "Encaixe": 926140,
    "Domiciliar": 926202,
})

FIELD_PERFIL_PACIENTE_1 = (1257961, {
    "Bebê 0-2": 922309, "Bebê": 922309, "Bebe 0-2": 922309,
    "Criança 3-12": 922311, "Criança": 922311, "Crianca": 922311,
    "Adolescente 13-18": 923406, "Adolescente": 923406,
    "Adulto de 19 a 49": 922313, "Adulto 19-49": 922313, "Adulto": 922313,
    "Acima de 50": 922315, "Idoso": 922315,
})

# Tipo MULTISELECT — campo AÇÕES (workflow interno da equipe)
FIELD_ACOES = (1259312, {
    "Agendar Encaixe": 925134, "Encaixe": 925134,
    "Agendar Domiciliar": 925336, "Domiciliar": 925336,
})

# "Ñ ACEITO CONVÊNIO" — convênio que o paciente queria usar mas a clínica
# NÃO credencia. Preenchido quando o lead insiste no convênio não aceito.
FIELD_NAO_ACEITO_CONVENIO = (1175268, {
    "Afeb": 897198,
    "Amil": 843464,
    "Assefaz": 843504,
    "Bradesco": 902366, "Bradesco Saúde": 902366,
    "Bradesco Top Nacional": 902366, "Bradesco Saude": 902366,
    "BRB": 902824, "BRB Saúde": 902824, "BRB Saude": 902824,
    "Cassi": 841860,
    "Fusex": 919143,
    "GEAP": 898162,
    "HAP VIDA": 898284, "Hapvida": 898284, "Hap Vida": 898284, "HapVida": 898284,
    "Inas GDF": 923352, "Inas": 923352,
    "Notre Dame": 921367, "NotreDame": 921367, "Notredame": 921367,
    "PM": 921427, "Polícia Militar": 921427, "Policia Militar": 921427,
    "Porto Seguro": 895650,
    "SUS": 921395,
    "Sul América": 843502, "Sul America": 843502, "SulAmérica": 843502,
    "Unimed": 898838,
    "Outro": 926611,
})

# "MOTIVOS PERDA" (multiselect) — motivo do lead perdido.
FIELD_MOTIVOS_PERDA = (1260434, {
    "Somente Convênio": 926086, "Somente Convenio": 926086,
    "Só Convênio": 926086, "Só com Convênio": 926086,
})

# "NUMERO TELEFONE" (multiselect) — canal por onde o lead fala com a
# clínica. Carimbado pelo agente conforme a porta de entrada da mensagem.
FIELD_NUMERO_TELEFONE = (1260633, {
    "81331005": 926673, "8133": 926673, "8133-1005": 926673,
    "96630710": 926675, "0710": 926675, "9663-0710": 926675,
})

# "ATIVADO IA?" (select) — indica se a IA está conduzindo o lead.
# ATIVADO: a Lia acabou de processar uma mensagem neste lead.
# SOLICITADO: reativação solicitada (handoff humano pendente de reativar).
# DESATIVADO: handoff humano detectado (mensagem manual / pausa de handoff).
# 02/06/2026 — ID renovado: campo foi recriado no Kommo (era 1260635,
# virou 1260817). Nome confirmado: "ATIVADO IA?" type=select, 3 enums.
FIELD_ATIVADO_IA = (1260817, {
    "ATIVADO": 927031, "ATIVA": 927031, "ATIVO": 927031, "ON": 927031,
    "SOLICITADO": 927033, "SOLICITAR": 927033, "PENDENTE": 927033,
    "DESATIVADO": 927035, "DESATIVADA": 927035, "OFF": 927035,
})

# "HORA ATIVAÇÃO" (date_time) — momento em que a IA foi REATIVADA, ou seja,
# voltou a atuar depois de ter estado DESATIVADA (após atendimento humano).
FIELD_HORA_ATIVACAO = 1260639

# "ATENDENTE (s)" (multiselect) — quem está conduzindo o atendimento.
# A Lia carimba "Lia" sempre que a IA processa uma mensagem do lead.
FIELD_ATENDENTE = (1246419, {
    "LIA": 926681, "IA": 926681, "AGENTE": 926681,
})

# Status "Closed - lost" (Venda perdida) — id reservado, vale em qualquer funil.
STATUS_CLOSED_LOST = 143

# Textareas / textos livres
FIELD_NOME_PACIENTE_1 = 1255757


def nome_paciente_pode_ser_gravado(nome_raw: str | None) -> tuple[bool, str]:
    """Decide se um nome de paciente está completo o suficiente pra gravar
    no campo Kommo `N.NOME PACIENTE` (regra 5.2.4 do prompt mestre).

    Retorna (pode_gravar, status_str). Em caso de erro do validador,
    devolve (True, "fallback") — não bloqueia o fluxo principal.

    Origem: bug lead 24048691 (Marcela só primeiro nome). Pluga
    voice_agent.nomes.avaliar_nome_paciente.
    """
    if not nome_raw or not str(nome_raw).strip():
        return False, "vazio"
    try:
        from voice_agent.nomes import NomeStatus, avaliar_nome_paciente
        status = avaliar_nome_paciente(nome_raw)
        if status == NomeStatus.COMPLETO:
            return True, "completo"
        return False, status.value
    except Exception:  # noqa: BLE001
        # Se validador quebrar, NÃO bloqueia (defensivo).
        return True, "fallback"
FIELD_MOTIVO_PACIENTE_1 = 1255727
FIELD_DIA_TURNO_PERIODO = 1259960  # "DIA/TURNO/PERÍODO ⚠️" — preferência textual
FIELD_DIA_CONSULTA_1 = 1255723     # "1.DIA CONSULTA" (date_time) — data/hora confirmada

# Date (timestamp YYYY-MM-DDTHH:MM:SS-03:00)
FIELD_DATA_NASCIMENTO_PACIENTE_1 = 1259984

# ----------------------- camada MULTIPACIENTE (fichas 1 a 6)
# Cada lead pode ter até 6 pacientes (ex.: mãe agendando vários filhos).
# Mapas numerados {n: field_id} para gravar a ficha de cada paciente.
FIELD_NOME_PACIENTES = {
    1: 1255757, 2: 1255761, 3: 1255779,
    4: 1255925, 5: 1257661, 6: 1260332,
}
FIELD_NASC_PACIENTES = {
    1: 1259984, 2: 1255729, 3: 1255787,
    4: 1255927, 5: 1257663, 6: 1260334,
}
FIELD_MOTIVO_PACIENTES = {
    1: 1255727, 2: 1255733, 3: 1255783,
    4: 1255929, 5: 1257665, 6: 1260338,
}
# CPF — necessário para o agendamento no Medware.
FIELD_CPF_PACIENTE_1 = 1260414
# COD-AGENDAMENTO (numeric) — id do agendamento criado no Medware via API.
FIELD_COD_AGENDAMENTO = 1260645
FIELD_CPF_PACIENTES = {
    1: 1260414, 2: 1260416, 3: 1260418,
    4: 1260548, 5: 1260422, 6: 1260424,
}

# ── Novos campos criados 31/05/2026 ──────────────────────────────
# "N.MOTIVO" (multiselect) — Tipo de motivo da consulta padronizado
# (substitui parcialmente o textarea livre 1.MOTIVO CONSULTA).
# 5 opções: Rotina/Check-up, Retorno/Acompanhamento, Pré-operatório,
# Emergência/Urgência, Pós-Operatório.
# Lia preenche automático após classificar o motivo do paciente.
FIELD_MOTIVO_TIPO_PACIENTES: dict[int, tuple[int, dict[str, int]]] = {
    1: (1260719, {
        "Rotina/Check-up": 926733,
        "Retorno/Acompanhamento": 926735,
        "Pré-operatório": 926737,
        "Emergência/Urgência": 926739,
        "Pós-Operatório": 926741,
    }),
    2: (1260723, {
        "Rotina/Check-up": 926753,
        "Retorno/Acompanhamento": 926755,
        "Pré-operatório": 926757,
        "Emergência/Urgência": 926759,
        "Pós-Operatório": 926761,
    }),
    3: (1260727, {
        "Rotina/Check-up": 926773,
        "Retorno/Acompanhamento": 926775,
        "Pré-operatório": 926777,
        "Emergência/Urgência": 926779,
        "Pós-Operatório": 926781,
    }),
    4: (1260731, {
        "Rotina/Check-up": 926793,
        "Retorno/Acompanhamento": 926795,
        "Pré-operatório": 926797,
        "Emergência/Urgência": 926799,
        "Pós-Operatório": 926801,
    }),
    5: (1260735, {
        "Rotina/Check-up": 926813,
        "Retorno/Acompanhamento": 926815,
        "Pré-operatório": 926817,
        "Emergência/Urgência": 926819,
        "Pós-Operatório": 926821,
    }),
    6: (1260739, {
        "Rotina/Check-up": 926833,
        "Retorno/Acompanhamento": 926835,
        "Pré-operatório": 926837,
        "Emergência/Urgência": 926839,
        "Pós-Operatório": 926841,
    }),
}

# "N.EXAMES" (select) — Agrupador de exames vinculado ao agendamento.
# 5 opções: Agrupa1..Agrupa5 (4 automáticos + Personalizado manual).
# Lia preenche automático via selecionar_agrupador() em procedimentos.py.
FIELD_EXAMES_PACIENTES: dict[int, tuple[int, dict[str, int]]] = {
    1: (1260721, {
        "Agrupa1-Adulto Rotina (9 exames)": 926743,
        "Agrupa2-Adulto Emergência (6 exames)": 926745,
        "Agrupa3-Criança Rotina (6 exames)": 926747,
        "Agrupa4-Criança Urgência(5 exames)": 926749,
        "Agrupa5-Personalizado (escolha manual)": 926751,
    }),
    2: (1260725, {
        "Agrupa1-Adulto Rotina (9 exames)": 926763,
        "Agrupa2-Adulto Emergência (6 exames)": 926765,
        "Agrupa3-Criança Rotina (6 exames)": 926767,
        "Agrupa4-Criança Urgência(5 exames)": 926769,
        "Agrupa5-Personalizado (escolha manual)": 926771,
    }),
    3: (1260729, {
        "Agrupa1-Adulto Rotina (9 exames)": 926783,
        "Agrupa2-Adulto Emergência (6 exames)": 926785,
        "Agrupa3-Criança Rotina (6 exames)": 926787,
        "Agrupa4-Criança Urgência(5 exames)": 926789,
        "Agrupa5-Personalizado (escolha manual)": 926791,
    }),
    4: (1260733, {
        "Agrupa1-Adulto Rotina (9 exames)": 926803,
        "Agrupa2-Adulto Emergência (6 exames)": 926805,
        "Agrupa3-Criança Rotina (6 exames)": 926807,
        "Agrupa4-Criança Urgência(5 exames)": 926809,
        "Agrupa5-Personalizado (escolha manual)": 926811,
    }),
    5: (1260737, {
        "Agrupa1-Adulto Rotina (9 exames)": 926823,
        "Agrupa2-Adulto Emergência (6 exames)": 926825,
        "Agrupa3-Criança Rotina (6 exames)": 926827,
        "Agrupa4-Criança Urgência(5 exames)": 926829,
        "Agrupa5-Personalizado (escolha manual)": 926831,
    }),
    6: (1260741, {
        "Agrupa1-Adulto Rotina (9 exames)": 926843,
        "Agrupa2-Adulto Emergência (6 exames)": 926845,
        "Agrupa3-Criança Rotina (6 exames)": 926847,
        "Agrupa4-Criança Urgência(5 exames)": 926849,
        "Agrupa5-Personalizado (escolha manual)": 926851,
    }),
}

# Etapas do funil ATENDE em que o agente fica DESLIGADO — tratamento
# conduzido por humanos ou contato que não é paciente (fornecedor).
#
# Bug C-42 (26/06/2026, Thamilla 23811372): adicionado 5-AGENDADO. Lia
# escrevia respostas incoerentes em lead já agendado (afirmava AMIL não
# credenciado mesmo com convênio Saúde Caixa ativo + consulta 02/07 16:30
# confirmada). Confirmação/lembrete D-1 fica com humano até pipeline_lock
# (#183) e filtros C-42 estarem confirmados em prod.
# ATUALIZADO 30/06/2026 22:30 (Fábio) — política simplificada:
# IA desligada APENAS em 1-ATENDIMENTO HUMANO. Revoga Bug C-42 + C-24a.
# Segurança em runtime é dos filtros ja_agendado (5 camadas) + regras prompt.
ST_AGENT_OFF = frozenset({
    106563343,  # 1-ATENDIMENTO HUMANO — atendente assumiu de propósito
})

# Nomes legíveis das etapas do funil ATENDE (status_id → nome).
ST_NAMES = {
    96441724: "0-ETAPA ENTRADA",
    106563343: "0-ATENDIMENTO HUMANO",
    101508307: "1.LEADS FRIO",
    102560495: "2-AGENDAR",
    106184631: "3.REAGENDAR",
    101507507: "4-AGENDADO",
    101109455: "5-CONFIRMAR OU CONFIRMADO",
    106184983: "5.1-NO-SHOW",
    91486864: "6-REALIZADO CONSULTA",
    106157139: "7-CIRURGIAS ANDAMENTO",
    106484343: "8-LENTES ANDAMENTO",
    106484347: "9-FORNECEDORES",
    106157327: "10-PRÓXIMA CONSULTA",
    142: "Closed - won",
    143: "Closed - lost",
}

# Etapas que significam que o lead JÁ TEM consulta marcada ou realizada —
# a conversa é confirmação/dúvida, NUNCA um novo agendamento do zero.
ST_JA_AGENDADO = frozenset({
    101507507,  # 4-AGENDADO / 5-AGENDADO (renumeração 31/05/2026)
    101109455,  # 5-CONFIRMAR OU CONFIRMADO / 6-CONFIRMAR
    106653499,  # 7.CONFIRMADO (adicionado 01/06/2026, bug Diones 23742328)
    91486864,   # 6-REALIZADO CONSULTA / 8-REALIZADO CONSULTA
    106157327,  # 10-PRÓXIMA CONSULTA
})


def _format_date_iso(iso_yyyymmdd: str) -> Optional[str]:
    """Converte 'YYYY-MM-DD' em 'YYYY-MM-DDT00:00:00-03:00' (BRT)."""
    if not iso_yyyymmdd or len(iso_yyyymmdd) < 10:
        return None
    return f"{iso_yyyymmdd[:10]}T00:00:00-03:00"


# Camada 3 do ja_agendado — detecta agendamento via nota humana
# (Fábio 02/06/2026): atendentes humanos agendam via Medware + nota
# livre, sem disciplinarmente atualizar status_id ou 1.DIA CONSULTA.
# Lia ficava cega e oferecia slot de novo (bug recorrente).
_RE_AGENDOU_HUMANO = re.compile(
    r"\b(agend(?:ei|ou|ado|amento|ada)|"
    r"marqu(?:ei|ou|ado|ada)|"
    r"confirm(?:ei|ou|ado|ada)|"
    r"gravado|grav(?:ei|ou)|"
    r"salv(?:ei|ou)|"
    r"reserv(?:ei|ou|ado|ada))\b",
    re.IGNORECASE,
)
_RE_DATA_FUTURA = re.compile(
    r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"  # dd/mm/aaaa
    r"|(\d{1,2}[hH]\d{0,2})"  # 14h ou 14h30
    r"|(\b(?:segunda|terça|quarta|quinta|sexta|sábado|domingo))",
    re.IGNORECASE,
)


# Camada 4 do ja_agendado — parser do template "Conclusão de Agendamento"
# Blink (Fábio 02/06/2026). Atendente humano envia template estruturado
# via WhatsApp. Não vira nota Kommo, então camadas 1-3 não pegam.
# Esta camada lê histórico de mensagens WhatsApp e detecta o template
# de forma determinística (regex sobre rótulos fixos).
#
# Estrutura do template:
#   ✅ Conclusão de Agendamento.
#   📅 Data e Hora da primeira consulta: DD/MM/AAAA HH:MM
#   👤 Paciente(s): NOME
#   👩‍⚕️Médica: Dra. NOME
#   🩺 Especialidade: NOME
#   📋 Convênio: NOME
#   📍 Unidade: NOME

_RE_TEMPLATE_CONCLUSAO = re.compile(
    r"conclus[ãa]o\s+de\s+agendamento", re.IGNORECASE,
)
_RE_TEMPLATE_DATA_HORA = re.compile(
    r"data\s+e\s+hora[^:]*:\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"  # DD/MM/AAAA
    r"\s+(\d{1,2}[:hH]\d{2})",  # HH:MM
    re.IGNORECASE,
)
_RE_TEMPLATE_PACIENTE = re.compile(
    r"paciente(?:\(s\))?\s*[:：]\s*([^\n\r]+)", re.IGNORECASE,
)
_RE_TEMPLATE_MEDICO = re.compile(
    r"m[ée]dic[oa]\s*[:：]\s*([^\n\r]+)", re.IGNORECASE,
)
_RE_TEMPLATE_ESPECIALIDADE = re.compile(
    r"especialidade\s*[:：]\s*([^\n\r]+)", re.IGNORECASE,
)
_RE_TEMPLATE_CONVENIO = re.compile(
    r"conv[êe]nio\s*[:：]\s*([^\n\r]+)", re.IGNORECASE,
)
_RE_TEMPLATE_UNIDADE = re.compile(
    r"unidade\s*[:：]\s*([^\n\r]+)", re.IGNORECASE,
)


def _limpa_campo_template(s: str) -> str:
    """Tira emojis + asteriscos + espaços extras de um valor do template."""
    if not s:
        return ""
    # Remove emojis comuns no início/meio
    s = re.sub(r"[☀-➿\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF]", "", s)
    s = s.replace("*", "").strip()
    # Remove parênteses de label tipo "(s)"
    s = re.sub(r"\s+", " ", s)
    return s.strip(" :*-")


def detectar_template_conclusao_agendamento(
    texto: str,
) -> Optional[dict]:
    """Camada 4: detecta template "Conclusão de Agendamento" Blink em
    uma mensagem outbound do atendente humano.

    Devolve dict com `{paciente, medico, especialidade, convenio,
    unidade, data, hora, data_iso}` se template detectado e tem pelo
    menos 4 campos preenchidos. None caso contrário.

    Critério mínimo: marca "conclusão de agendamento" + data+hora +
    paciente + médico — esses 4 são obrigatórios.
    """
    if not texto:
        return None
    # 1) marca obrigatória do template
    if not _RE_TEMPLATE_CONCLUSAO.search(texto):
        return None
    # 2) data + hora
    m_dh = _RE_TEMPLATE_DATA_HORA.search(texto)
    if not m_dh:
        return None
    data_raw = m_dh.group(1)
    hora_raw = m_dh.group(2).replace("h", ":").replace("H", ":")
    # Normaliza pra ISO
    try:
        # DD/MM/YYYY ou DD-MM-YYYY ou DD/MM/YY
        parts = re.split(r"[/-]", data_raw)
        dia, mes, ano = int(parts[0]), int(parts[1]), int(parts[2])
        if ano < 100:
            ano += 2000
        h_parts = hora_raw.split(":")
        hh = int(h_parts[0])
        mm = int(h_parts[1]) if len(h_parts) > 1 and h_parts[1] else 0
        # Valida ranges (rejeita 99/99/9999 ou 25h)
        if not (1 <= dia <= 31 and 1 <= mes <= 12
                and 2024 <= ano <= 2030
                and 0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        # datetime parsing real (rejeita 31/02 etc)
        datetime(ano, mes, dia, hh, mm)
        data_iso = f"{ano:04d}-{mes:02d}-{dia:02d}T{hh:02d}:{mm:02d}:00-03:00"
    except (ValueError, IndexError):
        return None
    out = {
        "data": data_raw,
        "hora": hora_raw,
        "data_iso": data_iso,
    }
    # 3) paciente (obrigatório)
    m_pac = _RE_TEMPLATE_PACIENTE.search(texto)
    if not m_pac:
        return None
    out["paciente"] = _limpa_campo_template(m_pac.group(1))
    # 4) médico (obrigatório)
    m_med = _RE_TEMPLATE_MEDICO.search(texto)
    if not m_med:
        return None
    out["medico"] = _limpa_campo_template(m_med.group(1))
    # 5) campos opcionais (mas se faltam, devolve mesmo assim)
    for chave, regex in (
        ("especialidade", _RE_TEMPLATE_ESPECIALIDADE),
        ("convenio", _RE_TEMPLATE_CONVENIO),
        ("unidade", _RE_TEMPLATE_UNIDADE),
    ):
        m = regex.search(texto)
        if m:
            out[chave] = _limpa_campo_template(m.group(1))
    return out


# Camada 5 — detector genérico de conclusão em histórico de mensagens.
# Complementa a camada 4 (template Blink preciso). Quando atendente
# humano improvisa fora do template (ex.: "Stephany: confirmei pra
# 09/06 às 18h com a Karla, paciente OK"), o template não bate mas a
# Lia ainda precisa saber. Camada 5 procura outbound humano +
# palavras-chave de conclusão + data nos últimos N mensagens.
_RE_CONCLUSAO_GENERICA = re.compile(
    r"\b(agend(?:ei|ou|ado|amento)|"
    r"marqu(?:ei|ou|ado|ada)|"
    r"confirm(?:ei|ou|ado|ada)|"
    r"reserv(?:ei|ou|ado|ada)|"
    r"finaliz(?:ei|ou|ado|ada)|"
    r"conclu(?:i|iu|[íi]do))\b",
    re.IGNORECASE,
)


def detectar_conclusao_no_historico(
    mensagens: list[dict], janela_h: int = 72,
) -> tuple[bool, Optional[str]]:
    """Camada 5: varre últimas mensagens (notas + chat) procurando
    outbound humano (created_by != 0) com palavra-chave de conclusão +
    data nas últimas janela_h horas.

    Diferente da camada 3 (nota humana strita), olha QUALQUER mensagem
    cujo autor seja humano — inclui o chat WhatsApp registrado como
    nota tipo message_cashed/outgoing_chat_message.
    """
    if not mensagens:
        return False, None
    agora = datetime.now(timezone.utc)
    for m in mensagens:
        if not isinstance(m, dict):
            continue
        # Humano = created_by não-zero
        if int(m.get("created_by") or 0) == 0:
            continue
        # Janela temporal
        ts_raw = m.get("created_at")
        if ts_raw:
            try:
                d = datetime.fromisoformat(
                    str(ts_raw).replace("Z", "+00:00"),
                )
                if (agora - d).total_seconds() > janela_h * 3600:
                    continue
            except (ValueError, TypeError):
                pass
        texto = (m.get("text") or "").strip()
        if not texto:
            continue
        if (
            _RE_CONCLUSAO_GENERICA.search(texto)
            and _RE_DATA_FUTURA.search(texto)
        ):
            return True, texto[:140].replace("\n", " ")
    return False, None


def _ja_agendado_por_nota_humana(
    notas: list[dict], janela_h: int = 72,
) -> tuple[bool, Optional[str]]:
    """Camada 3 do ja_agendado: parser de notas escritas por humano.

    Se há nota com `created_by != 0` (= usuário Kommo real, não o bot)
    nas últimas `janela_h` horas E o texto contém palavras-chave de
    agendamento (`agendei/marquei/confirmou/gravou/salvei/reservou`)
    E uma data parseável (DD/MM ou dia da semana ou hora) → True.

    Devolve `(eh_agendado, motivo_texto_preview)` pra logging.
    """
    if not notas:
        return False, None
    agora = datetime.now(timezone.utc)
    for n in notas:
        if not isinstance(n, dict):
            continue
        # Bot do voice_agent grava com created_by=0; humanos têm user_id
        if int(n.get("created_by") or 0) == 0:
            continue
        # Janela temporal
        ts_raw = n.get("created_at")
        if ts_raw:
            try:
                d = datetime.fromisoformat(
                    str(ts_raw).replace("Z", "+00:00"),
                )
                if (agora - d).total_seconds() > janela_h * 3600:
                    continue
            except (ValueError, TypeError):
                pass
        texto = (n.get("text") or "").strip()
        if not texto:
            continue
        if (
            _RE_AGENDOU_HUMANO.search(texto)
            and _RE_DATA_FUTURA.search(texto)
        ):
            preview = texto[:140].replace("\n", " ")
            return True, preview
    return False, None


def ler_cf_valor(lead_json: dict, field_id: int) -> Optional[str]:
    """Lê o valor (texto/label) de um custom_field do lead pelo field_id.

    Para campos select/multiselect o Kommo devolve o label em `value`.
    Devolve o 1º valor encontrado como string, ou None se ausente/vazio.
    Função pura — facilita a auditoria (task #82) testar sem rede.
    """
    if not isinstance(lead_json, dict):
        return None
    for cf in (lead_json.get("custom_fields_values") or []):
        if not isinstance(cf, dict):
            continue
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals and isinstance(vals[0], dict):
                v = vals[0].get("value")
                if v is not None and str(v).strip() != "":
                    return str(v)
    return None


def _pick_enum(table: dict[str, int], value: str) -> Optional[int]:
    """Faz match case-insensitive + sem acento na tabela de enum."""
    if not value:
        return None
    import unicodedata
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s.strip())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s.lower()
    target = norm(value)
    for k, v in table.items():
        if norm(k) == target:
            return v
    # Fallback: prefixo
    for k, v in table.items():
        if target.startswith(norm(k)) or norm(k).startswith(target):
            return v
    return None


# Auto-skip blacklist — field_ids que o Kommo rejeitou com NotSupportedChoice
# em algum momento desta execução. Populado em runtime pelo retry inteligente
# em update_lead_fields. Sobrevive entre chamadas (class-level set).
#
# Resolve a classe inteira de bug "campo foi deletado/renomeado no Kommo e o
# código continuou tentando gravar, derrubando o PATCH todo". Em vez de
# abortar boot (drástico), na primeira falha o builder aprende e nas chamadas
# seguintes pula o campo sozinho. Self-healing.
_KOMMO_DEAD_FIELD_IDS: set[int] = set()


@dataclass
class KommoClient:
    subdomain: str
    token: str
    timeout: float = 8.0

    @property
    def _base(self) -> str:
        # FIX 07/06/2026 — IP do Easypanel (2.24.110.21) está em blocklist
        # do Cloudflare/WAF do Kommo: 403 nginx em TODAS chamadas /api/v4.
        # Workaround definitivo: roteamos via Cloudflare Worker proxy
        # (kommo-proxy.oabphi.workers.dev), que faz fetch interno até
        # univeja.kommo.com do IP da Cloudflare (não blocklisted).
        # Worker source: deploy/cloudflare-worker-kommo-proxy.js
        return "https://kommo-proxy.oabphi.workers.dev/api/v4"

    @property
    def _headers(self) -> dict[str, str]:
        # FIX Bug #240 (05/06/2026) — WAF Kommo retornava 403 em /api/v4/leads.
        # FIX 06/06/2026 — IP do Easypanel ficou em greylist do Cloudflare
        # depois de tempo com User-Agent vazio. UA "blink-agent" não basta —
        # Cloudflare bloqueia pela combinação header+IP. Solução: enviar set
        # completo de headers que browser real envia. Identificamos como
        # integração via X-Client-App.
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": f"https://{self.subdomain}.kommo.com/",
            "Origin": f"https://{self.subdomain}.kommo.com",
            "X-Client-App": "blink-agent/1.0 (+https://blinkoftalmologia.com.br)",
        }

    # ----------------------- busca lead por telefone

    def find_lead_id_by_phone(self, phone: str) -> Optional[int]:
        """Busca lead pelo telefone. Retorna o ID do mais recente.

        Tenta variações BR (com/sem o 9 extra) automaticamente.
        """
        if _chaos_ativo_kommo():
            raise TimeoutError("chaos_test_active")
        candidates: list[str] = []
        normalized = (phone or "").replace("+", "").replace(" ", "").replace("-", "")
        if normalized:
            candidates.append(normalized)
            # Variantes BR
            if normalized.startswith("55") and len(normalized) in (12, 13):
                ddd = normalized[2:4]
                rest = normalized[4:]
                if len(normalized) == 13 and rest.startswith("9"):
                    candidates.append("55" + ddd + rest[1:])
                elif len(normalized) == 12:
                    candidates.append("55" + ddd + "9" + rest)
            # Last 8 digits (fallback robusto)
            if len(normalized) >= 8:
                candidates.append(normalized[-8:])

        seen: set[str] = set()
        for q in candidates:
            if q in seen:
                continue
            seen.add(q)
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self._base}/leads",
                        params={"query": q, "limit": 5, "order[updated_at]": "desc"},
                        headers=self._headers,
                    )
                if r.status_code == 204:
                    continue
                if r.status_code != 200:
                    log.warning("Kommo find_lead failed (q=%s): HTTP %d", q, r.status_code)
                    continue
                data = r.json() or {}
                leads = ((data.get("_embedded") or {}).get("leads") or [])
                if leads:
                    return int(leads[0]["id"])
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo find_lead error (q=%s): %s", q, e)
        return None

    # ----------------------- update lead

    def patch_custom_fields_raw(
        self, lead_id: int, cfs: list[dict],
    ) -> tuple[bool, dict]:
        """PATCH direto /api/v4/leads/{id} com custom_fields_values pré-formatados.

        Bypass de wrapper-mentiroso (Bug C-12, 05/06/2026): MCP/wrappers anteriores
        retornavam success:true mas NÃO gravavam custom_fields_values. Esta função:
        1. PATCH com payload exato (sem mapeamento semântico)
        2. GET imediato e CONFERE que os field_ids esperados estão presentes
        3. Retorna (ok_real, response_body) — NÃO mente

        `cfs` formato: [{"field_id": int, "values": [{"value": ..., "enum_id": opcional}]}]
        """
        payload = {"custom_fields_values": cfs}
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json=payload, headers=self._headers,
                )
                body: dict = {}
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    body = {"raw": (r.text or "")[:500]}
                ok_2xx = r.status_code // 100 == 2
                if not ok_2xx:
                    log.warning(
                        "[patch_cfs] HTTP %d lead=%s body=%r",
                        r.status_code, lead_id, body,
                    )
                    return (False, {"status": r.status_code, **body})
                # Validação real: GET imediato e confere field_ids
                g = c.get(
                    f"{self._base}/leads/{lead_id}",
                    headers=self._headers,
                )
                if g.status_code != 200:
                    log.warning(
                        "[patch_cfs] GET pós-PATCH falhou %d lead=%s",
                        g.status_code, lead_id,
                    )
                    return (True, body)  # PATCH 2xx, GET falhou → confia no PATCH
                got_cfs = (g.json() or {}).get("custom_fields_values") or []
                got_ids = {cf.get("field_id") for cf in got_cfs}
                expected = {c.get("field_id") for c in cfs}
                missing = expected - got_ids
                if missing:
                    log.error(
                        "[C-12] PATCH 2xx mas campos %s NÃO gravados! lead=%s",
                        missing, lead_id,
                    )
                    return (False, {"bug": "C-12", "missing": list(missing), **body})
                return (True, body)
        except Exception as e:  # noqa: BLE001
            log.exception("[patch_cfs] crash lead=%s: %s", lead_id, e)
            return (False, {"error": str(e)[:200]})

    def update_lead_fields(self, lead_id: int, fields: dict) -> bool:
        """Atualiza custom_fields_values do lead.

        `fields` é um dict {nome_semântico: valor} com chaves:
          name, birth_date_iso (YYYY-MM-DD), reason,
          convenio, unidade, medico, especialidade, tipo_agendamento,
          perfil_paciente, num_pacientes, dia_turno_periodo
        """
        cfs: list[dict[str, Any]] = []

        def add_text(field_id: int, val: Optional[str]):
            if val:
                cfs.append({"field_id": field_id, "values": [{"value": val}]})

        def add_select(field_def: tuple[int, dict], val: Optional[str]):
            if not val:
                return
            field_id, table = field_def
            enum_id = _pick_enum(table, val)
            if enum_id is None:
                log.warning("Kommo: valor '%s' não casa com enum do campo %d", val, field_id)
                return
            cfs.append({"field_id": field_id, "values": [{"enum_id": enum_id}]})

        def add_date(field_id: int, val: Optional[str]):
            iso = _format_date_iso(val) if val else None
            if iso:
                cfs.append({"field_id": field_id, "values": [{"value": iso}]})

        def add_datetime(field_id: int, ts: Optional[int]):
            """Campo date_time do Kommo — valor é timestamp Unix (segundos)."""
            if ts:
                cfs.append(
                    {"field_id": field_id, "values": [{"value": int(ts)}]}
                )

        # ── Fichas dos pacientes (camada multipaciente) ──────────────
        # Se a extração trouxe a lista `pacientes`, grava a ficha de cada
        # um nos campos numerados 1..6 (nome, nascimento, motivo, CPF).
        # Senão, usa os campos simples (compatibilidade — paciente único).
        def _digits(v: Any) -> str:
            return "".join(ch for ch in str(v or "") if ch.isdigit())

        # Validação de nome paciente (task 31/05/2026) — só grava se completo.
        # nome_paciente_pode_ser_gravado() é função pública (módulo nível),
        # pra ser testável sem entrar em update_lead_fields.
        def _gravar_nome_paciente_se_completo(field_id: int, nome_raw: str | None) -> None:
            ok, status_str = nome_paciente_pode_ser_gravado(nome_raw)
            if not ok:
                log.warning(
                    "[KOMMO] nome paciente NÃO gravado — %s: %r",
                    status_str, nome_raw,
                )
                return
            add_text(field_id, nome_raw)

        pacientes = fields.get("pacientes")
        if isinstance(pacientes, list) and pacientes:
            for idx, p in enumerate(pacientes[:6], start=1):
                if not isinstance(p, dict):
                    continue
                _gravar_nome_paciente_se_completo(
                    FIELD_NOME_PACIENTES[idx],
                    p.get("nome") or p.get("name"),
                )
                add_date(FIELD_NASC_PACIENTES[idx], p.get("birth_date_iso"))
                add_text(FIELD_MOTIVO_PACIENTES[idx],
                         p.get("reason") or p.get("motivo"))
                add_text(FIELD_CPF_PACIENTES[idx],
                         _digits(p.get("cpf")) or None)
                # Novos campos N.MOTIVO (tipo enum) e N.EXAMES (agrupador)
                # Lia preenche automático após selecionar_agrupador().
                _motivo_field = FIELD_MOTIVO_TIPO_PACIENTES.get(idx)
                if _motivo_field:
                    add_select(
                        _motivo_field,
                        p.get("motivo_tipo") or p.get("tipo_motivo"),
                    )
                _exames_field = FIELD_EXAMES_PACIENTES.get(idx)
                if _exames_field:
                    add_select(
                        _exames_field,
                        p.get("agrupador_label") or p.get("agrupador"),
                    )
            # nº de pacientes — rede de segurança se a extração não trouxe
            fields.setdefault("num_pacientes", str(min(len(pacientes), 10)))
        else:
            _gravar_nome_paciente_se_completo(
                FIELD_NOME_PACIENTE_1, fields.get("name"),
            )
            add_text(FIELD_MOTIVO_PACIENTE_1, fields.get("reason"))
            add_text(FIELD_CPF_PACIENTE_1, _digits(fields.get("cpf")) or None)
            add_date(FIELD_DATA_NASCIMENTO_PACIENTE_1,
                     fields.get("birth_date_iso"))
        add_text(FIELD_DIA_TURNO_PERIODO, fields.get("dia_turno_periodo"))
        add_select(FIELD_CONVENIO, fields.get("convenio"))
        add_select(FIELD_UNIDADE, fields.get("unidade"))
        add_select(FIELD_MEDICOS, fields.get("medico"))
        add_select(FIELD_ESPECIALIDADE, fields.get("especialidade"))
        # FIELD_TIPO_AGENDAMENTO desativado — campo 1260438 não existe no Kommo
        # e derrubava o PATCH inteiro com HTTP 400.
        add_select(FIELD_PERFIL_PACIENTE_1, fields.get("perfil_paciente"))
        add_select(FIELD_NUMERO_PACIENTES, fields.get("num_pacientes"))
        # AÇÕES — só é gravado quando o atendimento virou encaixe/domiciliar.
        add_select(FIELD_ACOES, fields.get("acoes"))
        # Ñ ACEITO CONVÊNIO — convênio que o paciente queria e a clínica
        # não credencia (preenchido quando o lead insiste nesse convênio).
        add_select(FIELD_NAO_ACEITO_CONVENIO, fields.get("nao_aceito_convenio"))
        # MOTIVOS PERDA — motivo do lead perdido (ex.: "Somente Convênio").
        add_select(FIELD_MOTIVOS_PERDA, fields.get("motivo_perda"))
        # NUMERO TELEFONE — canal de entrada do lead (8133 ou 0710).
        add_select(FIELD_NUMERO_TELEFONE, fields.get("numero_telefone"))
        # ATIVADO IA? — estado da IA no lead (ATIVADO / DESATIVADO).
        # Se o field_id estiver órfão, o auto-skip vai blacklistar em runtime.
        add_select(FIELD_ATIVADO_IA, fields.get("ativado_ia"))
        # HORA ATIVAÇÃO — timestamp de quando a IA voltou a atuar.
        # Se o field_id estiver órfão, o auto-skip blacklista em runtime.
        add_datetime(FIELD_HORA_ATIVACAO, fields.get("hora_ativacao_ts"))
        # ATENDENTE — carimba "Lia" quando a IA conduz o atendimento.
        # Se o enum estiver inválido, auto-skip blacklista em runtime.
        add_select(FIELD_ATENDENTE, fields.get("atendente"))
        # ── Campos de acompanhamento (task #231, 05/06/2026) ─────────────
        # Visíveis na lista do funil ATENDE pra equipe humana enxergar
        # o estado de cada lead sem abrir cada card.
        from voice_agent.campos_acompanhamento import (
            FIELD_STATUS_CONVERSA as _FIELD_STATUS_CONVERSA,
            FIELD_ULTIMA_MSG_OUTBOUND as _FIELD_ULTIMA_MSG_OUTBOUND,
            FIELD_PROXIMA_ACAO as _FIELD_PROXIMA_ACAO,
            FIELD_TS_ULTIMA_MSG_LIA as _FIELD_TS_LIA,
            FIELD_TS_ULTIMA_MSG_HUMANO as _FIELD_TS_HUMANO,
        )
        add_select(_FIELD_STATUS_CONVERSA, fields.get("status_conversa"))
        add_select(_FIELD_PROXIMA_ACAO, fields.get("proxima_acao"))
        add_text(_FIELD_ULTIMA_MSG_OUTBOUND, fields.get("ultima_msg_outbound"))
        # 2 timestamps separados — LIA vs HUMANO. Pipeline carimba LIA.
        # Webhook Kommo Automation carimba HUMANO.
        if _FIELD_TS_LIA:
            add_datetime(_FIELD_TS_LIA, fields.get("ts_ultima_msg_lia"))
            # compat com chave antiga "ts_ultima_msg_enviada"
            add_datetime(
                _FIELD_TS_LIA, fields.get("ts_ultima_msg_enviada"),
            )
        if _FIELD_TS_HUMANO:
            add_datetime(
                _FIELD_TS_HUMANO, fields.get("ts_ultima_msg_humano"),
            )
        # COD-AGENDAMENTO — preenchido apos gravar consulta no Medware via API.
        cod_ag = fields.get("cod_agendamento")
        if cod_ag:
            try:
                cfs.append({"field_id": FIELD_COD_AGENDAMENTO, "values": [{"value": int(cod_ag)}]})
            except (TypeError, ValueError):
                log.warning("cod_agendamento nao numerico: %s", cod_ag)

        # ── Observabilidade de templates Meta (task #379) ───────────────
        # Field_ids descobertos via list_custom_fields() na 1ª chamada
        # (cache em templates_observabilidade). Campos: ULTIMO TEMPLATE META,
        # TEMPLATES JÁ RECEBIDOS, CATEGORIA TEMPLATE, DATA ÚLTIMO DISPARO META,
        # STATUS ÚLTIMO DISPARO.
        _tobs_keys = (
            "ultimo_template_meta", "templates_ja_recebidos",
            "categoria_template", "data_ultimo_disparo_meta_ts",
            "status_ultimo_disparo",
        )
        if any(fields.get(k) is not None for k in _tobs_keys):
            try:
                from voice_agent.templates_observabilidade import (
                    descobrir_field_ids as _tobs_descobrir,
                    CAMPO_TO_KOMMO_KEY as _TOBS_MAP,
                )
                _tobs_fids = _tobs_descobrir(self)
                # ULTIMO TEMPLATE META (select por NOME do template)
                if (_v := fields.get("ultimo_template_meta")):
                    fid = _tobs_fids.get("ULTIMO TEMPLATE META")
                    if fid:
                        cfs.append({
                            "field_id": fid,
                            "values": [{"value": str(_v)}],
                        })
                # TEMPLATES JÁ RECEBIDOS (multiselect — best-effort 1 valor)
                if (_v := fields.get("templates_ja_recebidos")):
                    fid = _tobs_fids.get("TEMPLATES JÁ RECEBIDOS")
                    if fid:
                        cfs.append({
                            "field_id": fid,
                            "values": [{"value": str(_v)}],
                        })
                # CATEGORIA TEMPLATE (select)
                if (_v := fields.get("categoria_template")):
                    fid = _tobs_fids.get("CATEGORIA TEMPLATE")
                    if fid:
                        cfs.append({
                            "field_id": fid,
                            "values": [{"value": str(_v)}],
                        })
                # DATA ÚLTIMO DISPARO META (date_time)
                if (_v := fields.get("data_ultimo_disparo_meta_ts")):
                    fid = _tobs_fids.get("DATA ÚLTIMO DISPARO META")
                    if fid:
                        try:
                            cfs.append({
                                "field_id": fid,
                                "values": [{"value": int(_v)}],
                            })
                        except (TypeError, ValueError):
                            log.warning(
                                "templates_obs: data_ultimo_disparo_meta_ts"
                                " nao numerico: %r", _v,
                            )
                # STATUS ÚLTIMO DISPARO (select)
                if (_v := fields.get("status_ultimo_disparo")):
                    fid = _tobs_fids.get("STATUS ÚLTIMO DISPARO")
                    if fid:
                        cfs.append({
                            "field_id": fid,
                            "values": [{"value": str(_v)}],
                        })
            except Exception as _exc:  # noqa: BLE001
                log.warning("templates_obs: %s", _exc)

        # Auto-skip campos que o Kommo já rejeitou anteriormente neste runtime.
        cfs = [c for c in cfs if c.get("field_id") not in _KOMMO_DEAD_FIELD_IDS]

        if not cfs:
            return True

        payload = {"custom_fields_values": cfs}
        # Retry com auto-skip: se o Kommo rejeitar um campo com
        # NotSupportedChoice, identificamos qual, marcamos como morto e
        # tentamos de novo sem ele. Máximo 4 retries pra cobrir até 4
        # campos órfãos sem precisar reboot.
        for tentativa in range(5):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.patch(
                        f"{self._base}/leads/{lead_id}",
                        json=payload,
                        headers=self._headers,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo update error: %s", e)
                return False

            if r.status_code // 100 == 2:
                log.info(
                    "Kommo lead %d atualizado: %d campos (tentativa %d)",
                    lead_id, len(cfs), tentativa + 1,
                )
                return True

            # HTTP 400 — tenta extrair qual position do array foi rejeitada
            # e auto-blacklist o field_id correspondente.
            removeu = False
            if r.status_code == 400:
                try:
                    err = r.json() or {}
                    for ve in (err.get("validation-errors") or []):
                        for it in (ve.get("errors") or []):
                            if it.get("code") != "NotSupportedChoice":
                                continue
                            path = it.get("path") or ""
                            # path = "custom_fields_values.11.field_id"
                            parts = path.split(".")
                            if len(parts) >= 2 and parts[1].isdigit():
                                idx = int(parts[1])
                                if 0 <= idx < len(cfs):
                                    bad_fid = cfs[idx].get("field_id")
                                    if bad_fid:
                                        _KOMMO_DEAD_FIELD_IDS.add(int(bad_fid))
                                        log.warning(
                                            "Kommo: field_id %s órfão "
                                            "(deletado/enum inválido). "
                                            "Blacklist + retry sem ele.",
                                            bad_fid,
                                        )
                                        cfs.pop(idx)
                                        payload = {
                                            "custom_fields_values": cfs
                                        }
                                        removeu = True
                                        break
                        if removeu:
                            break
                except Exception:  # noqa: BLE001
                    pass
            if not removeu:
                log.warning(
                    "Kommo update lead %d falhou (tentativa %d): HTTP %d — %s",
                    lead_id, tentativa + 1, r.status_code, (r.text or "")[:300],
                )
                return False
            if not cfs:
                return True
        return False

    def update_leads_field_batch(
        self, field_def: tuple[int, dict], pairs: list[tuple[int, str]],
    ) -> dict:
        """Atualiza UM campo select em vários leads de uma vez (PATCH em lote).

        O Kommo aceita PATCH /leads com um array de leads (até 250 por
        requisição) — muito mais rápido que um PATCH por lead.

        `pairs` = lista de (lead_id, valor_textual). Retorna
        {ok, fail} com a contagem de leads atualizados.
        """
        field_id, table = field_def
        ok = 0
        fail = 0
        chunk = 250
        for i in range(0, len(pairs), chunk):
            bloco = pairs[i:i + chunk]
            body: list[dict] = []
            for lead_id, val in bloco:
                enum_id = _pick_enum(table, val)
                if enum_id is None:
                    fail += 1
                    continue
                body.append({
                    "id": int(lead_id),
                    "custom_fields_values": [
                        {"field_id": field_id, "values": [{"enum_id": enum_id}]},
                    ],
                })
            if not body:
                continue
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.patch(
                        f"{self._base}/leads", json=body, headers=self._headers,
                    )
                if r.status_code // 100 == 2:
                    ok += len(body)
                else:
                    fail += len(body)
                    log.warning(
                        "Kommo batch update falhou: HTTP %d — %s",
                        r.status_code, (r.text or "")[:300],
                    )
            except Exception as e:  # noqa: BLE001
                fail += len(body)
                log.warning("Kommo batch update error: %s", e)
            # Controle de ritmo — respeita o rate limit do Kommo.
            time.sleep(0.5)
        return {"ok": ok, "fail": fail}

    # ----------------------- nota (registro da conversa)

    def list_custom_fields(self, entity: str = "leads") -> list[dict]:
        """Lista todos os custom_fields da entidade (leads, contacts, companies).

        Retorna lista de {id, name, type, code, enums} ou [] em erro.
        Adicionado em 04/06/2026 (task #216).
        """
        try:
            results: list[dict] = []
            page = 1
            with httpx.Client(timeout=self.timeout) as c:
                while True:
                    r = c.get(
                        f"{self._base}/{entity}/custom_fields",
                        params={"limit": 250, "page": page},
                        headers=self._headers,
                    )
                    if r.status_code == 204:
                        break
                    if r.status_code != 200:
                        log.warning(
                            "Kommo list_custom_fields %s p%d: HTTP %d",
                            entity, page, r.status_code,
                        )
                        break
                    j = r.json() or {}
                    items = (j.get("_embedded") or {}).get("custom_fields") or []
                    results.extend(items)
                    if not items or len(items) < 250:
                        break
                    page += 1
            return results
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo list_custom_fields exception: %s", e)
            return []

    def create_custom_field(
        self,
        name: str,
        field_type: str,
        entity: str = "leads",
        code: Optional[str] = None,
        enums: Optional[list[str]] = None,
        group_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Cria 1 custom field via API Kommo.

        field_type: 'text', 'textarea', 'select', 'multiselect', 'date',
                    'date_time', 'numeric', 'checkbox', 'url'.
        enums: lista de strings (só pra select/multiselect).
        Retorna {id, name, type, enums} ou None em erro.

        Adicionado em 04/06/2026 (task #216).
        """
        payload_item: dict[str, Any] = {"name": name, "type": field_type}
        if code:
            payload_item["code"] = code
        if group_id:
            payload_item["group_id"] = group_id
        if enums and field_type in ("select", "multiselect"):
            payload_item["enums"] = [
                {"value": v, "sort": i + 1} for i, v in enumerate(enums)
            ]
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(
                    f"{self._base}/{entity}/custom_fields",
                    json=[payload_item],
                    headers=self._headers,
                )
            if r.status_code // 100 != 2:
                log.error(
                    "Kommo create_custom_field '%s' falhou HTTP %d: %s",
                    name, r.status_code, (r.text or "")[:400],
                )
                return None
            j = r.json() or {}
            items = (j.get("_embedded") or {}).get("custom_fields") or []
            if items:
                log.info("Kommo campo '%s' criado id=%s", name, items[0].get("id"))
                return items[0]
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo create_custom_field '%s' erro: %s", name, e)
            return None

    def ensure_custom_field(
        self,
        name: str,
        field_type: str,
        entity: str = "leads",
        enums: Optional[list[str]] = None,
        code: Optional[str] = None,
    ) -> dict:
        """Cria campo se não existir. Idempotente.

        Retorna {action: "created"|"exists", field: {...}}.
        """
        existing = self.list_custom_fields(entity=entity)
        for f in existing:
            if (f.get("name") or "").strip().lower() == name.strip().lower():
                return {"action": "exists", "field": f}
        created = self.create_custom_field(
            name=name, field_type=field_type,
            entity=entity, code=code, enums=enums,
        )
        if created:
            return {"action": "created", "field": created}
        return {"action": "failed", "field": None}

    def add_note(self, lead_id: int, text: str) -> bool:
        """Adiciona uma nota de texto ('common') na linha do tempo do lead.

        Usado para registrar as trocas de mensagem do agente — assim a
        equipe acompanha o andamento no Kommo, mesmo nos canais que não
        passam pelo chat nativo (8133 via API oficial, 0710 via Evolution).
        """
        if not text:
            return False
        payload = [{"note_type": "common", "params": {"text": text[:5000]}}]
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(
                    f"{self._base}/leads/{lead_id}/notes",
                    json=payload,
                    headers=self._headers,
                )
            if r.status_code // 100 == 2:
                log.info("Kommo nota gravada no lead %d", lead_id)
                return True
            log.warning(
                "Kommo add_note lead %d falhou: HTTP %d — %s",
                lead_id, r.status_code, (r.text or "")[:300],
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo add_note error: %s", e)
        return False

    # ----------------------- enriquecimento de contexto (onboarding)

    def get_caller_context(self, phone: str) -> dict:
        """Onboarding por telefone: busca o lead e o que o CRM já sabe.

        Usado no caminho Evolution (0710). Retorna:
        {found, lead_id, name, known:{campo:valor}}
        """
        lead_id = self.find_lead_id_by_phone(phone)
        if not lead_id:
            return {"found": False, "lead_id": None, "name": None, "known": {}}
        return self.get_caller_context_by_lead(lead_id)

    # ----------------------- reativação de leads frios

    def list_leads_by_status(
        self, pipeline_id: int, status_ids: list[int], limit: int = 200,
        page: int = 1,
    ) -> list[dict]:
        """Lista leads de um pipeline que estejam em qualquer uma das etapas
        informadas. Ordenado por updated_at asc (mais parados primeiro).

        Usa a API REST direta do Kommo (filter[statuses]) — diferente da
        busca textual, aqui o filtro por etapa funciona de fato.
        `page` permite paginar (Kommo entrega no máximo 250 por página).
        """
        params: dict[str, Any] = {
            "limit": min(int(limit), 250),
            "page": max(int(page), 1),
            "order[updated_at]": "asc",
        }
        for i, sid in enumerate(status_ids):
            params[f"filter[statuses][{i}][pipeline_id]"] = pipeline_id
            params[f"filter[statuses][{i}][status_id]"] = sid
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self._base}/leads", params=params, headers=self._headers)
            # Bug C-10 (05/06/2026): endpoints admin estavam retornando 0
            # leads em prod silenciosamente. Logging detalhado pra diagnose.
            if r.status_code == 204:
                log.info(
                    "[KOMMO list_leads_by_status] HTTP 204 (vazio) — "
                    "pipeline=%s status_ids=%s page=%s — etapa REALMENTE vazia",
                    pipeline_id, status_ids, page,
                )
                return []
            if r.status_code != 200:
                log.warning(
                    "[KOMMO list_leads_by_status] HTTP %d — pipeline=%s "
                    "status_ids=%s body=%r",
                    r.status_code, pipeline_id, status_ids,
                    (r.text or "")[:500],
                )
                return []
            data = r.json() or {}
            leads_raw = ((data.get("_embedded") or {}).get("leads") or [])
            log.info(
                "[KOMMO list_leads_by_status] OK — pipeline=%s status_ids=%s "
                "page=%s leads_count=%d",
                pipeline_id, status_ids, page, len(leads_raw),
            )
            return [
                {"id": ld["id"], "name": ld.get("name"),
                 "status_id": ld.get("status_id")}
                for ld in leads_raw
            ]
        except Exception as e:  # noqa: BLE001
            log.exception(
                "[KOMMO list_leads_by_status] EXCEPTION pipeline=%s "
                "status_ids=%s erro=%s",
                pipeline_id, status_ids, e,
            )
            return []

    def list_leads_recent(self, limit: int = 250, page: int = 1) -> list[dict]:
        """Lista leads ordenados pela atividade MAIS RECENTE primeiro
        (updated_at desc), com paginação.

        Usado pelo disparo de unificação: avisa primeiro quem teve
        contato mais recente (hoje, ontem) e vai descendo na base.
        """
        params: dict[str, Any] = {
            "limit": min(int(limit), 250),
            "page": max(int(page), 1),
            "order[updated_at]": "desc",
        }
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self._base}/leads", params=params, headers=self._headers)
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                log.warning("Kommo list_leads_recent: HTTP %d", r.status_code)
                return []
            data = r.json() or {}
            return [
                {"id": ld["id"], "name": ld.get("name"),
                 "status_id": ld.get("status_id"),
                 "updated_at": ld.get("updated_at")}
                for ld in ((data.get("_embedded") or {}).get("leads") or [])
            ]
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo list_leads_recent erro: %s", e)
            return []

    def get_lead_main_phone(self, lead_id: int | str) -> Optional[str]:
        """Retorna o telefone (só dígitos) do contato principal do lead."""
        info = self.get_lead_main_contact(lead_id) or {}
        return info.get("telefone") or None

    def get_lead_main_contact(self, lead_id: int | str) -> Optional[dict]:
        """Retorna {telefone, nome, status_id} do contato principal do lead.

        Usado por /admin/disparar-lead pra dispensar inputs manuais.
        Adicionado em 04/06/2026 (task #212).
        """
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}",
                    params={"with": "contacts"}, headers=self._headers,
                )
                if r.status_code != 200:
                    return None
                lead_data = r.json() or {}
                status_id = lead_data.get("status_id")
                contacts = (
                    (lead_data.get("_embedded") or {}).get("contacts") or []
                )
                if not contacts:
                    return None
                main = next(
                    (ct for ct in contacts if ct.get("is_main")), contacts[0]
                )
                cid = main.get("id")
                if not cid:
                    return None
                r2 = c.get(f"{self._base}/contacts/{cid}", headers=self._headers)
                if r2.status_code != 200:
                    return None
                contact_data = r2.json() or {}
                nome = (contact_data.get("name") or "").strip()
                telefone = None
                for cf in (contact_data.get("custom_fields_values") or []):
                    if cf.get("field_code") == "PHONE":
                        vals = cf.get("values") or []
                        if vals and vals[0].get("value"):
                            telefone = "".join(
                                ch for ch in str(vals[0]["value"]) if ch.isdigit()
                            ) or None
                            break
                return {
                    "telefone": telefone,
                    "nome": nome,
                    "status_id": status_id,
                }
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_lead_main_contact erro (lead %s): %s", lead_id, e)
        return None

    def get_lead_notes(
        self, lead_id: int | str, limit: int = 50,
    ) -> list[dict]:
        """Lista notas do lead, ordem cronológica (mais antigas primeiro).

        Usado pela camada 3 do ja_agendado (parser de notas humanas).
        Devolve lista de dicts {id, created_at, created_by, text, ...}
        ou [] em erro.
        """
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}/notes",
                    params={
                        "limit": min(int(limit), 250),
                        "order[created_at]": "desc",
                    },
                    headers=self._headers,
                )
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                log.warning(
                    "Kommo get_lead_notes %s: HTTP %d",
                    lead_id, r.status_code,
                )
                return []
            data = r.json() or {}
            return list(((data.get("_embedded") or {}).get("notes") or []))
        except Exception as e:  # noqa: BLE001
            log.warning(
                "Kommo get_lead_notes erro (lead %s): %s", lead_id, e,
            )
            return []

    def search_leads_by_window(
        self,
        pipeline_id: int,
        ts_from: int,
        ts_to: int,
        limit: int = 250,
    ) -> list[dict]:
        """Lista leads do pipeline criados dentro da janela [ts_from, ts_to].

        Usado pelo Lia Engineer Eval Loop pra coletar métricas de funil.

        Args:
            pipeline_id: ATENDE = 8601819.
            ts_from: epoch UTC inicial.
            ts_to: epoch UTC final.
            limit: máx por página.

        Returns:
            Lista de dicts de lead com custom_fields_values populado.
            Pagina automaticamente até 1500 leads (5 páginas). Retorna []
            em erro.
        """
        try:
            out: list[dict] = []
            for page in range(1, 7):
                params = {
                    "filter[pipeline_id]": int(pipeline_id),
                    "filter[created_at][from]": int(ts_from),
                    "filter[created_at][to]": int(ts_to),
                    "limit": min(int(limit), 250),
                    "page": page,
                }
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self._base}/leads",
                        params=params,
                        headers=self._headers,
                    )
                if r.status_code == 204:
                    break
                if r.status_code != 200:
                    log.warning(
                        "Kommo search_leads_by_window p%d: HTTP %d",
                        page, r.status_code,
                    )
                    break
                data = r.json() or {}
                page_leads = list(((data.get("_embedded") or {}).get("leads") or []))
                if not page_leads:
                    break
                out.extend(page_leads)
                if len(page_leads) < params["limit"]:
                    break
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo search_leads_by_window erro: %s", e)
            return []

    def search_leads_by_query(
        self,
        query: str,
        pipeline_id: int | None = 8601819,
        limit: int = 50,
    ) -> list[dict]:
        """Busca leads via query texto (matching nome, contato, telefone, etc).

        Origem: Bug C-27 Fábio 12/06/2026 — endpoint dedup-merge-por-telefone
        precisava buscar todos leads do mesmo telefone, mas o método existente
        `search_leads_by_window` filtra por created_at. Este aceita texto livre.

        Args:
            query: texto a buscar (nome paciente, telefone com ou sem DDI, etc).
            pipeline_id: filtra dentro do pipeline ATENDE (8601819). None = all.
            limit: máx leads por página.

        Returns:
            Lista de dicts de lead, vazia em erro.
        """
        if not query:
            return []
        try:
            out: list[dict] = []
            for page in range(1, 5):  # max 4 páginas = 200 leads
                params: dict = {
                    "query": str(query),
                    "limit": min(int(limit), 50),
                    "page": page,
                }
                if pipeline_id:
                    params["filter[pipeline_id]"] = int(pipeline_id)
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self._base}/leads",
                        params=params,
                        headers=self._headers,
                    )
                if r.status_code == 204:
                    break
                if r.status_code != 200:
                    log.warning(
                        "Kommo search_leads_by_query p%d: HTTP %d",
                        page, r.status_code,
                    )
                    break
                data = r.json() or {}
                page_leads = list(
                    ((data.get("_embedded") or {}).get("leads") or []),
                )
                if not page_leads:
                    break
                out.extend(page_leads)
                if len(page_leads) < params["limit"]:
                    break
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo search_leads_by_query erro: %s", e)
            return []

    def search_contacts_by_query(
        self, query: str, limit: int = 50,
    ) -> list[dict]:
        """Busca contatos no Kommo via query (telefone, email, nome).

        Origem: Bug C-27 Fábio 12/06/2026 — dedup-merge precisa achar
        TODOS os leads do mesmo telefone. Kommo armazena telefone no
        /contacts não em /leads. Padrão: busca contato → pega contact_id
        → busca leads vinculados a esse contato.

        Args:
            query: telefone (com ou sem DDI), email, ou nome.
            limit: máx contatos por página.

        Returns:
            Lista de dicts de contato com `_embedded.leads`, ou [] em erro.
        """
        if not query:
            return []
        try:
            out: list[dict] = []
            for page in range(1, 4):
                params = {
                    "query": str(query),
                    "limit": min(int(limit), 50),
                    "page": page,
                    "with": "leads",
                }
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self._base}/contacts",
                        params=params,
                        headers=self._headers,
                    )
                if r.status_code == 204:
                    break
                if r.status_code != 200:
                    log.warning(
                        "Kommo search_contacts_by_query p%d: HTTP %d",
                        page, r.status_code,
                    )
                    break
                data = r.json() or {}
                page_contacts = list(
                    ((data.get("_embedded") or {}).get("contacts") or []),
                )
                if not page_contacts:
                    break
                out.extend(page_contacts)
                if len(page_contacts) < params["limit"]:
                    break
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo search_contacts_by_query erro: %s", e)
            return []

    def get_leads_by_phone(
        self, telefone: str, pipeline_id: int | None = 8601819,
    ) -> list[dict]:
        """Pipeline pronto: busca leads de um telefone via /contacts.

        1. Busca contatos que casam o telefone.
        2. Coleta lead_ids vinculados.
        3. Busca cada lead via GET /leads/{id} pra ter dados completos.

        Args:
            telefone: E.164 ou local. Normaliza removendo +, espaços, parenteses.
            pipeline_id: filtra leads desse pipeline (ATENDE = 8601819).

        Returns:
            Lista de leads (dicts), vazia em erro.
        """
        if not telefone:
            return []
        # Normaliza: só dígitos
        import re as _re
        tel_norm = _re.sub(r"\D", "", str(telefone))
        if not tel_norm:
            return []

        # Busca por DDI completo + sem DDI (paciente pode ter cadastrado de várias formas)
        queries_tentativa = [tel_norm]
        if tel_norm.startswith("55") and len(tel_norm) >= 12:
            queries_tentativa.append(tel_norm[2:])  # sem 55

        leads_seen: set[int] = set()
        out: list[dict] = []
        for q in queries_tentativa:
            contatos = self.search_contacts_by_query(q) or []
            for c in contatos:
                if not isinstance(c, dict):
                    continue
                embedded_leads = (
                    (c.get("_embedded") or {}).get("leads") or []
                )
                for ld in embedded_leads:
                    lid = ld.get("id") if isinstance(ld, dict) else None
                    if not lid or int(lid) in leads_seen:
                        continue
                    # Busca lead completo
                    try:
                        lead_full = self.get_lead(lid)
                    except Exception:  # noqa: BLE001
                        lead_full = None
                    if not lead_full:
                        continue
                    if pipeline_id and lead_full.get("pipeline_id") != int(pipeline_id):
                        continue
                    leads_seen.add(int(lid))
                    out.append(lead_full)
        return out

    def list_recent_notes(
        self,
        since: datetime,
        author_user_id: int | None = 0,
        limit: int = 250,
        note_type: str | None = "common",
    ) -> list[dict]:
        """Lista notas globais Kommo desde `since` (UTC), opcionalmente
        filtradas por autor e tipo. Usado pelo Lia Engineer Autônomo pra
        detectar bugs em produção em tempo quase real.

        Args:
            since: timestamp UTC inicial.
            author_user_id: 0 = bot/automação (Lia). None = qualquer.
            limit: máx 250 (limite Kommo API).
            note_type: "common" / "incoming_chat_message" / etc. None = todos.

        Returns:
            Lista de dicts, cada um com keys
            {id, lead_id, created_at (epoch), created_by, note_type, params/text}.
            Normaliza pra incluir `lead_id` (vem aninhado no _embedded).
            Retorna [] em erro.

        Endpoint Kommo: GET /api/v4/leads/notes (notas globais — sem lead_id).
        """
        try:
            from datetime import timezone as _tz
            if since.tzinfo is None:
                since = since.replace(tzinfo=_tz.utc)
            ts_from = int(since.timestamp())
            params: dict = {
                "limit": min(int(limit), 250),
                "order[updated_at]": "desc",
                "filter[updated_at][from]": ts_from,
            }
            if note_type:
                params["filter[note_type]"] = note_type
            if author_user_id is not None:
                params["filter[created_by]"] = int(author_user_id)
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/notes",
                    params=params,
                    headers=self._headers,
                )
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                log.warning(
                    "Kommo list_recent_notes: HTTP %d desde %s",
                    r.status_code, since.isoformat(),
                )
                return []
            data = r.json() or {}
            notas = list(((data.get("_embedded") or {}).get("notes") or []))
            # Normalizar: incluir lead_id no top-level (Kommo coloca em entity_id)
            for n in notas:
                if "lead_id" not in n:
                    n["lead_id"] = n.get("entity_id")
            return notas
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo list_recent_notes erro: %s", e)
            return []

    def get_lead_messages(
        self, lead_id: int | str, limit: int = 30,
    ) -> list[dict]:
        """Lista mensagens (notas que são message_cashed ou similar)
        do lead. Usado pela camada 4 (template "Conclusão de
        Agendamento") pra varrer mensagens outbound do atendente humano
        que não viram nota comum.

        Estratégia: como Kommo expõe mensagens de WhatsApp via endpoint
        de chats que requer scope adicional, varremos notas com tipos
        de mensagem (message_cashed, service_message, incoming_chat_message,
        outgoing_chat_message). Em ambientes onde mensagens não ficam
        nas notas, devolve []  — camada 4 vira no-op silencioso.
        """
        notas = self.get_lead_notes(lead_id, limit=limit)
        out = []
        tipos_msg = {
            "message_cashed", "incoming_chat_message",
            "outgoing_chat_message", "extended_service_message",
        }
        for n in notas:
            nt = (n.get("note_type") or "").lower()
            if nt in tipos_msg or "message" in nt:
                # Normaliza acesso ao texto (pode estar em params.text
                # ou direto em text)
                texto = (
                    n.get("text")
                    or ((n.get("params") or {}).get("text"))
                    or ""
                )
                if texto:
                    out.append({
                        "text": texto,
                        "created_at": n.get("created_at"),
                        "created_by": n.get("created_by"),
                        "note_type": nt,
                    })
        return out

    def get_lead(self, lead_id: int | str) -> Optional[dict]:
        """Busca o lead completo (inclui custom_fields_values).

        Usado pela auditoria pós-consulta (task #82) pra ler N.EXAMES,
        N.NOME, médico/unidade/convênio e cod_agendamento. Devolve o JSON
        bruto do Kommo ou None em erro.
        """
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}", headers=self._headers,
                )
            if r.status_code != 200:
                log.warning("Kommo get_lead %s: HTTP %d", lead_id, r.status_code)
                return None
            return r.json() or None
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_lead erro (lead %s): %s", lead_id, e)
            return None

    def update_lead_status(
        self, lead_id: int, status_id: int, pipeline_id: Optional[int] = None,
    ) -> bool:
        """Move o lead para outra etapa do funil."""
        payload: dict[str, Any] = {"status_id": status_id}
        if pipeline_id:
            payload["pipeline_id"] = pipeline_id
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json=payload, headers=self._headers,
                )
            if r.status_code // 100 == 2:
                return True
            log.warning(
                "Kommo update_lead_status lead %s falhou: HTTP %d",
                lead_id, r.status_code,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo update_lead_status erro: %s", e)
        return False

    def rename_lead(self, lead_id: int, name: str) -> bool:
        """Atualiza a denominação (nome/título) do card do lead.

        Usado para dar visibilidade rápida à equipe humana — o título do
        card passa a refletir a situação atual do atendimento.
        """
        if not name or not str(name).strip():
            return False
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json={"name": str(name).strip()[:250]},
                    headers=self._headers,
                )
            if r.status_code // 100 == 2:
                return True
            log.warning(
                "Kommo rename_lead %s falhou: HTTP %d", lead_id, r.status_code
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo rename_lead erro: %s", e)
        return False

    # ----------------------- enriquecimento de contexto (onboarding)

    def get_caller_context_by_lead(self, lead_id: int | str) -> dict:
        """Onboarding por lead_id direto — usado no caminho Kommo (8133),
        onde o widget_request já entrega o lead_id."""
        out: dict = {
            "found": True, "lead_id": int(lead_id), "name": None,
            "status_id": None, "etapa": None, "ja_agendado": False,
            "known": {},
        }
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}",
                    params={"with": "contacts"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return out
            data = r.json() or {}
            sid = data.get("status_id")
            out["status_id"] = sid
            out["etapa"] = ST_NAMES.get(sid)
            # ja_agendado baseado em status_id (camada 1).
            # Camada 2 (1.DIA CONSULTA preenchido) é avaliada abaixo.
            ja_agendado_by_status = sid in ST_JA_AGENDADO
            id_to_label = {
                FIELD_NOME_PACIENTE_1: "nome_paciente",
                FIELD_MOTIVO_PACIENTE_1: "motivo",
                FIELD_CONVENIO[0]: "convenio",
                FIELD_UNIDADE[0]: "unidade",
                FIELD_MEDICOS[0]: "medico",
                FIELD_ESPECIALIDADE[0]: "especialidade",
                FIELD_DIA_TURNO_PERIODO: "dia_turno",
                FIELD_ATIVADO_IA[0]: "ativado_ia",
            }
            # 1.DIA CONSULTA é tratado separadamente porque é date_time (epoch)
            # e dispara a flag ja_agendado quando aponta para futuro/hoje.
            ja_agendado_by_consulta = False
            dia_consulta_ts: Optional[int] = None
            for cf in (data.get("custom_fields_values") or []):
                fid = cf.get("field_id")
                # Fallback agenda (02/07/2026) — campos "1./2. DIA COM CONVÊNIO"
                # (date_time epoch). São 2 slots já pré-calculados pela equipe/Lia
                # e gravados no lead. Quando o Medware ao vivo cai (timeout/vazio),
                # a Lia lê esses campos como FONTE B pra ofertar agenda sem depender
                # do servidor de agenda. Só valem se apontam pra futuro (> agora).
                # Caso Carolina 21225483: Medware fora → Lia entrou em loop de
                # hesitação 4x mesmo com 14/07 14:00 e 23/07 14:30 gravados aqui.
                if fid in (1259930, 1259932):
                    vals = cf.get("values") or []
                    if vals and vals[0].get("value"):
                        try:
                            ts = int(vals[0]["value"])
                            if ts > time.time():
                                _key = (
                                    "dia_conv_1_ts" if fid == 1259930
                                    else "dia_conv_2_ts"
                                )
                                out["known"][_key] = ts
                        except (ValueError, TypeError):
                            pass
                    continue
                # 1.DIA CONSULTA (date_time) → ja_agendado se >= ontem
                if fid == FIELD_DIA_CONSULTA_1:
                    vals = cf.get("values") or []
                    if vals and vals[0].get("value"):
                        try:
                            ts = int(vals[0]["value"])
                            # Aceita "consulta hoje OU futura" como sinal de já agendado
                            # (consulta de ontem já passou, não conta)
                            if ts > time.time() - 86400:
                                ja_agendado_by_consulta = True
                                dia_consulta_ts = ts
                                out["known"]["dia_consulta_ts"] = ts
                                # Para o agente saber a data legível.
                                # Bug C-47: SEMPRE em BRT (container é UTC).
                                out["known"]["dia_consulta_iso"] = (
                                    datetime.fromtimestamp(ts, tz=_TZ_BR).isoformat()
                                )
                        except (ValueError, TypeError):
                            pass
                    continue
                label = id_to_label.get(fid)
                if not label:
                    continue
                vals = cf.get("values") or []
                if vals:
                    v = vals[0].get("value")
                    if v:
                        out["known"][label] = v
            # Camada 3: nota humana recente com "agendei/marquei + data"
            # Origem: Fábio 02/06/2026 — atendente humano agenda no
            # Medware + escreve nota livre, sem atualizar 1.DIA CONSULTA.
            # Sem essa camada Lia ficava cega e refazia agendamento.
            notas_lead = []
            try:
                notas_lead = self.get_lead_notes(lead_id) or []
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "Kommo: erro lendo notas pra camada 3 lead %s: %s",
                    lead_id, e,
                )
            ja_agendado_by_humano, nota_preview = _ja_agendado_por_nota_humana(
                notas_lead,
            )
            if ja_agendado_by_humano:
                out["known"]["agendamento_por_humano_preview"] = nota_preview

            # Camada 4: template "Conclusão de Agendamento" Blink
            # (Fábio 02/06/2026 manhã). Atendente humano envia template
            # estruturado via WhatsApp depois de agendar no Medware. Vira
            # nota service_message no Kommo. Camadas 1-3 não pegam pq
            # não tem palavras-chave "agendei" e não é nota humana
            # comum. Esta camada faz parsing determinístico do template
            # e auto-popula known.*.
            ja_agendado_by_template = False
            template_dados: Optional[dict] = None
            try:
                for nota in notas_lead:
                    if not isinstance(nota, dict):
                        continue
                    texto = (nota.get("text") or "")
                    detectado = detectar_template_conclusao_agendamento(texto)
                    if detectado:
                        template_dados = detectado
                        ja_agendado_by_template = True
                        break
                # Se também não achou em notas, tenta no histórico de
                # mensagens WhatsApp (mensagens do chat — incluem
                # outbound humano que não vira nota).
                if not ja_agendado_by_template:
                    msgs = []
                    try:
                        msgs = self.get_lead_messages(lead_id, limit=30) or []
                    except Exception:  # noqa: BLE001
                        pass
                    for m in msgs:
                        texto = (m.get("text") or "")
                        detectado = detectar_template_conclusao_agendamento(
                            texto,
                        )
                        if detectado:
                            template_dados = detectado
                            ja_agendado_by_template = True
                            break
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "Kommo: camada 4 (template) erro lead %s: %s",
                    lead_id, e,
                )
            if ja_agendado_by_template and template_dados:
                # Auto-popula known.* (sem sobrescrever o que já existe)
                if not out["known"].get("nome_paciente") and template_dados.get("paciente"):
                    out["known"]["nome_paciente"] = template_dados["paciente"]
                if not out["known"].get("medico") and template_dados.get("medico"):
                    out["known"]["medico"] = template_dados["medico"]
                if not out["known"].get("especialidade") and template_dados.get("especialidade"):
                    out["known"]["especialidade"] = template_dados["especialidade"]
                if not out["known"].get("convenio") and template_dados.get("convenio"):
                    out["known"]["convenio"] = template_dados["convenio"]
                if not out["known"].get("unidade") and template_dados.get("unidade"):
                    out["known"]["unidade"] = template_dados["unidade"]
                if not out["known"].get("dia_consulta_iso") and template_dados.get("data_iso"):
                    out["known"]["dia_consulta_iso"] = template_dados["data_iso"]
                out["known"]["agendamento_por_template"] = (
                    f"{template_dados.get('data','')} "
                    f"{template_dados.get('hora','')}"
                ).strip()

            # Camada 5: detector genérico de conclusão no histórico.
            # Cobre o caso em que o atendente improvisa fora do template
            # (ex.: "Stephany: confirmei pra 09/06 às 18h com Karla").
            ja_agendado_by_historico = False
            historico_preview = None
            if not (
                ja_agendado_by_status or ja_agendado_by_consulta
                or ja_agendado_by_humano or ja_agendado_by_template
            ):
                try:
                    msgs_chat = self.get_lead_messages(lead_id, limit=30) or []
                except Exception:  # noqa: BLE001
                    msgs_chat = []
                # Junta notas humanas + mensagens de chat (humanas)
                candidatas = []
                for n in notas_lead:
                    candidatas.append({
                        "text": n.get("text"),
                        "created_at": n.get("created_at"),
                        "created_by": n.get("created_by"),
                    })
                candidatas.extend(msgs_chat)
                ja_agendado_by_historico, historico_preview = (
                    detectar_conclusao_no_historico(candidatas)
                )
                if ja_agendado_by_historico:
                    out["known"]["agendamento_por_historico_preview"] = (
                        historico_preview
                    )

            # ja_agendado = OR das CINCO camadas
            out["ja_agendado"] = (
                ja_agendado_by_status
                or ja_agendado_by_consulta
                or ja_agendado_by_humano
                or ja_agendado_by_template
                or ja_agendado_by_historico
            )
            if ja_agendado_by_consulta and not ja_agendado_by_status:
                # Caso típico do bug "Aurora": lead com 1.DIA CONSULTA preenchido
                # mas status ainda 2-AGENDAR (não foi movido). Loga aviso.
                log.info(
                    "Kommo: lead %s tem dia_consulta_ts=%s (futuro) mas status "
                    "%s não está em ST_JA_AGENDADO. ja_agendado=True por camada 2.",
                    lead_id, dia_consulta_ts, sid,
                )
            if ja_agendado_by_humano and not (
                ja_agendado_by_status or ja_agendado_by_consulta
            ):
                # Caso novo: humano agendou sem mexer nos campos.
                log.warning(
                    "Kommo: lead %s — ja_agendado=True por NOTA HUMANA "
                    "(camada 3). status=%s, 1.DIA CONSULTA vazio. "
                    "Nota: %r",
                    lead_id, sid, nota_preview,
                )
            if ja_agendado_by_template and not (
                ja_agendado_by_status or ja_agendado_by_consulta
            ):
                log.warning(
                    "Kommo: lead %s — ja_agendado=True por TEMPLATE "
                    "CONCLUSAO (camada 4). status=%s, 1.DIA CONSULTA "
                    "vazio. Dados: %s",
                    lead_id, sid, template_dados,
                )
            if ja_agendado_by_historico:
                log.warning(
                    "Kommo: lead %s — ja_agendado=True por HISTÓRICO "
                    "DE MENSAGEM (camada 5). Texto: %r",
                    lead_id, historico_preview,
                )

            # 'name' = nome do CONTATO (quem escreve no WhatsApp) — é esse
            # que o agente usa para CUMPRIMENTAR. NUNCA usar o nome do
            # paciente aqui: o paciente pode ser outra pessoa (ex.: a mãe
            # escreve, a consulta é do filho). O nome do paciente fica
            # separado, em known['nome_paciente'].
            contatos = (data.get("_embedded") or {}).get("contacts") or []
            main = next(
                (ct for ct in contatos if ct.get("is_main")),
                contatos[0] if contatos else None,
            )
            cid = (main or {}).get("id")
            if cid:
                with httpx.Client(timeout=self.timeout) as cc:
                    rc = cc.get(
                        f"{self._base}/contacts/{cid}",
                        headers=self._headers,
                    )
                if rc.status_code == 200:
                    cname = (rc.json() or {}).get("name")
                    if cname and str(cname).strip():
                        out["name"] = str(cname).strip()
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_caller_context_by_lead erro: %s", e)
        return out

    # ----------------------- convivência humano × agente

    def recent_human_handoff(self, lead_id: int | str, window_min: int) -> bool:
        """True se um humano enviou mensagem manual no chat há < window_min.

        O Kommo registra uma nota 'service_message' quando detecta uma
        mensagem manual de saída ("Agentes de IA foram desativados neste
        chat..."). Essa nota é o sinal de que um atendente assumiu a conversa.
        """
        if not lead_id or window_min <= 0:
            return False
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}/notes",
                    params={"limit": 50, "order[created_at]": "desc"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return False
            notes = ((r.json() or {}).get("_embedded") or {}).get("notes") or []
            agora = time.time()
            for nt in notes:
                if nt.get("note_type") != "service_message":
                    continue
                txt = (
                    (nt.get("params") or {}).get("text")
                    or nt.get("text") or ""
                ).lower()
                if "desativ" not in txt:
                    continue
                created = float(nt.get("created_at") or 0)
                if created and (agora - created) < window_min * 60:
                    return True
        except Exception as e:  # noqa: BLE001
            log.warning(
                "Kommo recent_human_handoff erro (lead %s): %s", lead_id, e
            )
        return False

    def ia_status_from_notes(self, lead_id: int | str) -> Optional[str]:
        """Lê as notas do lead e deduz o estado da IA: 'ATIVADO' / 'DESATIVADO'.

        Sinal de DESATIVADO: nota service_message do Kommo com 'desativ'
        ('Agentes de IA foram desativados neste chat...').
        Sinal de ATIVADO: nota da própria Lia ('🤖 Lia (WhatsApp)') ou uma
        service_message de reativação — mais recente que o último desativar.
        Retorna None quando não há nenhum sinal nas notas.
        """
        if not lead_id:
            return None
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}/notes",
                    params={"limit": 100, "order[created_at]": "desc"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return None
            notes = ((r.json() or {}).get("_embedded") or {}).get("notes") or []
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo ia_status_from_notes erro (lead %s): %s", lead_id, e)
            return None
        ts_off = 0.0   # último 'IA desativada'
        ts_on = 0.0    # última atividade da Lia / reativação
        for nt in notes:
            created = float(nt.get("created_at") or 0)
            txt = (
                (nt.get("params") or {}).get("text")
                or nt.get("text") or ""
            ).lower()
            if nt.get("note_type") == "service_message":
                if "desativ" in txt:
                    ts_off = max(ts_off, created)
                elif "ativ" in txt:  # 'agentes de IA foram ativados'
                    ts_on = max(ts_on, created)
            elif "lia (whatsapp)" in txt:
                ts_on = max(ts_on, created)
        if ts_off == 0.0 and ts_on == 0.0:
            return None
        return "DESATIVADO" if ts_off > ts_on else "ATIVADO"

    def agent_paused_for_lead(
        self, caller_context: Optional[dict], window_min: int,
    ) -> Optional[str]:
        """Decide se o agente deve ficar em SILÊNCIO para este lead.

        REGRA GERAL ARTICULADA (Fábio 02/06/2026 — bug Elisa 21392947):

        IA fica desligada APENAS quando a etapa do funil é
        explicitamente operacional/humana:
        - 1-ATENDIMENTO HUMANO
        - 7-CIRURGIAS ANDAMENTO, 8-LENTES, 9-FORNECEDORES
        - 5-CONFIRMAR, 6-CONFIRMADO (paciente respondendo template)

        Para QUALQUER outra etapa (entrada, frio, AGENDAR, REAGENDAR,
        AGENDADO, NO-SHOW, Closed-lost, Closed-won...), a IA deve
        responder mesmo se humano tiver escrito antes. Paciente pode
        voltar a qualquer momento e Lia tem que estar pronta.

        EXCEÇÃO TEMPORAL (sem permanência): se humano escreveu MENOS
        de 30 min atrás (Kommo gerou "🛑" recente), aguarda. Isso dá
        tempo do atendente terminar 1 conversa específica sem Lia
        falar por cima. Após 30 min, IA volta automaticamente.

        Histórico:
        - 01/06/2026 noite: regra 2 (service_message do Kommo)
          re-plugada após bug Marcela. Mas ficou permanente — sem
          decay temporal — e bloqueava em qualquer etapa.
        - 02/06/2026: bug Elisa (21392947). Lia silenciosa há 50 dias
          porque humano escreveu em 13/04. Auto-cura via regra de
          etapa: closed-lost NÃO é ST_AGENT_OFF → IA responde.
          Regra 2 vira temporária (30min), não permanente.

        Retorna o motivo ('ia-desativada' | 'etapa-humana'
        | 'humano-escreveu-recente') ou None.
        """
        if not caller_context or not caller_context.get("found"):
            return None

        # Regra 0 (Bug C-37b, Fábio 18/06/2026 — lead 21341221 Lívia):
        # Campo custom "ATIVADO IA?" do Kommo = "Desativado" → IA
        # silenciosa SEMPRE. Antes do fix, agent ignorava esse campo
        # e Lia respondia mesmo com humano tendo clicado "Desativar".
        # known["ativado_ia"] vem em UPPERCASE conforme update_lead_fields.
        ativado_ia = str(
            (caller_context.get("known") or {}).get("ativado_ia") or ""
        ).upper().strip()
        if ativado_ia in ("DESATIVADO", "DESATIVADA", "OFF"):
            return "ia-desativada"

        # Regra 1: etapa do funil é explicitamente operacional/humana
        # (ESTA É A REGRA PRIMÁRIA — Fábio 02/06/2026)
        if caller_context.get("status_id") in ST_AGENT_OFF:
            return "etapa-humana"

        # Regra 2 (refinada): silêncio TEMPORÁRIO se humano escreveu
        # nas últimas 30 minutos. Após esse window, IA volta sozinha
        # mesmo sem "🟢" explícito. Auto-cura para evitar leads órfãos.
        lead_id = caller_context.get("lead_id")
        if lead_id:
            try:
                ts_humano = self._ts_ultimo_humano_escreveu(lead_id)
                if ts_humano:
                    import time as _t
                    idade_min = (_t.time() - ts_humano) / 60.0
                    if idade_min < 30:
                        return "humano-escreveu-recente"
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "agent_paused_for_lead: checagem humano-recente "
                    "falhou (lead %s): %s", lead_id, e,
                )

        return None

    def _ts_ultimo_humano_escreveu(
        self, lead_id: int | str,
    ) -> Optional[float]:
        """Devolve epoch da última service_message "🛑 humano escreveu"
        mais recente que qualquer "🟢 IA ativada". None se não há
        marca de humano escrevendo, ou se a última marca é "🟢".

        Usado pelo agent_paused_for_lead pra decidir silêncio
        TEMPORÁRIO (não permanente como antes).
        """
        try:
            notas = self.get_lead_notes(lead_id, limit=50) or []
        except Exception:  # noqa: BLE001
            return None
        ultimo_ts: Optional[float] = None
        ultimo_eh_humano = False
        from datetime import datetime
        for n in notas:
            if not isinstance(n, dict):
                continue
            if (n.get("note_type") or "") != "service_message":
                continue
            texto = (n.get("text") or "").lower()
            if "agentes de ia" not in texto and "ai agents" not in texto:
                continue
            # Parse timestamp
            ts_raw = n.get("created_at")
            if not ts_raw:
                continue
            try:
                dt = datetime.fromisoformat(
                    str(ts_raw).replace("Z", "+00:00"),
                )
                ts = dt.timestamp()
            except (ValueError, TypeError):
                continue
            # Mais recente vence
            if ultimo_ts is None or ts > ultimo_ts:
                ultimo_ts = ts
                # "🛑 desativados" ou "stopped" = humano escreveu
                ultimo_eh_humano = (
                    "desativados" in texto or "desativadas" in texto
                    or "stopped" in texto or "🛑" in texto
                )
        return ultimo_ts if ultimo_eh_humano else None
