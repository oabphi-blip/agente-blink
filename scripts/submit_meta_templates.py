#!/usr/bin/env python3
"""Submete os 14 templates Blink ao Meta WhatsApp Business em 1 comando.

USO:
    export WABA_ID="123456789012345"
    export WHATSAPP_BUSINESS_TOKEN="EAAxxxxxx"
    python3 scripts/submit_meta_templates.py

Ou pra submeter UM template específico:
    python3 scripts/submit_meta_templates.py blink_lf_a_convenio_aceito_v1

Pra rodar em modo dry-run (só imprime payloads, não submete):
    python3 scripts/submit_meta_templates.py --dry-run

Pra checar status dos já submetidos:
    python3 scripts/submit_meta_templates.py --list

Saídas:
    ✅ name — submetido (id=...)
    ⏭️  name — já existe (skip)
    ❌ name — erro: detalhe

Aprovação Meta:
    UTILITY  → 24h típico
    MARKETING → 24-72h típico
    Status em real-time no Business Manager → Modelos de mensagem.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    # Fallback usando urllib (Python built-in) — pra rodar sem pip install
    import urllib.request
    import urllib.error

    class _MiniResponse:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body
            self.text = body
        def json(self):
            return json.loads(self._body)

    class _MiniRequests:
        @staticmethod
        def _do(method, url, headers=None, json_body=None, timeout=30, params=None):
            if params:
                qs = "&".join(f"{k}={v}" for k, v in params.items())
                url = f"{url}{'&' if '?' in url else '?'}{qs}"
            data = None
            if json_body is not None:
                data = json.dumps(json_body).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method=method, headers=headers or {}
            )
            if json_body is not None and "Content-Type" not in (headers or {}):
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return _MiniResponse(resp.status, resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return _MiniResponse(e.code, e.read().decode("utf-8"))

        @staticmethod
        def post(url, headers=None, json=None, timeout=30):
            return _MiniRequests._do("POST", url, headers, json, timeout)

        @staticmethod
        def get(url, headers=None, params=None, timeout=30):
            return _MiniRequests._do("GET", url, headers, None, timeout, params)

    requests = _MiniRequests()


META_API_VERSION = "v21.0"  # versão estável mais recente
LANG = "pt_BR"


# ============================================================================
# DEFINIÇÕES DOS 14 TEMPLATES (sincronizado com META_TEMPLATES_PARA_SUBMISSAO.md)
# ============================================================================

TEMPLATES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------
    # CICLO LEAD FRIO (MARKETING)
    # ---------------------------------------------------------------
    {
        "name": "blink_lf_a_convenio_aceito_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink Oftalmologia. Seu convênio {{2}} cobre "
                    "consulta com a Dra. Karla Delalibera — sem sair do bolso.\n\n"
                    "Tenho horário pra essa semana ainda. Como prefere?\n\n"
                    "1. Asa Norte\n"
                    "2. Águas Claras\n"
                    "3. Prefiro que me liguem\n\n"
                    "Responde com 1, 2 ou 3 que eu já organizo."
                ),
                "example": {
                    "body_text": [["Maria Teresa", "Plan Assiste — MPF"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Asa Norte"},
                    {"type": "QUICK_REPLY", "text": "Águas Claras"},
                    {"type": "QUICK_REPLY", "text": "Me liguem"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_b_particular_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink Oftalmologia. Sei que o convênio {{2}} "
                    "não cobre aqui — mas temos uma condição particular com "
                    "sinal de 50% via Pix pra reservar o horário.\n\n"
                    "Valor consulta Dra. Karla Delalibera: R$ 611 "
                    "(sinal R$ 305,50). Vale a tranquilidade de fechar com "
                    "a melhor.\n\n"
                    "Como prefere seguir?\n\n"
                    "1. Agendar essa semana\n"
                    "2. Agendar pra próximas 2 semanas\n"
                    "3. Receber link de avaliação online primeiro\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["Beatriz", "Inas GDF"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Essa semana"},
                    {"type": "QUICK_REPLY", "text": "Próximas 2 semanas"},
                    {"type": "QUICK_REPLY", "text": "Link avaliação"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_c_pediatrico_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá! Aqui é a Blink Oftalmologia, sobre a consulta "
                    "do(a) {{1}}.\n\n"
                    "Avaliação oftalmológica precoce na infância é o que "
                    "evita problemas de aprendizado e desenvolvimento "
                    "depois. A Dra. Karla Delalibera é oftalmopediatra — "
                    "atende criança calminha, sem demora.\n\n"
                    "Como podemos seguir?\n\n"
                    "1. Marcar essa semana\n"
                    "2. Marcar nas próximas 2 semanas\n"
                    "3. Me passe info sobre como é a consulta primeiro\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["Helena Maria"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Essa semana"},
                    {"type": "QUICK_REPLY", "text": "Próximas 2 semanas"},
                    {"type": "QUICK_REPLY", "text": "Como é a consulta"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_d_familia_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink Oftalmologia. Vi que vocês querem "
                    "consulta pra {{2}} e {{3}} — posso encaixar os dois "
                    "no mesmo dia, em horários seguidos, pra você não "
                    "voltar duas vezes.\n\n"
                    "Como prefere?\n\n"
                    "1. Mesmo dia essa semana\n"
                    "2. Mesmo dia nas próximas 2 semanas\n"
                    "3. Em datas separadas mesmo\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["Luana", "Helena Maria", "Vicente"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Essa semana"},
                    {"type": "QUICK_REPLY", "text": "Próximas 2 semanas"},
                    {"type": "QUICK_REPLY", "text": "Datas separadas"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_e_pausa_paciente_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink. Lembrei de você — da última vez você "
                    "comentou que ia {{2}}.\n\n"
                    "Sem pressão. Só quero deixar reservado um espaço "
                    "quando você estiver pronta. Me avisa:\n\n"
                    "1. Já resolvi, pode agendar essa semana\n"
                    "2. Ainda preciso de mais 2-3 semanas\n"
                    "3. Te aviso eu mesma quando estiver\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["Circe", "tirar o siso"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Já resolvi"},
                    {"type": "QUICK_REPLY", "text": "Mais 2-3 semanas"},
                    {"type": "QUICK_REPLY", "text": "Aviso depois"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_f_catarata_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink Oftalmologia. Vi que você tinha "
                    "interesse em avaliar a catarata com o Dr. Fabrício "
                    "Freitas, especialista em cirurgia refrativa e de "
                    "catarata.\n\n"
                    "A avaliação completa é R$ 297 — define se tem "
                    "indicação cirúrgica e qual a melhor lente. Quanto "
                    "antes a avaliação, mais opções de tratamento.\n\n"
                    "Como prefere?\n\n"
                    "1. Avaliação essa semana\n"
                    "2. Avaliação nas próximas 2 semanas\n"
                    "3. Quero entender melhor antes\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["João da Silva"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Essa semana"},
                    {"type": "QUICK_REPLY", "text": "Próximas 2 semanas"},
                    {"type": "QUICK_REPLY", "text": "Entender melhor"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_g_cliente_conhecido_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Aqui é a Blink Oftalmologia. Já faz mais de um ano "
                    "da sua última consulta com a Dra. Karla Delalibera — "
                    "está na hora do check-up anual pra acompanhar o "
                    "grau e a saúde dos olhos.\n\n"
                    "Já reservei essa janela pra você. Como prefere?\n\n"
                    "1. Marcar essa semana\n"
                    "2. Marcar nas próximas 2 semanas\n"
                    "3. Me avisa um dia antes pra eu confirmar\n\n"
                    "Responde 1, 2 ou 3."
                ),
                "example": {
                    "body_text": [["Circe"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Essa semana"},
                    {"type": "QUICK_REPLY", "text": "Próximas 2 semanas"},
                    {"type": "QUICK_REPLY", "text": "Avisar antes"},
                ],
            },
        ],
    },
    {
        "name": "blink_lf_h_sem_nome_v1",
        "language": LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá! Aqui é a Blink Oftalmologia.\n\n"
                    "Vi que você entrou em contato sobre consulta com a "
                    "gente e acabou ficando pendente — estou retomando "
                    "pra fechar.\n\n"
                    "Pra eu te oferecer o horário certo:\n\n"
                    "1. A consulta é pra você ou pra outra pessoa? "
                    "Me passa o nome.\n"
                    "2. É por convênio ou particular?\n"
                    "3. Prefere Asa Norte ou Águas Claras?\n\n"
                    "Responde 1, 2 e 3 em uma mensagem só que eu já "
                    "organizo o horário."
                ),
            },
        ],
    },
    # ---------------------------------------------------------------
    # CICLO CONFIRMAÇÃO + PÓS-CONSULTA (UTILITY)
    # ---------------------------------------------------------------
    {
        "name": "blink_conf_d1_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Em continuidade ao atendimento, informamos os dados "
                    "para confirmar a consulta.\n\n"
                    "Detalhes do Agendamento:\n"
                    "- Dia/Hora: {{2}}\n"
                    "- Paciente: {{3}}\n"
                    "- Médica: {{4}}\n\n"
                    "Se não recebermos confirmação em até 2 horas após "
                    "esta mensagem, chamaremos outro paciente da fila de "
                    "espera.\n\n"
                    "Caso isso aconteça, entraremos em contato para "
                    "remarcar seu atendimento. Obrigado!\n\n"
                    "1. Confirmo\n"
                    "2. Quero antecipar\n"
                    "3. Entrar na fila de espera (próx. 30 dias)"
                ),
                "example": {
                    "body_text": [[
                        "Kaliana",
                        "20/04/2026 13:30",
                        "Valentina Raulino Coelho Vilaça",
                        "Dra. Karla Delalibera",
                    ]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Confirmo"},
                    {"type": "QUICK_REPLY", "text": "Quero antecipar"},
                    {"type": "QUICK_REPLY", "text": "Fila de espera"},
                ],
            },
        ],
    },
    {
        "name": "blink_loc_aguas_claras_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Para a consulta prevista em {{2}}, segue o endereço "
                    "e o link de localização da Blink Oftalmologia, "
                    "unidade Águas Claras:\n\n"
                    "Endereço: Felicittá Shopping — Rua 36 Norte, "
                    "Lote 05 sn, Bloco 11, Loja 48 — Águas Claras, "
                    "Brasília DF\n\n"
                    "Estaremos à disposição para atender!"
                ),
                "example": {
                    "body_text": [["Kaliana", "20/04/2026 13:30"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Ver no Google Maps",
                        "url": "https://maps.app.goo.gl/FRbkUtg4U4xG55q18",
                    }
                ],
            },
        ],
    },
    {
        "name": "blink_loc_asa_norte_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Para a consulta prevista em {{2}}, segue o endereço "
                    "e o link de localização da Blink Oftalmologia, "
                    "unidade Asa Norte:\n\n"
                    "Endereço: SGAN 607, Asa Norte, Bloco A Sala 123, "
                    "Ed. Brasília Medical Center, CEP 70830-300\n\n"
                    "Estaremos à disposição para atender!"
                ),
                "example": {
                    "body_text": [["Kaliana", "20/04/2026 13:30"]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Ver no Google Maps",
                        "url": "https://maps.app.goo.gl/jPfjSsXA1bHhsyw56",
                    }
                ],
            },
        ],
    },
    {
        "name": "blink_pos_avaliacao_asa_norte_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Obrigado por confiar na {{2}}, especialista em "
                    "{{3}}.\n\n"
                    "Sua opinião é muito importante para ampliar nossa "
                    "visão. Buscamos saber como foi sua experiência na "
                    "Blink Oftalmologia, unidade Asa Norte."
                ),
                "example": {
                    "body_text": [[
                        "Kaliana",
                        "Dra. Karla Delalibera",
                        "Oftalmopediatria",
                    ]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Avaliar no Google",
                        "url": "https://g.page/r/CZYHYwv6CgYcEAE/review",
                    }
                ],
            },
        ],
    },
    {
        "name": "blink_pos_avaliacao_aguas_claras_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Obrigado por confiar na {{2}}, especialista em "
                    "{{3}}.\n\n"
                    "Sua opinião é muito importante para ampliar nossa "
                    "visão. Buscamos saber como foi sua experiência na "
                    "Blink Oftalmologia, unidade Águas Claras."
                ),
                "example": {
                    "body_text": [[
                        "Kaliana",
                        "Dra. Karla Delalibera",
                        "Oftalmologia Geral",
                    ]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Avaliar no Google",
                        "url": "https://g.page/r/CdTrhQ8o4DYaEAE/review",
                    }
                ],
            },
        ],
    },
    {
        "name": "blink_proxima_consulta_v1",
        "language": LANG,
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}!\n\n"
                    "Agradecemos pela realização da consulta na data de "
                    "{{2}}.\n\n"
                    "A próxima consulta de {{3}} está prevista para "
                    "daqui {{4}}.\n\n"
                    "Quer que eu já reserve um horário?\n\n"
                    "1. Sim, agendar essa semana\n"
                    "2. Sim, mas só daqui um tempo (me lembre depois)\n"
                    "3. Vou entrar em contato eu mesma quando estiver "
                    "pronta"
                ),
                "example": {
                    "body_text": [[
                        "Kaliana",
                        "20/04/2026 13:30",
                        "Benicio Raulino Coelho Vilaça",
                        "1 (um) ano",
                    ]]
                },
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Agendar agora"},
                    {"type": "QUICK_REPLY", "text": "Lembrar depois"},
                    {"type": "QUICK_REPLY", "text": "Eu entro em contato"},
                ],
            },
        ],
    },
]


# ============================================================================
# Cliente Meta Graph API
# ============================================================================

def _api_base(waba_id: str) -> str:
    return f"https://graph.facebook.com/{META_API_VERSION}/{waba_id}/message_templates"


def submit_one(template: dict, waba_id: str, token: str) -> tuple[bool, str]:
    """Submete um template. Retorna (sucesso, mensagem)."""
    url = _api_base(waba_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(url, headers=headers, json=template, timeout=30)
    except Exception as e:
        return False, f"erro rede: {e}"

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code in (200, 201):
        tid = data.get("id") or data.get("data", [{}])[0].get("id", "?")
        return True, f"id={tid}"

    err = data.get("error", {})
    msg = err.get("message", str(data))
    code = err.get("code")
    # Meta retorna code=100 com subcode 2388023 quando nome já existe
    if "already exists" in msg.lower() or err.get("error_subcode") == 2388023:
        return True, "já existe (skip)"
    return False, f"HTTP {r.status_code} [{code}]: {msg}"


def list_existing(waba_id: str, token: str) -> list[dict]:
    url = _api_base(waba_id)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, params={"limit": 100}, timeout=30)
        return r.json().get("data", [])
    except Exception as e:
        print(f"Erro ao listar: {e}")
        return []


def descobrir_waba_ids(token: str) -> list[dict]:
    """Lista WABAs visíveis pelo token. Retorna [{id, name, business_id}, ...]"""
    headers = {"Authorization": f"Bearer {token}"}
    encontrados = []

    # 1) Lista businesses do usuário
    try:
        r = requests.get(
            f"https://graph.facebook.com/{META_API_VERSION}/me/businesses",
            headers=headers,
            params={"limit": 50},
            timeout=30,
        )
        biz_list = r.json().get("data", [])
    except Exception as e:
        print(f"Erro listando businesses: {e}")
        biz_list = []

    # 2) Pra cada business, lista WABAs owned + client
    for biz in biz_list:
        biz_id = biz.get("id")
        biz_name = biz.get("name", "?")
        for endpoint in ("owned_whatsapp_business_accounts", "client_whatsapp_business_accounts"):
            try:
                r = requests.get(
                    f"https://graph.facebook.com/{META_API_VERSION}/{biz_id}/{endpoint}",
                    headers=headers,
                    params={"limit": 50},
                    timeout=30,
                )
                for waba in r.json().get("data", []):
                    encontrados.append({
                        "id": waba.get("id"),
                        "name": waba.get("name", "?"),
                        "business_id": biz_id,
                        "business_name": biz_name,
                        "tipo": endpoint.split("_")[0],
                    })
            except Exception:
                pass
    return encontrados


# ============================================================================
# CLI
# ============================================================================

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    do_list = "--list" in args
    discover = "--discover" in args
    only_name = next((a for a in args if not a.startswith("--")), None)

    if dry_run:
        for t in TEMPLATES:
            if only_name and t["name"] != only_name:
                continue
            print(json.dumps(t, ensure_ascii=False, indent=2))
            print("---")
        return

    # Tenta ler de scripts/.env.meta se existir (paste à prova de truncamento)
    env_file = os.path.join(os.path.dirname(__file__), ".env.meta")
    if os.path.exists(env_file):
        with open(env_file) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                # Permite WHATSAPP_BUSINESS_TOKEN, WABA_ID
                if k.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

    token = os.environ.get("WHATSAPP_BUSINESS_TOKEN")
    if not token:
        print("ERRO: defina WHATSAPP_BUSINESS_TOKEN (env var ou scripts/.env.meta).")
        sys.exit(1)

    # Validação básica de comprimento (token Meta tem ~200+ chars)
    if len(token) < 100:
        print(
            f"AVISO: token muito curto ({len(token)} chars). Token Meta "
            "tem ~200 chars. Verifique se colou completo."
        )

    waba_id = os.environ.get("WABA_ID")

    # Se WABA_ID não foi setado OU usuário pediu --discover, descobre automaticamente
    if not waba_id or discover:
        print("Descobrindo WABAs visíveis pelo token...")
        wabas = descobrir_waba_ids(token)
        if not wabas:
            print(
                "Nenhum WABA encontrado. Verifique se o token tem permissão "
                "'whatsapp_business_management' e 'business_management'."
            )
            sys.exit(1)
        print(f"\nWABAs encontrados ({len(wabas)}):")
        for i, w in enumerate(wabas, 1):
            print(f"  [{i}] id={w['id']}  name={w['name']!r}  business={w['business_name']!r}  tipo={w['tipo']}")
        print()
        if discover:
            print("Exporte WABA_ID com o id desejado e rode novamente sem --discover.")
            return
        # Se só tem 1, usa direto
        if len(wabas) == 1:
            waba_id = wabas[0]["id"]
            print(f"Usando WABA_ID={waba_id} automaticamente.\n")
        else:
            print("Múltiplos WABAs encontrados — exporte WABA_ID=<id> e rode novamente.")
            sys.exit(0)

    if do_list:
        existing = list_existing(waba_id, token)
        print(f"Templates já cadastrados ({len(existing)}):")
        for t in existing:
            print(f"  - {t.get('name'):50s} [{t.get('status')}] cat={t.get('category')}")
        return

    targets = [t for t in TEMPLATES if not only_name or t["name"] == only_name]
    if not targets:
        print(f"Nenhum template encontrado com nome: {only_name}")
        sys.exit(1)

    print(f"Submetendo {len(targets)} template(s)...\n")
    ok_count = err_count = 0
    for t in targets:
        sucesso, detalhe = submit_one(t, waba_id, token)
        prefix = "✅" if sucesso else "❌"
        print(f"{prefix} {t['name']:50s} — {detalhe}")
        if sucesso:
            ok_count += 1
        else:
            err_count += 1
        time.sleep(1)  # respeitar rate limit Meta

    print(f"\nResumo: {ok_count} sucesso(s), {err_count} erro(s).")
    print(
        "Aprovação Meta: UTILITY ~24h | MARKETING 24-72h.\n"
        "Status real-time: Business Manager → WhatsApp → Modelos."
    )


if __name__ == "__main__":
    main()
