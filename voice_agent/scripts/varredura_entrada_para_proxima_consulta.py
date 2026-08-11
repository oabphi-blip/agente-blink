#!/usr/bin/env python3
"""Varredura 0-ETAPA ENTRADA × Medware 2026 → move quem já consultou.

OBJETIVO (Fábio 18/06/2026):
  Varrer TODOS os leads em 0-ETAPA ENTRADA (Kommo status_id 96441724,
  pipeline ATENDE 8601819). Para cada lead, cruzar o telefone do contato
  com a agenda Medware 2026. Se o paciente já tem consulta REALIZADA em
  2026 → mover o lead para 10-PRÓXIMA CONSULTA (status_id 106157327) e
  gravar nota Kommo explicando o motivo.

  Pergunta de negócio respondida no fim: quantos leads SOBRAM em
  0-ETAPA ENTRADA após a varredura — essa é a fila real para campanha.

DESVIO INTENCIONAL da spec original (e por quê):
  A spec pedia 1 chamada Medware POR lead (buscar_pacientes + listar
  agendamentos por codPaciente). Mas:
    1. `MedwareClient.buscar_pacientes(telefonePaciente=...)` NÃO existe.
    2. `listar_agendamentos` é por PERÍODO de datas, não por codPaciente.
    3. A VM Medware "Light" estoura com carga (Bug C-38b) — N×12 chamadas
       seriam suicídio operacional.
  Solução adotada (mesma do voice_agent/reconciliation.py, já em prod):
  construir UM índice 2026 por telefone com 12 chamadas (1/mês), e cruzar
  localmente. Cada agendamento Medware expõe `paciente.telefone` — forma
  confirmada pelo reconciliation.py. Diferença vs reconciliation: aqui
  filtramos só REALIZADO (não conta agendamento futuro), só varremos
  ENTRADA, gravamos nota e CSV.

MODOS:
  (default) dry-run — só lê e escreve o CSV. NÃO altera o Kommo.
  --apply         — move o lead + grava nota Kommo de fato.

CREDENCIAIS (ordem de resolução):
  env var > .env (raiz / .env.local / voice_agent/.env) > config.json
  Necessárias: KOMMO_TOKEN, KOMMO_SUBDOMAIN(=univeja), MEDWARE_USER,
  MEDWARE_PASSWORD.

USO:
  python3 voice_agent/scripts/varredura_entrada_para_proxima_consulta.py
  python3 voice_agent/scripts/varredura_entrada_para_proxima_consulta.py --apply
  python3 voice_agent/scripts/varredura_entrada_para_proxima_consulta.py --max 1000
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Bootstrap de path — roda standalone a partir da raiz do repo.
# ---------------------------------------------------------------------------
REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR))

from voice_agent.kommo import KommoClient  # noqa: E402
from voice_agent.medware import MedwareClient  # noqa: E402


# ---------------------------------------------------------------------------
# Normalização de telefone — chave de pareamento Kommo × Medware.
#
# IMPORTANTE: o _phone_key do reconciliation.py NÃO serve aqui. Formatos reais:
#   Medware: "(61)996816365 (cel)" → 11 díg (DDD+9+8, SEM código país, COM 9º)
#   Kommo:   "556299016006"        → 12 díg (55+DDD+8, COM país, SEM 9º)
# O _phone_key antigo só normaliza 55-prefixado de 13 díg → o formato Medware
# escapa e o DDD é comido (→ zero match). Aqui canonizamos para DDD + 8 dígitos
# de assinante (drop 55, drop 9º dígito) — denominador comum aos dois lados.
# ---------------------------------------------------------------------------
def _phone_key(value: str) -> str:
    d = "".join(ch for ch in str(value or "") if ch.isdigit())
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]               # remove código do país
    if len(d) == 11 and d[2] == "9":
        d = d[:2] + d[3:]       # DDD + 9 + 8 → dropa o 9º dígito → DDD + 8
    return d[-10:] if len(d) >= 10 else d

# ---------------------------------------------------------------------------
# Constantes do funil (confirmadas em voice_agent/kommo.py + reconciliation.py)
# ---------------------------------------------------------------------------
PIPELINE_ATENDE = 8601819
ST_ENTRADA = 96441724        # 0-ETAPA ENTRADA (origem)
ST_PROXIMA_CONSULTA = 106157327  # 10-PRÓXIMA CONSULTA (destino)
ANO = 2026

OUTPUT_DIR = REPO_DIR / "outputs"


# ---------------------------------------------------------------------------
# Carregamento de credenciais (mesmo padrão dos scripts batch existentes).
# ---------------------------------------------------------------------------
ENV_FILES = [
    REPO_DIR / ".env",
    REPO_DIR / ".env.local",
    REPO_DIR / "voice_agent" / ".env",
    REPO_DIR / "lia_engineer" / ".env.local",
]


def _load_env_files() -> None:
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _config_json() -> dict:
    for path in (REPO_DIR / "config.json", Path.cwd() / "config.json"):
        if path.exists():
            try:
                import json
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
    return {}


def _resolver_credenciais() -> dict:
    _load_env_files()
    cfg = _config_json()
    kommo_cfg = cfg.get("kommo", {}) if isinstance(cfg, dict) else {}
    mw_cfg = cfg.get("medware", {}) if isinstance(cfg, dict) else {}
    return {
        "kommo_token": os.getenv("KOMMO_TOKEN") or kommo_cfg.get("token", ""),
        "kommo_subdomain": (
            os.getenv("KOMMO_SUBDOMAIN") or kommo_cfg.get("subdomain", "") or "univeja"
        ),
        "medware_user": os.getenv("MEDWARE_USER") or mw_cfg.get("user", ""),
        "medware_password": (
            os.getenv("MEDWARE_PASSWORD") or mw_cfg.get("password", "")
        ),
    }


# ---------------------------------------------------------------------------
# Detecção de consulta REALIZADA num dict de agendamento Medware.
# Os nomes de campo da API Light não estão documentados no repo — por isso
# checamos múltiplas grafias defensivamente. Na 1ª execução real, o script
# dumpa amostras do JSON cru (ver --dump-sample) para confirmar/refinar.
# ---------------------------------------------------------------------------
def _get_ci(d: dict, *keys: str) -> Any:
    """get case-insensitive por uma lista de chaves candidatas."""
    if not isinstance(d, dict):
        return None
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, ""):
            return v
    return None


def _agendamento_realizado(ag: dict) -> bool:
    """True se o agendamento foi REALIZADO.

    Critérios (OR):
      - codStatusAgendamento == 5 (status REALIZADO no Medware)
      - hora_chegada E hora_liberacao preenchidos (paciente chegou e saiu)
    """
    status = _get_ci(
        ag, "codStatusAgendamento", "codStatus", "statusAgendamento", "status",
    )
    try:
        if status is not None and int(status) == 5:
            return True
    except (TypeError, ValueError):
        if str(status).strip().upper() in ("REALIZADO", "ATENDIDO", "FINALIZADO"):
            return True
    chegada = _get_ci(ag, "horaChegada", "hora_chegada", "dataHoraChegada")
    liberacao = _get_ci(
        ag, "horaLiberacao", "hora_liberacao", "dataHoraLiberacao", "horaSaida",
    )
    return bool(chegada) and bool(liberacao)


def _data_agendamento(ag: dict) -> str:
    """Extrai a data legível (DD/MM/AAAA) do agendamento, se houver."""
    raw = _get_ci(
        ag, "dataHoraChegada", "dataHoraAgendada", "dataHoraReferencia",
        "dataAgendamento", "data", "dataConsulta", "dataHora",
        "dataHoraAgendamento", "dia",
    )
    if not raw:
        return ""
    s = str(raw)
    # ISO "2026-06-18..." → DD/MM/AAAA
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s[:10]


def _telefone_do_agendamento(ag: dict) -> str:
    """Telefone do paciente dentro do dict de agendamento."""
    pac = ag.get("paciente") if isinstance(ag, dict) else None
    if isinstance(pac, dict):
        tel = _get_ci(pac, "telefone", "celular", "telefonePaciente", "fone")
        if tel:
            return str(tel)
    # fallback: telefone direto no agendamento
    tel = _get_ci(ag, "telefone", "celular", "telefonePaciente")
    return str(tel) if tel else ""


# ---------------------------------------------------------------------------
# Índice Medware 2026: phone_key → {realizado, ultima_data, total}
# ---------------------------------------------------------------------------
def construir_indice_medware(
    mw: MedwareClient, dump_sample: bool = False,
) -> dict[str, dict]:
    indice: dict[str, dict] = {}
    samples: list[dict] = []
    total_ags = 0
    import calendar
    for mes in range(1, 13):
        ini = f"01/{mes:02d}/{ANO}"
        # último dia REAL do mês — Medware retorna HTTP 400 para datas
        # inválidas como 31/06 (não "ignora o excedente"). Bug herdado do
        # reconciliation.py que pulava fev/abr/jun/set/nov silenciosamente.
        ultimo = calendar.monthrange(ANO, mes)[1]
        fim = f"{ultimo:02d}/{mes:02d}/{ANO}"
        try:
            ags = mw.listar_agendamentos(ini, fim)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Medware mês {mes:02d}/{ANO} falhou: {e}")
            continue
        ags = ags or []
        total_ags += len(ags)
        print(f"  · {mes:02d}/{ANO}: {len(ags)} agendamentos")
        for ag in ags:
            if dump_sample and len(samples) < 3 and isinstance(ag, dict):
                samples.append(ag)
            tel = _telefone_do_agendamento(ag)
            key = _phone_key(tel)
            if not key:
                continue
            realizado = _agendamento_realizado(ag)
            slot = indice.setdefault(
                key, {"realizado": False, "ultima_data": "", "total": 0}
            )
            slot["total"] += 1
            if realizado:
                slot["realizado"] = True
                data = _data_agendamento(ag)
                if data:
                    slot["ultima_data"] = data
    print(
        f"  → índice: {len(indice)} telefones distintos, "
        f"{total_ags} agendamentos varridos em {ANO}"
    )
    if dump_sample and samples:
        import json
        print("\n  AMOSTRA de agendamentos crus (confirmar nomes de campo):")
        for i, s in enumerate(samples, 1):
            print(f"  [{i}] {json.dumps(s, ensure_ascii=False)[:600]}")
        print()
    return indice


# ---------------------------------------------------------------------------
# Varredura principal
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Aplica de fato (move lead + grava nota). Default = dry-run.",
    )
    parser.add_argument(
        "--max", type=int, default=1000,
        help="Máximo de leads a varrer em ENTRADA (default 1000).",
    )
    parser.add_argument(
        "--dump-sample", action="store_true",
        help="Imprime 3 agendamentos crus do Medware para inspecionar campos.",
    )
    args = parser.parse_args()
    aplicar = bool(args.apply)

    print("=" * 70)
    print("VARREDURA 0-ETAPA ENTRADA × MEDWARE 2026 → 10-PRÓXIMA CONSULTA")
    print(f"Modo: {'APLICAR (move + nota)' if aplicar else 'DRY-RUN (só CSV)'}")
    print("=" * 70)

    cred = _resolver_credenciais()
    faltando = [
        nome for nome, val in (
            ("KOMMO_TOKEN", cred["kommo_token"]),
            ("MEDWARE_USER", cred["medware_user"]),
            ("MEDWARE_PASSWORD", cred["medware_password"]),
        ) if not val
    ]
    if faltando:
        print("\n❌ Credenciais ausentes no Mac (nem env, nem .env, nem config.json):")
        for f in faltando:
            print(f"   - {f}")
        print(
            "\n   Como resolver (escolha 1):\n"
            "   (a) criar arquivo .env na raiz do repo com:\n"
            "       KOMMO_TOKEN=...\n"
            "       KOMMO_SUBDOMAIN=univeja\n"
            "       MEDWARE_USER=...\n"
            "       MEDWARE_PASSWORD=...\n"
            "   (b) OU rodar este script no Easypanel (env vars já existem lá):\n"
            "       app blink/agent → Terminal → python3 voice_agent/scripts/\n"
            "       varredura_entrada_para_proxima_consulta.py\n"
            "   (c) OU exportar inline:\n"
            "       KOMMO_TOKEN=... MEDWARE_USER=... MEDWARE_PASSWORD=... \\\n"
            "         python3 voice_agent/scripts/"
            "varredura_entrada_para_proxima_consulta.py"
        )
        return 2

    kommo = KommoClient(
        subdomain=cred["kommo_subdomain"], token=cred["kommo_token"]
    )
    medware = MedwareClient(
        identificacao=cred["medware_user"], senha=cred["medware_password"]
    )

    # Sanidade Medware antes de varrer 12 meses.
    st = medware.status()
    print(f"\nMedware status: {st}")
    if not st.get("ok"):
        print("❌ Medware indisponível — abortando (não dá pra cruzar agenda).")
        return 3

    print("\n[1/3] Construindo índice Medware 2026 (12 chamadas, 1/mês)...")
    indice = construir_indice_medware(medware, dump_sample=args.dump_sample)
    if not indice:
        print("❌ Índice Medware vazio — abortando para não tomar decisão cega.")
        return 4

    print("\n[2/3] Paginando leads em 0-ETAPA ENTRADA...")
    leads: list[dict] = []
    page = 1
    while len(leads) < args.max:
        batch = kommo.list_leads_by_status(
            PIPELINE_ATENDE, [ST_ENTRADA], limit=250, page=page,
        )
        if not batch:
            break
        leads.extend(batch)
        page += 1
        if page > 40:  # teto de segurança (40×250 = 10k)
            break
    leads = leads[: args.max]
    total_entrada = len(leads)
    print(f"  → {total_entrada} leads em ENTRADA para avaliar")

    print(f"\n[3/3] Cruzando leads × Medware ({'APLICANDO' if aplicar else 'dry-run'})...")
    linhas: list[dict] = []
    cont = {
        "mover": 0, "movido_ok": 0, "movido_falha": 0,
        "ja_pendente_em_entrada": 0, "sem_match_medware": 0,
        "sem_contato": 0,
    }

    for i, ld in enumerate(leads, 1):
        lead_id = ld.get("id")
        nome_lead = ld.get("name") or ""
        decisao = ""
        ultima_data = ""
        telefone = ""
        try:
            contato = kommo.get_lead_main_contact(lead_id) or {}
            telefone = contato.get("telefone") or ""
            nome_contato = contato.get("nome") or ""
            if not telefone:
                decisao = "sem_contato"
            else:
                key = _phone_key(telefone)
                slot = indice.get(key)
                if not slot:
                    decisao = "sem_match_medware"
                elif slot.get("realizado"):
                    decisao = "mover"
                    ultima_data = slot.get("ultima_data") or ""
                else:
                    # tem agendamento em 2026 mas não REALIZADO (futuro/cancelado)
                    decisao = "ja_pendente_em_entrada"

            # Aplicação
            aplicado = ""
            if decisao == "mover":
                cont["mover"] += 1
                if aplicar:
                    nota = (
                        f"Cruzamento Medware: paciente já consultou em "
                        f"{ultima_data or ('em ' + str(ANO))}. Movido de "
                        f"0-ETAPA ENTRADA para 10-PRÓXIMA CONSULTA para "
                        f"acompanhamento de retorno. [varredura automática "
                        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}]"
                    )
                    moveu = kommo.update_lead_status(
                        lead_id, ST_PROXIMA_CONSULTA, PIPELINE_ATENDE,
                    )
                    notou = kommo.add_note(lead_id, nota) if moveu else False
                    aplicado = "ok" if moveu else "falha_mover"
                    if moveu:
                        cont["movido_ok"] += 1
                        if not notou:
                            aplicado = "movido_sem_nota"
                    else:
                        cont["movido_falha"] += 1
                    time.sleep(0.25)  # respeita rate-limit Kommo/proxy
            else:
                cont[decisao] = cont.get(decisao, 0) + 1

            linhas.append({
                "lead_id": lead_id,
                "nome_lead": nome_lead,
                "nome_contato": nome_contato if telefone else "",
                "telefone": telefone,
                "decisao": decisao,
                "ultima_consulta_2026": ultima_data,
                "aplicado": aplicado,
            })
        except Exception as e:  # noqa: BLE001
            linhas.append({
                "lead_id": lead_id, "nome_lead": nome_lead, "nome_contato": "",
                "telefone": telefone, "decisao": f"erro:{str(e)[:60]}",
                "ultima_consulta_2026": "", "aplicado": "",
            })
        if i % 25 == 0:
            print(f"  ... {i}/{total_entrada}")

    # -------------------------------------------------------------- CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sufixo = "APPLY" if aplicar else "DRYRUN"
    csv_path = OUTPUT_DIR / f"varredura_entrada_proxima_consulta_{sufixo}_{ts}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "lead_id", "nome_lead", "nome_contato", "telefone",
            "decisao", "ultima_consulta_2026", "aplicado",
        ])
        w.writeheader()
        w.writerows(linhas)

    # ----------------------------------------------------------- resumo
    movidos = cont["movido_ok"] if aplicar else cont["mover"]
    sobram_entrada = total_entrada - movidos

    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"Total em 0-ETAPA ENTRADA varridos: {total_entrada}")
    print(f"  • Já consultaram em {ANO} (mover→PRÓXIMA): {cont['mover']}")
    if aplicar:
        print(f"      - movidos com sucesso: {cont['movido_ok']}")
        print(f"      - falha ao mover:      {cont['movido_falha']}")
    print(f"  • Têm agenda {ANO} mas NÃO realizada (ficam): "
          f"{cont['ja_pendente_em_entrada']}")
    print(f"  • Sem match no Medware (ficam):  {cont['sem_match_medware']}")
    print(f"  • Sem telefone de contato:       {cont['sem_contato']}")
    print("-" * 70)
    print(f"➡ SOBRAM em 0-ETAPA ENTRADA após a varredura: {sobram_entrada}")
    print("   (essa é a FILA REAL para ativar com campanha)")
    if not aplicar:
        print("\n⚠ DRY-RUN: nada foi alterado no Kommo. Rode com --apply para mover.")
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
