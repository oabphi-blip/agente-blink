"""
Task #418 (20/07/2026) — Cliente SQL direto do Medware.

Descoberta: Medware expõe endpoint `/api/Medware/ConsultaDB/Executar`
que aceita queries SELECT/WITH read-only. Muito mais preciso que a REST
tradicional pra:

- Listar slots livres com dia da semana correto (mata bug C-31/C-53
  "Karla sábado" / "Águas Claras quinta errada")
- Buscar paciente por telefone/CPF com match exato (elimina duplicação
  do bug C-27 Samuel/Pryscilla)
- Detectar duplicatas do bug C-59 (Eloah 11x mesmo slot)
- Fornecer histórico clínico REAL pra Lia (anti-alucinação)

Todas as datas/horas voltam em TZ BRASÍLIA local (America/Sao_Paulo).
Zero conversão UTC — o Medware é o servidor local da clínica, hora é
sempre local. Fonte da verdade.

Segurança endpoint:
- Só SELECT/WITH (server-side, não precisamos validar)
- Uma instrução por request
- Sem GEN_ID, NEXT VALUE FOR, RDB$SET_CONTEXT

Env vars:
- MEDWARE_SQL_BASE_URL — padrão https://medware.blinkoftalmologia.com.br/api
- MEDWARE_USER, MEDWARE_PASSWORD — mesmas credenciais do medware.py

Cache:
- Token JWT cacheado em memória (thread-safe), renova quando faltam <5min
- Consultas de agenda cacheadas em Redis 60s (evita hammering Medware)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Optional

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://medware.blinkoftalmologia.com.br/api"
_HTTP_TIMEOUT = 15
_TOKEN_RENOVAR_ANTES_S = 300  # renova quando faltam <5min

# Cache de token em memória, thread-safe
_token_lock = threading.Lock()
_token_cache: dict[str, Any] = {"token": None, "exp": 0.0}


class MedwareSQLError(Exception):
    """Erro genérico do endpoint SQL (400 do servidor, timeout, parse falha)."""


def _base_url() -> str:
    return (os.environ.get("MEDWARE_SQL_BASE_URL") or _DEFAULT_BASE).rstrip("/")


def _credenciais() -> tuple[str, str]:
    user = os.environ.get("MEDWARE_USER") or os.environ.get("MEDWARE_LOGIN") or ""
    senha = os.environ.get("MEDWARE_PASSWORD") or os.environ.get("MEDWARE_SENHA") or ""
    return user, senha


def _jwt_exp(token: str) -> Optional[float]:
    """Extrai `exp` (epoch) do payload JWT sem validar assinatura."""
    try:
        import base64
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp") or 0)
    except Exception:  # noqa: BLE001
        return None


def _http_post(url: str, headers: dict, body: dict) -> tuple[int, Any]:
    """POST com body JSON. Retorna (status, json_ou_texto)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
    except Exception as e:
        raise MedwareSQLError(f"http_erro: {e}") from e
    try:
        return code, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return code, {"raw": raw}


def _renovar_token() -> str:
    """Chama /Acesso/login e cacheia token. Thread-safe. Retorna token."""
    user, senha = _credenciais()
    if not user or not senha:
        raise MedwareSQLError("MEDWARE_USER/MEDWARE_PASSWORD ausentes no env")
    url = f"{_base_url()}/Acesso/login"
    code, resp = _http_post(
        url,
        {"Content-Type": "application/json"},
        {"identificacao": user, "senha": senha},
    )
    if code >= 400 or not isinstance(resp, dict):
        raise MedwareSQLError(f"login falhou HTTP {code}: {resp}")
    token = resp.get("token")
    if not token:
        raise MedwareSQLError(f"login sem token: {resp}")
    exp = _jwt_exp(token) or (time.time() + 3600)
    with _token_lock:
        _token_cache["token"] = token
        _token_cache["exp"] = exp
    log.info(
        "medware_sql: token renovado, exp em %.0fs",
        exp - time.time(),
    )
    return token


def obter_token() -> str:
    """Retorna token válido — do cache ou renovando."""
    with _token_lock:
        tok = _token_cache.get("token")
        exp = _token_cache.get("exp") or 0
    if tok and time.time() < (exp - _TOKEN_RENOVAR_ANTES_S):
        return tok
    return _renovar_token()


def executar(query: str) -> dict:
    """Executa uma consulta SELECT no Medware. Retorna dict:
    {colunas: [{coluna, tipo}], dados: [{col:val}], limiteRegistros, resultadoTruncado}
    Levanta MedwareSQLError se HTTP >= 400 ou JSON inválido.
    """
    q = (query or "").strip()
    if not q:
        raise MedwareSQLError("query vazia")
    lower = q.lower().lstrip()
    if not (lower.startswith("select") or lower.startswith("with")):
        raise MedwareSQLError("apenas SELECT/WITH permitidos")

    token = obter_token()
    url = f"{_base_url()}/Medware/ConsultaDB/Executar"
    code, resp = _http_post(
        url,
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        {"query": q},
    )
    if code == 401:
        # token expirou entre chamadas — renova e tenta 1x
        token = _renovar_token()
        code, resp = _http_post(
            url,
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            {"query": q},
        )
    if code >= 400:
        raise MedwareSQLError(f"HTTP {code}: {str(resp)[:300]}")
    if not isinstance(resp, dict):
        raise MedwareSQLError(f"resposta não-json: {str(resp)[:200]}")
    return resp


def rows(resposta: dict) -> list[dict]:
    """Extrai lista de dict das linhas da resposta. Trims strings."""
    dados = resposta.get("dados") or []
    out = []
    for r in dados:
        if not isinstance(r, dict):
            continue
        limpo = {}
        for k, v in r.items():
            key = k.strip() if isinstance(k, str) else k
            if isinstance(v, str):
                limpo[key] = v.strip()
            else:
                limpo[key] = v
        out.append(limpo)
    return out


# ============================================================================
# QUERIES OPERACIONAIS — funções especializadas
# ============================================================================

# Códigos mapeados (mesma tabela do tools_lia.py::COD_MEDICO_POR_NOME)
COD_MEDICO_KARLA = 12080
COD_MEDICO_FABRICIO = 12081
COD_UNIDADE_ASA_NORTE = 5
COD_UNIDADE_AGUAS_CLARAS = 3


def paciente_por_telefone(celular: str) -> list[dict]:
    """Busca paciente por celular (10 ou 11 dígitos). Retorna lista com
    CODPACIENTE, NOME, DATANASC. Match exato usando LIKE %tel% pra tolerar
    DDD/formatos diferentes.
    """
    cel = "".join(ch for ch in (celular or "") if ch.isdigit())
    if len(cel) < 10:
        return []
    # Firebird SQL: LIKE case-sensitive; agenda usa NUMEROCELULAR SEM DDI
    tail = cel[-9:] if len(cel) >= 9 else cel
    q = (
        f"SELECT FIRST 5 CODPACIENTE, NOME, DATANASC "
        f"FROM PACIENTE WHERE NUMEROCELULAR CONTAINING '{tail}' "
        f"OR TELEFONE CONTAINING '{tail}' "
        f"ORDER BY DATAULTMOVIMENTO DESC"
    )
    try:
        return rows(executar(q))
    except MedwareSQLError as e:
        # Coluna NUMEROCELULAR pode não existir com esse nome — fallback pra NOME parcial
        log.warning("paciente_por_telefone erro schema: %s", e)
        return []


def agendamentos_por_data(data_iso: str, cod_medico: int, cod_unidade: int) -> list[dict]:
    """Retorna agendamentos ocupados num dia específico, médico+unidade.
    Todas as datas em TZ local (Brasília, sem conversão).
    """
    q = (
        f"SELECT CODAGENDAMENTO, CODPACIENTE, DATAHORAAGENDADA "
        f"FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE)='{data_iso}' "
        f"ORDER BY DATAHORAAGENDADA"
    )
    try:
        return rows(executar(q))
    except MedwareSQLError as e:
        log.warning("agendamentos_por_data erro: %s", e)
        return []


def agendamentos_paciente(cod_paciente: int, limit: int = 5) -> list[dict]:
    """Histórico de agendamentos do paciente (últimos N)."""
    q = (
        f"SELECT FIRST {int(limit)} "
        f"a.CODAGENDAMENTO, a.DATAHORAAGENDADA, a.CODMEDICO, m.NOME AS MEDICO "
        f"FROM AGENDAMENTO a LEFT JOIN MEDICO m ON m.CODMEDICO=a.CODMEDICO "
        f"WHERE a.CODPACIENTE={int(cod_paciente)} "
        f"ORDER BY a.DATAHORAAGENDADA DESC"
    )
    try:
        return rows(executar(q))
    except MedwareSQLError as e:
        log.warning("agendamentos_paciente erro: %s", e)
        return []


def contar_slots_ocupados_hora(cod_medico: int, cod_unidade: int, data_hora_iso: str) -> int:
    """Retorna quantos PACIENTES DISTINTOS estão no slot.

    CRÍTICO (descoberto 20/07/2026): no Medware, 1 consulta = múltiplos
    registros AGENDAMENTO (um por procedimento/exame). Todos compartilham
    DATAHORAAGENDADA e CODPACIENTE. Usar COUNT(DISTINCT CODPACIENTE) dá
    o número REAL de consultas naquele slot — independente de quantos
    exames a paciente vai fazer.

    Ex: slot 20/07 11:30 tem 56 registros (18 exames × 3 pacientes) →
    retorna 3 (pacientes distintos).
    """
    d, h = data_hora_iso.split("T") if "T" in data_hora_iso else (data_hora_iso, "00:00:00")
    if len(h) == 5:
        h = h + ":00"
    hora_h, hora_m, _ = h.split(":")
    q = (
        f"SELECT COUNT(DISTINCT CODPACIENTE) AS QTD FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE)='{d}' "
        f"AND EXTRACT(HOUR FROM DATAHORAAGENDADA)={int(hora_h)} "
        f"AND EXTRACT(MINUTE FROM DATAHORAAGENDADA)={int(hora_m)}"
    )
    try:
        r = rows(executar(q))
        return int(r[0].get("QTD", 0)) if r else 0
    except MedwareSQLError as e:
        log.warning("contar_slots_ocupados_hora erro: %s", e)
        return 0


# Alias retro-compatível — 'duplicata' era interpretação errada; cada
# 'duplicata' é 1 procedimento do agrupador da consulta. Mantido pra não
# quebrar chamadores existentes.
def contar_duplicatas_slot(cod_medico: int, cod_unidade: int, data_hora_iso: str) -> int:
    """DEPRECATED — usar contar_slots_ocupados_hora."""
    return contar_slots_ocupados_hora(cod_medico, cod_unidade, data_hora_iso)


def existe_agendamento(
    cod_medico: int, cod_unidade: int,
    data_hora_iso: str, cod_paciente: int = 0,
) -> Optional[int]:
    """Retorna CODAGENDAMENTO do PAI existente pra
    (medico+unidade+data+hora [+paciente opcional]) OU None se slot livre.

    Fix 20/07/2026: filtra CODAGENDAMENTOPAI IS NULL — só o PAI da consulta,
    não os N filhos/exames. Sem esse filtro, cada consulta parecia N
    'duplicatas' e o dedup bloqueava agendamento legítimo.

    Uso principal em criar_agendamento: chamar ANTES de POST. Se existe,
    retornar o mesmo CODAGENDAMENTO em vez de gravar duplicata.

    Se cod_paciente > 0, checa também por paciente (evita bloquear paciente
    diferente no mesmo slot compartilhado — raro).
    """
    d, h = data_hora_iso.split("T") if "T" in data_hora_iso else (data_hora_iso, "00:00:00")
    if len(h) == 5:
        h = h + ":00"
    hora_h, hora_m, _ = h.split(":")
    filtro_pac = f" AND CODPACIENTE={int(cod_paciente)}" if cod_paciente else ""
    # Fix 20/07/2026: dedup por PACIENTE, não por CODAGENDAMENTO.
    # Semântica: "existe alguma consulta desse paciente neste slot?"
    # Se cod_paciente=0, "alguma consulta de qualquer paciente".
    q = (
        f"SELECT FIRST 1 CODAGENDAMENTO FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE)='{d}' "
        f"AND EXTRACT(HOUR FROM DATAHORAAGENDADA)={int(hora_h)} "
        f"AND EXTRACT(MINUTE FROM DATAHORAAGENDADA)={int(hora_m)}"
        f"{filtro_pac} "
        f"ORDER BY CODAGENDAMENTO ASC"
    )
    try:
        r = rows(executar(q))
        if r:
            return int(r[0].get("CODAGENDAMENTO", 0)) or None
        return None
    except MedwareSQLError as e:
        log.warning("existe_agendamento erro: %s", e)
        return None


def listar_grade_medico(cod_medico: int, cod_unidade: int) -> list[dict]:
    """Retorna a grade semanal do médico+unidade (HORARIOAGENDA ativos).

    Cada linha: {CODHORARIOAGENDA, CODAGENDA, DIASEMANA, HORAINICIO, HORAFIM,
                 INTERVALO, DATAINICIO, DATAFIM}.

    DIASEMANA (convenção Medware): 1=domingo, 2=segunda, 3=terça, 4=quarta,
    5=quinta, 6=sexta, 7=sábado. STATUS=-1 significa ativo (não confundir
    com STATUS=1 que é INATIVO nesse schema).
    """
    q = (
        f"SELECT DISTINCT h.CODHORARIOAGENDA, h.CODAGENDA, h.DIASEMANA, "
        f"h.HORAINICIO, h.HORAFIM, h.INTERVALO, h.DATAINICIO, h.DATAFIM "
        f"FROM MEDICO_PROCED_HORARIOAGENDA mp "
        f"JOIN HORARIOAGENDA h ON h.CODHORARIOAGENDA=mp.CODHORARIOAGENDA "
        f"JOIN AGENDA a ON a.CODAGENDA=h.CODAGENDA "
        f"WHERE mp.CODMEDICO={int(cod_medico)} "
        f"AND a.CODUNIDADE={int(cod_unidade)} "
        f"AND h.STATUS=-1 AND a.STATUS=-1 "
        f"ORDER BY h.DIASEMANA, h.HORAINICIO"
    )
    try:
        return rows(executar(q))
    except MedwareSQLError as e:
        log.warning("listar_grade_medico erro: %s", e)
        return []


def _isoweekday_para_diasemana_medware(iso: int) -> int:
    """Python isoweekday (1=seg..7=dom) → Medware DIASEMANA (1=dom..7=sab)."""
    return (iso % 7) + 1


def _hhmm_para_minutos(hora: str) -> int:
    """'08:30' ou '08:30:00' → 510."""
    p = hora.split(":")
    return int(p[0]) * 60 + int(p[1])


def _minutos_para_hhmm(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def listar_slots_livres(
    cod_medico: int,
    cod_unidade: int,
    dias: int = 14,
    data_inicio: Optional[str] = None,
    n_slots: int = 1,
) -> list[dict]:
    """Slots LIVRES do médico+unidade nos próximos N dias.

    Estratégia:
    1. Carrega grade semanal (HORARIOAGENDA + MEDICO_PROCED_HORARIOAGENDA)
    2. Carrega TODOS agendamentos ocupados no período
    3. Expande grade em slots concretos por dia (data + hora)
    4. Filtra ocupados
    5. Se n_slots > 1: verifica que os próximos N-1 slots de 30min também
       estão livres (blocos contíguos para múltiplas consultas seguidas)
    6. Retorna lista ordenada [{data_iso, hora, dia_semana, dow_python}]

    Todas as datas/horas em TZ BRASÍLIA local (Medware é o servidor local
    da clínica, sem conversão). Retorna hora HH:MM formato string.

    dias: quantos dias a partir de hoje (default 14).
    data_inicio: opcional 'YYYY-MM-DD'. Padrão: hoje BRT.
    n_slots: número de slots contíguos de 30min necessários (default 1).
             Usar 2+ quando o paciente precisa de múltiplas consultas
             seguidas (ex: avaliação + exames adicionais).
    """
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    brt = ZoneInfo("America/Sao_Paulo")
    hoje = date.today() if not data_inicio else date.fromisoformat(data_inicio)
    agora_brt = datetime.now(brt)

    grade = listar_grade_medico(cod_medico, cod_unidade)
    if not grade:
        return []

    # Índice: DIASEMANA (Medware) → lista de faixas de horário
    grade_por_dia: dict[int, list[dict]] = {}
    for g in grade:
        dw = int(g.get("DIASEMANA", 0))
        grade_por_dia.setdefault(dw, []).append(g)

    # Ocupados no período — DISTINCT(DATAHORAAGENDADA, CODPACIENTE).
    # Fix 20/07/2026: cada consulta tem N registros (um por procedimento).
    # Contar DISTINCT paciente por slot dá ocupação real independente de
    # quantos exames a paciente vai fazer. Um slot só é ocupado se tem
    # pelo menos 1 paciente distinto marcado nele.
    fim = hoje + timedelta(days=dias)
    q_ocupados = (
        f"SELECT DISTINCT DATAHORAAGENDADA, CODPACIENTE FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE) >= '{hoje.isoformat()}' "
        f"AND CAST(DATAHORAAGENDADA AS DATE) < '{fim.isoformat()}'"
    )
    ocupados: set[tuple[str, str]] = set()
    try:
        for r in rows(executar(q_ocupados)):
            dh = r.get("DATAHORAAGENDADA", "")
            if "T" in dh:
                d, h = dh.split("T")
                ocupados.add((d, h[:5]))
    except MedwareSQLError as e:
        log.warning("listar_slots_livres ocupados erro: %s", e)

    # Expande grade em slots — primeiro monta conjunto completo de LIVRES
    # para permitir verificação de blocos contíguos (n_slots > 1).
    candidatos: list[dict] = []
    livres_set: set[tuple[str, str]] = set()  # (data_iso, hora_str)

    for offset in range(dias):
        dia = hoje + timedelta(days=offset)
        dw_medware = _isoweekday_para_diasemana_medware(dia.isoweekday())
        faixas = grade_por_dia.get(dw_medware, [])
        for faixa in faixas:
            hora_ini = _hhmm_para_minutos(str(faixa.get("HORAINICIO", "")))
            hora_fim = _hhmm_para_minutos(str(faixa.get("HORAFIM", "")))
            intervalo = int(faixa.get("INTERVALO", 30)) or 30
            for m in range(hora_ini, hora_fim, intervalo):
                hora_str = _minutos_para_hhmm(m)
                data_iso = dia.isoformat()

                # Filtra ocupados
                if (data_iso, hora_str) in ocupados:
                    continue

                # Filtra slots no passado (mesmo dia hoje)
                if offset == 0:
                    slot_dt = datetime.combine(dia, datetime.min.time(), tzinfo=brt)
                    slot_dt = slot_dt.replace(hour=m // 60, minute=m % 60)
                    if slot_dt <= agora_brt:
                        continue

                candidatos.append({
                    "data_iso": data_iso,
                    "hora": hora_str,
                    "hora_min": m,
                    "dia_semana": dia.isoweekday(),  # 1=seg..7=dom
                    "diasemana_medware": dw_medware,
                })
                livres_set.add((data_iso, hora_str))

    # Filtro de bloco contíguo: n_slots > 1 exige que os próximos N-1
    # slots de 30min no MESMO DIA também estejam livres.
    if n_slots <= 1:
        livres = [{k: v for k, v in c.items() if k != "hora_min"} for c in candidatos]
    else:
        livres = []
        for c in candidatos:
            data_iso = c["data_iso"]
            inicio_min = c["hora_min"]
            # Verifica slots subsequentes (30min cada)
            bloco_ok = all(
                (data_iso, _minutos_para_hhmm(inicio_min + 30 * i)) in livres_set
                for i in range(1, n_slots)
            )
            if bloco_ok:
                livres.append({k: v for k, v in c.items() if k != "hora_min"})

    return livres


def listar_slots_ocupados_dia(
    cod_medico: int, cod_unidade: int, data_iso: str,
) -> set[tuple[str, str]]:
    """Retorna set de (data, hora) ocupados no dia — pra subtrair da grade
    HORARIOAGENDA e obter slots LIVRES.
    """
    q = (
        f"SELECT DISTINCT DATAHORAAGENDADA FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE)='{data_iso}'"
    )
    try:
        result = set()
        for r in rows(executar(q)):
            dh = r.get("DATAHORAAGENDADA", "")
            if "T" in dh:
                d, h = dh.split("T")
                result.add((d, h[:5]))  # HH:MM
        return result
    except MedwareSQLError as e:
        log.warning("listar_slots_ocupados_dia erro: %s", e)
        return set()


# ============================================================================
# HEALTHCHECK
# ============================================================================

def healthcheck() -> dict:
    """Retorna dict {ok, latencia_ms, versao, ...} pra /admin/healthz."""
    t0 = time.time()
    try:
        r = executar("SELECT FIRST 1 CODPACIENTE FROM PACIENTE")
        return {
            "ok": True,
            "latencia_ms": round((time.time() - t0) * 1000, 1),
            "linhas": len(rows(r)),
            "token_exp_seg": int((_token_cache.get("exp") or 0) - time.time()),
        }
    except MedwareSQLError as e:
        return {"ok": False, "erro": str(e)[:200]}


# ============================================================================
# BUG C-73 (26/07/2026) — SQL CANÔNICO SINGLE-DATE COM CONTAINING
# Requisitos mínimos pra mostrar agenda: médico + unidade + 1 data específica.
# Nome/data_nasc/convênio são coletados DEPOIS que paciente escolher o slot.
# ============================================================================

def _normalizar_para_sql(nome: str) -> str:
    """Remove acentos, uppercase, tira prefixo 'Dr.'/'Dra.' e retorna o PRIMEIRO nome.

    Usado no CONTAINING do Medware (Firebird é case-insensitive mas acento-sensitive).

    Exemplos:
        "Dra. Karla Delalíbera" → "KARLA"
        "Dr. Fabrício Freitas"  → "FABRICIO"
        "Karla"                 → "KARLA"
    """
    if not nome:
        return ""
    nfkd = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    sem_titulo = re.sub(r"\b(Dra?\.?\s*)", "", sem_acento, flags=re.IGNORECASE).strip()
    partes = sem_titulo.upper().split()
    return partes[0] if partes else ""


def _normalizar_unidade_para_sql(nome: str) -> str:
    """Remove acentos e uppercase — mantém o nome COMPLETO da unidade.

    Exemplos:
        "Águas Claras" → "AGUAS CLARAS"
        "Asa Norte"    → "ASA NORTE"
    """
    if not nome:
        return ""
    nfkd = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.strip().upper()


_SQL_HORARIOS_LIVRES_DIA = """\
WITH RECURSIVE HORARIOS (HORARIO) AS (
    SELECT CAST('08:30:00' AS TIME) FROM RDB$DATABASE
    UNION ALL
    SELECT DATEADD(MINUTE, 30, HORARIO)
    FROM HORARIOS
    WHERE HORARIO < CAST('17:30:00' AS TIME)
),
AGENDAMENTOS AS (
    SELECT
        CAST(A.DATAHORAAGENDADA AS TIME) AS HORARIO,
        MAX(CASE WHEN COALESCE(A.BLOQUEADO, 0) <> 0 THEN 1 ELSE 0 END) AS BLOQUEADO,
        MAX(CASE WHEN A.STATUS = -1
                  AND A.CODPACIENTE IS NOT NULL
                  AND A.DATAHORACANCELADO IS NULL
                 THEN 1 ELSE 0 END) AS OCUPADO,
        MAX(CASE WHEN A.STATUS = 0
                  OR A.DATAHORACANCELADO IS NOT NULL
                 THEN 1 ELSE 0 END) AS CANCELADO
    FROM AGENDAMENTO A
    INNER JOIN (
        SELECT CODMEDICO FROM MEDICO
        WHERE NOME CONTAINING '{medico_nome}'
    ) M ON M.CODMEDICO = A.CODMEDICO
    INNER JOIN (
        SELECT CODAGENDA FROM AGENDA
        WHERE DESCRICAO CONTAINING '{unidade_nome}'
    ) AG ON AG.CODAGENDA = A.CODAGENDA
    WHERE CAST(A.DATAHORAAGENDADA AS DATE) = '{data}'
      AND A.CODAGENDAMENTOPAI IS NULL
    GROUP BY CAST(A.DATAHORAAGENDADA AS TIME)
),
TB_AGENDA AS (
    SELECT H.HORARIO,
        CASE
            WHEN COALESCE(A.BLOQUEADO,0)=1 THEN 'BLOQUEADO'
            WHEN COALESCE(A.OCUPADO,0)=1 THEN 'OCUPADO'
            WHEN COALESCE(A.CANCELADO,0)=1 THEN 'CANCELADO'
            ELSE 'LIVRE'
        END AS DISPONIBILIDADE
    FROM HORARIOS H
    LEFT JOIN AGENDAMENTOS A ON A.HORARIO = H.HORARIO
)
SELECT HORARIO FROM TB_AGENDA
WHERE DISPONIBILIDADE IN ('LIVRE', 'CANCELADO')
  AND HORARIO NOT BETWEEN CAST('12:00:00' AS TIME) AND CAST('13:00:00' AS TIME)
ORDER BY HORARIO\
"""


def horarios_livres_dia(
    medico_nome: str,
    unidade_nome: str,
    data_iso: str,
) -> list[str]:
    """Horários LIVRES para médico+unidade num único dia via SQL canônico.

    Usa WITH RECURSIVE pra gerar todos os slots 08:30–17:30 de 30 em 30 min,
    LEFT JOIN com ocupação real (CONTAINING case-insensitive pra médico/unidade),
    filtra BLOQUEADO/OCUPADO, exclui almoço 12:00–13:00.

    Requisito mínimo C-73: médico + unidade + 1 data específica.
    Nome/data_nasc/convênio são coletados DEPOIS que paciente escolher o slot.

    Args:
        medico_nome: nome ou primeiro nome do médico (ex: "Karla", "Dra. Karla Delalíbera").
                     Apenas o primeiro nome é usado no CONTAINING.
        unidade_nome: nome ou parte do nome da unidade (ex: "Águas Claras", "Asa Norte").
                      Acentos são removidos, uppercase aplicado.
        data_iso:    data no formato 'YYYY-MM-DD'.

    Returns:
        Lista de strings 'HH:MM' ordenada cronologicamente. Lista vazia se erro ou sem slots.

    Note:
        C-71: caller deve garantir que unidade_nome é a unidade CORRETA para o dia
        da semana pedido (_inferir_unidade_por_dia em responder.py).
    """
    mn = _normalizar_para_sql(medico_nome)
    un = _normalizar_unidade_para_sql(unidade_nome)
    if not mn or not un or not data_iso:
        log.warning(
            "horarios_livres_dia: parâmetros inválidos mn=%r un=%r data=%r",
            mn, un, data_iso,
        )
        return []
    q = _SQL_HORARIOS_LIVRES_DIA.format(
        medico_nome=mn,
        unidade_nome=un,
        data=data_iso,
    )
    try:
        resp = executar(q)
        result = rows(resp)
        horarios = []
        for r in result:
            h = r.get("HORARIO") or ""
            if isinstance(h, str) and ":" in h:
                horarios.append(h[:5])   # "HH:MM:SS" → "HH:MM"
            elif h:                       # pode ser objeto time
                horarios.append(str(h)[:5])
        log.info(
            "horarios_livres_dia: %d slots para medico=%r unidade=%r data=%s",
            len(horarios), mn, un, data_iso,
        )
        return horarios
    except MedwareSQLError as e:
        log.warning(
            "horarios_livres_dia erro: %s (medico=%r unidade=%r data=%r)",
            e, mn, un, data_iso,
        )
        return []


def slot_ainda_disponivel_sql(
    medico_nome: str,
    unidade_nome: str,
    data_iso: str,
    hora: str,
    dias_alternativos: int = 10,
) -> tuple[bool, list[dict]]:
    """Re-verifica em tempo real se slot ainda está livre via SQL (anti race-condition).

    Problema: Lia consulta Medware → oferta slot → paciente demora horas → outro
    agendamento ocupa o slot → Lia tentava gravar slot inexistente, causando
    agendamento em horário ocupado (Bug 02/08/2026, leads 24400924 Danielle e outros).

    Solução: antes de gravar, consulta horarios_livres_dia para a data específica
    e confirma se a hora ainda aparece na lista. Se não, busca alternativas.

    Args:
        medico_nome: nome do médico (ex: "Karla", "Dra. Karla Delalíbera").
        unidade_nome: nome da unidade (ex: "Asa Norte", "Águas Claras").
        data_iso: data no formato 'YYYY-MM-DD'.
        hora: hora no formato 'HH:MM'.
        dias_alternativos: quantos dias buscar alternativas se slot ocupado (default 10).

    Returns:
        (True, []) — slot disponível, pode gravar.
        (False, alternativas[:4]) — slot ocupado, lista com próximos disponíveis
            [{data_iso, data_br, dia_semana, hora}].

    Fail-open: se SQL falhar, assume disponível para não bloquear conversas.
    """
    from datetime import date as _date, timedelta as _td

    hora_norm = hora[:5]

    # 1. Verificar se o slot específico ainda existe
    horas_livres = horarios_livres_dia(medico_nome, unidade_nome, data_iso)
    if hora_norm in horas_livres:
        return True, []

    log.warning(
        "[SLOT-CHECK-SQL] OCUPADO: medico=%r unidade=%r data=%s hora=%s",
        medico_nome, unidade_nome, data_iso, hora_norm,
    )

    # 2. Slot ocupado — buscar alternativas nos próximos N dias
    _DIAS_PT = [
        "segunda-feira", "terça-feira", "quarta-feira",
        "quinta-feira", "sexta-feira", "sábado", "domingo",
    ]
    alternativas: list[dict] = []
    try:
        data_inicio = _date.fromisoformat(data_iso)
        for offset in range(dias_alternativos):
            dia = data_inicio + _td(days=offset)
            dia_iso = dia.isoformat()
            horas = horarios_livres_dia(medico_nome, unidade_nome, dia_iso)
            for h in horas:
                alternativas.append({
                    "data_iso": dia_iso,
                    "data_br": dia.strftime("%d/%m/%Y"),
                    "dia_semana": _DIAS_PT[dia.weekday()],
                    "hora": h,
                })
            if len(alternativas) >= 4:
                break
    except Exception as exc:
        log.warning("[SLOT-CHECK-SQL] busca alternativas falhou: %s", exc)

    return False, alternativas[:4]
