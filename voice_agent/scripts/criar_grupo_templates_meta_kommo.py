"""Cria grupo '📤 Templates Meta' no Kommo e move os 5 custom fields pra dentro.

Idempotente: se o grupo já existe pelo nome, reusa. Se algum campo já
está no grupo certo, pula.
"""
import json
import os
import sys
import urllib.error
import urllib.request


KOMMO_SUBDOMAIN = os.environ.get("KOMMO_SUBDOMAIN", "univeja")
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")

GROUP_NAME = "📤 Templates Meta"

CAMPOS_ALVO = [
    "ULTIMO TEMPLATE META",
    "TEMPLATES JÁ RECEBIDOS",
    "CATEGORIA TEMPLATE",
    "DATA ÚLTIMO DISPARO META",
    "STATUS ÚLTIMO DISPARO",
]


def _http(method: str, path: str, body=None) -> dict:
    url = f"https://{KOMMO_SUBDOMAIN}.kommo.com{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {KOMMO_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "blink-criar-grupo-kommo/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            return {
                "status": resp.status,
                "body": json.loads(body) if body else {},
            }
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "body": e.read().decode("utf-8", errors="replace")[:1500],
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "exception", "body": str(e)}


def listar_grupos() -> list[dict]:
    """Lista grupos existentes em leads."""
    res = _http("GET", "/api/v4/leads/custom_fields/groups")
    if res["status"] != 200:
        return []
    return res["body"].get("_embedded", {}).get("custom_field_groups", []) or []


def criar_grupo(nome: str) -> dict:
    """Cria novo grupo. Retorna dict com id se ok."""
    payload = [{"name": nome, "sort": 999}]
    res = _http("POST", "/api/v4/leads/custom_fields/groups", payload)
    return res


def encontrar_ou_criar_grupo() -> str | None:
    grupos = listar_grupos()
    for g in grupos:
        # Match case-insensitive, ignorando emoji
        nome_g = g.get("name", "").strip()
        if nome_g == GROUP_NAME or nome_g.replace("📤 ", "") == GROUP_NAME.replace("📤 ", ""):
            print(f"  Grupo já existe: '{nome_g}' id={g.get('id')}")
            return g.get("id")

    print(f"  Criando grupo '{GROUP_NAME}'...")
    res = criar_grupo(GROUP_NAME)
    if res["status"] not in (200, 201):
        print(f"  FALHA criar grupo: status={res['status']}")
        print(f"  body: {res['body']}")
        return None
    grupos_criados = res["body"].get("_embedded", {}).get("custom_field_groups", [])
    if not grupos_criados:
        print(f"  Grupo criado mas API não retornou id. body: {res['body']}")
        return None
    grp_id = grupos_criados[0].get("id")
    print(f"  Grupo criado: id={grp_id}")
    return grp_id


def listar_campos() -> dict[str, dict]:
    """Retorna {nome_uppercase: cf_dict} de todos os custom fields de leads."""
    out: dict[str, dict] = {}
    page = 1
    while page <= 20:
        res = _http("GET", f"/api/v4/leads/custom_fields?page={page}&limit=250")
        if res["status"] != 200:
            break
        items = res["body"].get("_embedded", {}).get("custom_fields", [])
        if not items:
            break
        for cf in items:
            out[cf["name"].strip().upper()] = cf
        if len(items) < 250:
            break
        page += 1
    return out


def mover_campo_pra_grupo(field_id: int, group_id: str) -> dict:
    """PATCH pra atribuir group_id ao campo."""
    payload = {"group_id": group_id}
    res = _http(
        "PATCH",
        f"/api/v4/leads/custom_fields/{field_id}",
        payload,
    )
    return res


def main() -> int:
    if not KOMMO_TOKEN:
        print("ERRO: KOMMO_TOKEN nao setado.")
        return 2

    print(f"Subdomain: {KOMMO_SUBDOMAIN}")
    print(f"Token: ...{KOMMO_TOKEN[-6:]} ({len(KOMMO_TOKEN)} chars)\n")

    print("[1/3] Encontrando/criando grupo...")
    grp_id = encontrar_ou_criar_grupo()
    if not grp_id:
        print("Abortando — nao consegui obter group_id.")
        return 1
    print()

    print("[2/3] Localizando os 5 campos alvo...")
    campos_existentes = listar_campos()
    alvos_encontrados: list[dict] = []
    faltando: list[str] = []
    for nome in CAMPOS_ALVO:
        cf = campos_existentes.get(nome.upper())
        if cf:
            alvos_encontrados.append(cf)
            print(f"  ✓ {nome:30s} id={cf['id']} group_id_atual={cf.get('group_id')}")
        else:
            faltando.append(nome)
            print(f"  ✗ {nome:30s} NAO ENCONTRADO")

    if faltando:
        print(f"\n{len(faltando)} campos faltando. Rode primeiro:")
        print("  criar_campos_kommo_templates_meta.py")
        return 1
    print()

    print(f"[3/3] Movendo {len(alvos_encontrados)} campos pra grupo id={grp_id}...")
    movidos = 0
    ja_no_grupo = 0
    falhas = []
    for cf in alvos_encontrados:
        if cf.get("group_id") == grp_id:
            ja_no_grupo += 1
            print(f"  = {cf['name']:30s} ja esta no grupo")
            continue
        res = mover_campo_pra_grupo(cf["id"], grp_id)
        if res["status"] == 200:
            movidos += 1
            print(f"  → {cf['name']:30s} movido OK")
        else:
            falhas.append({
                "campo": cf["name"],
                "status": res["status"],
                "body": res["body"],
            })
            print(f"  ! {cf['name']:30s} FALHA status={res['status']}")
            print(f"     {str(res['body'])[:200]}")

    print(f"\nResumo:")
    print(f"  Grupo id: {grp_id}")
    print(f"  Movidos agora: {movidos}")
    print(f"  Ja estavam no grupo: {ja_no_grupo}")
    print(f"  Falhas: {len(falhas)}")

    out_path = "/tmp/blink_grupo_templates_meta.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "group_id": grp_id,
            "group_name": GROUP_NAME,
            "movidos": movidos,
            "ja_no_grupo": ja_no_grupo,
            "falhas": falhas,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nDetalhe: {out_path}")

    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
