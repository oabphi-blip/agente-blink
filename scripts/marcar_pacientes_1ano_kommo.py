#!/usr/bin/env python3
"""
Marca 620 pacientes que estão há +1 ano sem vir no Kommo com o campo
CAMPANHAS = "Pacientes sem consulta há mais de 1 ano".

Fonte: pacientes_mais_1ano.csv (extraído do Excel Medware 15/07/2026)
Field Kommo: CAMPANHAS (id 1260440, multiselect)
Enum a marcar: "Pacientes sem consulta há mais de 1 ano" (id 927750)

Estratégia:
1. Pra cada paciente: busca no Kommo por telefone (E.164 sem 55)
   ou nome quando não tem telefone.
2. Se encontra 1+ lead, adiciona o enum novo PRESERVANDO valores
   existentes de CAMPANHAS (multiselect).
3. Salva progresso em kommo_marcar_progresso.json (retomada automática).
4. Gera relatório CSV: paciente, lead_id, url, status_final.

Rate limit Kommo: ~7 req/s. Script usa 0.15s entre chamadas (segurança).

Uso:
    export KOMMO_TOKEN=eyJ0eXA...  # ou cole quando pedido
    python3 scripts/marcar_pacientes_1ano_kommo.py

Retomada: rode de novo — pula pacientes já processados via progresso.json.

Piloto Micaella (lead 21578879) já marcada em 15/07/2026 11:49 UTC.
Script começa do paciente 2 automaticamente (via progresso.json).
"""

from __future__ import annotations

import csv
import getpass
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

KOMMO_BASE = "https://univeja.kommo.com/api/v4"
# Fallback via Cloudflare Worker proxy se IP Easypanel estiver bloqueado:
KOMMO_BASE_PROXY = "https://kommo-proxy.oabphi.workers.dev/api/v4"

CAMPO_CAMPANHAS_ID = 1260440
ENUM_MARCAR_ID = 927750
ENUM_MARCAR_VALUE = "Pacientes sem consulta há mais de 1 ano"

PIPELINE_ATENDE = 8601819

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "pacientes_mais_1ano.csv")
PROGRESSO_PATH = os.path.join(os.path.dirname(__file__), "..", "kommo_marcar_progresso.json")
RELATORIO_PATH = os.path.join(os.path.dirname(__file__), "..", "kommo_marcar_relatorio.csv")

DELAY = 0.15  # 150ms entre chamadas ~ 6-7 req/s (dentro do rate limit)
TIMEOUT = 20


def carregar_pacientes() -> list[dict]:
    with open(CSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def carregar_progresso() -> dict:
    if not os.path.exists(PROGRESSO_PATH):
        return {"processados": {}}  # {nome: {"lead_ids":[...], "status":"marcado"|"nao_encontrado"|"erro"}}
    with open(PROGRESSO_PATH, encoding="utf-8") as f:
        return json.load(f)


def salvar_progresso(p: dict) -> None:
    with open(PROGRESSO_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)


def obter_token() -> str:
    # 1. Env var
    t = os.environ.get("KOMMO_TOKEN")
    if t:
        return _limpar_token(t)
    # 2. Arquivo /tmp/kommo_token.txt (salva do clipboard via pbpaste)
    for arquivo in ("/tmp/kommo_token.txt", os.path.expanduser("~/kommo_token.txt")):
        if os.path.exists(arquivo):
            with open(arquivo, encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                print(f"✅ Token lido de {arquivo}")
                return _limpar_token(t)
    print("KOMMO_TOKEN não encontrado.")
    print("Opções:")
    print("  a) Cole abaixo o token JWT completo (começa com eyJ...):")
    print("  b) Salve no arquivo /tmp/kommo_token.txt e rode de novo")
    print("     Comando pra salvar do clipboard: pbpaste > /tmp/kommo_token.txt")
    t = getpass.getpass("Token: ").strip()
    return _limpar_token(t)


def _limpar_token(raw: str) -> str:
    """Tolerante — aceita colar linha inteira do .env ou só o valor.
    Ex: 'KOMMO_TOKEN=eyJ...' → 'eyJ...'
        'export KOMMO_TOKEN=eyJ...' → 'eyJ...'
        'eyJ...' → 'eyJ...'
    """
    t = (raw or "").strip().strip('"').strip("'")
    if "=" in t and t.split("=", 1)[0].strip().upper().endswith("KOMMO_TOKEN"):
        t = t.split("=", 1)[1].strip().strip('"').strip("'")
    return t


def http(url: str, method: str = "GET", body: dict | None = None, token: str = "") -> tuple[int, dict]:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "blink-mark-pacientes/1.0",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
    except Exception as e:
        return (0, {"error": str(e)})
    try:
        js = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        js = {"raw": raw}
    return (code, js)


def buscar_leads(query: str, token: str) -> list[dict]:
    """Retorna lista de leads que casam com a query (telefone/nome)."""
    if not query.strip():
        return []
    q = urllib.parse.quote(query.strip())
    url = f"{KOMMO_BASE}/leads?query={q}&limit=10&with=contacts"
    code, js = http(url, token=token)
    if code == 204:
        return []
    if code >= 400 or not js:
        return []
    embedded = js.get("_embedded") or {}
    return embedded.get("leads") or []


def get_lead(lead_id: int, token: str) -> dict:
    url = f"{KOMMO_BASE}/leads/{lead_id}"
    code, js = http(url, token=token)
    if code >= 400:
        return {}
    return js


def cf_campanhas_atuais(lead: dict) -> list[dict]:
    """Retorna lista atual de {value, enum_id} do campo CAMPANHAS."""
    for cf in (lead.get("custom_fields_values") or []):
        if cf.get("field_id") == CAMPO_CAMPANHAS_ID:
            return list(cf.get("values") or [])
    return []


def marcar_lead(lead_id: int, token: str) -> tuple[bool, str]:
    """Adiciona enum 927750 no CAMPANHAS PRESERVANDO valores existentes."""
    lead = get_lead(lead_id, token)
    if not lead:
        return (False, "get_lead_falhou")
    atuais = cf_campanhas_atuais(lead)
    # Já marcado?
    if any(v.get("enum_id") == ENUM_MARCAR_ID for v in atuais):
        return (True, "ja_marcado")
    # Preserva os enum_ids existentes + adiciona o novo
    novos = [{"enum_id": v["enum_id"]} for v in atuais if v.get("enum_id")]
    novos.append({"enum_id": ENUM_MARCAR_ID})
    body = {
        "custom_fields_values": [
            {"field_id": CAMPO_CAMPANHAS_ID, "values": novos}
        ]
    }
    url = f"{KOMMO_BASE}/leads/{lead_id}"
    code, js = http(url, method="PATCH", body=body, token=token)
    if code >= 400:
        return (False, f"http_{code}:{js.get('title','?')}")
    # Validação: GET e checa se enum realmente entrou
    time.sleep(DELAY)
    lead2 = get_lead(lead_id, token)
    atuais2 = cf_campanhas_atuais(lead2)
    if any(v.get("enum_id") == ENUM_MARCAR_ID for v in atuais2):
        return (True, "marcado_ok")
    return (False, "patch_ok_mas_nao_gravou_C12")


def normalizar_nome_busca(nome: str) -> str:
    """Retorna nome sem sufixos comuns pra melhorar match Kommo."""
    n = re.sub(r"\s+", " ", nome.strip()).upper()
    return n


def score_match(lead: dict, nome: str, tel: str) -> int:
    """Pontua match. Mais alto = melhor."""
    score = 0
    lname = (lead.get("name") or "").upper()
    if nome.upper() in lname or lname in nome.upper():
        score += 5
    # Se lead tem telefone contato = paciente tel → match perfeito
    for ct in (lead.get("_embedded") or {}).get("contacts") or []:
        cid = ct.get("id")
        if cid and tel:
            # Match indireto — buscando por tel já garantiu match parcial
            score += 3
    # Pipeline ATENDE preferido
    if lead.get("pipeline_id") == PIPELINE_ATENDE:
        score += 2
    return score


def main() -> int:
    pacientes = carregar_pacientes()
    total = len(pacientes)
    print(f"📋 Total pacientes: {total}")

    prog = carregar_progresso()
    ja = prog.get("processados", {})
    print(f"📌 Já processados: {len(ja)} (retoma pelo restante)")

    token = obter_token()
    if not token or not (token.startswith("eyJ") or token.startswith("def")):
        print("❌ KOMMO_TOKEN inválido. Deve começar com eyJ (JWT).")
        return 1

    # Sanity check token
    print("Validando token…", end=" ")
    code, _ = http(f"{KOMMO_BASE}/leads?limit=1", token=token)
    if code >= 400:
        print(f"❌ HTTP {code} — token inválido/expirado.")
        return 2
    print("OK.")

    inicio = time.time()
    for i, p in enumerate(pacientes, start=1):
        nome = p["paciente"].strip()
        if not nome or nome in ja:
            continue

        tel = (p.get("telefone_limpo") or "").strip()

        # Estratégia de busca: telefone primeiro (mais preciso), fallback nome
        leads = []
        if tel and len(tel) >= 10:
            # tenta 3 variantes: com 55, sem 55, últimos 9 dígitos
            for q in (tel, tel.lstrip("55"), tel[-9:] if len(tel) >= 9 else tel):
                leads = buscar_leads(q, token)
                if leads:
                    break
                time.sleep(DELAY)
        if not leads:
            leads = buscar_leads(nome, token)

        time.sleep(DELAY)

        if not leads:
            ja[nome] = {"lead_ids": [], "status": "nao_encontrado"}
            print(f"⚠️  [{i:03d}/{total}] {nome[:40]} — NÃO encontrado")
            salvar_progresso({"processados": ja})
            continue

        # Ordena por score, pega top 3 pra marcar (caso duplicados)
        leads_scored = sorted(leads, key=lambda l: -score_match(l, nome, tel))
        top = leads_scored[:3]  # marca até 3 leads do mesmo paciente

        marcados = []
        erros = []
        for l in top:
            ok, motivo = marcar_lead(l["id"], token)
            if ok:
                marcados.append({"id": l["id"], "url": f"https://univeja.kommo.com/leads/detail/{l['id']}", "motivo": motivo})
            else:
                erros.append({"id": l["id"], "erro": motivo})
            time.sleep(DELAY)

        if marcados:
            ja[nome] = {"lead_ids": [m["id"] for m in marcados], "status": "marcado", "detalhes": marcados}
            print(f"✅ [{i:03d}/{total}] {nome[:40]} — {len(marcados)} lead(s) marcado(s)")
        else:
            ja[nome] = {"lead_ids": [], "status": "erro", "erros": erros}
            print(f"❌ [{i:03d}/{total}] {nome[:40]} — {erros}")

        salvar_progresso({"processados": ja})

        # Log de progresso a cada 25
        if i % 25 == 0:
            elapsed = time.time() - inicio
            eta_min = (total - i) * (elapsed / i) / 60
            marcados_total = sum(1 for v in ja.values() if v["status"] == "marcado")
            nao_enc = sum(1 for v in ja.values() if v["status"] == "nao_encontrado")
            print(f"   ── {marcados_total} marcados | {nao_enc} não encontrados | ETA {eta_min:.1f} min")

    # Gera relatório final CSV
    with open(RELATORIO_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["paciente", "status", "lead_ids", "url_primeiro"])
        for nome, info in sorted(ja.items()):
            ids = info.get("lead_ids", [])
            url = f"https://univeja.kommo.com/leads/detail/{ids[0]}" if ids else ""
            w.writerow([nome, info["status"], ";".join(map(str, ids)), url])

    marcados = sum(1 for v in ja.values() if v["status"] == "marcado")
    nao_enc = sum(1 for v in ja.values() if v["status"] == "nao_encontrado")
    erros = sum(1 for v in ja.values() if v["status"] == "erro")
    print(f"\n✅ Concluído em {(time.time()-inicio)/60:.1f} min")
    print(f"   {marcados} marcados | {nao_enc} não encontrados | {erros} erros")
    print(f"   Relatório: {RELATORIO_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
