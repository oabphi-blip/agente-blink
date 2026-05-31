#!/usr/bin/env python3
"""Cria 10 campos no Kommo: 2.MOTIVO + 2.EXAMES até 6.MOTIVO + 6.EXAMES.

Replica os campos 1.MOTIVO (multiselect 5 opções) e 1.EXAMES (select 5
opções) já criados pelo Fábio, agora para os pacientes 2 a 6.

USO no terminal do Mac:
    cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
    python3 scripts/criar_campos_pacientes_kommo.py

Token vem do env KOMMO_TOKEN. Pra setar:
    export KOMMO_TOKEN="eyJ0eXAi..."  (o mesmo do Easypanel)

Idempotente: antes de criar, lista campos existentes e pula os que já
existem (verifica por nome — ex.: se "2.MOTIVO" já existe, pula).

Roda em modo DRY-RUN por padrão. Pra criar de verdade:
    python3 scripts/criar_campos_pacientes_kommo.py --apply
"""
from __future__ import annotations

import os
import sys
import time
import json
import argparse

import httpx


# ============================================================
# CONFIG
# ============================================================

SUBDOMAIN = "univeja"
BASE = f"https://{SUBDOMAIN}.kommo.com/api/v4"

# Opções do campo MOTIVO (mesma ordem que Fábio criou no 1.MOTIVO)
ENUMS_MOTIVO = [
    "Rotina/Check-up",
    "Retorno/Acompanhamento",
    "Pré-operatório",
    "Emergência/Urgência",
    "Pós-Operatório",
]

# Opções do campo EXAMES (mesma ordem que Fábio criou no 1.EXAMES)
ENUMS_EXAMES = [
    "Agrupa1-Adulto Rotina (9 exames)",
    "Agrupa2-Adulto Emergência (6 exames)",
    "Agrupa3-Criança Rotina (6 exames)",
    "Agrupa4-Criança Urgência(5 exames)",
    "Agrupa5-Personalizado (escolha manual)",
]


def get_token() -> str:
    tok = os.environ.get("KOMMO_TOKEN") or os.environ.get("KOMMO_LONGLIVED")
    if not tok:
        print(
            "ERRO: setar KOMMO_TOKEN no env antes de rodar.\n"
            "  export KOMMO_TOKEN='eyJ0eXAi...'",
            file=sys.stderr,
        )
        sys.exit(1)
    return tok


def get_existing_field_names(client: httpx.Client, headers: dict) -> set[str]:
    """Lista todos os custom_fields de leads e retorna set de nomes."""
    names: set[str] = set()
    page = 1
    while True:
        r = client.get(
            f"{BASE}/leads/custom_fields",
            params={"limit": 250, "page": page},
            headers=headers,
        )
        if r.status_code == 204:
            break
        r.raise_for_status()
        data = r.json() or {}
        items = (data.get("_embedded") or {}).get("custom_fields") or []
        for f in items:
            n = (f.get("name") or "").strip()
            if n:
                names.add(n)
        if not (data.get("_links") or {}).get("next"):
            break
        page += 1
    return names


def construir_payload_motivo(numero: int) -> dict:
    """multiselect com 5 opções (igual 1.MOTIVO)."""
    return {
        "name": f"{numero}.MOTIVO",
        "type": "multiselect",
        "enums": [
            {"value": v, "sort": (i + 1) * 10}
            for i, v in enumerate(ENUMS_MOTIVO)
        ],
    }


def construir_payload_exames(numero: int) -> dict:
    """select com 5 opções (igual 1.EXAMES)."""
    return {
        "name": f"{numero}.EXAMES",
        "type": "select",
        "enums": [
            {"value": v, "sort": (i + 1) * 10}
            for i, v in enumerate(ENUMS_EXAMES)
        ],
    }


def criar_campo(
    client: httpx.Client, headers: dict, payload: dict
) -> dict | None:
    """POST /api/v4/leads/custom_fields. Kommo aceita lista de campos
    OU um único objeto. Aqui usamos lista de 1 elemento."""
    r = client.post(
        f"{BASE}/leads/custom_fields",
        json=[payload],
        headers=headers,
        timeout=15.0,
    )
    if r.status_code // 100 == 2:
        items = (r.json() or {}).get("_embedded", {}).get(
            "custom_fields", []
        )
        return items[0] if items else None
    print(
        f"  ERRO HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr,
    )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply", action="store_true",
        help="Cria os campos no Kommo. Sem essa flag roda em dry-run.",
    )
    args = parser.parse_args()

    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Lista o que serão os 10 campos a criar
    campos: list[dict] = []
    for n in range(2, 7):
        campos.append(construir_payload_motivo(n))
        campos.append(construir_payload_exames(n))

    if not args.apply:
        print("=== DRY-RUN — nenhum campo será criado ===\n")
        print(
            "Pra criar de verdade, rode novamente com --apply:\n"
            "  python3 scripts/criar_campos_pacientes_kommo.py --apply\n"
        )
        print("Campos que serão criados:\n")
        for c in campos:
            n_enums = len(c.get("enums", []))
            print(f"  • {c['name']:<14}  type={c['type']:<11}  {n_enums} opções")
        return 0

    with httpx.Client(timeout=15.0) as client:
        print("=== Conectando ao Kommo ===")
        existentes = get_existing_field_names(client, headers)
        print(f"Total de custom_fields hoje: {len(existentes)}\n")

        criados = 0
        pulados = 0
        falhas = 0
        for c in campos:
            nome = c["name"]
            if nome in existentes:
                print(f"  [SKIP] {nome:<14} — já existe")
                pulados += 1
                continue
            print(f"  [POST] {nome:<14} ...", end=" ", flush=True)
            res = criar_campo(client, headers, c)
            if res:
                fid = res.get("id")
                print(f"OK (field_id={fid})")
                criados += 1
            else:
                print("FALHOU")
                falhas += 1
            # Respeitar rate-limit
            time.sleep(0.4)

        print(
            f"\n=== Final: {criados} criados, {pulados} pulados, "
            f"{falhas} falhas ==="
        )
        return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
