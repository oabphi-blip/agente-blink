#!/usr/bin/env python3
"""
Conta elegíveis pra campanha Fabrício DEDUPLICANDO por TELEFONE do paciente.

Regra Fábio (11/06):
  • Base tem 10.000+ leads, mas COM duplicatas (mesmo telefone em vários leads).
  • Pra evitar custo Meta desnecessário, só 1 disparo por telefone único.
  • Quando há duplicatas, escolhe o "melhor" via score:
      notas × 5    (mais histórico = paciente mais real)
    + campos × 3   (mais campos preenchidos = mais info)
    + recency × 1  (updated_at mais recente)

Depois aplica filtros normais SÓ no vencedor:
  • Tem MEDICOS contém Karla (ou status finalizado base Karla)
  • NÃO tem MEDICOS contém Fabrício
  • ATIVADO IA? != Desativado

Salva:
  • elegiveis_fabricio_{ts}.json      — pra rodar o batch
  • duplicatas_ignoradas_{ts}.json    — pra auditoria
"""

import os
import sys
import time
import json
import re
from pathlib import Path
from datetime import datetime
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
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")
KOMMO_BASE = "https://univeja.kommo.com/api/v4"

if not KOMMO_TOKEN:
    print("❌ KOMMO_TOKEN não encontrado")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PIPELINE_ATENDE = 8601819

STATUS_REALIZADO  = 91486864
STATUS_AGENDADO   = 101507507
STATUS_CONFIRMAR  = 101109455
STATUS_CONFIRMADO = 106653499
STATUS_BASE_KARLA = {STATUS_REALIZADO, STATUS_AGENDADO, STATUS_CONFIRMAR, STATUS_CONFIRMADO}

FIELD_MEDICOS     = 1256257
FIELD_ATIVADO_IA  = 1260817
FIELD_CONVENIO    = 853206
FIELD_DIA_CONSULTA = 1255723  # date_time — última/próxima consulta agendada
FIELD_PHONE_CODE  = "PHONE"  # field_code do telefone em contato

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def kommo_get(path, params=None):
    url = f"{KOMMO_BASE}/{path.lstrip('/')}"
    h = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, headers=h, params=params or {}, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        return None


def cf_value_by_id(entity, field_id):
    for cf in entity.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def cf_values_multi_by_id(entity, field_id):
    for cf in entity.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            return [v.get("value") for v in (cf.get("values") or [])]
    return []


def cf_value_by_code(entity, code):
    for cf in entity.get("custom_fields_values") or []:
        if cf.get("field_code") == code:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None


def normalizar_telefone(tel_raw):
    """Normaliza pra string E.164 só com dígitos. Retorna '' se inválido."""
    if not tel_raw:
        return ""
    # Tira tudo que não é dígito
    digitos = re.sub(r"\D", "", str(tel_raw))
    if not digitos:
        return ""
    # Adiciona 55 se não tem
    if not digitos.startswith("55"):
        if len(digitos) >= 10:
            digitos = "55" + digitos
    # Telefone BR válido tem 12-13 dígitos com 55
    if len(digitos) < 12 or len(digitos) > 13:
        return ""
    return digitos


def extrair_telefone_principal(lead):
    """Vasculha contatos embedded do lead pra achar 1º telefone válido."""
    contacts = (lead.get("_embedded") or {}).get("contacts") or []
    for c in contacts:
        # O 'with=contacts' retorna ID + alguns campos. Telefone pode estar lá.
        phone_raw = cf_value_by_code(c, FIELD_PHONE_CODE)
        norm = normalizar_telefone(phone_raw)
        if norm:
            return norm
    return ""


def tem_fabricio(lead):
    medicos = cf_values_multi_by_id(lead, FIELD_MEDICOS)
    return any("fabr" in (m or "").lower() for m in medicos)


def tem_karla(lead):
    medicos = cf_values_multi_by_id(lead, FIELD_MEDICOS)
    if any("karla" in (m or "").lower() for m in medicos):
        return True
    return lead.get("status_id") in STATUS_BASE_KARLA


def ia_desativada(lead):
    return cf_value_by_id(lead, FIELD_ATIVADO_IA) == "Desativado"


def score_lead(lead):
    """Score pra escolher MELHOR lead entre duplicatas.

    Refinado 11/06 (Fábio): priorizar lead que tem o ÚLTIMO AGENDAMENTO COM
    KARLA mais recente — é o que sustenta a sequência pra Fabrício.

    Pesos (mais alto vence):
      • 1.DIA CONSULTA (timestamp) → divide por 86400 (dia) — sinal MAIS FORTE
      • MEDICOS contém Karla → +1000 (confirmação direta)
      • status_id em base Karla → +500
      • nº campos preenchidos → ×3
      • updated_at recente → ×1 (dia)
    """
    # 1.DIA CONSULTA — peso máximo, é o sinal direto de "vínculo com Karla"
    dia_consulta_ts = cf_value_by_id(lead, FIELD_DIA_CONSULTA)
    dia_consulta_score = 0
    if dia_consulta_ts:
        try:
            dia_consulta_score = int(dia_consulta_ts) // 86400
        except (ValueError, TypeError):
            pass

    # Confirmação MEDICOS = Karla
    medicos_score = 0
    if any("karla" in (m or "").lower() for m in cf_values_multi_by_id(lead, FIELD_MEDICOS)):
        medicos_score = 1000

    # Status em base Karla
    status_score = 500 if lead.get("status_id") in STATUS_BASE_KARLA else 0

    # nº de campos preenchidos
    cf_count = sum(1 for cf in (lead.get("custom_fields_values") or []) if cf.get("values"))

    # Recency (updated_at) — desempate fino
    ts = lead.get("updated_at") or 0
    if isinstance(ts, str):
        try:
            ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
        except (ValueError, TypeError):
            ts = 0
    updated_score = ts // 86400 if ts else 0

    return (
        dia_consulta_score
        + medicos_score
        + status_score
        + cf_count * 3
        + updated_score
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("DEDUP por telefone — campanha Fabrício pra base Karla")
    print("=" * 60)

    todos = []
    page = 1
    total_lidos = 0

    while True:
        print(f"▶ Página {page} ...", end=" ", flush=True)
        resp = kommo_get("leads", {
            "filter[pipeline_id]": PIPELINE_ATENDE,
            "limit": 250,
            "page": page,
            "with": "contacts",
        })
        if not resp:
            print("erro (ou fim)")
            break
        leads_pg = (resp.get("_embedded") or {}).get("leads") or []
        if not leads_pg:
            print("(vazia)")
            break
        total_lidos += len(leads_pg)
        print(f"{len(leads_pg)} leads · acumulado {total_lidos}")
        todos.extend(leads_pg)
        if len(leads_pg) < 250:
            break
        page += 1
        time.sleep(0.2)

    print()
    print(f"📊 Total leads brutos no pipeline ATENDE: {total_lidos}")
    print()

    # ----- BUCKET POR TELEFONE -----
    print("▶ Indexando por telefone...")
    sem_tel = 0
    por_telefone = defaultdict(list)
    for lead in todos:
        tel = extrair_telefone_principal(lead)
        if not tel:
            sem_tel += 1
            continue
        por_telefone[tel].append(lead)

    print(f"   Sem telefone válido: {sem_tel}")
    print(f"   Telefones únicos: {len(por_telefone)}")
    print()

    # ----- ESCOLHE 1 LEAD POR TELEFONE -----
    print("▶ Escolhendo melhor lead por telefone (score)...")
    vencedores = []
    duplicatas_ignoradas = []
    for tel, leads_do_tel in por_telefone.items():
        if len(leads_do_tel) == 1:
            vencedores.append(leads_do_tel[0])
            continue
        # Sort por score desc
        ordenados = sorted(leads_do_tel, key=score_lead, reverse=True)
        vencedor = ordenados[0]
        vencedores.append(vencedor)
        for perdedor in ordenados[1:]:
            duplicatas_ignoradas.append({
                "lead_id": perdedor["id"],
                "telefone": tel,
                "venceu_lead_id": vencedor["id"],
                "score_vencedor": score_lead(vencedor),
                "score_perdedor": score_lead(perdedor),
            })

    print(f"   Telefones com duplicatas: {sum(1 for v in por_telefone.values() if len(v) > 1)}")
    print(f"   Total duplicatas ignoradas: {len(duplicatas_ignoradas)}")
    print()

    # ----- FILTROS DE ELEGIBILIDADE NO VENCEDOR -----
    print("▶ Aplicando filtros (Karla / sem Fabrício / IA ativa)...")
    eligiveis = []
    nao_karla = 0
    tem_fab = 0
    ia_off = 0
    for lead in vencedores:
        if not tem_karla(lead):
            nao_karla += 1; continue
        if tem_fabricio(lead):
            tem_fab += 1; continue
        if ia_desativada(lead):
            ia_off += 1; continue
        eligiveis.append({
            "id": lead.get("id"),
            "name": (lead.get("name") or "")[:80],
            "status_id": lead.get("status_id"),
            "convenio": cf_value_by_id(lead, FIELD_CONVENIO),
            "telefone": extrair_telefone_principal(lead),
        })

    # ----- RESUMO -----
    print()
    print("=" * 60)
    print("RESUMO FINAL")
    print("=" * 60)
    print(f"  Leads brutos no pipeline ATENDE: {total_lidos}")
    print(f"  Sem telefone válido:              {sem_tel}")
    print(f"  Telefones únicos:                 {len(por_telefone)}")
    print(f"  Após dedup por telefone:          {len(vencedores)} leads vencedores")
    print(f"  Duplicatas ignoradas:             {len(duplicatas_ignoradas)}")
    print(f"  Filtrado (não Karla):             {nao_karla}")
    print(f"  Filtrado (tem Fabrício):          {tem_fab}")
    print(f"  Filtrado (IA desativada):         {ia_off}")
    print(f"  ✅ ELEGÍVEIS pra disparo:         {len(eligiveis)}")
    print()
    print(f"  Cap 80/dia → {(len(eligiveis) // 80) + 1} dias úteis pra finalizar")
    print(f"  Cap 80/dia → ~{((len(eligiveis) // 80) + 1) // 5} semanas")
    print()

    # ----- AMOSTRA -----
    print("=== Amostra dos 5 primeiros elegíveis ===")
    for e in eligiveis[:5]:
        print(f"  {e['id']:>10} · status {e['status_id']} · {e['telefone']} · {(e['convenio'] or '(sem)')[:25]} · {e['name'][:40]}")

    # ----- SALVA -----
    ts = int(time.time())
    out_eligiveis = REPO_DIR / "scripts" / f"elegiveis_fabricio_{ts}.json"
    out_dups = REPO_DIR / "scripts" / f"duplicatas_ignoradas_{ts}.json"
    out_eligiveis.write_text(json.dumps(eligiveis, ensure_ascii=False, indent=2))
    out_dups.write_text(json.dumps(duplicatas_ignoradas, ensure_ascii=False, indent=2))
    print()
    print(f"📝 Elegíveis salvos:    {out_eligiveis.name} ({len(eligiveis)} entradas)")
    print(f"📝 Duplicatas ignoradas: {out_dups.name} ({len(duplicatas_ignoradas)} entradas)")


if __name__ == "__main__":
    main()
