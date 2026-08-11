#!/usr/bin/env python3
"""
Auditoria do batch ferias julho — Bug C-21.

Lê os 81 lead_ids disparados, busca cada um no Kommo, verifica:
  - 1.MÊS PRÓX CONSULTA (1260588) tem valor de mês futuro?
  - 1.DIA CONSULTA (1255723) é menor que 6 meses atrás?

Quem violar = ATROPELO de protocolo médico. Listar pra reconhecer nas notas
e desculpa eventual.

Roda sem disparar nada — só leitura.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

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
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")
if not KOMMO_TOKEN:
    print("❌ KOMMO_TOKEN não encontrado")
    sys.exit(2)

KOMMO_BASE = "https://univeja.kommo.com/api/v4"

# Field IDs
FIELD_DIA_CONSULTA = 1255723       # date_time
FIELD_MES_PROX_CONSULTA = 1260588  # select "Maio 2027"
FIELD_NOME_PACIENTE = 1255757
FIELD_DATA_NASC = 1259984


def get_lead(lead_id: int) -> dict | None:
    url = f"{KOMMO_BASE}/leads/{lead_id}"
    h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, headers=h, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def cf_value(lead: dict, field_id: int):
    for cf in lead.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def main():
    log_file = REPO_DIR / "scripts" / "disparos_ok.txt"
    # Re-extrair do log mais recente
    logs = sorted(REPO_DIR.glob("scripts/log_batch_ferias_julho_*.txt"))
    if not logs:
        print("❌ Nenhum log batch encontrado")
        sys.exit(1)
    last = logs[-1]
    print(f"📂 Log batch: {last.name}\n")

    # Extrair lead_ids OK
    lead_ids = []
    for line in last.read_text().splitlines():
        if "→ OK lead=" in line:
            import re
            m = re.search(r"lead=(\d+)", line)
            if m:
                lead_ids.append(int(m.group(1)))

    print(f"📊 {len(lead_ids)} disparos OK pra auditar")
    print(f"⚙️  Verificando campos 1.MÊS PRÓX CONSULTA + 1.DIA CONSULTA\n")

    seis_meses_atras = datetime.now() - timedelta(days=183)
    seis_meses_atras_ts = seis_meses_atras.timestamp()

    atropelados = []
    ok = []
    sem_dados = []

    for i, lid in enumerate(lead_ids, 1):
        lead = get_lead(lid)
        if not lead:
            print(f"[{i:2d}/{len(lead_ids)}] {lid} → ❌ não recuperado")
            continue

        nome = cf_value(lead, FIELD_NOME_PACIENTE) or "(sem nome)"
        mes_prox = cf_value(lead, FIELD_MES_PROX_CONSULTA)
        dia_consulta_ts = cf_value(lead, FIELD_DIA_CONSULTA)

        motivos = []
        if mes_prox:
            motivos.append(f"PRÓX CONSULTA já agendada: {mes_prox}")
        if dia_consulta_ts:
            try:
                ts = int(dia_consulta_ts)
                if ts > seis_meses_atras_ts:
                    dt = datetime.fromtimestamp(ts)
                    motivos.append(f"DIA CONSULTA recente: {dt.strftime('%d/%m/%Y')}")
            except Exception:
                pass

        if motivos:
            atropelados.append({
                "lead_id": lid,
                "nome_paciente": nome,
                "url": f"https://univeja.kommo.com/leads/detail/{lid}",
                "motivos": motivos,
            })
            print(f"[{i:2d}/{len(lead_ids)}] {lid} ⚠️  ATROPELO — {nome} → {' + '.join(motivos)}")
        elif not (mes_prox or dia_consulta_ts):
            sem_dados.append(lid)
        else:
            ok.append(lid)

        time.sleep(0.4)

    print()
    print("=" * 60)
    print("RESUMO DA AUDITORIA")
    print("=" * 60)
    print(f"  Total disparos OK:           {len(lead_ids)}")
    print(f"  ⚠️  ATROPELOU protocolo:      {len(atropelados)}")
    print(f"  ✓ Sem violação (sem dados):   {len(sem_dados)}")
    print(f"  ✓ Sem violação (dados OK):    {len(ok)}")

    # Salvar relatório
    relatorio = REPO_DIR / "scripts" / f"auditoria_bug_c21_{int(time.time())}.json"
    relatorio.write_text(json.dumps({
        "ts": time.time(),
        "atropelados": atropelados,
        "total_disparos": len(lead_ids),
    }, ensure_ascii=False, indent=2))
    print(f"\n📝 Relatório: {relatorio.name}")

    if atropelados:
        print(f"\n⚠️  LEADS ATROPELADOS (Bug C-21):")
        for a in atropelados:
            print(f"  • {a['nome_paciente']} (#{a['lead_id']})")
            for m in a['motivos']:
                print(f"      └─ {m}")
            print(f"      {a['url']}")


if __name__ == "__main__":
    main()
