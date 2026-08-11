#!/usr/bin/env python3
"""
Batch ativação — #07-lista-pacientes-julho — template blink_proxima_consulta_ferias_v1.

Lê os 184 nomes da lista de julho (embutidos abaixo), busca cada um no Kommo,
filtra por status_id e convênio, dispara o template via endpoint
/admin/disparar-template/{lead_id} do agent em prod.

Skip:
  • Status finalizados: 91486864 (8-REALIZADO), 101507507 (5-AGENDADO),
    101109455 (6-CONFIRMAR), 106653499 (7.CONFIRMADO), 142, 143, 106184983.
  • Convênios bloqueados: Inas, GDF, Cassi, SulAmerica, Bradesco.

Cada disparo grava nota Kommo automaticamente (dispatcher).

Roda standalone — não depende do agent local, só lê WEBHOOK_SECRET do .env.
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------

REPO_DIR = Path(__file__).resolve().parents[1]
ENV_FILES = [
    REPO_DIR / ".env",
    REPO_DIR / ".env.local",
    REPO_DIR / "voice_agent" / ".env",
    REPO_DIR / "lia_engineer" / ".env.local",  # fallback — Lia Engineer compartilha as envs
]

def load_env() -> None:
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v

load_env()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
KOMMO_TOKEN = os.environ.get("KOMMO_TOKEN", "")
AGENT_BASE = os.environ.get("AGENT_BASE_URL", "https://blink-agent.6prkfn.easypanel.host")
KOMMO_BASE = "https://univeja.kommo.com/api/v4"

if not WEBHOOK_SECRET:
    print("❌ WEBHOOK_SECRET não encontrado em .env / .env.local / voice_agent/.env")
    sys.exit(2)
if not KOMMO_TOKEN:
    print("❌ KOMMO_TOKEN não encontrado em .env")
    sys.exit(2)

print(f"✓ WEBHOOK_SECRET carregado ({len(WEBHOOK_SECRET)} chars)")
print(f"✓ KOMMO_TOKEN carregado ({len(KOMMO_TOKEN)} chars)")
print(f"✓ AGENT_BASE = {AGENT_BASE}")
print()

# ---------------------------------------------------------------------------
# Regras de skip
# ---------------------------------------------------------------------------

STATUS_FINALIZADOS = {
    91486864,   # 8-REALIZADO CONSULTA
    101507507,  # 5-AGENDADO
    101109455,  # 6-CONFIRMAR
    106653499,  # 7.CONFIRMADO
    106184983,  # 7.1-NO-SHOW
    142,        # closed-won
    143,        # closed-lost
}

CONVENIOS_BLOQUEADOS = ["inas", "gdf", "cassi", "sulamerica", "sul america", "bradesco"]

TEMPLATE_NAME = "blink_proxima_consulta_ferias_v1"
TEMPLATE_LANG = "pt_BR"

# ---------------------------------------------------------------------------
# Lista completa #07-lista-pacientes-julho (extraída do Slack)
# Formato: (id_canal, nome_primario_pra_busca, todos_os_nomes_separados_por_/)
# ---------------------------------------------------------------------------

LISTA_JULHO = [
    # 0001 - 0050
    ("0001", "Thomas Döwich Rall"),
    ("0002", "Bruno Cassol de Castro"),
    ("0003", "Sofia Ayami Veloso Yano"),
    ("0004", "Lucas Portugal Pissutti"),
    ("0005", "Fabio Alexandre e Silva"),
    ("0006", "Isis Cardoso Bruno"),
    ("0007", "Laura Ferreira Monteiro"),
    ("0008", "Barbara Cristina Galvão Adiala"),
    ("0009", "Rodrigo Henriques Campos"),
    ("0010", "Fellipe Teixeira Carvalho"),
    ("0011", "Marina Aliprandi Camilato"),
    ("0012", "Eduardo Cocota Mendes"),
    ("0013", "Pietra Fantinel Tomasini"),
    ("0014", "Carina Schlabitz Ferreira"),
    ("0015", "Guilherme Eustáquio de Moraes Mota"),
    ("0016", "Fernanda Botelho Silveira"),
    ("0017", "Rogens Lino Gonçalves Barbosa"),
    ("0018", "Wendel Teixeira Santos"),
    ("0019", "Marcia Castilho de Sales"),
    ("0020", "Miguel Miranda de Oliveira"),
    ("0021", "Roberta Maria Rocha Barbosa Ferreira"),
    ("0022", "Jorge Reis Munhoz Belo"),
    ("0023", "Beatriz Belo Freire"),
    ("0024", "Clarice Rocha Brandão de Souza Cavalcanti"),
    ("0025", "Rayssa Santana de Moraes"),
    ("0026", "Clara Delalibera Rodrigues"),
    ("0027", "Maria Thereza de Medeiros Alves Kuhlmann"),
    ("0028", "Leonel Masoller Wendt Filho"),
    ("0029", "Mateus Albuquerque de Almeida"),
    ("0030", "Joaquim Pinheiro da Luz"),
    ("0031", "Arnaldo Ribeiro Nacarato"),
    ("0032", "Janaina Pereira Braz de Souza"),
    ("0033", "Gustavo Moura de Sousa"),
    ("0034", "Helena Araujo Soares Santos"),
    ("0035", "Jonas Morinishi da Silva Rocha"),
    ("0036", "Leise Rios Viana Ayres"),
    ("0037", "Mavie Oliveira Severo Franco"),
    ("0038", "Sara Regazzi Moreira"),
    ("0039", "Micaella Pinho Soares Alcantara Crema"),
    ("0040", "Davi Nogueira Rodrigues"),
    ("0041", "Leandro Vinicius Fortes da Silva"),
    ("0042", "Joaquim Luiz Blanger Santiago"),
    ("0043", "Daniel Cantanhede de Barros"),
    ("0044", "Eduardo Andrade Caetano Oliveira"),
    ("0045", "Laura Buhler Vilhena"),
    ("0046", "Benicio Ávila Niemeyer"),
    ("0047", "Vitor Garcia Scarpinelli"),
    ("0048", "Davi Morais dos Santos"),
    ("0049", "Laura Goncalves Carneiro"),
    ("0050", "Tomás Guimarães Figueiredo"),
    # 0051 - 0100
    ("0051", "Joao Rafael Machado Goncalves Olinto Pessoa"),
    ("0052", "Joao Inacio Rodrigues Moreira"),
    ("0053", "Henrique Francica Aguiar de Oliveira"),
    ("0054", "Laura Ferreira Monteiro"),
    ("0055", "Lais Marques Moreira"),
    ("0056", "Helena Ayumi Goto Santiago"),
    ("0057", "Manuela Barbosa de Macedo Esteves"),
    ("0058", "Murilo de Sousa Vieira Oliveira"),
    ("0059", "Liana Sena da Silva Castro"),
    ("0060", "Teresa Gardino Menezes de Carvalho"),
    ("0061", "Jade Tupinamba Cruz de Azevedo"),
    ("0062", "Hugo Mello Kohnert Seidler"),
    ("0063", "Pathna Leticia Freitas Placido Mendes Carneiro"),
    ("0064", "Rebecah Carmo de Sousa"),
    ("0065", "Angelo Fioravanti de Oliveira"),
    ("0066", "Olivia Afonso de Paula Rodrigues"),
    ("0067", "Heitor Quixabeira Marinho"),
    ("0068", "Felipe Melo Borges"),
    ("0069", "Noah Barbosa Gonçalves"),
    ("0070", "Pedro Mayer de Camargo"),
    ("0071", "Vitoria Altfuldisck Soares"),
    ("0072", "Tito Neves Weber Pinheiro"),
    ("0073", "Laura Pessoa Marangon"),
    ("0074", "Osman Farias Filho"),
    ("0075", "Sophia Pan Teixeira"),
    ("0076", "Martin Rideyoshi Teijeira Guibo"),
    ("0077", "Helienne Rizzo de Paula"),
    ("0078", "Jade de Oliveira Cabral"),
    ("0079", "Luciana Paola Demociani"),
    ("0080", "Davi Schroder de Holanda Faria"),
    ("0081", "Enrico de Lima Santana"),
    ("0082", "Clara Carvalho Jordão"),
    ("0083", "Júlia Requião de Andrade"),
    ("0084", "Ana Luiza Moreira de Oliveira"),
    ("0085", "João Miguel Vieira Alves Valduga"),
    ("0086", "Maria Fernanda de Almeida Carvalho"),
    ("0087", "Maria Eduarda de Oliveira Florindo"),
    ("0088", "Fernanda Lopes Braga"),
    ("0089", "Afonso Oliveira Lopes"),
    ("0090", "Beatriz Lobosque de Almeida Cunha"),
    ("0091", "Lis de Melo Cunha"),
    ("0092", "Lana Marcal de Sousa Barbosa"),
    ("0093", "Isaac Cardoso Leite"),
    ("0094", "Selena Deolindo de Carvalho Amaral"),
    ("0095", "Carlos Eduardo Siqueira dos Santos"),
    ("0096", "Debora Fernanda Moura dos Santos"),
    ("0097", "Isabela Alves Crescenti"),
    ("0098", "Ana Clara de Oliveira dos Santos"),
    ("0099", "Mateus Yoshihiro Matos Lima Tatugawa"),
    ("0100", "Gabriel Sbampato Franca Moura Paim"),
    # 0101 - 0150
    ("0101", "Cecilia Fantinel Tomasini"),
    ("0102", "Beatriz Rocha Ferreira de Oliveira"),
    ("0103", "Serena Melo Guerra"),
    ("0104", "Cesar Nogueira Rodrigues"),
    ("0105", "Arthur Guedes Souza"),
    ("0106", "Isadora Ribeiro Soares"),
    ("0107", "Priscila Goggin Alves"),
    ("0108", "Ava Gruneich do Amaral"),
    ("0109", "Henrique Melo Vianna"),
    ("0110", "Maite Barbosa Ruztz"),
    ("0111", "Sandra Cristina Ribeiro"),
    ("0112", "Eloah Zuany Fagundes"),
    ("0113", "Francesca Marliere Pita"),
    ("0114", "Joao Pedro dos Santos Reis"),
    ("0115", "Alice de Abreu Sobreira"),
    ("0116", "Giovana Pereira dos Santos"),
    ("0117", "Fernando Nagano Foschiera"),
    ("0118", "Zahara Teofilo Bonfim"),
    ("0119", "Miguel Pereira Masoller"),
    ("0120", "Eva Cardoso Santana"),
    ("0121", "Gabriela Castro Silva"),
    ("0122", "Julia Poema Cardoso da Silva"),
    ("0123", "Beatriz Cardoso Souto Muniz"),
    ("0124", "Maria Alice Alvarenga Peixoto"),
    ("0125", "Luisa Lopes Rocha"),
    ("0126", "Davi Oliveira Silva"),
    ("0127", "Miguel Soares do Nascimento"),
    ("0128", "Maria Valentina Ceciliano Eleuterio"),
    ("0129", "Bernardo Reis Costa"),
    ("0130", "Leonardo Machado de Sousa"),
    ("0131", "Ravi Bandeira Oliveira Bezerra"),
    ("0132", "Melissa Vargas Nakatani"),
    ("0133", "Anna Flavia Araujo Ribeiro Sant Anna"),
    ("0134", "Heloisa Abdala Rosa"),
    ("0135", "Isabella Guimaraes Elmasry"),
    ("0136", "Julia Curi de Sousa"),
    ("0137", "Heloisa Abdala Rosa"),
    ("0138", "Leticia Carneiro Dornellas de Castro"),
    ("0139", "Henrique de Medeiros Santana"),
    ("0140", "Benicio de Matos"),
    ("0141", "Arthur Nunes Duarte Martins"),
    ("0142", "Gabriele Vasconcelos Arnaud"),
    ("0143", "Larissa Vitoria de Mendonca Lima"),
    ("0144", "Enzo Olivi Lins de Araujo"),
    ("0145", "Julia Kineipp de Souza Andrade"),
    ("0146", "Henrique Monteiro Roberto Alves"),
    ("0147", "Antonio Debortoli Maschio"),
    ("0148", "Fernando Avila Sampaio"),
    ("0149", "Livia Villani Calais"),
    ("0150", "Henry Gomes dos Reis"),
    # 0151 - 0184
    ("0151", "Arthur de Mello Curado"),
    ("0152", "Luna Cecilia Assis de Mello"),
    ("0153", "Sonia Maria Rodrigues de Melo"),
    ("0154", "Rebeca Bernardes Marques"),
    ("0155", "Guilherme Linhares Godoi"),
    ("0156", "Eloah Bender Rodrigues"),
    ("0157", "Felipe Magalhaes Meinberg"),
    ("0158", "Davi Curado Freire"),
    ("0159", "Gael Alves e Domingues Soares"),
    ("0160", "Arthur Ribeiro Cruzeiro"),
    ("0161", "Rebecca Escorcio Sousa"),
    ("0162", "Davi de Oliveira Almeida"),
    ("0163", "Eduardo Campelo Gomes"),
    ("0164", "Heitor Pires Pimentel"),
    ("0165", "Ana Clara Rabello Ataides"),
    ("0166", "Tales de Castro Santos"),
    ("0167", "Bernardo Alves Ferreira"),
    ("0168", "Hugo Fernando Kotama Varela"),
    ("0169", "Joao Pedro Brito Correa"),
    ("0170", "Aleksander Velozo Pascoal"),
    ("0171", "Gustavo Lima Rodrigues"),
    ("0172", "Maria Julia Torres Lopes"),
    ("0173", "Maria Helena da Silva Pinto"),
    ("0174", "Samuel Fernandes de Freitas"),
    ("0175", "Ana Laís Alves da Silva"),
    ("0176", "Henrique Botelho de Carvalho"),
    ("0177", "Caetano de Oliveira Lobo"),
    ("0178", "Elis Dias de Assis"),
    ("0179", "Marina Mítica Nunes"),
    ("0180", "Emanuele Santana Abreu"),
    ("0181", "Fábio Junior Francisco Almeida"),
    ("0182", "Catarina Nery Siqueira"),
    ("0183", "Lucca Viana Barreto"),
    ("0184", "Antonio Pereira Abreu"),
]

# ---------------------------------------------------------------------------
# Helpers Kommo
# ---------------------------------------------------------------------------

def kommo_search(query: str) -> list:
    url = f"{KOMMO_BASE}/leads"
    params = {"query": query, "limit": 5, "with": "contacts"}
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("_embedded", {}).get("leads", [])
    except Exception as e:
        print(f"  ⚠️  Kommo search error: {e}")
        return []


def get_first_name(name: str) -> str:
    return name.strip().split()[0].title() if name.strip() else ""


def extract_convenio(lead: dict) -> str:
    for cf in lead.get("custom_fields_values") or []:
        if cf.get("field_id") == 853206:  # CONVÊNIO
            vals = cf.get("values") or []
            if vals:
                return (vals[0].get("value") or "").strip().lower()
    return ""


# Bug C-21 (Fábio 10/06/2026) — respeitar protocolo médico
FIELD_DIA_CONSULTA = 1255723        # date_time da última/próxima consulta
FIELD_MES_PROX_CONSULTA = 1260588   # select "Maio 2027" etc

def _cf_value(lead: dict, field_id: int):
    for cf in lead.get("custom_fields_values") or []:
        if cf.get("field_id") == field_id:
            vals = cf.get("values") or []
            if vals:
                return vals[0].get("value")
    return None

def protocolo_medico_ja_definido(lead: dict) -> tuple[bool, str]:
    """Retorna (bloquear, motivo).

    Bloqueia se:
      • 1.MÊS PRÓX CONSULTA preenchido (Dra. Karla já definiu retorno)
      • 1.DIA CONSULTA é data <6 meses atrás (paciente acabou de consultar)
    """
    import time as _t
    seis_meses_atras = _t.time() - (183 * 86400)
    mes_prox = _cf_value(lead, FIELD_MES_PROX_CONSULTA)
    if mes_prox:
        return True, f"1.MÊS PRÓX CONSULTA = {mes_prox}"
    dia_consulta = _cf_value(lead, FIELD_DIA_CONSULTA)
    if dia_consulta:
        try:
            ts = int(dia_consulta)
            if ts > seis_meses_atras:
                from datetime import datetime
                dt = datetime.fromtimestamp(ts)
                return True, f"1.DIA CONSULTA recente: {dt.strftime('%d/%m/%Y')}"
        except Exception:
            pass
    return False, ""


def convenio_bloqueado(conv: str) -> bool:
    if not conv:
        return False
    return any(b in conv for b in CONVENIOS_BLOQUEADOS)


def get_lead_main_contact_name(lead: dict) -> str:
    contacts = (lead.get("_embedded") or {}).get("contacts") or []
    if not contacts:
        return ""
    # tenta com first contact
    cid = contacts[0].get("id")
    if not cid:
        return ""
    url = f"{KOMMO_BASE}/contacts/{cid}"
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return (r.json().get("name") or "").strip()
    except Exception:
        pass
    return ""

# ---------------------------------------------------------------------------
# Disparo via endpoint
# ---------------------------------------------------------------------------

def disparar(lead_id: int, primeiro_nome: str, medico: str = "Dra. Karla") -> dict:
    url = f"{AGENT_BASE}/admin/disparar-template/{lead_id}"
    payload = {
        "template": TEMPLATE_NAME,
        "lang": TEMPLATE_LANG,
        "body_params": [primeiro_nome, medico],
    }
    params = {"secret": WEBHOOK_SECRET}
    try:
        r = requests.post(url, params=params, json=payload, timeout=20)
        return {
            "status_code": r.status_code,
            "body": r.text[:500],
            "ok": 200 <= r.status_code < 300,
        }
    except Exception as e:
        return {"status_code": 0, "body": str(e), "ok": False}

# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def main() -> None:
    log_path = Path(__file__).resolve().parent / f"log_batch_ferias_julho_{int(time.time())}.txt"
    print(f"📝 Log: {log_path}\n")

    counts = {"DISPARA": 0, "SKIP_REALIZADO": 0, "SKIP_CONVENIO": 0, "SKIP_PROTOCOLO": 0, "SKIP_NOTFOUND": 0, "ERRO": 0}
    detalhes = []

    print(f"▶ Processando {len(LISTA_JULHO)} entradas da lista de julho...\n")

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"# Batch ferias julho — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for idx, (slack_id, nome) in enumerate(LISTA_JULHO, start=1):
            tag_prefix = f"[{idx:3d}/{len(LISTA_JULHO)}] #{slack_id} {nome[:40]:<40}"
            leads = kommo_search(nome)

            if not leads:
                counts["SKIP_NOTFOUND"] += 1
                msg = f"{tag_prefix} → SKIP (não encontrado no Kommo)"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            # Escolher o lead mais "ativo" — prefere status_id NÃO finalizado
            lead = None
            for cand in leads:
                if cand.get("status_id") not in STATUS_FINALIZADOS:
                    lead = cand
                    break
            if lead is None:
                # todos finalizados
                counts["SKIP_REALIZADO"] += 1
                msg = f"{tag_prefix} → SKIP (todos os {len(leads)} leads estão em status finalizado)"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            lead_id = lead["id"]
            status_id = lead.get("status_id")
            conv = extract_convenio(lead)

            if convenio_bloqueado(conv):
                counts["SKIP_CONVENIO"] += 1
                msg = f"{tag_prefix} → SKIP (convênio bloqueado: {conv})"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            # Bug C-21 — respeitar protocolo médico
            bloquear, motivo_proto = protocolo_medico_ja_definido(lead)
            if bloquear:
                counts["SKIP_PROTOCOLO"] += 1
                msg = f"{tag_prefix} → SKIP PROTOCOLO (Bug C-21): {motivo_proto}"
                print(msg); logf.write(msg + "\n")
                time.sleep(0.3)
                continue

            # Buscar nome do contato pra body_param.
            # Bug 11/06 (Fábio, lead 22723784 Enzo Olivi): NUNCA cair pro nome do
            # paciente como fallback — o contato é a pessoa que recebe a mensagem,
            # geralmente o responsável (mãe/pai). Se contato vazio → "olá" puro.
            contato_nome = get_lead_main_contact_name(lead)
            primeiro = get_first_name(contato_nome)
            # Validação anti-fallback-paciente: nome inválido vira "olá"
            try:
                from voice_agent.contato_nome import nome_contato_invalido
                if nome_contato_invalido(primeiro):
                    primeiro = "olá"
            except ImportError:
                # Fallback se import falhar: regras mínimas
                proibidos = {"voce", "ola", "oi", "cliente", "paciente",
                             "test", "teste", "inbra", "lia", ""}
                if not primeiro or primeiro.lower() in proibidos:
                    primeiro = "olá"

            # Disparar
            result = disparar(lead_id, primeiro, "Dra. Karla")
            if result["ok"]:
                counts["DISPARA"] += 1
                msg = f"{tag_prefix} → OK lead={lead_id} status={status_id} primeiro={primeiro}"
            else:
                counts["ERRO"] += 1
                msg = f"{tag_prefix} → ERRO {result['status_code']}: {result['body'][:120]}"
            print(msg); logf.write(msg + "\n")
            detalhes.append({
                "slack_id": slack_id, "nome": nome,
                "lead_id": lead_id, "status_id": status_id,
                "convenio": conv, "primeiro_nome": primeiro,
                "disparo": result,
            })

            # Rate limit / pacing
            time.sleep(0.6)

        # Resumo final
        print()
        print("=" * 60)
        print("RESUMO FINAL")
        print("=" * 60)
        for k, v in counts.items():
            print(f"  {k:<20} {v}")
        print(f"  {'TOTAL':<20} {sum(counts.values())}")

        logf.write("\n# RESUMO\n")
        for k, v in counts.items():
            logf.write(f"{k}: {v}\n")
        logf.write(f"TOTAL: {sum(counts.values())}\n")
        logf.write("\n# DETALHES JSON\n")
        logf.write(json.dumps(detalhes, ensure_ascii=False, indent=2))

    print(f"\n📝 Log completo: {log_path}")


if __name__ == "__main__":
    main()
