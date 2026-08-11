#!/usr/bin/env python3
"""Cria 10 campos no Kommo: 2.MOTIVO + 2.EXAMES até 6.MOTIVO + 6.EXAMES.

INTERATIVO E IDEMPOTENTE — basta rodar:

    cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
    python3 scripts/criar_campos_pacientes_kommo.py

O script:
  1. Tenta ler KOMMO_TOKEN do env. Se não tiver, pede pra colar.
  2. Conecta ao Kommo e valida o token (GET /account).
  3. Lista os custom_fields existentes hoje.
  4. Mostra o plano: campos a criar (pula os que já existem).
  5. Pergunta confirmação [s/N].
  6. Cria, mostrando progresso.
  7. Resume no final.

Sem flags, sem export manual obrigatório, sem export prévio.
"""
from __future__ import annotations

import os
import sys
import time
import getpass

try:
    import httpx
except ImportError:
    print(
        "ERRO: biblioteca 'httpx' não instalada.\n"
        "Instale com:  pip3 install --user httpx\n"
        "Ou:  python3 -m pip install --user --break-system-packages httpx",
        file=sys.stderr,
    )
    sys.exit(2)


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


# ============================================================
# UI helpers
# ============================================================

def linha(c: str = "─", n: int = 60) -> None:
    print(c * n)


def cabecalho(titulo: str) -> None:
    print()
    linha("=")
    print(f"  {titulo}")
    linha("=")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


# ============================================================
# Token
# ============================================================

def get_token() -> str:
    """Lê token do env. Se vazio ou for placeholder, pede ao usuário."""
    tok = (os.environ.get("KOMMO_TOKEN") or "").strip()
    if tok and "COLE" not in tok.upper() and len(tok) > 100:
        ok("Token encontrado no env KOMMO_TOKEN")
        return tok

    print(
        "\nKOMMO_TOKEN não encontrado no ambiente."
        "\nPra obter:"
        "\n  1. Abrir: https://6prkfn.easypanel.host/projects/blink/app/agent/environment"
        "\n  2. Copiar o VALOR de KOMMO_TOKEN (JWT longo, começa com 'eyJ0eXAi')"
        "\n  3. Colar abaixo (não aparecerá na tela — é seguro):\n"
    )
    tok = getpass.getpass("KOMMO_TOKEN: ").strip()
    if not tok or len(tok) < 100:
        fail("Token vazio ou muito curto. Abortando.")
        sys.exit(1)
    return tok


# ============================================================
# HTTP
# ============================================================

def validar_token(
    client: httpx.Client, headers: dict
) -> dict:
    """GET /account pra validar token e mostrar o subdomain."""
    r = client.get(f"{BASE}/account", headers=headers, timeout=15.0)
    if r.status_code == 401:
        fail("Token rejeitado (HTTP 401 Unauthorized). Verifique se é válido.")
        sys.exit(1)
    if r.status_code != 200:
        fail(f"Falha ao validar conta: HTTP {r.status_code} {r.text[:200]}")
        sys.exit(1)
    return r.json() or {}


def listar_campos_existentes(
    client: httpx.Client, headers: dict
) -> set[str]:
    names: set[str] = set()
    page = 1
    while True:
        r = client.get(
            f"{BASE}/leads/custom_fields",
            params={"limit": 250, "page": page},
            headers=headers,
            timeout=15.0,
        )
        if r.status_code == 204:
            break
        if r.status_code != 200:
            fail(f"Falha ao listar campos: HTTP {r.status_code}")
            sys.exit(1)
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
    return {
        "name": f"{numero}.MOTIVO",
        "type": "multiselect",
        "enums": [
            {"value": v, "sort": (i + 1) * 10}
            for i, v in enumerate(ENUMS_MOTIVO)
        ],
    }


def construir_payload_exames(numero: int) -> dict:
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
    fail(f"HTTP {r.status_code}: {r.text[:300]}")
    return None


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    cabecalho("CRIAR CAMPOS KOMMO — pacientes 2 a 6")
    print(
        "Replica 1.MOTIVO + 1.EXAMES (já criados) para os pacientes\n"
        "2, 3, 4, 5 e 6 — total 10 campos."
    )

    cabecalho("PASSO 1/4 — TOKEN")
    token = get_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    cabecalho("PASSO 2/4 — VALIDANDO TOKEN")
    with httpx.Client(timeout=15.0) as client:
        acc = validar_token(client, headers)
        ok(f"Conta: {acc.get('name', 'desconhecida')} "
           f"(subdomain: {acc.get('subdomain', '?')})")

        cabecalho("PASSO 3/4 — DETECTANDO CAMPOS JÁ EXISTENTES")
        existentes = listar_campos_existentes(client, headers)
        ok(f"Total de custom_fields atuais: {len(existentes)}")
        if "1.MOTIVO" in existentes:
            ok("1.MOTIVO já existe (será replicado)")
        else:
            warn(
                "1.MOTIVO NÃO foi encontrado — verifique se foi criado "
                "antes de continuar."
            )
        if "1.EXAMES" in existentes:
            ok("1.EXAMES já existe (será replicado)")
        else:
            warn(
                "1.EXAMES NÃO foi encontrado — verifique se foi criado "
                "antes de continuar."
            )

        # Plano
        a_criar = []
        a_pular = []
        for n in range(2, 7):
            for payload_fn in (
                construir_payload_motivo,
                construir_payload_exames,
            ):
                p = payload_fn(n)
                if p["name"] in existentes:
                    a_pular.append(p["name"])
                else:
                    a_criar.append(p)

        cabecalho(
            f"PASSO 4/4 — PLANO: "
            f"{len(a_criar)} novos · {len(a_pular)} já existem"
        )
        if a_pular:
            print("  Pular (já existem):")
            for n in a_pular:
                print(f"    • {n}")
        if a_criar:
            print("  Criar:")
            for p in a_criar:
                print(f"    • {p['name']:<14}  {p['type']:<11}  "
                      f"{len(p['enums'])} opções")
        else:
            cabecalho("RESULTADO")
            ok("Nada a fazer — todos os 10 campos já existem.")
            return 0

        # Confirmação
        print()
        resp = input(
            f"Criar os {len(a_criar)} campos no Kommo agora? [s/N]: "
        ).strip().lower()
        if resp not in ("s", "sim", "y", "yes"):
            warn("Abortado pelo usuário. Nenhum campo foi criado.")
            return 0

        cabecalho("CRIANDO CAMPOS")
        criados = 0
        falhas = 0
        for p in a_criar:
            print(f"  POST  {p['name']:<14} ...", end=" ", flush=True)
            res = criar_campo(client, headers, p)
            if res:
                fid = res.get("id")
                print(f"OK (field_id={fid})")
                criados += 1
            else:
                print("FALHOU")
                falhas += 1
            time.sleep(0.4)

        cabecalho("RESUMO")
        ok(f"{criados} campos criados")
        if a_pular:
            ok(f"{len(a_pular)} já existiam (pulados)")
        if falhas:
            fail(f"{falhas} falharam — verifique os erros acima")
            return 1
        print(
            "\n  Próximo passo: abra qualquer lead → aba Pacientes → role\n"
            "  até SEGUNDO/TERCEIRO/QUARTO/QUINTO/SEXTO PACIENTE e confirme\n"
            "  que os campos N.MOTIVO e N.EXAMES aparecem."
        )
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAbortado (Ctrl+C).", file=sys.stderr)
        sys.exit(130)
