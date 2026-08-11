#!/usr/bin/env python3
"""
Batch — apresentar Dr. Fabrício Freitas (catarata) pra base Dra. Karla.

Reusa infra:
  • Lista elegíveis (do contar_elegiveis_fabricio.py OU varredura direta)
  • Endpoint /admin/disparar-template/{lead_id} grava nota Kommo automática
  • Cap 80/dia, janela 9h-17h BRT, espaçamento ~6min entre disparos
  • Dedup via nota Kommo (não dispara 2x pro mesmo lead)
  • Bifurca por convênio: aceito → texto padrão; não aceito → texto com ✨valor especial

Rodar com `--dry-run` pra simular. Sem flag = produção real.
"""

import os
import sys
import time
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

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
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
AGENT_BASE = os.environ.get("AGENT_BASE_URL", "https://blink-agent.6prkfn.easypanel.host")
KOMMO_BASE = "https://univeja.kommo.com/api/v4"

if not KOMMO_TOKEN or not WEBHOOK_SECRET:
    print("❌ Faltam envs KOMMO_TOKEN e/ou WEBHOOK_SECRET")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TEMPLATE_NAME = "7711_apresentar_dr_fabricio_freitas_6qcphu"
TEMPLATE_LANG = "pt_BR"
CAP_DIARIO_DEFAULT = 80
JANELA_INICIO_HORA = 9      # BRT
JANELA_FIM_HORA = 17        # BRT
INTERVALO_DISPARO_SEG = 6 * 60  # 6 minutos

CONVENIOS_NAO_ACEITOS = [
    "inas", "gdf", "cassi", "sulam", "sul amer", "bradesco",
    "unimed", "amil", "hapvida", "porto seguro", "notre dame",
    "golden", "geap", "fusex", "fapes", "afeb", "assefaz",
    "afego", "asete", "brb", "caesan", "camed", "cnti",
    "eletronorte", "embratel", "quality",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def janela_horario_ok():
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    if agora.weekday() >= 5:  # sáb/dom
        return False
    return JANELA_INICIO_HORA <= agora.hour < JANELA_FIM_HORA


def kommo_get(path, **params):
    url = f"{KOMMO_BASE}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, headers=h, params=params, timeout=20)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def cf_value(lead, field_id):
    for cf in lead.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def get_primeiro_nome_contato(lead):
    """Pega 1º nome via contato principal do lead."""
    contacts = (lead.get("_embedded") or {}).get("contacts") or []
    if not contacts:
        return "olá"
    cid = contacts[0].get("id")
    if not cid:
        return "olá"
    h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(f"{KOMMO_BASE}/contacts/{cid}", headers=h, timeout=10)
        if r.status_code == 200:
            nome = (r.json().get("name") or "").strip()
            if nome:
                primeiro = nome.split()[0].title()
                # Validação inline (mesma lógica do contato_nome.py mas reduzida)
                proibidos = {"voce", "voce?", "ola", "oi", "cliente",
                             "paciente", "test", "teste", "inbra", "lia"}
                if primeiro.lower() in proibidos or len(primeiro) < 2:
                    return "olá"
                return primeiro
    except Exception:
        pass
    return "olá"


def convenio_eh_nao_aceito(conv_str):
    if not conv_str:
        return False
    low = conv_str.lower()
    return any(c in low for c in CONVENIOS_NAO_ACEITOS)


def ja_recebeu_template(lead_id):
    notes = kommo_get(f"leads/{lead_id}/notes", limit=50)
    if not notes:
        return False
    for n in (notes.get("_embedded") or {}).get("notes") or []:
        txt = (n.get("params") or {}).get("text", "") or n.get("text") or ""
        if TEMPLATE_NAME.lower() in txt.lower() or "apresentar_dr_fabricio" in txt.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Disparo
# ---------------------------------------------------------------------------


def disparar(lead_id, primeiro_nome, eh_nao_aceito, dry_run=False):
    """Dispara o template via endpoint do agent.

    O template 7711 espera body_params básicos. Como existem variantes,
    sempre passa primeiro_nome e adiciona marca pra não-aceito no nome
    da nota (pra equipe humana saber).
    """
    if dry_run:
        return {"status_code": 0, "body": "DRY_RUN", "ok": True}
    url = f"{AGENT_BASE}/admin/disparar-template/{lead_id}"
    payload = {
        "template": TEMPLATE_NAME,
        "lang": TEMPLATE_LANG,
        "body_params": [primeiro_nome],  # Ajustar se template tiver mais slots
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
    ap.add_argument("--dry-run", action="store_true", help="Não dispara — só simula")
    ap.add_argument("--cap", type=int, default=CAP_DIARIO_DEFAULT,
                    help=f"Cap diário (default {CAP_DIARIO_DEFAULT})")
    ap.add_argument("--lista", type=str, default=None,
                    help="Arquivo JSON pré-gerado (do contar_elegiveis_fabricio.py)")
    ap.add_argument("--ignore-horario", action="store_true",
                    help="Ignora janela horária")
    args = ap.parse_args()

    if not args.ignore_horario and not janela_horario_ok():
        print("⏰ Fora da janela 9h-17h BRT dia útil — abortando")
        sys.exit(0)

    # Carregar lista
    if args.lista:
        elegiveis = json.loads(Path(args.lista).read_text())
        print(f"📥 Lista carregada: {len(elegiveis)} elegíveis ({args.lista})")
    else:
        # Pega do mais recente arquivo elegiveis_fabricio_*.json
        candidatos = sorted(REPO_DIR.glob("scripts/elegiveis_fabricio_*.json"))
        if not candidatos:
            print("❌ Sem lista. Rode contar_elegiveis_fabricio.py primeiro.")
            sys.exit(1)
        ultima = candidatos[-1]
        elegiveis = json.loads(ultima.read_text())
        print(f"📥 Lista mais recente: {ultima.name} ({len(elegiveis)} elegíveis)")

    log_path = REPO_DIR / "scripts" / f"log_batch_fabricio_{int(time.time())}.txt"
    print(f"📝 Log: {log_path.name}")
    print(f"📊 Cap diário: {args.cap}")
    print(f"⏰ Janela: 9h-17h BRT, espaçamento {INTERVALO_DISPARO_SEG//60}min")
    print(f"🔥 dry_run: {args.dry_run}")
    print()

    counts = {"OK": 0, "JA_RECEBEU": 0, "SEM_TELEFONE": 0, "ERRO": 0, "FORA_HORARIO": 0}
    detalhes = []

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"# Batch Fabrício — {datetime.now().isoformat()}\n\n")

        for idx, lead_meta in enumerate(elegiveis, 1):
            if counts["OK"] >= args.cap:
                print(f"\n✅ Cap diário atingido ({args.cap})")
                break
            if not args.ignore_horario and not janela_horario_ok():
                print(f"\n⏰ Fim de janela horária")
                counts["FORA_HORARIO"] = len(elegiveis) - idx
                break

            lead_id = lead_meta["id"]
            tag = f"[{idx:4d}/{len(elegiveis)}] {lead_id}"

            # Dedup (busca nota)
            if ja_recebeu_template(lead_id):
                counts["JA_RECEBEU"] += 1
                msg = f"{tag} → SKIP (já recebeu template antes)"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            # Buscar lead completo (precisa do contato pro primeiro_nome)
            # CORRIGIDO 11/06: parâmetro Kommo v4 é "with" (não "with_")
            url = f"{KOMMO_BASE}/leads/{lead_id}"
            h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
            try:
                r = requests.get(url, headers=h, params={"with": "contacts"}, timeout=15)
                lead = r.json() if r.status_code == 200 else None
            except Exception:
                lead = None
            if not lead:
                counts["ERRO"] += 1
                msg = f"{tag} → ERRO (lead não recuperado)"
                print(msg); logf.write(msg + "\n")
                continue

            primeiro = get_primeiro_nome_contato(lead)
            conv = cf_value(lead, 853206) or ""
            eh_nao_aceito = convenio_eh_nao_aceito(conv)

            # Disparo
            result = disparar(lead_id, primeiro, eh_nao_aceito, dry_run=args.dry_run)
            if result["ok"]:
                counts["OK"] += 1
                marker = "[NÃO ACEITO]" if eh_nao_aceito else "[ACEITO]"
                msg = f"{tag} → OK {marker} primeiro={primeiro} conv={conv[:30]}"
            else:
                counts["ERRO"] += 1
                msg = f"{tag} → ERRO {result['status_code']}: {result['body'][:100]}"
            print(msg); logf.write(msg + "\n")
            detalhes.append({
                "lead_id": lead_id, "primeiro_nome": primeiro,
                "convenio": conv, "eh_nao_aceito": eh_nao_aceito,
                "disparo": result,
            })

            # Pacing: espaçar próximo disparo
            if counts["OK"] < args.cap:
                time.sleep(INTERVALO_DISPARO_SEG)

        # Resumo
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
