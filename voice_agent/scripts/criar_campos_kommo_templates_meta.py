"""Cria 5 custom fields no Kommo pra observabilidade de templates Meta.

Campos criados (todos no entity_type=leads):
  1. ULTIMO TEMPLATE META          (select)       — nome do último template disparado
  2. TEMPLATES JÁ RECEBIDOS        (multiselect)  — histórico completo de templates
  3. CATEGORIA TEMPLATE            (select)       — categoria do último (Captação, etc.)
  4. DATA ÚLTIMO DISPARO META      (date_time)    — quando saiu o último
  5. STATUS ÚLTIMO DISPARO         (select)       — sent / delivered / read / failed

Os enums dos campos select (1, 2 e 4) começam vazios e são populados
pelo sync_meta_to_kommo.py.

Idempotente: se o campo já existe pelo nome, NÃO recria — só reporta.
"""
import json
import os
import sys
import urllib.error
import urllib.request


KOMMO_SUBDOMAIN = os.environ.get("KOMMO_SUBDOMAIN", "univeja")
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")

# Categorias fixas — corresponde ao prefixo dos templates Meta
CATEGORIAS = [
    "Captação",
    "Reativação",
    "Reagendar",
    "Confirmação",
    "Recuperação valor",
    "Pós-consulta avaliação",
    "Apresentação médico",
    "Operacional",
    "Lista fria",
]

STATUS_DISPARO = ["sent", "delivered", "read", "failed"]


CAMPOS_A_CRIAR = [
    {
        "name": "ULTIMO TEMPLATE META",
        "type": "select",
        "enums": [],  # populado depois pelo sync
    },
    {
        "name": "TEMPLATES JÁ RECEBIDOS",
        "type": "multiselect",
        "enums": [],  # populado depois pelo sync
    },
    {
        "name": "CATEGORIA TEMPLATE",
        "type": "select",
        "enums": [{"value": c, "sort": i + 1} for i, c in enumerate(CATEGORIAS)],
    },
    {
        "name": "DATA ÚLTIMO DISPARO META",
        "type": "date_time",
        "enums": [],
    },
    {
        "name": "STATUS ÚLTIMO DISPARO",
        "type": "select",
        "enums": [{"value": s, "sort": i + 1} for i, s in enumerate(STATUS_DISPARO)],
    },
]


def _http(method: str, path: str, body: dict | None = None) -> dict:
    url = f"https://{KOMMO_SUBDOMAIN}.kommo.com{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {KOMMO_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "blink-setup-templates-meta/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return {"status": resp.status, "body": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "body": e.read().decode("utf-8", errors="replace")[:1500],
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "exception", "body": str(e)}


def listar_campos_existentes() -> dict[str, int]:
    """Retorna {nome_campo_uppercase: field_id} de todos os campos de leads."""
    out: dict[str, int] = {}
    page = 1
    while page <= 20:  # 20 páginas x 250 = cap defensivo
        res = _http(
            "GET",
            f"/api/v4/leads/custom_fields?page={page}&limit=250",
        )
        if res["status"] != 200:
            break
        items = res["body"].get("_embedded", {}).get("custom_fields", [])
        if not items:
            break
        for cf in items:
            out[cf["name"].strip().upper()] = cf["id"]
        if len(items) < 250:
            break
        page += 1
    return out


def criar_campo(campo: dict) -> dict:
    payload = {
        "name": campo["name"],
        "type": campo["type"],
        "is_api_only": False,
        "is_required": False,
    }
    if campo["enums"]:
        payload["enums"] = campo["enums"]
    res = _http("POST", "/api/v4/leads/custom_fields", [payload])
    return res


def main() -> int:
    if not KOMMO_TOKEN:
        print("ERRO: KOMMO_TOKEN nao setado.")
        return 2
    print(f"Subdomain: {KOMMO_SUBDOMAIN}")
    print(f"Token: ...{KOMMO_TOKEN[-6:]} ({len(KOMMO_TOKEN)} chars)\n")

    existentes = listar_campos_existentes()
    print(f"Total campos existentes em leads: {len(existentes)}\n")

    resultado = {"criados": [], "ja_existem": [], "falharam": []}

    for campo in CAMPOS_A_CRIAR:
        nome_up = campo["name"].upper()
        if nome_up in existentes:
            field_id = existentes[nome_up]
            resultado["ja_existem"].append({"name": campo["name"], "id": field_id})
            print(f"  EXISTE: {campo['name']:30s} id={field_id}")
            continue
        res = criar_campo(campo)
        if res["status"] == 200:
            cf = res["body"].get("_embedded", {}).get("custom_fields", [{}])[0]
            field_id = cf.get("id")
            resultado["criados"].append({"name": campo["name"], "id": field_id})
            print(f"  CRIADO: {campo['name']:30s} id={field_id}")
        else:
            resultado["falharam"].append({
                "name": campo["name"],
                "status": res["status"],
                "body": (
                    res["body"] if isinstance(res["body"], str)
                    else json.dumps(res["body"])[:500]
                ),
            })
            print(f"  FALHOU: {campo['name']:30s} status={res['status']}")
            print(f"          {res['body']}")

    print(f"\nResumo: criados={len(resultado['criados'])}, "
          f"ja_existem={len(resultado['ja_existem'])}, "
          f"falharam={len(resultado['falharam'])}")

    # Salva resultado em arquivo pra ser consumido pelo próximo passo
    out_path = "/tmp/blink_campos_kommo_templates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\nResultado salvo em: {out_path}")

    return 0 if not resultado["falharam"] else 1


if __name__ == "__main__":
    sys.exit(main())
