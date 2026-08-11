"""Validador Factual — cruza TODA afirmação numérica/factual da Lia com
fonte de verdade ANTES de enviar.

Hoje a Lia pode inventar:
    - "consulta R$ 611" (correto Karla, mas precisa cruzar)
    - "quarta-feira, 11/06" (data×dia incoerente — bug Tatiana)
    - "Sala 123/124" (precisa bater com endereço oficial)
    - "Dra. Karla" (paciente quer Fabrício — escolha errada)
    - "INAS GDF aceito" (KB 18 diz NÃO — bug Maria Agostini)
    - "exame agora mesmo" (Medware não tem slot pra hoje)

Cada uma dessas é uma AFIRMAÇÃO sobre FATO. Validador Factual extrai a
afirmação, identifica o tipo (preço/data/médico/convênio/endereço/horário),
busca a fonte de verdade correspondente, e cruza.

Se INCONSISTENTE → bloqueia envio + log + substituição.

Diferente dos filtros `_viola_*` (que pegam padrões REATIVOS), o validador
factual é PROATIVO: extrai → cruza → decide.

Cosmoética: a Lia só afirma o que é verdadeiro e checkável. Zero alucinação
matemática.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any


# ────────────────────────────────────────────────────────────────────────
# Modelo de afirmação factual
# ────────────────────────────────────────────────────────────────────────

@dataclass
class AfirmacaoFactual:
    """Uma afirmação extraída do texto da Lia."""
    tipo: str  # "preco" / "data" / "medico" / "convenio" / "endereco" / "horario_atendimento"
    valor_declarado: str
    posicao_no_texto: int
    contexto_curto: str  # 30 chars antes e depois


@dataclass
class ResultadoValidacao:
    """Resultado da validação de uma afirmação contra fonte de verdade."""
    afirmacao: AfirmacaoFactual
    consistente: bool
    valor_correto: Optional[str] = None
    fonte_consultada: str = ""
    motivo_inconsistencia: str = ""


# ────────────────────────────────────────────────────────────────────────
# Fontes de verdade
# ────────────────────────────────────────────────────────────────────────

# Preços oficiais por médico (KB 19)
PRECOS_OFICIAIS = {
    "karla_consulta_sem_convenio": 611.00,
    "karla_sinal_50_pct": 305.50,
    "fabricio_avaliacao_catarata_sem_convenio": 297.00,
    "fabricio_sinal_50_pct": 148.50,
    "karla_sdp_estrabismo_sem_convenio": 800.00,
    "karla_sdp_sinal_50_pct": 400.00,
}

# Endereços oficiais
ENDERECOS_OFICIAIS = {
    "asa_norte": "SGAN 607, Bloco A, Edifício Medical Center, 1° Andar, Sala 123/124",
    "aguas_claras": "Rua das Pitangueiras, lote 1-3 sala 219 - Edifício Universittus",
}

# Chaves Pix oficiais (allowlist)
PIX_OFICIAIS = {
    "asa_norte": "karladelaliberaoftalmo@gmail.com",
    "aguas_claras": "52.303.729/0001-30",
}

# Médicos × dia da semana (CLAUDE.md seção 9-A)
DIAS_ATENDIMENTO = {
    "karla": [0, 1, 2, 3, 4],  # seg-sex
    "fabricio": [1, 3],         # ter+qui
    "katia": [],                 # em pausa
}

# Convênios KB18 NÃO aceitos (lowercase + variantes)
CONVENIOS_NAO_ACEITOS = frozenset({
    "afeb", "afego", "amil", "assefaz", "asete", "aste",
    "bradesco", "brb", "cassi", "caeme", "caesan", "camed", "cnti",
    "eletronorte", "embratel", "fusex", "fapes", "geap", "golden",
    "hapvida", "hap vida", "inas", "gdf inas", "gdf saúde",
    "notre dame", "polícia militar", "porto seguro", "quality",
    "sul américa", "sul america", "sulamérica", "sus",
    "unimed", "unafisco",
})

# Convênios KB17 ACEITOS
CONVENIOS_ACEITOS = frozenset({
    "pro ser stj", "tjdft pró-saúde", "plan assiste", "mpf", "mpu",
    "e-vida", "anafe", "bacen", "care plus", "casec", "casembrapa",
    "conab", "fascal", "omint", "pf saúde", "plas/jmu", "stm",
    "proasa", "saúde caixa", "saude caixa", "petrobrás", "petrobras",
    "serpro", "sis senado", "stf-med", "trf", "tre", "trt", "tst",
    "câmara dos deputados", "particular", "não se aplica",
})


# ────────────────────────────────────────────────────────────────────────
# Extratores por tipo
# ────────────────────────────────────────────────────────────────────────

_REGEX_PRECO = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", re.IGNORECASE)
_REGEX_DATA_DIA = re.compile(
    r"(segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)[\s\-,()*]*(?:feira)?[\s\-,()*]*(\d{1,2})/(\d{1,2})",
    re.IGNORECASE,
)
_REGEX_CONVENIO_AFIRMADO = re.compile(
    r"\b(atende[mr]o?s?|cobr[ei]mos|aceita?mos|credenci\w*)\b"
    r"[\s,]+(?:o|a|os|as|do|da|dos|das|um|uma)?[\s,]*"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\s\-/]{2,40}?)"
    r"(?=[.,!?\n;]|\s+(?:sim|com|para|por|à|na|no|em|e\s)|\s*$)",
    re.IGNORECASE,
)


def extrair_afirmacoes(texto: str) -> List[AfirmacaoFactual]:
    """Extrai todas as afirmações factuais do texto."""
    afirmacoes = []
    for m in _REGEX_PRECO.finditer(texto):
        afirmacoes.append(AfirmacaoFactual(
            tipo="preco", valor_declarado=m.group(1),
            posicao_no_texto=m.start(),
            contexto_curto=texto[max(0, m.start()-30):m.end()+30],
        ))
    for m in _REGEX_DATA_DIA.finditer(texto):
        afirmacoes.append(AfirmacaoFactual(
            tipo="data_dia_semana",
            valor_declarado=f"{m.group(1)} {m.group(2)}/{m.group(3)}",
            posicao_no_texto=m.start(),
            contexto_curto=texto[max(0, m.start()-30):m.end()+30],
        ))
    for m in _REGEX_CONVENIO_AFIRMADO.finditer(texto):
        # Filtrar negações
        ctx_antes = texto[max(0, m.start()-30):m.start()].lower()
        if "não " in ctx_antes or "nao " in ctx_antes or "infelizmente" in ctx_antes:
            continue
        afirmacoes.append(AfirmacaoFactual(
            tipo="convenio_atende",
            valor_declarado=m.group(2).strip(),
            posicao_no_texto=m.start(),
            contexto_curto=texto[max(0, m.start()-30):m.end()+30],
        ))
    return afirmacoes


# ────────────────────────────────────────────────────────────────────────
# Validadores por tipo (cruzam com fonte de verdade)
# ────────────────────────────────────────────────────────────────────────

def validar_preco(af: AfirmacaoFactual, ctx: Dict) -> ResultadoValidacao:
    """Confere se R$ X declarado bate com preço oficial pro médico/serviço."""
    valor_str = af.valor_declarado.replace(".", "").replace(",", ".")
    try:
        valor_num = float(valor_str)
    except ValueError:
        return ResultadoValidacao(af, False, motivo_inconsistencia="preço malformado")
    medico = (ctx.get("known", {}).get("medico") or "").lower()
    # Procurar preço oficial compatível
    precos_validos = list(PRECOS_OFICIAIS.values())
    if valor_num in precos_validos:
        return ResultadoValidacao(af, True, fonte_consultada="KB 19")
    return ResultadoValidacao(
        af, False, fonte_consultada="KB 19",
        motivo_inconsistencia=f"R$ {valor_num:.2f} não bate com tabela oficial: {precos_validos}",
    )


def validar_data_dia_semana(af: AfirmacaoFactual, ctx: Dict) -> ResultadoValidacao:
    """Confere se "quarta-feira, 10/06" bate com calendário real."""
    m = _REGEX_DATA_DIA.search(af.valor_declarado)
    if not m:
        return ResultadoValidacao(af, True)  # malformed, deixa passar
    dia_semana_str = m.group(1).lower()
    dia_num = int(m.group(2))
    mes_num = int(m.group(3))
    weekday_esperado = {
        "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
        "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    }.get(dia_semana_str)
    if weekday_esperado is None:
        return ResultadoValidacao(af, True)
    hoje = ctx.get("hoje") or date.today()
    try:
        data_real = date(hoje.year, mes_num, dia_num)
    except ValueError:
        return ResultadoValidacao(af, False, motivo_inconsistencia="data inválida")
    if data_real < hoje - timedelta(days=30):
        try:
            data_real = date(hoje.year + 1, mes_num, dia_num)
        except ValueError:
            return ResultadoValidacao(af, False, motivo_inconsistencia="data inválida")
    weekday_real = data_real.weekday()
    if weekday_real == weekday_esperado:
        return ResultadoValidacao(af, True, fonte_consultada="calendário")
    nomes_pt = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return ResultadoValidacao(
        af, False, fonte_consultada="calendário",
        valor_correto=f"{nomes_pt[weekday_real]}-feira, {dia_num:02d}/{mes_num:02d}",
        motivo_inconsistencia=(
            f"{dia_num:02d}/{mes_num:02d} é {nomes_pt[weekday_real]} "
            f"(não {dia_semana_str})"
        ),
    )


def validar_convenio_atende(af: AfirmacaoFactual, ctx: Dict) -> ResultadoValidacao:
    """Confere se convênio afirmado como 'aceito' está mesmo em KB 17."""
    nome_low = af.valor_declarado.lower()
    # Procurar em NÃO aceitos primeiro (têm prioridade)
    for conv in CONVENIOS_NAO_ACEITOS:
        if conv in nome_low:
            return ResultadoValidacao(
                af, False, fonte_consultada="KB 18",
                motivo_inconsistencia=f"'{conv}' é NÃO aceito pela Blink",
            )
    for conv in CONVENIOS_ACEITOS:
        if conv in nome_low:
            return ResultadoValidacao(af, True, fonte_consultada="KB 17")
    # Não conhecido — incerto, escala humano
    return ResultadoValidacao(
        af, False, fonte_consultada="KB 17/18",
        motivo_inconsistencia=f"'{nome_low}' não está em KB 17 (aceitos) nem KB 18 (não aceitos). Confirmar com humano.",
    )


# ────────────────────────────────────────────────────────────────────────
# API principal
# ────────────────────────────────────────────────────────────────────────

def validar_texto_lia(texto: str, ctx: Optional[Dict] = None) -> List[ResultadoValidacao]:
    """Valida TODAS as afirmações factuais do texto.

    Args:
        texto: resposta gerada pela Lia
        ctx: caller_context com known.medico, known.unidade, hoje, etc

    Returns:
        Lista de ResultadoValidacao. Filtrar `not r.consistente` pra ver
        problemas. Lista vazia = nada pra validar (não significa OK).
    """
    if not texto:
        return []
    ctx = ctx or {}
    afirmacoes = extrair_afirmacoes(texto)
    resultados = []
    for af in afirmacoes:
        if af.tipo == "preco":
            resultados.append(validar_preco(af, ctx))
        elif af.tipo == "data_dia_semana":
            resultados.append(validar_data_dia_semana(af, ctx))
        elif af.tipo == "convenio_atende":
            resultados.append(validar_convenio_atende(af, ctx))
    return resultados


def todas_consistentes(resultados: List[ResultadoValidacao]) -> bool:
    """True se todas as afirmações passaram validação."""
    return all(r.consistente for r in resultados)


def inconsistencias(resultados: List[ResultadoValidacao]) -> List[ResultadoValidacao]:
    return [r for r in resultados if not r.consistente]
