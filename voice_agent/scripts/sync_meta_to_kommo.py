"""Sincroniza templates aprovados no Meta WhatsApp Business → enums de
custom fields no Kommo.

Roda DEPOIS de criar_campos_kommo_templates_meta.py (precisa dos field_ids).

O que faz:
  1. GET Meta Graph: lista todos os templates do WABA (paginado).
  2. Filtra status=APPROVED.
  3. Pra cada template: categoriza pelo prefixo OU allowlist legacy.
  4. PATCH no Kommo: atualiza enums de
       ULTIMO TEMPLATE META         (select)
       TEMPLATES JÁ RECEBIDOS        (multiselect)
  5. Mantém enums existentes (não apaga). Adiciona os novos.
  6. Marca como "[OBSOLETO]" templates do Kommo que não estão mais aprovados.

Idempotente. Pode rodar quantas vezes quiser.
"""
import json
import os
import sys
import urllib.error
import urllib.request


KOMMO_SUBDOMAIN = os.environ.get("KOMMO_SUBDOMAIN", "univeja")
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")
META_TOKEN = os.environ.get("WHATSAPP_CLOUD_TOKEN", "")
WABA_ID = os.environ.get("WHATSAPP_CLOUD_WABA_ID", "1990931811727552")
META_API_VERSION = "v21.0"


# Allowlist de templates antigos sem prefixo padronizado → categoria
LEGACY_ALLOWLIST: dict[str, str] = {
    "1089_mens_ativar_conv_parada_qz7kbz": "Reativação",
    "1039_ativar_grau_urgencia": "Captação",
    "1020_retorno_anual": "Reativação",
    "1019_sem_convenio": "Lista fria",
    "7711_apresentar_dr_fabricio_freitas_6qcphu": "Apresentação médico",
}

PREFIX_TO_CATEGORY: dict[str, str] = {
    "captar_": "Captação",
    "reativar_": "Reativação",
    "reagendar_": "Reagendar",
    "confirma_": "Confirmação",
    "recupera_": "Recuperação valor",
    "avalia_google_": "Pós-consulta avaliação",
    "blink_avaliacao_google_": "Pós-consulta avaliação",
    "blink_recuperacao_": "Recuperação valor",
    "apresentar_dr_": "Apresentação médico",
    "op_": "Operacional",
    "lf_": "Lista fria",
}


def _categorizar(template_name: str) -> str:
    if template_name in LEGACY_ALLOWLIST:
        return LEGACY_ALLOWLIST[template_name]
    nl = template_name.lower()
    for prefix, cat in PREFIX_TO_CATEGORY.items():
        if nl.startswith(prefix):
            return cat
    return "Operacional"  # default seguro


def _http_kommo(method: str, path: str, body: dict | list | None = None) -> dict:
    url = f"https://{KOMMO_SUBDOMAIN}.kommo.com{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {KOMMO_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "blink-sync-meta-kommo/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", errors="replace")[:2000]}
    except Exception as e:  # noqa: BLE001
        return {"status": "exception", "body": str(e)}


def _http_meta(path: str) -> dict:
    url = f"https://graph.facebook.com/{META_API_VERSION}{path}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {META_TOKEN}",
            "User-Agent": "blink-sync-meta-kommo/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", errors="replace")[:2000]}
    except Exception as e:  # noqa: BLE001
        return {"status": "exception", "body": str(e)}


def listar_templates_meta() -> list[dict]:
    """Lista todos templates do WABA paginando. Retorna só status=APPROVED."""
    aprovados = []
    after = None
    page = 0
    while page < 20:
        path = f"/{WABA_ID}/message_templates?limit=200&fields=name,status,category,language"
        if after:
            path += f"&after={after}"
        res = _http_meta(path)
        if res["status"] != 200:
            print(f"  Meta API erro (página {page}): status={res['status']}")
            print(f"  body: {res['body']}")
            break
        items = res["body"].get("data", [])
        for t in items:
            if t.get("status") == "APPROVED":
                aprovados.append({
                    "name": t["name"],
                    "category": t.get("category", ""),
                    "language": t.get("language", ""),
                    "blink_categoria": _categorizar(t["name"]),
                })
        cursor = res["body"].get("paging", {}).get("cursors", {}).get("after")
        if not cursor or not items:
            break
        after = cursor
        page += 1
    return aprovados


def encontrar_field_ids() -> dict[str, int]:
    """Encontra os ids dos 2 campos que vamos sincronizar."""
    alvos = {
        "ULTIMO TEMPLATE META": None,
        "TEMPLATES JÁ RECEBIDOS": None,
    }
    page = 1
    while page <= 20:
        res = _http_kommo(
            "GET",
            f"/api/v4/leads/custom_fields?page={page}&limit=250",
        )
        if res["status"] != 200:
            break
        items = res["body"].get("_embedded", {}).get("custom_fields", [])
        if not items:
            break
        for cf in items:
            nome_up = cf["name"].strip().upper()
            if nome_up in alvos:
                alvos[nome_up] = cf["id"]
        if len(items) < 250:
            break
        page += 1
    return {k: v for k, v in alvos.items() if v is not None}


def get_enums_atuais(field_id: int) -> list[dict]:
    res = _http_kommo("GET", f"/api/v4/leads/custom_fields/{field_id}")
    if res["status"] != 200:
        return []
    return res["body"].get("enums", []) or []


def upsert_enums(field_id: int, templates: list[dict]) -> dict:
    """Adiciona os templates Meta como enums no campo Kommo.

    Mantém enums existentes (não apaga, pra não quebrar leads que já
    tinham valor). Marca [OBSOLETO] os enums que não estão mais aprovados.
    """
    atuais = get_enums_atuais(field_id)
    nomes_meta = {t["name"] for t in templates}
    nomes_kommo_atual = {e["value"]: e for e in atuais}

    sort = max((e.get("sort", 0) for e in atuais), default=0)
    novos_enums = list(atuais)  # mantém tudo que já existe

    # Adiciona novos
    adicionados = []
    for t in templates:
        if t["name"] not in nomes_kommo_atual:
            sort += 1
            novos_enums.append({"value": t["name"], "sort": sort})
            adicionados.append(t["name"])

    # Marca obsoletos (renomeia valor pra "[OBSOLETO] xxx")
    obsoletos = []
    for valor, enum_obj in nomes_kommo_atual.items():
        if (valor not in nomes_meta
                and not valor.startswith("[OBSOLETO]")):
            # Acha o mesmo objeto na lista novos_enums e renomeia
            for ne in novos_enums:
                if ne.get("value") == valor:
                    ne["value"] = f"[OBSOLETO] {valor}"
                    obsoletos.append(valor)
                    break

    payload = {"enums": novos_enums}
    res = _http_kommo(
        "PATCH",
        f"/api/v4/leads/custom_fields/{field_id}",
        payload,
    )
    return {
        "status": res["status"],
        "adicionados": adicionados,
        "obsoletos": obsoletos,
        "total_kommo_apos": len(novos_enums),
    }


def sincronizar() -> dict:
    """Executa o sync Meta → Kommo de forma callable (endpoint + worker cron).

    Retorna dict:
      {
        ok: bool,
        erro: str | None,
        total_aprovados: int,
        adicionados: list[str],   # union de todos os campos
        obsoletos: list[str],     # union de todos os campos
        relatorio: {<NOME_CAMPO>: {status, adicionados[], obsoletos[],
                                  total_kommo_apos}, ...},
        templates: list[dict],    # preview até 50 dos aprovados
      }
    Nunca levanta — coloca o erro em `erro` e retorna ok=False.
    """
    if not KOMMO_TOKEN:
        return {
            "ok": False, "erro": "KOMMO_TOKEN nao setado",
            "total_aprovados": 0, "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": [],
        }
    if not META_TOKEN:
        return {
            "ok": False, "erro": "WHATSAPP_CLOUD_TOKEN nao setado",
            "total_aprovados": 0, "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": [],
        }

    try:
        templates = listar_templates_meta()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "erro": f"meta_falhou: {exc}",
            "total_aprovados": 0, "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": [],
        }

    if not templates:
        return {
            "ok": False, "erro": "nenhum_template_aprovado",
            "total_aprovados": 0, "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": [],
        }

    try:
        field_ids = encontrar_field_ids()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "erro": f"kommo_falhou: {exc}",
            "total_aprovados": len(templates),
            "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": templates[:50],
        }

    if len(field_ids) < 2:
        return {
            "ok": False,
            "erro": (
                "campos_kommo_faltando: rode "
                "criar_campos_kommo_templates_meta.py primeiro"
            ),
            "total_aprovados": len(templates),
            "adicionados": [], "obsoletos": [],
            "relatorio": {}, "templates": templates[:50],
        }

    relatorio: dict[str, dict] = {}
    set_adicionados: set[str] = set()
    set_obsoletos: set[str] = set()
    for nome_campo, field_id in field_ids.items():
        try:
            res = upsert_enums(field_id, templates)
        except Exception as exc:  # noqa: BLE001
            relatorio[nome_campo] = {
                "status": "exception",
                "adicionados": [], "obsoletos": [],
                "total_kommo_apos": 0, "erro": str(exc)[:200],
            }
            continue
        relatorio[nome_campo] = res
        for n in (res.get("adicionados") or []):
            set_adicionados.add(n)
        for n in (res.get("obsoletos") or []):
            set_obsoletos.add(n)

    return {
        "ok": True,
        "erro": None,
        "total_aprovados": len(templates),
        "adicionados": sorted(set_adicionados),
        "obsoletos": sorted(set_obsoletos),
        "relatorio": relatorio,
        "templates": templates[:50],
    }


# Alias público — usado pelo endpoint admin e pelo worker do cron interno.
def main_callable() -> dict:
    return sincronizar()


def main() -> int:
    res = sincronizar()
    if not res["ok"]:
        print(f"ERRO: {res['erro']}")
        if res["erro"] in (
            "KOMMO_TOKEN nao setado", "WHATSAPP_CLOUD_TOKEN nao setado",
        ):
            return 2
        return 1

    print(f"WABA_ID: {WABA_ID}")
    print(f"Kommo: {KOMMO_SUBDOMAIN}\n")
    print(f"[1/3] Templates Meta aprovados: {res['total_aprovados']}")
    for t in (res.get("templates") or [])[:5]:
        print(f"    - {t['name']:60s} categoria={t['blink_categoria']}")
    if res["total_aprovados"] > 5:
        print(f"    ... +{res['total_aprovados'] - 5} mais")
    print()
    print(f"[2/3] Custom fields Kommo: {list(res['relatorio'].keys())}\n")
    print("[3/3] Resumo enums:")
    for nome_campo, det in (res.get("relatorio") or {}).items():
        print(f"  {nome_campo}")
        print(f"    status: {det.get('status')}")
        print(f"    adicionados: {len(det.get('adicionados') or [])}")
        print(f"    obsoletos: {len(det.get('obsoletos') or [])}")
        print(f"    total enums após: {det.get('total_kommo_apos')}")

    print(
        f"\nSync concluído. {res['total_aprovados']} templates Meta "
        f"sincronizados com Kommo."
    )
    out_path = "/tmp/blink_sync_meta_kommo.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
        print(f"Detalhe completo em: {out_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] não consegui gravar {out_path}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
