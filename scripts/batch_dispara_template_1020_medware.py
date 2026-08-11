#!/usr/bin/env python3
"""
Dispara template 1020_retorno_mais_de_1_ano_v1 pra cada paciente da
lista gerada pelo medware_pacientes_sem_retorno.py.

Usa telefone direto do Medware (verdade) — não passa pelo Kommo.
Cap 100/dia, janela 9-17h BRT, espaçado 4min.

Roda via Meta Graph API direto.
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

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

META_TOKEN = os.environ.get("WHATSAPP_CLOUD_TOKEN", "")
META_PHONE_ID = os.environ.get("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "668422093022140")

if not META_TOKEN:
    print("❌ WHATSAPP_CLOUD_TOKEN não encontrado")
    sys.exit(2)

TEMPLATE_NAME = "1020_retorno_mais_de_1_ano_v1"
TEMPLATE_LANG = "pt_BR"
CAP_DEFAULT = 100
INTERVALO_SEG = 4 * 60   # 4 min
JANELA_INICIO_H = 9
JANELA_FIM_H = 17


def janela_horario_ok(ignore=False):
    if ignore:
        return True
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    if agora.weekday() >= 5:
        return False
    return JANELA_INICIO_H <= agora.hour < JANELA_FIM_H


def disparar_template(telefone: str, primeiro_nome: str, nome_paciente: str, data_ultima: str, dry_run=False) -> dict:
    """Dispara via Meta Graph API."""
    if dry_run:
        return {"ok": True, "status": 0, "body": "DRY_RUN"}
    url = f"https://graph.facebook.com/v22.0/{META_PHONE_ID}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "template",
        "template": {
            "name": TEMPLATE_NAME,
            "language": {"code": TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": primeiro_nome[:60]},
                        {"type": "text", "text": nome_paciente[:60]},
                        {"type": "text", "text": data_ultima[:20]},
                    ],
                }
            ],
        },
    }
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {META_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=20,
        )
        ok = 200 <= r.status_code < 300
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:200]}
        return {"ok": ok, "status": r.status_code, "body": data}
    except Exception as e:
        return {"ok": False, "status": 0, "body": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", type=str, default=None, help="JSON gerado por medware_pacientes_sem_retorno.py")
    ap.add_argument("--cap", type=int, default=CAP_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ignore-horario", action="store_true")
    args = ap.parse_args()

    if not args.ignore_horario and not janela_horario_ok():
        print("⏰ Fora janela 9h-17h BRT dia útil — abortando")
        sys.exit(0)

    if args.lista:
        path = Path(args.lista)
    else:
        cands = sorted(REPO_DIR.glob("scripts/pacientes_sem_retorno_1ano_*.json"))
        if not cands:
            print("❌ Lista não encontrada. Rode medware_pacientes_sem_retorno.py primeiro.")
            sys.exit(1)
        path = cands[-1]

    elegiveis = json.loads(path.read_text())
    print(f"📥 Lista: {path.name} ({len(elegiveis)} elegíveis)")
    print(f"📊 Cap: {args.cap} · espaçamento: {INTERVALO_SEG//60}min · dry_run: {args.dry_run}\n")

    log_path = REPO_DIR / "scripts" / f"log_medware_1020_{int(time.time())}.txt"

    counts = {"OK": 0, "ERRO": 0}
    detalhes = []

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"# Disparo template 1020 via Medware — {datetime.now().isoformat()}\n\n")

        for idx, p in enumerate(elegiveis, 1):
            if counts["OK"] >= args.cap:
                print(f"\n✅ Cap atingido ({args.cap})")
                break
            if not args.ignore_horario and not janela_horario_ok():
                print(f"\n⏰ Fim de janela")
                break

            tel = p["telefone"]
            nome_pac = p.get("nome", "")
            primeiro = nome_pac.split()[0].title() if nome_pac else "olá"
            # Como Medware traz nome do paciente (não contato), usamos
            # primeiro nome como "nome do contato" — em muitos casos é
            # a própria pessoa (adulto).
            data_ultima = p.get("ultimaConsulta", "data anterior")

            tag = f"[{idx:4d}/{len(elegiveis)}] {p['codPaciente']:>6}"
            r = disparar_template(tel, primeiro, primeiro, data_ultima, dry_run=args.dry_run)

            if r["ok"]:
                counts["OK"] += 1
                wamid = ""
                try:
                    wamid = r["body"]["messages"][0]["id"]
                except Exception:
                    pass
                msg = f"{tag} → OK {tel} {primeiro}/{data_ultima} {wamid[:30]}"
            else:
                counts["ERRO"] += 1
                msg = f"{tag} → ERRO {r['status']}: {str(r['body'])[:120]}"
            print(msg); logf.write(msg + "\n")
            detalhes.append({
                "codPaciente": p["codPaciente"],
                "telefone": tel,
                "primeiro_nome": primeiro,
                "data_ultima": data_ultima,
                "resposta": r,
            })

            if counts["OK"] < args.cap:
                time.sleep(INTERVALO_SEG)

        print()
        print("=" * 60)
        print("RESUMO")
        print("=" * 60)
        for k, v in counts.items():
            print(f"  {k}: {v}")
        logf.write(f"\n# RESUMO\n{json.dumps(counts, indent=2)}\n")
        logf.write(f"\n# DETALHES\n{json.dumps(detalhes, ensure_ascii=False, indent=2, default=str)}\n")

    print(f"\n📝 Log: {log_path.name}")


if __name__ == "__main__":
    main()
