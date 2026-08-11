#!/usr/bin/env python3
"""
Povoa o canal Slack C0BHGTD6U66 (#00-lista-pacientes-mais-de-1-ano)
com 620 pacientes do Medware que estão há mais de 1 ano sem vir.

Fonte: PACIENTES QUE ESTAO HA MAIS DE UM ANO OU DOIS SEM VIR.xls
       (620 registros, extraído em 15/07/2026)
CSV limpo: pacientes_mais_1ano.csv (na raiz do projeto)

Formato de cada thread:
  Msg principal:  0001_NOME COMPLETO PACIENTE
  Thread comment: URL search Kommo + últ consulta + convênio + telefone

Uso:
  1. Setar env SLACK_BOT_TOKEN_PACIENTES ou colar quando pedido:
     export SLACK_BOT_TOKEN_PACIENTES=xoxb-...
  2. python3 scripts/povoar_slack_pacientes_mais_1ano.py

Segurança:
  - Progresso salvo em pacientes_mais_1ano_progresso.json
  - Retomada automática: se rodar de novo, pula pacientes já postados
  - Rate limit Slack: 1 req/s (tier 3). Pausa 1.2s entre chamadas.
  - Estimativa total: ~25min pra 620 pacientes (2 posts/paciente = 1240 chamadas)
"""

from __future__ import annotations

import csv
import getpass
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CHANNEL_ID = "C0BHGTD6U66"
KOMMO_BASE = "https://univeja.kommo.com/leads/pipeline/8601819"
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "pacientes_mais_1ano.csv")
PROGRESSO_PATH = os.path.join(os.path.dirname(__file__), "..", "pacientes_mais_1ano_progresso.json")
DELAY_ENTRE_CHAMADAS = 1.2  # segundos


def carregar_pacientes() -> list[dict]:
    with open(CSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def carregar_progresso() -> dict:
    if not os.path.exists(PROGRESSO_PATH):
        return {"postados": [], "ultimo_numero": 0}
    with open(PROGRESSO_PATH, encoding="utf-8") as f:
        return json.load(f)


def salvar_progresso(p: dict) -> None:
    with open(PROGRESSO_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)


def obter_token() -> str:
    t = os.environ.get("SLACK_BOT_TOKEN_PACIENTES") or os.environ.get("SLACK_BOT_TOKEN")
    if t:
        return t
    print("SLACK_BOT_TOKEN não encontrado no env.")
    print("Cole seu Bot Token (começa com xoxb-...) e Enter:")
    return getpass.getpass("Token: ").strip()


def slack_post(token: str, payload: dict) -> dict:
    """POST pra chat.postMessage."""
    url = "https://slack.com/api/chat.postMessage"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def montar_msg_principal(numero: int, nome: str) -> str:
    return f"{numero:04d}_{nome.strip()}"


def montar_comment(paciente: dict) -> str:
    nome_busca = urllib.parse.quote(paciente["paciente"].strip())
    url_kommo = f"{KOMMO_BASE}?term={nome_busca}"
    linhas = [f"🔎 Kommo: {url_kommo}"]
    tel = paciente.get("telefone_limpo", "").strip()
    if tel:
        linhas.append(f"📞 Telefone Medware: {tel}")
    data = paciente.get("data_iso", "").strip()
    if data:
        # ISO -> BR
        try:
            y, m, d = data.split("-")
            linhas.append(f"🗓 Última consulta agendada: {d}/{m}/{y}")
        except Exception:
            linhas.append(f"🗓 Última consulta agendada: {data}")
    op = paciente.get("operadora", "").strip()
    if op:
        linhas.append(f"🏥 Operadora Medware: {op}")
    email = paciente.get("email", "").strip()
    if email and email.lower() != "não possui":
        linhas.append(f"✉️ E-mail: {email}")
    return "\n".join(linhas)


def main() -> int:
    pacientes = carregar_pacientes()
    total = len(pacientes)
    print(f"Total de pacientes no CSV: {total}")

    prog = carregar_progresso()
    ja_postados = set(prog.get("postados", []))
    ultimo_num = int(prog.get("ultimo_numero", 0))
    print(f"Já postados anteriormente: {len(ja_postados)}. Último número: {ultimo_num:04d}")

    token = obter_token()
    if not token or not token.startswith("xoxb-"):
        print("❌ Token Slack inválido (deve começar com xoxb-).")
        return 1

    inicio = time.time()
    numero = ultimo_num
    for i, p in enumerate(pacientes, start=1):
        nome = p["paciente"].strip()
        if not nome or nome in ja_postados:
            continue
        numero += 1

        msg_principal = montar_msg_principal(numero, nome)
        # 1) Posta mensagem principal
        try:
            r = slack_post(token, {
                "channel": CHANNEL_ID,
                "text": msg_principal,
            })
        except Exception as e:
            print(f"❌ #{numero:04d} {nome} — erro post principal: {e}")
            time.sleep(3)
            continue
        if not r.get("ok"):
            print(f"❌ #{numero:04d} {nome} — Slack não OK: {r.get('error')}")
            time.sleep(3)
            continue
        thread_ts = r.get("ts") or r.get("message", {}).get("ts")
        time.sleep(DELAY_ENTRE_CHAMADAS)

        # 2) Posta comment na thread
        try:
            r2 = slack_post(token, {
                "channel": CHANNEL_ID,
                "thread_ts": thread_ts,
                "text": montar_comment(p),
            })
        except Exception as e:
            print(f"⚠️  #{numero:04d} thread erro: {e}")

        ja_postados.add(nome)
        prog["postados"] = sorted(ja_postados)
        prog["ultimo_numero"] = numero
        salvar_progresso(prog)

        # Progresso a cada 10
        if numero % 10 == 0:
            elapsed = time.time() - inicio
            restante = total - numero
            eta_min = (restante * (elapsed / max(numero - ultimo_num, 1))) / 60
            print(f"✅ #{numero:04d} · {nome[:40]} · ETA {eta_min:.1f} min")
        else:
            print(f"✅ #{numero:04d} · {nome[:40]}")

        time.sleep(DELAY_ENTRE_CHAMADAS)

    print(f"\n✅ Concluído: {numero:04d} pacientes postados em {(time.time()-inicio)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
