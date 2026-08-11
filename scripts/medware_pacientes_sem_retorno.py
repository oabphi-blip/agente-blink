#!/usr/bin/env python3
"""
Cruzamento Medware → lista de pacientes sem retorno há mais de 1 ano.

VERSÃO 2 (11/06/2026 15:00): chama endpoint server-side do agent
(/admin/medware-pacientes-sem-retorno) que tem auth Medware. Script
local não precisa mais de credenciais Medware.

Estratégia (Fábio 11/06/2026):
  Medware é fonte da verdade. Kommo pode estar desatualizado.

  1. Lista agendamentos REALIZADOS de TODOS os médicos entre 01/01/2024
     e (hoje - 1 ano).
  2. Lista agendamentos pós (hoje - 1 ano).
  3. Diff por codPaciente: quem aparece em (1) mas NÃO em (2) é elegível.
  4. Salva JSON com {codPaciente, nome, telefone, dataNascimento, cpf,
     dataUltimaConsulta, codMedico, unidade}.
  5. Estatística por médico/unidade.

Próximo passo (outro script): disparar template 1020_retorno_mais_de_1_ano_v1
via Meta Graph pra cada paciente com telefone válido.

Roda standalone — só lê Medware e Meta env vars do .env.local.
"""

import os
import sys
import re
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlencode

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

MEDWARE_BASE = os.environ.get(
    "MEDWARE_API_BASE",
    "https://medware.blinkoftalmologia.com.br/api",
).rstrip("/")

# Não precisa auth — endpoint público da clínica.

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Médicos da Blink (codMedico Medware)
COD_MEDICO_KARLA = 12080
COD_MEDICO_FABRICIO = 12081

MEDICOS_BLINK = {
    COD_MEDICO_KARLA: "Dra. Karla Delalibera",
    COD_MEDICO_FABRICIO: "Dr. Fabrício Freitas",
}

UNIDADES = {
    1: "Asa Norte",
    3: "Águas Claras",
    5: "Asa Norte",
}

# Hoje - 1 ano (data limite)
HOJE = datetime.now()
LIMITE_1_ANO = HOJE - timedelta(days=365)

# Janela de busca: últimos 30 meses
DATA_INICIO_BUSCA = HOJE - timedelta(days=30 * 30)  # 2.5 anos atrás


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def medware_agendamentos(data_inicio: str, data_fim: str, cod_medico: int = None) -> list:
    """Lista agendamentos no Medware no intervalo dado.

    data_inicio/data_fim no formato 'YYYY-MM-DD'.
    """
    url = f"{MEDWARE_BASE}/Medware/Agendamentos/Listar"
    params = {
        "dataInicio": data_inicio,
        "dataFim": data_fim,
    }
    if cod_medico:
        params["codMedico"] = cod_medico
    try:
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            print(f"   ⚠️  HTTP {r.status_code}: {r.text[:100]}")
            return []
        data = r.json()
        if isinstance(data, dict) and data.get("ok") is False:
            print(f"   ⚠️  Medware retornou ok=false: {data.get('error', '')}")
            return []
        if isinstance(data, dict) and "data" in data:
            return data["data"] or []
        return data or []
    except Exception as e:
        print(f"   ⚠️  Erro: {e}")
        return []


def normalizar_telefone(tel_raw: str) -> str:
    if not tel_raw:
        return ""
    digitos = re.sub(r"\D", "", str(tel_raw))
    if not digitos:
        return ""
    if not digitos.startswith("55") and len(digitos) >= 10:
        digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 13:
        return ""
    return digitos


def consulta_foi_realizada(ag: dict) -> bool:
    """Heurística: consulta realizada se tem dataHoraLiberacao OR
    dataHoraChegada preenchida."""
    return bool(ag.get("dataHoraLiberacao") or ag.get("dataHoraChegada"))


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("PACIENTES SEM RETORNO HÁ MAIS DE 1 ANO (via agent server-side)")
    print("=" * 60)

    # ----- Chama endpoint agent (que tem auth Medware) -----
    AGENT_BASE = os.environ.get("AGENT_BASE_URL", "https://blink-agent.6prkfn.easypanel.host")
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
    if not WEBHOOK_SECRET:
        print("❌ WEBHOOK_SECRET não encontrado")
        sys.exit(2)

    print(f"▶ Chamando {AGENT_BASE}/admin/medware-pacientes-sem-retorno ...")
    print("   (varre 30 meses de agendamentos; pode demorar 1-3 min)")
    try:
        r = requests.get(
            f"{AGENT_BASE}/admin/medware-pacientes-sem-retorno",
            params={"secret": WEBHOOK_SECRET, "meses_min": "12", "meses_busca": "30"},
            timeout=300,
        )
    except Exception as e:
        print(f"❌ Erro chamando agent: {e}")
        sys.exit(1)

    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text[:500]}")
        sys.exit(1)
    resp = r.json()
    if not resp.get("ok"):
        print(f"❌ Agent retornou erro: {resp}")
        sys.exit(1)

    print(f"   ✓ Páginas varridas: {resp.get('paginas_varridas')}")
    print(f"   ✓ Total agendamentos: {resp.get('total_agendamentos')}")
    print(f"   ✓ Pacientes únicos: {resp.get('pacientes_unicos')}")
    print(f"   ✓ Data corte: {resp.get('data_corte')}\n")

    pacientes_brutos = resp.get("pacientes") or []
    print(f"📊 Elegíveis devolvidos pelo agent: {len(pacientes_brutos)}\n")

    # Skip o resto da lógica antiga — agent já filtrou tudo
    todos_ag = []  # unused
    por_paciente = {p["codPaciente"]: {
        "codPaciente": p["codPaciente"],
        "nome": p["nome"],
        "telefone": p["telefone"],
        "dataNascimento": p["dataNascimento"],
        "cpf": p["cpf"],
        "agendamentos": [{
            "data": datetime.fromisoformat(p["ultimaConsulta_iso"]),
            "codMedico": p["codMedico"],
            "codUnidade": p["codUnidade"],
        }] * (p["totalConsultas"] or 1),
    } for p in pacientes_brutos}
    print(f"   Pacientes únicos: {len(por_paciente)}\n")

    # ----- Indexar por paciente -----
    print("▶ Indexando por codPaciente...")
    por_paciente: dict[int, dict] = {}
    for ag in todos_ag:
        if not consulta_foi_realizada(ag):
            continue
        paciente = ag.get("paciente") or {}
        cod = paciente.get("codPaciente")
        if not cod:
            continue

        try:
            data_ag = datetime.strptime(ag["dataHoraAgendada"], "%d/%m/%Y %H:%M")
        except Exception:
            continue

        bucket = por_paciente.setdefault(cod, {
            "codPaciente": cod,
            "nome": paciente.get("nome", ""),
            "telefone": paciente.get("telefone", ""),
            "dataNascimento": paciente.get("dataNascimento", ""),
            "cpf": paciente.get("cpf", ""),
            "agendamentos": [],
        })
        bucket["agendamentos"].append({
            "data": data_ag,
            "codMedico": (ag.get("medico") or {}).get("codMedico"),
            "codUnidade": ag.get("codUnidade"),
        })

    print(f"   Pacientes únicos: {len(por_paciente)}\n")

    # ----- Filtrar elegíveis -----
    print("▶ Filtrando elegíveis (última consulta há mais de 1 ano)...")
    elegiveis = []
    descartados_recente = 0
    sem_telefone = 0

    for cod, bucket in por_paciente.items():
        ags_sorted = sorted(bucket["agendamentos"], key=lambda x: x["data"], reverse=True)
        ultima = ags_sorted[0]
        if ultima["data"] >= LIMITE_1_ANO:
            descartados_recente += 1
            continue

        tel_norm = normalizar_telefone(bucket["telefone"])
        if not tel_norm:
            sem_telefone += 1
            continue

        # Pega médico mais frequente desse paciente
        med_count = defaultdict(int)
        for a in bucket["agendamentos"]:
            if a.get("codMedico"):
                med_count[a["codMedico"]] += 1
        med_principal = max(med_count, key=med_count.get) if med_count else None

        elegiveis.append({
            "codPaciente": cod,
            "nome": bucket["nome"],
            "telefone": tel_norm,
            "telefone_bruto": bucket["telefone"],
            "dataNascimento": bucket["dataNascimento"],
            "cpf": bucket["cpf"],
            "ultimaConsulta": ultima["data"].strftime("%d/%m/%Y"),
            "ultimaConsulta_iso": ultima["data"].strftime("%Y-%m-%d"),
            "totalConsultas": len(bucket["agendamentos"]),
            "medicoPrincipal_cod": med_principal,
            "medicoPrincipal_nome": MEDICOS_BLINK.get(med_principal, "?"),
            "unidadeUltima_nome": UNIDADES.get(ultima.get("codUnidade"), "?"),
        })

    print(f"   Descartados (consulta recente): {descartados_recente}")
    print(f"   Descartados (sem telefone válido): {sem_telefone}")
    print(f"   ✅ ELEGÍVEIS: {len(elegiveis)}\n")

    # ----- Stats por médico -----
    por_medico = defaultdict(int)
    for e in elegiveis:
        por_medico[e["medicoPrincipal_nome"]] += 1
    print("📊 Distribuição por médico principal:")
    for med, n in sorted(por_medico.items(), key=lambda x: -x[1]):
        print(f"   {n:>5} · {med}")
    print()

    # ----- Amostra -----
    print("📋 Amostra (5 primeiros):")
    for e in elegiveis[:5]:
        print(f"   {e['codPaciente']:>6} · {e['ultimaConsulta']} · {e['telefone']:14} · {e['medicoPrincipal_nome'][:25]:25} · {e['nome'][:40]}")
    print()

    # ----- Salvar -----
    ts = int(time.time())
    out = REPO_DIR / "scripts" / f"pacientes_sem_retorno_1ano_{ts}.json"
    out.write_text(json.dumps(elegiveis, ensure_ascii=False, indent=2))
    print(f"📝 Salvo em: {out.name}")
    print(f"   Pra disparar: usar batch_dispara_template_1020_para_medware.py")


if __name__ == "__main__":
    main()
