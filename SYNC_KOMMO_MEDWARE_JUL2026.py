#!/usr/bin/env python3
"""
SYNC_KOMMO_MEDWARE_JUL2026.py
=============================

Para cada lead no funil ATENDE (8601819), etapa 0-ETAPA ENTRADA (96441724),
com CAMPANHA=Julho/2026 (custom_field 1260440, enum 927043), faz:

  1. Lê do Kommo: 1.NOME PACIENTE, 1.DATA NASC, 1.DIA CONSULTA + 2/3/4/5/6
  2. Busca paciente(s) no Medware por primeiroNome + segundoNome
  3. Lista agendamentos do paciente (busca a última REALIZADA + próxima futura)
  4. Atualiza no Kommo: 1.NOME (canonical Medware), 1.DATA NASC, 1.DIA CONSULTA
     (e 2/3/4/5/6 quando há múltiplos pacientes no mesmo lead)
  5. Grava nota explicativa em PT-BR

Sobrescreve sempre (regra Fábio 28/06/2026). Se NÃO acha match Medware,
grava nota "sem match Medware" e segue.

Como rodar:
  python3 SYNC_KOMMO_MEDWARE_JUL2026.py            # processa tudo
  python3 SYNC_KOMMO_MEDWARE_JUL2026.py --dry-run  # só simula
  python3 SYNC_KOMMO_MEDWARE_JUL2026.py --leads 21431041,21401645  # só esses
  python3 SYNC_KOMMO_MEDWARE_JUL2026.py --skip-done  # pula leads já sincados hoje

Variáveis de ambiente necessárias (o .command pede no terminal):
  KOMMO_TOKEN, MEDWARE_USER, MEDWARE_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import urllib.request
import urllib.parse
import urllib.error

# -------------------------------------------------------------------- consts
BRT = timezone(timedelta(hours=-3))

KOMMO_BASE = "https://univeja.kommo.com/api/v4"
PIPELINE_ATENDE = 8601819
STATUS_ENTRADA = 96441724
FIELD_CAMPANHAS = 1260588   # 1.PRÓX CONSULTA (era 1260440 vazio — fix 29/06/2026 22:30)
ENUM_JULHO = 926336          # "Julho 2026" (era 927043 — fix 29/06/2026 22:30)

MEDWARE_BASE = "https://medware.blinkoftalmologia.com.br/api"

# Field IDs Kommo (descobertos via kommo_list_custom_fields 28/06/2026)
SLOTS = {
    1: {"nome": 1255757, "nasc": 1259984, "dia": 1255723},
    2: {"nome": 1255761, "nasc": 1255729, "dia": 1255725},
    3: {"nome": 1255779, "nasc": 1255787, "dia": 1255781},
    4: {"nome": 1255925, "nasc": 1255927, "dia": 1255931},
    5: {"nome": 1257661, "nasc": 1257663, "dia": 1257667},
    6: {"nome": 1260332, "nasc": 1260334, "dia": 1260346},
}

LOG_DIR = Path(__file__).parent / "logs_sync_jul2026"
LOG_DIR.mkdir(exist_ok=True)
RUN_TS = datetime.now(BRT).strftime("%Y%m%d_%H%M%S")
LOG_PATH = LOG_DIR / f"sync_{RUN_TS}.log"
REPORT_PATH = LOG_DIR / f"sync_{RUN_TS}_report.json"


def log(msg: str) -> None:
    line = f"[{datetime.now(BRT).strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def progress_bar(atual: int, total: int, t_inicio: float, label: str = "") -> str:
    """Barra ASCII com %, contador e ETA."""
    if total == 0:
        return ""
    pct = atual / total
    barras = int(pct * 30)
    bar = "█" * barras + "░" * (30 - barras)
    elapsed = time.time() - t_inicio
    if atual > 0:
        eta = elapsed * (total - atual) / atual
        eta_str = f"{int(eta // 60)}m{int(eta % 60):02d}s"
    else:
        eta_str = "?"
    return f"[{bar}] {pct*100:5.1f}% | {atual}/{total} {label} | ETA {eta_str}"


# --------------------------------------------------------------------- http
def http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[dict] = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"_raw": raw}
            return r.status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"_raw": raw, "_error": str(e)}
        return e.code, parsed


# ------------------------------------------------------------------- Kommo
class KommoClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def list_leads_status_with_cf(self) -> list[dict]:
        """Lista leads em 0-ENTRADA e filtra os que têm campanha Julho/2026."""
        all_leads: list[dict] = []
        page = 1
        while True:
            params = urllib.parse.urlencode({
                "filter[statuses][0][pipeline_id]": PIPELINE_ATENDE,
                "filter[statuses][0][status_id]": STATUS_ENTRADA,
                "limit": 250,
                "page": page,
            })
            url = f"{KOMMO_BASE}/leads?{params}"
            code, body = http_request("GET", url, self.headers)
            if code != 200:
                log(f"⚠️ list_leads page {page} HTTP {code}: {body}")
                break
            leads = (body.get("_embedded", {}) or {}).get("leads", []) or []
            if not leads:
                break
            all_leads.extend(leads)
            log(f"📄 Page {page}: +{len(leads)} (total {len(all_leads)})")
            if len(leads) < 250:
                break
            page += 1
            time.sleep(0.3)

        log(f"✅ Total em 0-ENTRADA: {len(all_leads)}")
        # filtrar por campanha Julho/2026 — precisa buscar 1-a-1 pra ver cf
        julho: list[int] = []
        for i, ld in enumerate(all_leads, 1):
            lid = ld["id"]
            code, detail = http_request(
                "GET", f"{KOMMO_BASE}/leads/{lid}?with=contacts", self.headers,
            )
            if code == 429:
                log(f"  ⏸️ rate-limit, aguardando 10s...")
                time.sleep(10)
                continue
            if code != 200:
                continue
            cfs = detail.get("custom_fields_values") or []
            camp = next((c for c in cfs if c.get("field_id") == FIELD_CAMPANHAS), None)
            if camp and any(v.get("enum_id") == ENUM_JULHO for v in (camp.get("values") or [])):
                julho.append(lid)
            # progresso a cada 100 leads
            if i % 100 == 0:
                log(f"  📊 filtro: {i}/{len(all_leads)} processados, {len(julho)} Julho/2026")
            time.sleep(0.08)
        log(f"🎯 Julho/2026: {len(julho)} leads — IDs: {','.join(map(str, julho))}")
        return julho

    def get_lead(self, lead_id: int) -> Optional[dict]:
        code, body = http_request(
            "GET", f"{KOMMO_BASE}/leads/{lead_id}?with=contacts", self.headers,
        )
        if code != 200:
            log(f"⚠️ get_lead {lead_id} HTTP {code}")
            return None
        return body

    def patch_lead(self, lead_id: int, custom_fields: list[dict]) -> bool:
        code, body = http_request(
            "PATCH",
            f"{KOMMO_BASE}/leads/{lead_id}",
            self.headers,
            body={"custom_fields_values": custom_fields},
        )
        if code not in (200, 202):
            log(f"❌ patch_lead {lead_id} HTTP {code}: {body}")
            return False
        return True

    def add_note(self, lead_id: int, text: str) -> bool:
        code, body = http_request(
            "POST",
            f"{KOMMO_BASE}/leads/{lead_id}/notes",
            self.headers,
            body=[{"note_type": "common", "params": {"text": text}}],
        )
        if code not in (200, 201, 202):
            log(f"⚠️ add_note {lead_id} HTTP {code}: {body}")
            return False
        return True


# ----------------------------------------------------------------- Medware
class MedwareClient:
    def __init__(self, user: str, password: str) -> None:
        self.user = user
        self.password = password
        self._token: Optional[str] = None

    def _login(self) -> None:
        url = f"{MEDWARE_BASE}/Acesso/login"
        code, body = http_request(
            "POST",
            url,
            {"Content-Type": "application/json"},
            body={"identificacao": self.user, "senha": self.password},
        )
        if code != 200:
            raise RuntimeError(f"Medware login HTTP {code}: {body}")
        self._token = body.get("token")
        log("🔑 Medware token OK")

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def buscar_pacientes(self, primeiro: str, segundo: Optional[str] = None) -> list[dict]:
        # Endpoint correto descoberto via voice_agent/medware.py:
        # GET Medware/Paciente/Listar (singular, com prefixo Medware/)
        params = {"primeiroNome": primeiro}
        if segundo:
            params["segundoNome"] = segundo
        for path in ("Medware/Paciente/Listar", "Medware/Pacientes/Listar"):
            url = f"{MEDWARE_BASE}/{path}?{urllib.parse.urlencode(params)}"
            code, body = http_request("GET", url, self._headers())
            if code == 401:
                self._login()
                code, body = http_request("GET", url, self._headers())
            if code != 200:
                continue
            if isinstance(body, list):
                return body
            if isinstance(body, dict):
                if body.get("codPaciente"):
                    return [body]
                lst = body.get("data") or body.get("pacientes")
                if isinstance(lst, list):
                    return lst
        return []

    def listar_agendamentos(self, cod_paciente: int, dt_ini: str, dt_fim: str) -> list[dict]:
        # Endpoint correto: Medware/Agendamento/Listar (singular)
        # Datas em DD/MM/YYYY, param codpaciente
        params = {
            "codpaciente": cod_paciente,
            "dataInicio": dt_ini,
            "dataFim": dt_fim,
        }
        url = f"{MEDWARE_BASE}/Medware/Agendamento/Listar?{urllib.parse.urlencode(params)}"
        code, body = http_request("GET", url, self._headers())
        if code == 401:
            self._login()
            code, body = http_request("GET", url, self._headers())
        if code != 200:
            log(f"  ⚠️ listar_agendamentos cod={cod_paciente} HTTP {code}: {str(body)[:120]}")
            return []
        if isinstance(body, list):
            return body
        return body.get("data") or []


# ----------------------------------------------------------- helpers de data
def parse_dt_br(s: str) -> Optional[datetime]:
    """'06/03/2026 15:30' → datetime BRT."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=BRT)
        except ValueError:
            continue
    return None


def to_iso_brt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S-03:00")


def clean_nome(s: str) -> str:
    s = (s or "").strip().rstrip(".")
    return re.sub(r"\s+", " ", s)


def split_primeiro_segundo(nome_completo: str) -> tuple[str, Optional[str]]:
    parts = clean_nome(nome_completo).split()
    if not parts:
        return "", None
    if len(parts) == 1:
        return parts[0].upper(), None
    return parts[0].upper(), parts[1].upper()


# --------------------------------------------------------- proc principal
def processar_lead(
    lead_id: int,
    kommo: KommoClient,
    medware: MedwareClient,
    dry_run: bool,
) -> dict:
    res: dict[str, Any] = {"lead_id": lead_id, "ok": False, "pacientes": [], "skip_reason": None}
    detail = kommo.get_lead(lead_id)
    if not detail:
        res["skip_reason"] = "get_lead_failed"
        return res
    cfs = {c["field_id"]: c for c in detail.get("custom_fields_values") or []}

    cfs_update: list[dict] = []
    notas_pacientes: list[str] = []
    # Medware espera datas em DD/MM/YYYY (confirmado via voice_agent/medware.py:609)
    hoje = datetime.now(BRT).strftime("%d/%m/%Y")
    futuro = (datetime.now(BRT) + timedelta(days=730)).strftime("%d/%m/%Y")
    passado = (datetime.now(BRT) - timedelta(days=1095)).strftime("%d/%m/%Y")

    for slot, ids in SLOTS.items():
        nome_cf = cfs.get(ids["nome"])
        if not nome_cf or not nome_cf.get("values"):
            continue
        nome_raw = (nome_cf["values"][0] or {}).get("value") or ""
        nome = clean_nome(nome_raw)
        if not nome or nome in (",", "."):
            continue
        primeiro, segundo = split_primeiro_segundo(nome)
        if not primeiro:
            continue
        log(f"  🔎 [{slot}] {nome} (primeiro={primeiro}, segundo={segundo})")
        pacientes = medware.buscar_pacientes(primeiro, segundo)
        # narrow filter: nome contém primeiro AND segundo
        sobrenome_alvo = clean_nome(nome).upper().split()
        if sobrenome_alvo and len(sobrenome_alvo) >= 2:
            ultimo = sobrenome_alvo[-1]
            pacientes = [
                p for p in pacientes
                if (
                    primeiro in (p.get("nome") or "").upper()
                    and (
                        not segundo
                        or segundo in (p.get("nome") or "").upper()
                    )
                    and (
                        ultimo in (p.get("nome") or "").upper()
                        or len(pacientes) == 1
                    )
                )
            ]
        if not pacientes:
            notas_pacientes.append(f"⚠️ Slot {slot} {nome} — SEM MATCH MEDWARE")
            continue
        # se múltiplos, pega o que tem data nasc preenchida primeiro
        pacientes.sort(key=lambda p: 0 if p.get("dataNascimento") else 1)
        p = pacientes[0]
        cod = p.get("codPaciente")
        nome_canonical = p.get("nome") or nome
        nome_canonical_title = " ".join(w.capitalize() for w in nome_canonical.split())
        nasc_str = p.get("dataNascimento") or ""
        nasc_dt = parse_dt_br(nasc_str + " 00:00") if nasc_str else None

        agendamentos = medware.listar_agendamentos(cod, passado, futuro)
        # ignorar agendamentos "criados pra migração" (pré-Blink)
        agendamentos = [
            a for a in agendamentos
            if "migrar o prontuário" not in (a.get("obs") or "").lower()
        ]
        # status 5=REALIZADO, 1=AGENDADO, 6=CANCELADO
        futuros = [a for a in agendamentos if a.get("codStatusAgendamento") == 1]
        realizados = [a for a in agendamentos if a.get("codStatusAgendamento") == 5]

        def _dt_ag(a):
            return parse_dt_br(a.get("dataHoraAgendada") or "")

        futuros.sort(key=lambda a: _dt_ag(a) or datetime.min.replace(tzinfo=BRT))
        realizados.sort(key=lambda a: _dt_ag(a) or datetime.min.replace(tzinfo=BRT), reverse=True)

        if futuros:
            ag = futuros[0]
            tag = "PRÓX AGENDADA"
        elif realizados:
            ag = realizados[0]
            tag = "ÚLTIMA REALIZADA"
        else:
            ag = None
            tag = ""

        dia_dt = _dt_ag(ag) if ag else None

        # montar PATCH
        cfs_update.append({
            "field_id": ids["nome"],
            "values": [{"value": nome_canonical_title}],
        })
        if nasc_dt:
            cfs_update.append({
                "field_id": ids["nasc"],
                "values": [{"value": to_iso_brt(nasc_dt)}],
            })
        if dia_dt:
            cfs_update.append({
                "field_id": ids["dia"],
                "values": [{"value": to_iso_brt(dia_dt)}],
            })
        nota_paciente = (
            f"✅ Slot {slot}. {nome_canonical_title} (cod {cod})"
            f" — nasc {nasc_str or 'N/A'}"
            f" — {tag} {dia_dt.strftime('%d/%m/%Y %H:%M') if dia_dt else 'sem agendamento'}"
        )
        notas_pacientes.append(nota_paciente)
        res["pacientes"].append({
            "slot": slot,
            "cod": cod,
            "nome": nome_canonical_title,
            "nasc": nasc_str,
            "dia": to_iso_brt(dia_dt) if dia_dt else None,
            "tag": tag,
        })

    if not cfs_update and not notas_pacientes:
        res["skip_reason"] = "sem_pacientes_no_kommo"
        return res

    if dry_run:
        log(f"  🟡 DRY-RUN — não gravou. Updates planejados: {len(cfs_update)}")
        res["ok"] = True
        res["dry_run"] = True
        return res

    if cfs_update:
        ok_patch = kommo.patch_lead(lead_id, cfs_update)
        if not ok_patch:
            res["skip_reason"] = "patch_failed"
            return res
    nota = (
        f"[Claude Cowork — {datetime.now(BRT).strftime('%d/%m/%Y %H:%M')} "
        f"— sync Medware → Kommo (JUL2026)]\n\n"
        + "\n".join(notas_pacientes)
    )
    kommo.add_note(lead_id, nota)
    res["ok"] = True
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--leads", help="lead_ids separados por vírgula (pula descoberta)")
    ap.add_argument("--skip-done", action="store_true", help="pula leads com nota Claude hoje")
    args = ap.parse_args()

    token_kommo = os.environ.get("KOMMO_TOKEN")
    user_med = os.environ.get("MEDWARE_USER", "agendamentoweb")
    pass_med = os.environ.get("MEDWARE_PASSWORD")
    if not token_kommo or not pass_med:
        print("❌ Setar KOMMO_TOKEN e MEDWARE_PASSWORD nas variáveis de ambiente.")
        return 2

    kommo = KommoClient(token_kommo)
    medware = MedwareClient(user_med, pass_med)

    if args.leads:
        lead_ids = [int(x.strip()) for x in args.leads.split(",") if x.strip()]
    else:
        log("🔍 Buscando leads filtrados (0-ENTRADA × Julho/2026)...")
        lead_ids = kommo.list_leads_status_with_cf()

    log(f"📋 Total a processar: {len(lead_ids)}")
    if args.dry_run:
        log("🟡 MODO DRY-RUN (não vai gravar)")

    report = {"started_at": datetime.now(BRT).isoformat(), "leads": [], "totals": {}}
    ok = 0
    skipped = 0
    erros = 0
    t_inicio = time.time()
    for i, lid in enumerate(lead_ids, 1):
        log(f"\n— [{i}/{len(lead_ids)}] lead {lid} —")
        try:
            r = processar_lead(lid, kommo, medware, args.dry_run)
        except Exception as e:  # noqa: BLE001
            log(f"❌ erro {lid}: {e}")
            r = {"lead_id": lid, "ok": False, "skip_reason": f"exception: {e}"}
            erros += 1
        report["leads"].append(r)
        if r.get("ok"):
            ok += 1
            log(f"  ✅ OK ({len(r.get('pacientes', []))} pacientes)")
        elif r.get("skip_reason"):
            skipped += 1
            log(f"  ⏭️ skip: {r['skip_reason']}")
        # barra de progresso
        log(f"  {progress_bar(i, len(lead_ids), t_inicio, 'leads')} | ok={ok} skip={skipped} err={erros}")
        time.sleep(0.4)

    report["totals"] = {
        "total": len(lead_ids), "ok": ok, "skipped": skipped, "erros": erros,
    }
    report["finished_at"] = datetime.now(BRT).isoformat()
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    log(f"\n🎯 FIM: ok={ok} skipped={skipped} erros={erros}")
    log(f"📋 Log: {LOG_PATH}")
    log(f"📋 Relatório JSON: {REPORT_PATH}")
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
