#!/usr/bin/env python3
"""
Bug History Analyzer — Sistema de aprendizado automático de bugs históricos
===========================================================================

Por que só agora?
  Cada bug era corrigido em modo reativo (bug a bug), sem olhar para cima.
  Com 65+ test_bug_*.py acumulados, o meta-padrão emergiu: a maioria dos bugs
  é instância de "LLM inferiu algo que Python já podia calcular/bloquear".
  Este script converte esse dataset em ferramenta proativa.

Usos:
  # Relatório temporal (dia/semana/mês)
  python scripts/bug_history_analyzer.py relatorio [--periodo dia|semana|mes]

  # Encontrar bug similar para novo sintoma
  python scripts/bug_history_analyzer.py buscar "Lia perguntou qual médico quando já sabia"

  # Detectar root causes recorrentes
  python scripts/bug_history_analyzer.py recorrencias

  # Gerar filtro pós-geração para novo bug
  python scripts/bug_history_analyzer.py gerar-filtro \\
      --frases-proibidas "Qual turno funciona melhor" "manhã ou tarde" \\
      --substituir "Deixa eu verificar os horários disponíveis" \\
      --bug-id C-103 --descricao "Lia pergunta turno quando já tem medico+unidade"

  # Extrair dataset JSON completo
  python scripts/bug_history_analyzer.py exportar [--output bugs_dataset.json]

Fonte de dados:
  1. tests/test_bug_*.py — 65+ arquivos, 3718 testes
  2. voice_agent/knowledge_base/ — KB da Lia
  3. CLAUDE.md — rolling log de bugs (seção "ÚLTIMAS 5 LIÇÕES")
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from math import log, sqrt
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
TESTS_DIR = ROOT / "tests"
SCRIPTS_DIR = ROOT / "scripts"

# ── Fix types — meta-padrão extraído dos 65+ bugs ────────────────────────────
FIX_TYPES = {
    "bypass_deterministico":
        "Python intercepta ANTES do LLM (blindagens_deterministicas.py)",
    "enriquecimento_ctx":
        "Python deriva fato de dado estruturado ANTES do LLM (enriquecimento_ctx.py / intent_classifier.py)",
    "filtro_pos_geracao":
        "Python detecta frase proibida no outbound e substitui (_scrub_prohibited)",
    "guard_fsm":
        "Python corrige estado do FSM antes de pedir resposta ao LLM",
    "guard_inbound":
        "Python detecta padrão no inbound do paciente e age antes do LLM",
    "guard_ia_paused":
        "Verifica agent_paused_for_lead antes de chamar responder",
    "infra_kommo_api":
        "Bug de integração Kommo / Meta Graph / Redis",
    "prompt_kb":
        "Regra faltando ou errada no _MASTER_INSTRUCTION.md / knowledge_base/",
    "dedup_loop":
        "Deduplicação / anti-loop no pipeline ou dedup_outbound.py",
    "context_overflow":
        "Contexto muito grande para a API Claude (CTX-GUARD)",
    "outro": "Não classificado",
}

# ── Inferência de fix_type pelo módulo importado no test ─────────────────────
_MODULE_TO_FIX = {
    "blindagens_deterministicas": "bypass_deterministico",
    "deve_responder": "bypass_deterministico",
    "tentar_bypass": "bypass_deterministico",
    "scrub_prohibited": "filtro_pos_geracao",
    "responder": "filtro_pos_geracao",
    "_FAKE_AGENDA": "filtro_pos_geracao",
    "_has_stall": "filtro_pos_geracao",
    "enriquecimento_ctx": "enriquecimento_ctx",
    "intent_classifier": "enriquecimento_ctx",
    "_extract_pre_slots": "enriquecimento_ctx",
    "fsm_conversa": "guard_fsm",
    "agent_paused": "guard_ia_paused",
    "dedup_outbound": "dedup_loop",
    "zep_adapter": "context_overflow",
    "pipeline": "guard_inbound",
    "kommo": "infra_kommo_api",
    "webhook": "infra_kommo_api",
}


# ─────────────────────────────────────────────────────────────────────────────
# Estrutura de dados de um bug
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BugRecord:
    bug_id: str                        # "C-74"
    date_str: str                      # "2026-07-26" (extraído do docstring)
    sintoma: str                       # Descrição resumida do sintoma
    causa_raiz: str                    # Causa raiz (extraída do docstring)
    fix_type: str                      # um dos FIX_TYPES
    modules_changed: list[str]         # módulos alterados
    trigger_phrases: list[str]         # frases que triggeravam o bug
    test_file: str                     # caminho do arquivo de teste
    test_count: int                    # número de testes no arquivo
    origin_lead: str                   # lead_id real (se mencionado)
    full_docstring: str                # docstring completa para TF-IDF

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def bug_date(self) -> Optional[date]:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(self.date_str[:10], fmt).date()
            except ValueError:
                continue
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Extrator de bugs dos test files
# ─────────────────────────────────────────────────────────────────────────────

_DATE_RE = re.compile(
    r"(?:(\d{2}/\d{2}/\d{4})|(\d{4}-\d{2}-\d{2}))"
    r"|(?:\((\d{2}/\d{2}/\d{4})\))"
)
_BUGID_RE = re.compile(r"\bBug\s+(C-\d+)\b|\b(C-\d+)\s+\(", re.IGNORECASE)
_LEAD_RE = re.compile(r"\blead\s+(\d{6,})\b", re.IGNORECASE)


def _extract_strings_from_ast(tree: ast.AST) -> list[str]:
    """Extrai strings literais de um AST Python (casos de teste reais)."""
    strings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.strip()
            # Filtra: strings curtas são labels, longas demais são docstrings
            if 10 < len(v) < 300 and "\n" not in v:
                strings.append(v)
    return strings


def _infer_fix_type(source: str, imports: list[str]) -> str:
    """Infere fix_type pelo que é importado / referenciado no test."""
    for key, ftype in _MODULE_TO_FIX.items():
        if key in source:
            return ftype
    return "outro"


def _extract_date(text: str) -> str:
    """Extrai primeira data encontrada no texto."""
    m = _DATE_RE.search(text)
    if not m:
        return ""
    raw = m.group(1) or m.group(2) or m.group(3) or ""
    if "/" in raw:
        try:
            return datetime.strptime(raw, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return raw
    return raw


def _extract_bug_id(text: str) -> str:
    """Extrai ID do bug (C-NN)."""
    # Primeiro tenta no filename
    fname_match = re.search(r"test_bug_(c\d+)", text, re.IGNORECASE)
    if fname_match:
        return fname_match.group(1).upper().replace("C0", "C-").replace("C", "C-") \
            if "-" not in fname_match.group(1) else fname_match.group(1).upper()
    m = _BUGID_RE.search(text)
    if m:
        return m.group(1) or m.group(2) or ""
    return ""


def extract_bug_from_testfile(test_file: Path) -> Optional[BugRecord]:
    """Lê um test_bug_*.py e extrai BugRecord estruturado."""
    try:
        source = test_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Extrai docstring do módulo
    docstring = ""
    try:
        tree = ast.parse(source)
        doc = ast.get_docstring(tree)
        if doc:
            docstring = doc
    except SyntaxError:
        tree = None

    # Bug ID — do filename primeiro
    fname = test_file.stem  # "test_bug_c74_faq_especialidade"
    bug_id_match = re.search(r"test_bug_(c\d+)", fname, re.IGNORECASE)
    if bug_id_match:
        raw = bug_id_match.group(1).upper()  # "C74"
        bug_id = f"C-{raw[1:]}" if "-" not in raw else raw  # "C-74"
    else:
        bug_id = _extract_bug_id(docstring + fname)

    # Data — do docstring
    date_str = _extract_date(docstring)
    if not date_str:
        # tenta extrair da modificação do arquivo
        mtime = datetime.fromtimestamp(test_file.stat().st_mtime)
        date_str = mtime.strftime("%Y-%m-%d")

    # Lead real
    lead_m = _LEAD_RE.search(docstring)
    origin_lead = lead_m.group(1) if lead_m else ""

    # Sintoma — primeira frase não-vazia do docstring (após título/bug ID)
    sintoma = ""
    if docstring:
        lines = [l.strip() for l in docstring.splitlines() if l.strip()]
        for line in lines:
            if not re.match(r"^Bug\s+C-\d+|^Pytest|^Fix|^Causa", line, re.IGNORECASE):
                sintoma = line[:200]
                break
        if not sintoma and lines:
            sintoma = lines[0][:200]

    # Causa raiz — busca padrão "Causa raiz:"
    causa = ""
    m = re.search(r"Causa\s+raiz[:\s]+(.+?)(?:\n\n|\Z)", docstring, re.DOTALL | re.IGNORECASE)
    if m:
        causa = m.group(1).strip()[:300]

    # Fix type — por importações e referências
    fix_type = _infer_fix_type(source, [])

    # Módulos alterados — pelos imports no test
    modules = []
    for imp_match in re.finditer(r"from\s+voice_agent\.(\w+)|import\s+voice_agent\.(\w+)", source):
        mod = imp_match.group(1) or imp_match.group(2)
        if mod and mod not in modules:
            modules.append(mod)

    # Frases trigger — strings literais do test (casos reais)
    trigger_phrases = []
    if tree:
        all_strings = _extract_strings_from_ast(tree)
        # Filtra: parece mensagem de paciente ou da Lia (em PT-BR, >15 chars)
        for s in all_strings:
            if any(c in s for c in "aeiouáéíóúãõ") and len(s) > 15:
                trigger_phrases.append(s)

    # Conta testes
    test_count = len(re.findall(r"^\s+def test_", source, re.MULTILINE))

    return BugRecord(
        bug_id=bug_id,
        date_str=date_str,
        sintoma=sintoma,
        causa_raiz=causa,
        fix_type=fix_type,
        modules_changed=modules,
        trigger_phrases=trigger_phrases[:20],  # máx 20 por bug
        test_file=str(test_file.relative_to(ROOT)),
        test_count=test_count,
        origin_lead=origin_lead,
        full_docstring=docstring[:800],
    )


def load_all_bugs(tests_dir: Path = TESTS_DIR) -> list[BugRecord]:
    """Carrega todos os BugRecords dos test_bug_*.py."""
    records = []
    for f in sorted(tests_dir.glob("test_bug_*.py")):
        rec = extract_bug_from_testfile(f)
        if rec:
            records.append(rec)
    # Ordena por data (mais recente primeiro)
    records.sort(key=lambda r: r.date_str or "0000", reverse=True)
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Motor de similaridade TF-IDF simples (sem dependências externas)
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokeniza texto PT-BR simples — palavras lowercase, sem pontuação."""
    return re.findall(r"[a-záéíóúãõâêîôûçàèìòù]+", text.lower())


def _build_tfidf(docs: list[str]) -> tuple[list[dict], set]:
    """Constrói TF-IDF para lista de documentos.
    Retorna: (lista de {term: tf-idf}, vocabulário)
    """
    # Term frequency por doc
    tf_docs = []
    all_terms = set()
    for doc in docs:
        tokens = _tokenize(doc)
        tf = defaultdict(float)
        for t in tokens:
            tf[t] += 1
        total = max(len(tokens), 1)
        tf_docs.append({t: c / total for t, c in tf.items()})
        all_terms.update(tf.keys())

    # Document frequency
    df = defaultdict(int)
    for tf in tf_docs:
        for t in tf:
            df[t] += 1

    n = max(len(docs), 1)
    # TF-IDF
    tfidf_docs = []
    for tf in tf_docs:
        tfidf = {t: v * log(n / df[t] + 1) for t, v in tf.items()}
        tfidf_docs.append(tfidf)

    return tfidf_docs, all_terms


def _cosine(a: dict, b: dict) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    norm_a = sqrt(sum(v * v for v in a.values()))
    norm_b = sqrt(sum(v * v for v in b.values()))
    if norm_a * norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_similar_bugs(query: str, bugs: list[BugRecord], top_k: int = 5) -> list[tuple[BugRecord, float]]:
    """Encontra bugs mais similares ao texto de query (TF-IDF cosine)."""
    docs = [f"{r.sintoma} {r.causa_raiz} {r.full_docstring}" for r in bugs]
    docs.append(query)  # query como último doc

    tfidf_docs, _ = _build_tfidf(docs)
    query_vec = tfidf_docs[-1]
    bug_vecs = tfidf_docs[:-1]

    scored = [(bug, _cosine(query_vec, vec)) for bug, vec in zip(bugs, bug_vecs)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(b, s) for b, s in scored[:top_k] if s > 0.01]


# ─────────────────────────────────────────────────────────────────────────────
# Detector de recorrências
# ─────────────────────────────────────────────────────────────────────────────

# Root causes meta-padrão (para clustering)
_ROOT_CAUSE_PATTERNS = {
    "llm_perguntou_derivavel": [
        "qual médico", "qual turno", "qual unidade", "qual convênio",
        "perguntou turno", "perguntou médico", "derivável", "já sabia",
        "redundant", "perguntar novamente", "criança", "pediatria",
    ],
    "stall_hesitacao": [
        "deixa eu consultar", "reconferir", "volto em 1 minuto",
        "vou buscar", "agenda fora do ar", "medware instável",
        "hesitação", "stall", "loop",
    ],
    "filtro_sem_guarda": [
        "loop infinito", "mesmo turno", "fallback repetível",
        "guarda anti-loop", "sem guarda", "loop circular",
    ],
    "ia_responde_quando_nao_deveria": [
        "ATENDIMENTO HUMANO", "Desativado", "agent_paused", "salesbot",
        "continua respondendo", "ignora desativado",
    ],
    "data_dia_semana_errado": [
        "dia da semana", "inventou", "sexta", "quinta", "quarta",
        "data errada", "calendar", "bug C-35",
    ],
    "ctx_overflow": [
        "context length", "overflow", "BadRequestError 400",
        "máximo de contexto", "C-56", "token",
    ],
    "slot_ocupado_ofertado": [
        "slot ocupado", "horário ocupado", "já marcado", "COUNT(*)",
        "duplicata", "agenda errada",
    ],
}


def detect_recurrences(bugs: list[BugRecord]) -> dict[str, list[BugRecord]]:
    """Agrupa bugs pelo root cause meta-padrão."""
    clusters: dict[str, list[BugRecord]] = defaultdict(list)
    for bug in bugs:
        text = f"{bug.sintoma} {bug.causa_raiz} {bug.full_docstring}".lower()
        matched = False
        for cluster_name, keywords in _ROOT_CAUSE_PATTERNS.items():
            if sum(1 for kw in keywords if kw.lower() in text) >= 2:
                clusters[cluster_name].append(bug)
                matched = True
                break
        if not matched:
            clusters["outros"].append(bug)
    return dict(clusters)


# ─────────────────────────────────────────────────────────────────────────────
# Gerador de código — filtro pós-geração
# ─────────────────────────────────────────────────────────────────────────────

def generate_filter_code(
    bug_id: str,
    descricao: str,
    frases_proibidas: list[str],
    substituir_por: str,
    condicao_ctx: str = "",
) -> tuple[str, str]:
    """Gera (código_filtro, codigo_pytest) para um novo bug do tipo filtro_pos_geracao.

    Args:
        bug_id: "C-103"
        descricao: "Lia pergunta turno quando tem medico+unidade"
        frases_proibidas: ["Qual turno funciona", "manhã ou tarde", "turno preferido"]
        substituir_por: Texto de substituição seguro
        condicao_ctx: código Python de condição sobre ctx, ex: "bool(ctx.get('known',{}).get('medico'))"
    """
    bid = bug_id.upper().replace("C ", "C-").strip()
    varname = bid.lower().replace("-", "_")  # "c_103"
    const_name = f"_FRASES_PROIBIDAS_{varname.upper()}"
    func_name = f"_viola_bug_{varname}"
    today = date.today().strftime("%d/%m/%Y")

    # Regex patterns a partir das frases proibidas
    patterns = []
    for frase in frases_proibidas:
        # Escapa e transforma em regex flexível
        escaped = re.escape(frase)
        # Deixa espaços flexíveis
        escaped = escaped.replace(r"\ ", r"\s+")
        patterns.append(escaped)

    regex_str = "|".join(f"(?:{p})" for p in patterns)

    # ── Código do filtro ─────────────────────────────────────────────────────
    cond_snippet = ""
    if condicao_ctx:
        cond_snippet = f"\n    # Condição de contexto: só bloqueia quando {condicao_ctx}\n    if not ({condicao_ctx}):\n        return None"

    codigo_filtro = f'''
# ─── Bug {bid} ({today}) ─────────────────────────────────────────────────────
# {descricao}
{const_name} = re.compile(
    r"(?:{regex_str})",
    re.IGNORECASE,
)

def {func_name}(text: str, ctx: dict) -> "str | None":
    """{descricao} — Bug {bid}.
    Retorna substituição se violação detectada, None se OK."""{cond_snippet}
    if {const_name}.search(text):
        log.warning("[{bid}] frase proibida detectada: %r", text[:120])
        return (
            "{substituir_por}"
        )
    return None
'''

    # ── Código do pytest ─────────────────────────────────────────────────────
    test_cases = "\n".join(
        f'''    def test_bloqueia_{i+1}(self):
        ctx = {{"found": True, "known": {{}}}}
        r = {func_name}("{frase}", ctx)
        assert r is not None, "Bug {bid}: frase não bloqueada: {repr(frase)}"
'''
        for i, frase in enumerate(frases_proibidas)
    )

    codigo_pytest = f'''"""
Pytest Bug {bid} — {descricao}

Gerado automaticamente por scripts/bug_history_analyzer.py em {today}.
"""
import pytest
# from voice_agent.blindagens_deterministicas import {func_name}
# TODO: mover {func_name} para blindagens_deterministicas.py antes de rodar


# ── Deve bloquear frases proibidas ───────────────────────────────────────────

class TestBloqueiaFrasesProibidas:

{test_cases}

# ── Não deve bloquear frases normais ─────────────────────────────────────────

class TestNaoBloqueiaFrasesNormais:

    def test_frase_ok_1(self):
        ctx = {{"found": True, "known": {{}}}}
        r = {func_name}("Tenho 2 horários disponíveis para você", ctx)
        assert r is None, "Frase normal foi bloqueada incorretamente"

    def test_frase_ok_2(self):
        ctx = {{"found": True, "known": {{}}}}
        r = {func_name}("Qual o melhor horário para você?", ctx)
        assert r is None
'''

    return codigo_filtro.strip(), codigo_pytest.strip()


def generate_enrichment_code(
    bug_id: str,
    descricao: str,
    campo_derivado: str,
    fonte: str,
    regra_python: str,
) -> str:
    """Gera código para enriquecimento_ctx.py quando LLM pergunta algo derivável.

    Args:
        bug_id: "C-103"
        descricao: "LLM perguntou médico quando motivo='estrabismo' já definia Karla"
        campo_derivado: "medico"
        fonte: "motivo"
        regra_python: "if 'estrabismo' in (known.get('motivo') or '').lower(): return 'Karla'"
    """
    bid = bug_id.upper()
    today = date.today().strftime("%d/%m/%Y")

    return f'''
    # ── Bug {bid} ({today}) — {descricao} ──
    # Deriva '{campo_derivado}' de '{fonte}' sem perguntar ao LLM
    if not known.get("{campo_derivado}"):
        _{campo_derivado}_src = (known.get("{fonte}") or "").strip()
        if _{campo_derivado}_src:
            # {regra_python}
            {regra_python}
'''.rstrip()


# ─────────────────────────────────────────────────────────────────────────────
# Relatório temporal
# ─────────────────────────────────────────────────────────────────────────────

def relatorio_temporal(bugs: list[BugRecord], periodo: str = "semana") -> str:
    """Gera relatório de bugs por período temporal."""
    hoje = date.today()
    if periodo == "dia":
        cutoff = hoje - timedelta(days=1)
        label = "ÚLTIMAS 24H"
    elif periodo == "semana":
        cutoff = hoje - timedelta(days=7)
        label = "ÚLTIMA SEMANA"
    elif periodo == "mes":
        cutoff = hoje - timedelta(days=30)
        label = "ÚLTIMO MÊS"
    else:
        cutoff = date(2000, 1, 1)
        label = "TOTAL"

    periodo_bugs = [b for b in bugs if (b.bug_date or date(2000, 1, 1)) >= cutoff]

    lines = [
        f"\n{'='*65}",
        f"  RELATÓRIO DE BUGS — {label}",
        f"  Período: {cutoff.strftime('%d/%m/%Y')} → {hoje.strftime('%d/%m/%Y')}",
        f"  Total dataset: {len(bugs)} bugs | Período: {len(periodo_bugs)} bugs",
        f"{'='*65}\n",
    ]

    if not periodo_bugs:
        lines.append("  Nenhum bug no período.")
        return "\n".join(lines)

    # Por fix_type
    by_type: dict[str, list[BugRecord]] = defaultdict(list)
    for b in periodo_bugs:
        by_type[b.fix_type].append(b)

    lines.append("── Por tipo de fix:")
    for ftype, blist in sorted(by_type.items(), key=lambda x: -len(x[1])):
        pct = len(blist) * 100 // len(periodo_bugs)
        ids = ", ".join(b.bug_id for b in blist)
        lines.append(f"  {ftype:30s} {len(blist):3d} ({pct:2d}%)  [{ids}]")
        lines.append(f"    └ {FIX_TYPES.get(ftype, '')}")

    # Meta-padrão dominante
    lines.append("\n── Meta-padrão dominante:")
    top_type = max(by_type.items(), key=lambda x: len(x[1]))[0]
    lines.append(f"  {top_type} ({len(by_type[top_type])} / {len(periodo_bugs)} bugs)")
    if top_type in ("bypass_deterministico", "filtro_pos_geracao", "enriquecimento_ctx", "guard_fsm"):
        lines.append(
            "  → LLM foi chamado para algo que Python pode calcular/bloquear."
        )
        lines.append(
            "  → Recomendação: auditar todos os campos que o LLM pode perguntar"
        )
        lines.append(
            "    e verificar se cada um tem derivação Python em enriquecimento_ctx.py"
        )

    # Lista cronológica
    lines.append("\n── Bugs no período (mais recente primeiro):")
    for b in sorted(periodo_bugs, key=lambda x: x.date_str, reverse=True):
        lines.append(
            f"  {b.bug_id:8s} {b.date_str[:10]}  [{b.fix_type}]"
        )
        lines.append(f"    {b.sintoma[:80]}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def cmd_relatorio(args: list[str]) -> None:
    periodo = "semana"
    for a in args:
        if a in ("dia", "semana", "mes", "total"):
            periodo = a
    bugs = load_all_bugs()
    print(relatorio_temporal(bugs, periodo))


def cmd_buscar(args: list[str]) -> None:
    if not args:
        print("Uso: buscar <texto do sintoma>")
        return
    query = " ".join(args)
    bugs = load_all_bugs()
    resultados = find_similar_bugs(query, bugs, top_k=5)
    print(f"\n── Bugs similares a: {repr(query[:60])}\n")
    if not resultados:
        print("  Nenhum resultado encontrado.")
        return
    for bug, score in resultados:
        print(f"  {bug.bug_id:8s} [{score:.2f}]  {bug.date_str[:10]}  [{bug.fix_type}]")
        print(f"    {bug.sintoma[:100]}")
        if bug.causa_raiz:
            print(f"    Causa: {bug.causa_raiz[:100]}")
        print()
    print("── Fix sugerido com base nos bugs mais similares:")
    if resultados:
        top_fix = resultados[0][0].fix_type
        print(f"  {top_fix}: {FIX_TYPES.get(top_fix, '')}")


def cmd_recorrencias(args: list[str]) -> None:
    bugs = load_all_bugs()
    clusters = detect_recurrences(bugs)
    print(f"\n── Recorrências detectadas ({len(bugs)} bugs total)\n")
    for cluster, blist in sorted(clusters.items(), key=lambda x: -len(x[1])):
        if cluster == "outros":
            continue
        ids = ", ".join(b.bug_id for b in blist)
        print(f"  ROOT CAUSE: {cluster} ({len(blist)} bugs)")
        print(f"  Bugs: {ids}")
        # Tendência: crescendo ou diminuindo?
        datas = [b.bug_date for b in blist if b.bug_date]
        if len(datas) >= 2:
            recente = sum(1 for d in datas if d >= date.today() - timedelta(days=30))
            print(f"  Últimos 30 dias: {recente} / {len(blist)} total", end="")
            if recente >= len(blist) // 2 and len(blist) > 2:
                print("  ⚠️  CRESCENDO — não resolvido na raiz")
            else:
                print()
        print()


def cmd_gerar_filtro(args: list[str]) -> None:
    """Parse simples dos args para gerar código de filtro."""
    bug_id = "C-XXX"
    descricao = "Descrição do bug"
    frases: list[str] = []
    substituir = "Vou verificar os horários disponíveis para você."
    condicao = ""

    i = 0
    while i < len(args):
        if args[i] == "--bug-id" and i + 1 < len(args):
            bug_id = args[i + 1]; i += 2
        elif args[i] == "--descricao" and i + 1 < len(args):
            descricao = args[i + 1]; i += 2
        elif args[i] == "--substituir" and i + 1 < len(args):
            substituir = args[i + 1]; i += 2
        elif args[i] == "--condicao" and i + 1 < len(args):
            condicao = args[i + 1]; i += 2
        elif args[i] == "--frases-proibidas":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                frases.append(args[i]); i += 1
        else:
            i += 1

    if not frases:
        print("Erro: --frases-proibidas é obrigatório.")
        print("Exemplo:")
        print('  python scripts/bug_history_analyzer.py gerar-filtro \\')
        print('      --bug-id C-103 \\')
        print('      --descricao "Lia pergunta turno quando já tem medico+unidade" \\')
        print('      --frases-proibidas "Qual turno funciona melhor" "manhã ou tarde" \\')
        print('      --substituir "Deixa eu verificar os horários disponíveis"')
        return

    filtro_code, pytest_code = generate_filter_code(
        bug_id=bug_id,
        descricao=descricao,
        frases_proibidas=frases,
        substituir_por=substituir,
        condicao_ctx=condicao,
    )

    print(f"\n{'='*65}")
    print(f"  CÓDIGO GERADO — Bug {bug_id}")
    print(f"{'='*65}")
    print("\n── Adicionar em voice_agent/blindagens_deterministicas.py:\n")
    print(filtro_code)
    print(f"\n{'─'*65}")
    print(f"\n── Salvar em tests/test_bug_{bug_id.lower().replace('-', '_')}.py:\n")
    print(pytest_code)

    # Salva os arquivos
    out_filter = SCRIPTS_DIR / f"_gerado_{bug_id.lower().replace('-','_')}_filtro.py"
    out_pytest = TESTS_DIR / f"test_bug_{bug_id.lower().replace('-','_')}_gerado.py"
    out_filter.write_text(filtro_code, encoding="utf-8")
    out_pytest.write_text(pytest_code, encoding="utf-8")
    print(f"\n✅ Filtro salvo em: {out_filter}")
    print(f"✅ Pytest salvo em: {out_pytest}")
    print("\n⚠️  TODO:")
    print(f"  1. Mover filtro para blindagens_deterministicas.py")
    print(f"  2. Adicionar chamada em tentar_bypass_deterministico() ou _scrub_prohibited()")
    print(f"  3. Rodar: python -m pytest {out_pytest}")


def cmd_exportar(args: list[str]) -> None:
    """Exporta dataset completo como JSON."""
    output = "bugs_dataset.json"
    for a in args:
        if not a.startswith("--"):
            output = a
    bugs = load_all_bugs()
    data = {
        "generated": date.today().isoformat(),
        "total": len(bugs),
        "fix_type_summary": {
            ftype: len([b for b in bugs if b.fix_type == ftype])
            for ftype in FIX_TYPES
        },
        "bugs": [b.as_dict() for b in bugs],
    }
    out_path = ROOT / output
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Dataset exportado: {out_path} ({len(bugs)} bugs)")

    # Sumário dos padrões
    print("\n── Fix type distribution:")
    for ftype, count in sorted(data["fix_type_summary"].items(), key=lambda x: -x[1]):
        if count > 0:
            pct = count * 100 // len(bugs)
            bar = "█" * (count // max(1, len(bugs) // 20))
            print(f"  {ftype:30s} {count:3d} ({pct:2d}%) {bar}")


def cmd_ajuda() -> None:
    print(__doc__)


COMMANDS = {
    "relatorio": cmd_relatorio,
    "buscar": cmd_buscar,
    "recorrencias": cmd_recorrencias,
    "gerar-filtro": cmd_gerar_filtro,
    "exportar": cmd_exportar,
    "ajuda": lambda _: cmd_ajuda(),
    "--help": lambda _: cmd_ajuda(),
    "-h": lambda _: cmd_ajuda(),
}


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        cmd_ajuda()
        return
    cmd = argv[0]
    rest = argv[1:]
    fn = COMMANDS.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"Comando desconhecido: {cmd!r}")
        print(f"Disponíveis: {', '.join(COMMANDS)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
