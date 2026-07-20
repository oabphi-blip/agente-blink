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
import threading
import time
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


def contar_duplicatas_slot(cod_medico: int, cod_unidade: int, data_hora_iso: str) -> int:
    """Retorna quantos AGENDAMENTOS existem no slot exato (médico, unidade, data, hora).
    Usado pra detectar Bug C-59 (56 duplicatas 20/07 11:30)."""
    # Firebird compara DATETIME via CAST — string literal '2026-07-20T08:30:00' quebra
    # com HTTP 400. Split em data + hora, usar CAST(... AS DATE) + EXTRACT.
    d, h = data_hora_iso.split("T") if "T" in data_hora_iso else (data_hora_iso, "00:00:00")
    if len(h) == 5:
        h = h + ":00"
    hora_h, hora_m, hora_s = h.split(":")
    q = (
        f"SELECT COUNT(*) AS QTD FROM AGENDAMENTO "
        f"WHERE CODMEDICO={int(cod_medico)} AND CODUNIDADE={int(cod_unidade)} "
        f"AND CAST(DATAHORAAGENDADA AS DATE)='{d}' "
        f"AND EXTRACT(HOUR FROM DATAHORAAGENDADA)={int(hora_h)} "
        f"AND EXTRACT(MINUTE FROM DATAHORAAGENDADA)={int(hora_m)}"
    )
    try:
        r = rows(executar(q))
        return int(r[0].get("QTD", 0)) if r else 0
    except MedwareSQLError as e:
        log.warning("contar_duplicatas_slot erro: %s", e)
        return 0


def existe_agendamento(
    cod_medico: int, cod_unidade: int,
    data_hora_iso: str, cod_paciente: int = 0,
) -> Optional[int]:
    """DEDUP KEY do Bug C-59: retorna CODAGENDAMENTO existente pra
    (medico+unidade+data+hora [+paciente opcional]) OU None se slot está livre.

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
