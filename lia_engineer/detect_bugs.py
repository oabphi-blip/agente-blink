"""Detecta bugs em produção lendo notas Kommo recentes + logs Easypanel.

Não é mágica. São padrões observáveis e indexáveis. Exemplos reais
(lead 24125064 Tatiana, 09/06/2026):

| Padrão | Regex / heurística | Causa raiz |
|---|---|---|
| "deixa eu (re)consultar a agenda" | regex | Cat 1 — Sonnet decidiu texto livre em FSM=AGENDA |
| 2+ mensagens Lia em < 10s | timestamp diff | Race condition (#183 não funcionou) |
| "quarta-feira, 11/06" (data não bate dia) | calc weekday vs string | Cat 2 — filtro `_viola_data_vs_dia_semana` escapou |
| "Atendemos {convênio_kb18}" | match KB 18 | Cat 3 — KB ↔ Kommo enum desincronizado |
| 4+ perguntas em 1 msg (4+ "?") | regex count | Cat 6 — formulário em vez de diálogo |
| "Registrado como X" depois "Registrado como Y" | sliding window | Race + FSM dessincronizado |

Cada match cria um `BugReport` que vira input pro `propose_fix.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


# ────────────────────────────────────────────────────────────────────────
# Padrões de bug observáveis (cada novo bug indexado vira regex aqui)
# ────────────────────────────────────────────────────────────────────────

PADROES_BUG = [
    {
        "id": "vou_consultar_e_nao_volta",
        "regex": re.compile(
            r"deixa eu (re)?consultar|vou (re)?consultar|"
            r"vou buscar os hor[áa]rios|aguardando.*hor[áa]rios|"
            r"vou registrar.*equipe finalizar",
            re.IGNORECASE,
        ),
        "categoria_raiz": "cat1_tool_calling_nao_forcado_em_AGENDA",
        "severidade": "P0",  # bug crítico, repete há semanas
        "exemplos": ["Juliene 24053159", "Grace 24112452", "Karla Pacheco 24039387",
                     "Tatiana 24125064 turno 14"],
    },
    {
        "id": "atende_convenio_nao_aceito",
        "regex": re.compile(
            r"\b(atende[mr]o?s?|cobr[ei]mos|aceita?mos|credenci\w*)\b.{0,40}"
            r"\b(inas|gdf saúde|bradesco|cassi|sul am[ée]rica|hap[\s-]?vida|"
            r"unimed|notre dame|porto seguro|amil|fusex|geap|brb)\b",
            re.IGNORECASE,
        ),
        "filtro_extra": lambda txt: not re.search(
            r"\bn[ãa]o\s+(atend|cobr|aceit|credenc|est[áa]\s+(credenc|na\s+rede|coberto)|cobre)",
            txt, re.IGNORECASE,
        ),
        "categoria_raiz": "cat3_kb_kommo_enum_desincronizado",
        "severidade": "P0",
        "exemplos": ["Maria Agostini 24117314"],
    },
    {
        "id": "multiplas_perguntas_em_uma_msg",
        "regex": re.compile(r".*"),  # match all, filtra por contagem
        "filtro_extra": lambda txt: txt.count("?") >= 3,
        "categoria_raiz": "cat6_formulario_em_vez_de_dialogo",
        "severidade": "P1",
        "exemplos": ["Alessandro 24112156", "Tatiana 24125064 turno 4"],
    },
    {
        "id": "data_dia_semana_inconsistente",
        # Detecta "quarta-feira, 11/06" e checa se 11/06 é mesmo quarta
        "regex": re.compile(
            r"(segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)[\s\-,]*"
            r"(?:feira)?[\s\-,()*]*(\d{1,2})/(\d{1,2})",
            re.IGNORECASE,
        ),
        "validador": "valida_dia_data",
        "categoria_raiz": "cat2_filtro_regex_escapou",
        "severidade": "P1",
        "exemplos": ["Priscila 24055629", "Tatiana 24125064 turno 15"],
    },
    {
        "id": "horario_comercial_inventado",
        "regex": re.compile(
            r"hor[áa]rio comercial|seg-sex 8.{0,4}18h|seg.*a.*sex.*8.*18",
            re.IGNORECASE,
        ),
        "categoria_raiz": "cat2_filtro_regex_escapou",
        "severidade": "P2",
        "exemplos": ["Juliene 24053159"],
    },
    {
        "id": "contradicao_classificacao_motivo",
        "regex_par": [
            re.compile(r"registrado como (urg[êe]ncia|rotina)", re.IGNORECASE),
            re.compile(r"registrar como (rotina|urg[êe]ncia)", re.IGNORECASE),
        ],
        "categoria_raiz": "cat1_race_condition_pipeline_lock",
        "severidade": "P0",
        "exemplos": ["Tatiana 24125064 turnos 10/11/12"],
    },
    {
        "id": "mensagem_duplicada_lia_em_janela_curta",
        "deteccao": "sliding_window_timestamp",
        "janela_segundos": 15,
        "categoria_raiz": "cat1_race_condition_pipeline_lock",
        "severidade": "P0",
        "exemplos": ["Tatiana 24125064 turnos 4-5 (7s)", "Tatiana turnos 17-18-19"],
    },
    {
        "id": "promete_retorno_humano_sem_volta",
        "regex": re.compile(
            r"vou registrar.*(equipe|atendente|secretária).*"
            r"(finaliz|atend|retorn)",
            re.IGNORECASE,
        ),
        "categoria_raiz": "cat1_tool_calling_nao_forcado",
        "severidade": "P0",
        "exemplos": ["Juliene 24053159"],
    },
]


# ────────────────────────────────────────────────────────────────────────
# Modelo de dados
# ────────────────────────────────────────────────────────────────────────

@dataclass
class BugReport:
    """Um bug detectado em produção, pronto pra ser corrigido."""

    lead_id: int
    """ID do lead no Kommo onde o bug apareceu."""

    timestamp: datetime
    """Quando o bug ocorreu (UTC)."""

    padrao_id: str
    """ID do padrão em PADROES_BUG que casou."""

    categoria_raiz: str
    """Categoria de causa-raiz (cat1/cat2/cat3/cat4/cat5/cat6)."""

    severidade: str
    """P0 (crítico) / P1 (importante) / P2 (cosmético)."""

    texto_lia: str
    """Texto exato da Lia que disparou a detecção."""

    contexto_lead: dict = field(default_factory=dict)
    """Snapshot dos custom_fields no momento do bug, pra propose_fix usar."""

    historico_notas_anterior: list = field(default_factory=list)
    """Últimas 5 notas anteriores ao bug, pra contexto."""

    def chave_dedup(self) -> str:
        """Chave pra evitar processar o mesmo bug 2x. Inclui janela 1h."""
        hora = self.timestamp.strftime("%Y%m%d_%H")
        return f"{self.padrao_id}:{self.lead_id}:{hora}"


# ────────────────────────────────────────────────────────────────────────
# Detecção de padrões em texto único
# ────────────────────────────────────────────────────────────────────────

def detectar_padroes_em_texto(
    texto: str,
    lead_id: int,
    timestamp: datetime,
    contexto_lead: Optional[dict] = None,
    ja_dia_da_semana_hoje: Optional[datetime] = None,
) -> List[BugReport]:
    """Roda os regex de `PADROES_BUG` contra `texto`.

    Retorna lista de BugReport (pode ser vazia). Cada padrão que casar
    vira 1 BugReport.

    Args:
        texto: conteúdo da nota (msg da Lia)
        lead_id: ID Kommo do lead
        timestamp: quando a msg foi enviada (UTC)
        contexto_lead: custom_fields do lead pra enriquecer
        ja_dia_da_semana_hoje: data de referência pra validar "dia+data"
            (default = timestamp.date())
    """
    if not texto:
        return []
    if ja_dia_da_semana_hoje is None:
        ja_dia_da_semana_hoje = timestamp

    bugs: List[BugReport] = []

    for padrao in PADROES_BUG:
        # 1) Pular padrões que dependem de comparação entre notas (sliding window).
        if padrao.get("deteccao") == "sliding_window_timestamp":
            continue
        if "regex_par" in padrao:
            continue  # tratado em detectar_padroes_sliding_window

        regex = padrao.get("regex")
        if not regex:
            continue
        m = regex.search(texto)
        if not m:
            continue

        # 2) Filtro extra (ex: contagem de '?')
        filtro_extra = padrao.get("filtro_extra")
        if filtro_extra and not filtro_extra(texto):
            continue

        # 3) Validador (ex: dia da semana × data)
        validador = padrao.get("validador")
        if validador == "valida_dia_data":
            if _data_bate_dia_semana(m, ja_dia_da_semana_hoje):
                continue  # tudo certo, não é bug

        bugs.append(BugReport(
            lead_id=lead_id,
            timestamp=timestamp,
            padrao_id=padrao["id"],
            categoria_raiz=padrao["categoria_raiz"],
            severidade=padrao["severidade"],
            texto_lia=texto[:500],
            contexto_lead=contexto_lead or {},
        ))

    return bugs


# ────────────────────────────────────────────────────────────────────────
# Detecção sliding-window (mensagens duplicadas em <15s, contradição)
# ────────────────────────────────────────────────────────────────────────

def detectar_padroes_sliding_window(
    notas_ordenadas: List[dict],
    lead_id: int,
) -> List[BugReport]:
    """Detecta race condition: 2+ msgs Lia em janela curta.

    Args:
        notas_ordenadas: lista de dicts {at: datetime, txt: str, author: str},
            ordenadas por `at` ascendente.

    Returns:
        Lista de BugReport pra cada janela violada.
    """
    bugs: List[BugReport] = []

    notas_lia = [n for n in notas_ordenadas if n.get("author") in ("LIA", "LIA/inbound")]

    for i in range(len(notas_lia) - 1):
        n1 = notas_lia[i]
        n2 = notas_lia[i + 1]
        delta = (n2["at"] - n1["at"]).total_seconds()

        # Padrão 1: 2 msgs Lia em <15s = race condition
        if 0 < delta < 15:
            bugs.append(BugReport(
                lead_id=lead_id,
                timestamp=n2["at"],
                padrao_id="mensagem_duplicada_lia_em_janela_curta",
                categoria_raiz="cat1_race_condition_pipeline_lock",
                severidade="P0",
                texto_lia=f"[+{delta:.0f}s] {n1['txt'][:200]} || {n2['txt'][:200]}",
            ))

        # Padrão 2: contradição "Registrado como X" → "Registrado como Y"
        for padrao in PADROES_BUG:
            if "regex_par" not in padrao:
                continue
            r1, r2 = padrao["regex_par"]
            m1 = r1.search(n1["txt"])
            m2 = r2.search(n2["txt"])
            if m1 and m2 and delta < 60:
                # Comparar grupos: se "urgência" → "rotina" ou vice-versa
                v1 = (m1.group(1) or "").lower()
                v2 = (m2.group(1) or "").lower()
                if v1 != v2:
                    bugs.append(BugReport(
                        lead_id=lead_id,
                        timestamp=n2["at"],
                        padrao_id=padrao["id"],
                        categoria_raiz=padrao["categoria_raiz"],
                        severidade=padrao["severidade"],
                        texto_lia=f"[+{delta:.0f}s] classifiquei {v1!r} → {v2!r}",
                    ))

    return bugs


# ────────────────────────────────────────────────────────────────────────
# Validador: dia da semana × data numérica
# ────────────────────────────────────────────────────────────────────────

_DIA_PARA_WEEKDAY = {
    "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}


def _data_bate_dia_semana(match: re.Match, referencia: datetime) -> bool:
    """Verifica se 'quarta-feira, 11/06' bate. Retorna True se OK."""
    try:
        dia_semana_str = (match.group(1) or "").lower()
        dia_num = int(match.group(2))
        mes_num = int(match.group(3))
        weekday_esperado = _DIA_PARA_WEEKDAY.get(dia_semana_str)
        if weekday_esperado is None:
            return True
        # Tentar formar data no ano de referência
        ano = referencia.year
        try:
            data_real = datetime(ano, mes_num, dia_num)
        except ValueError:
            return False  # data inválida (ex: 31/02)
        # Se data_real está muito no passado, considera próximo ano
        if data_real.date() < referencia.date() - timedelta(days=30):
            data_real = datetime(ano + 1, mes_num, dia_num)
        return data_real.weekday() == weekday_esperado
    except (ValueError, AttributeError):
        return True  # malformed, não conta como bug


# ────────────────────────────────────────────────────────────────────────
# Entrypoint principal: detectar todos bugs em todas as notas
# ────────────────────────────────────────────────────────────────────────

def detectar_bugs_em_lead(
    notas: List[dict],
    lead_id: int,
    contexto_lead: Optional[dict] = None,
) -> List[BugReport]:
    """Detecta TODOS os bugs no histórico de notas de 1 lead.

    Args:
        notas: lista de dicts {at: datetime, txt: str, author: str}.
            'author' = "LIA" / "humano" / "u123".
        lead_id: ID Kommo.
        contexto_lead: custom_fields atuais.

    Returns:
        Lista deduplicada de BugReport, ordenada por timestamp.
    """
    bugs: List[BugReport] = []

    # 1) Padrões em texto único
    for n in notas:
        if n.get("author") not in ("LIA", "LIA/inbound"):
            continue
        bugs.extend(detectar_padroes_em_texto(
            n["txt"], lead_id, n["at"], contexto_lead,
        ))

    # 2) Padrões sliding window
    notas_ord = sorted(notas, key=lambda n: n["at"])
    bugs.extend(detectar_padroes_sliding_window(notas_ord, lead_id))

    # 3) Dedup por chave
    seen = set()
    unique = []
    for b in sorted(bugs, key=lambda b: b.timestamp):
        k = b.chave_dedup()
        if k not in seen:
            seen.add(k)
            unique.append(b)

    return unique
