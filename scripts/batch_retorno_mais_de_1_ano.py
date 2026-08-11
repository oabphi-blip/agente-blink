#!/usr/bin/env python3
"""
Batch campanha — pacientes com última consulta há mais de 1 ano.

Template Meta aprovado: 1020_retorno_mais_de_1_ano_v1
  Body: "Olá, {{1}}!
         Faz mais de um ano que {{2}} não consulta com a Dra. Karla
         (última visita: {{3}}).
         Hora da próxima consulta 💙"
  Botões: [ Agendar agora ] [ Me lembre depois ]

Filtros de elegibilidade:
  • 1.DIA CONSULTA (1255723) preenchido E ≥ 13 meses atrás
  • 1.MÊS PRÓX CONSULTA (1260588) VAZIO (Dra. Karla não definiu retorno)
  • ATIVADO IA? != Desativado
  • Convênio NÃO bloqueado (Inas/GDF/Cassi/SulAmérica/Bradesco/Unimed)
  • Telefone válido no contato
  • Não recebeu este template antes (dedup nota Kommo)

Dedup por telefone: se 5 leads do mesmo telefone caem nos filtros,
manda 1 só (o de maior score: dia_consulta mais recente + cf preenchidos).

Cap 100/dia, janela 9h-17h BRT, espaçado 4min, pausa fim de semana.
"""

import os
import sys
import time
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from collections import defaultdict

import requests

# ---------------------------------------------------------------------------
# Envs
# ---------------------------------------------------------------------------

REPO_DIR = Path(__file__).resolve().parents[1]
ENV_FILES = [
    REPO_DIR / "lia_engineer" / ".env.local",
    REPO_DIR / ".env",
    REPO_DIR / ".env.local",
]


def load_env():
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v


load_env()
KOMMO_TOKEN     = os.environ.get("KOMMO_TOKEN", "")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")
AGENT_BASE      = os.environ.get("AGENT_BASE_URL", "https://blink-agent.6prkfn.easypanel.host")
KOMMO_BASE      = "https://univeja.kommo.com/api/v4"

if not KOMMO_TOKEN or not WEBHOOK_SECRET:
    print("❌ Faltam envs KOMMO_TOKEN e/ou WEBHOOK_SECRET")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TEMPLATE_NAME     = "1020_retorno_mais_de_1_ano_v1"
TEMPLATE_LANG     = "pt_BR"
CAP_DIARIO_DEFAULT = 100
JANELA_INICIO_HORA = 9
JANELA_FIM_HORA    = 17
INTERVALO_SEG      = 4 * 60   # 4 min entre disparos
MIN_MESES_ULTIMA   = 13       # 13 meses = "mais de 1 ano"

PIPELINE_ATENDE   = 8601819

FIELD_MEDICOS         = 1256257
FIELD_ATIVADO_IA      = 1260817
FIELD_CONVENIO        = 853206
FIELD_DIA_CONSULTA    = 1255723   # last/next consulta data_time
FIELD_MES_PROX_CONS   = 1260588   # "Maio 2027" etc — VAZIO = sem retorno marcado
FIELD_NOME_PACIENTE   = 1255757

CONVENIOS_BLOQUEADOS = [
    "inas", "gdf", "cassi", "sulam", "sul amer", "bradesco",
    "unimed", "amil", "hapvida",
]

# ---------------------------------------------------------------------------
# Helpers Kommo
# ---------------------------------------------------------------------------


def kommo_get(path, params=None):
    url = f"{KOMMO_BASE}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, headers=h, params=params or {}, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def cf_value(entity, field_id):
    for cf in entity.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def cf_value_by_code(entity, code):
    for cf in entity.get("custom_fields_values") or []:
        if cf.get("field_code") == code:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def normalizar_telefone(tel_raw):
    if not tel_raw:
        return ""
    digitos = re.sub(r"\D", "", str(tel_raw))
    if not digitos:
        return ""
    if not digitos.startswith("55"):
        if len(digitos) >= 10:
            digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 13:
        return ""
    return digitos


def extrair_telefone(lead):
    contacts = (lead.get("_embedded") or {}).get("contacts") or []
    for c in contacts:
        phone = cf_value_by_code(c, "PHONE")
        norm = normalizar_telefone(phone)
        if norm:
            return norm
    return ""


def extrair_primeiro_nome_contato(lead):
    contacts = (lead.get("_embedded") or {}).get("contacts") or []
    for c in contacts:
        nome = (c.get("name") or "").strip()
        if not nome:
            continue
        primeiro = nome.split()[0].title()
        proibidos = {"voce", "ola", "oi", "cliente", "paciente",
                     "test", "teste", "inbra", "lia", "blink"}
        if primeiro.lower() in proibidos or len(primeiro) < 2:
            continue
        return primeiro
    return ""


def janela_horario_ok(ignore=False):
    if ignore:
        return True
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    if agora.weekday() >= 5:
        return False
    return JANELA_INICIO_HORA <= agora.hour < JANELA_FIM_HORA


def convenio_bloqueado(conv):
    if not conv:
        return False
    low = conv.lower()
    return any(c in low for c in CONVENIOS_BLOQUEADOS)


def ja_recebeu_template(lead_id):
    notes = kommo_get(f"leads/{lead_id}/notes", {"limit": 50})
    if not notes:
        return False
    for n in (notes.get("_embedded") or {}).get("notes") or []:
        txt = (n.get("params") or {}).get("text", "") or n.get("text") or ""
        if TEMPLATE_NAME.lower() in txt.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Filtros de elegibilidade
# ---------------------------------------------------------------------------


def elegivel_para_campanha(lead, agora_ts):
    """Retorna (True, motivo_ok) ou (False, motivo_skip)."""
    # 1.MÊS PRÓX CONSULTA preenchido → médico já definiu retorno
    mes_prox = cf_value(lead, FIELD_MES_PROX_CONS)
    if mes_prox:
        return False, f"PRÓX CONSULTA preenchida ({mes_prox})"

    # 1.DIA CONSULTA precisa estar preenchido E mais de 13 meses atrás
    dia_consulta_ts = cf_value(lead, FIELD_DIA_CONSULTA)
    if not dia_consulta_ts:
        return False, "sem data última consulta"
    try:
        ts = int(dia_consulta_ts)
    except (ValueError, TypeError):
        return False, "data inválida"
    meses_atras = (agora_ts - ts) / (86400 * 30)
    if meses_atras < MIN_MESES_ULTIMA:
        return False, f"última consulta há só {meses_atras:.1f} meses"

    # Data futura é absurdo (consulta marcada futura)
    if ts > agora_ts:
        return False, "data futura (consulta agendada)"

    # IA desativada
    if cf_value(lead, FIELD_ATIVADO_IA) == "Desativado":
        return False, "IA desativada"

    # Convênio bloqueado
    conv = cf_value(lead, FIELD_CONVENIO) or ""
    if convenio_bloqueado(conv):
        return False, f"convênio bloqueado: {conv}"

    return True, "ok"


def score_lead_dedup(lead):
    """Score para escolher 1 lead por telefone (dedup).

    Critério: lead com 1.DIA CONSULTA mais recente vence.
    """
    dia_consulta_ts = cf_value(lead, FIELD_DIA_CONSULTA)
    if dia_consulta_ts:
        try:
            return int(dia_consulta_ts)
        except (ValueError, TypeError):
            pass
    return 0


# ---------------------------------------------------------------------------
# Disparo
# ---------------------------------------------------------------------------


def disparar(lead_id, primeiro_nome_contato, nome_paciente, data_ultima_str, dry_run=False):
    if dry_run:
        return {"status_code": 0, "body": "DRY_RUN", "ok": True}
    url = f"{AGENT_BASE}/admin/disparar-template/{lead_id}"
    payload = {
        "template": TEMPLATE_NAME,
        "lang": TEMPLATE_LANG,
        "body_params": [primeiro_nome_contato, nome_paciente, data_ultima_str],
    }
    params = {"secret": WEBHOOK_SECRET}
    try:
        r = requests.post(url, params=params, json=payload, timeout=25)
        return {"status_code": r.status_code, "body": r.text[:300],
                "ok": 200 <= r.status_code < 300}
    except Exception as e:
        return {"status_code": 0, "body": str(e), "ok": False}


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cap", type=int, default=CAP_DIARIO_DEFAULT)
    ap.add_argument("--ignore-horario", action="store_true")
    args = ap.parse_args()

    if not janela_horario_ok(args.ignore_horario):
        print("⏰ Fora da janela 9h-17h BRT dia útil — abortando")
        sys.exit(0)

    print("=" * 60)
    print("BATCH retorno > 1 ano — template 1020")
    print("=" * 60)
    print(f"Cap diário: {args.cap}")
    print(f"Espaçamento: {INTERVALO_SEG//60}min")
    print(f"Dry-run: {args.dry_run}")
    print()

    agora_ts = int(time.time())

    # ----- VARRER PIPELINE ATENDE -----
    print("▶ Varredura completa do pipeline ATENDE...")
    todos = []
    page = 1
    while True:
        resp = kommo_get("leads", {
            "filter[pipeline_id]": PIPELINE_ATENDE,
            "limit": 250, "page": page, "with": "contacts",
        })
        if not resp:
            break
        leads_pg = (resp.get("_embedded") or {}).get("leads") or []
        if not leads_pg:
            break
        todos.extend(leads_pg)
        print(f"  Página {page}: +{len(leads_pg)} · total {len(todos)}")
        if len(leads_pg) < 250:
            break
        page += 1
        time.sleep(0.2)

    print(f"\n📊 Total leads brutos: {len(todos)}")
    print()

    # ----- ELEGIBILIDADE -----
    print("▶ Aplicando filtros de elegibilidade...")
    elegiveis_brutos = []
    motivos_skip = defaultdict(int)
    for lead in todos:
        ok, motivo = elegivel_para_campanha(lead, agora_ts)
        if ok:
            elegiveis_brutos.append(lead)
        else:
            # Agrupa por chave (sem detalhe dinâmico)
            chave = motivo.split("(")[0].strip().split(":")[0]
            motivos_skip[chave] += 1
    print(f"   Elegíveis brutos: {len(elegiveis_brutos)}")
    for m, n in sorted(motivos_skip.items(), key=lambda x: -x[1])[:10]:
        print(f"      skip · {m}: {n}")
    print()

    # ----- DEDUP POR TELEFONE -----
    print("▶ Dedup por telefone...")
    por_tel = defaultdict(list)
    sem_tel = 0
    for lead in elegiveis_brutos:
        tel = extrair_telefone(lead)
        if not tel:
            sem_tel += 1
            continue
        por_tel[tel].append(lead)
    print(f"   Sem telefone válido: {sem_tel}")
    print(f"   Telefones únicos:    {len(por_tel)}")

    vencedores = []
    for tel, leads_do_tel in por_tel.items():
        if len(leads_do_tel) == 1:
            vencedores.append(leads_do_tel[0])
        else:
            melhor = max(leads_do_tel, key=score_lead_dedup)
            vencedores.append(melhor)
    print(f"   Vencedores únicos (= disparos planejados): {len(vencedores)}")
    print()

    # ----- DISPARO -----
    log_path = REPO_DIR / "scripts" / f"log_batch_retorno_{int(time.time())}.txt"
    print(f"📝 Log: {log_path.name}")
    print()

    counts = {"OK": 0, "JA_RECEBEU": 0, "ERRO": 0, "FORA_HORARIO": 0}
    detalhes = []

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"# Batch retorno > 1 ano — {datetime.now().isoformat()}\n\n")

        for idx, lead in enumerate(vencedores, 1):
            if counts["OK"] >= args.cap:
                print(f"\n✅ Cap diário atingido ({args.cap})")
                break
            if not janela_horario_ok(args.ignore_horario):
                print(f"\n⏰ Fim de janela horária")
                break

            lead_id = lead["id"]
            tag = f"[{idx:4d}/{len(vencedores)}] {lead_id}"

            if ja_recebeu_template(lead_id):
                counts["JA_RECEBEU"] += 1
                msg = f"{tag} → SKIP (já recebeu template)"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            # Body params
            primeiro_contato = extrair_primeiro_nome_contato(lead) or "olá"
            nome_paciente_full = cf_value(lead, FIELD_NOME_PACIENTE) or "você"
            primeiro_paciente = nome_paciente_full.strip().split()[0].title() if nome_paciente_full else "você"
            dia_consulta_ts = cf_value(lead, FIELD_DIA_CONSULTA)
            try:
                data_ultima_str = datetime.fromtimestamp(int(dia_consulta_ts)).strftime("%d/%m/%Y")
            except Exception:
                data_ultima_str = "data anterior"

            result = disparar(lead_id, primeiro_contato, primeiro_paciente, data_ultima_str, dry_run=args.dry_run)
            if result["ok"]:
                counts["OK"] += 1
                msg = f"{tag} → OK contato={primeiro_contato} pac={primeiro_paciente} data={data_ultima_str}"
            else:
                counts["ERRO"] += 1
                msg = f"{tag} → ERRO {result['status_code']}: {result['body'][:100]}"
            print(msg); logf.write(msg + "\n")
            detalhes.append({
                "lead_id": lead_id,
                "contato": primeiro_contato,
                "paciente": primeiro_paciente,
                "data_ultima": data_ultima_str,
                "disparo": result,
            })

            if counts["OK"] < args.cap:
                time.sleep(INTERVALO_SEG)

        print()
        print("=" * 60)
        print("RESUMO")
        print("=" * 60)
        for k, v in counts.items():
            print(f"  {k:<20} {v}")
        logf.write(f"\n# RESUMO\n{json.dumps(counts, indent=2)}\n")
        logf.write(f"\n# DETALHES\n{json.dumps(detalhes, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
