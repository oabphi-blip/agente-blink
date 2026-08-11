"""Submete os 2 templates K1/K2 ao Meta WhatsApp Business via Graph API.
Roda em 30s. Templates Utility geralmente aprovam em 1-15min.

Pre-req:
  Env WHATSAPP_CLOUD_TOKEN (token Meta — preferencialmente o novo rotacionado)
  Env WHATSAPP_CLOUD_WABA_ID (default 1990931811727552)
"""
import json
import os
import sys
import urllib.request
import urllib.error


WABA_ID = os.environ.get("WHATSAPP_CLOUD_WABA_ID", "1990931811727552")
TOKEN = os.environ.get("WHATSAPP_CLOUD_TOKEN", "")
API_VERSION = "v21.0"


# Template K1 — Asa Norte
TEMPLATE_K1 = {
    "name": "blink_avaliacao_google_asa_norte_v2",
    "language": "pt_BR",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            "text": (
                "Olá, {{1}}!\n\n"
                "😊 Obrigado por confiar na {{2}}, especialista em {{3}}.\n\n"
                "📢 Sua opinião é muito importante para ampliar nossa visão!\n\n"
                "Buscamos saber: como foi sua experiência na "
                "Blink Oftalmologia unidade Asa Norte?"
            ),
            "example": {
                "body_text": [[
                    "Maria",
                    "Dra. Karla Delalíbera",
                    "Avaliação do Processamento Visual",
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
}


# Template K2 — Águas Claras
TEMPLATE_K2 = {
    "name": "blink_avaliacao_google_aguas_claras_v2",
    "language": "pt_BR",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            "text": (
                "Olá, {{1}}!\n\n"
                "😊 Obrigado por confiar na {{2}}, especialista em {{3}}.\n\n"
                "📢 Sua opinião é muito importante para ampliar nossa visão!\n\n"
                "Buscamos saber: como foi sua experiência na "
                "Blink Oftalmologia unidade Águas Claras?"
            ),
            "example": {
                "body_text": [[
                    "João",
                    "Dr. Fabrício Freitas",
                    "saúde ocular do adulto 50+",
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
}


# Template R1 — Recuperação após valor da consulta (paciente não respondeu)
# Variáveis: {{1}}=nome, {{2}}=especialidade/motivo, {{3}}=médico
TEMPLATE_R1 = {
    "name": "blink_recuperacao_apos_valor_v2",
    "language": "pt_BR",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            "text": (
                "Olá, {{1}}, tudo bem?\n\n"
                "Queremos te oferecer mais opções para a sua avaliação de "
                "{{2}} com a {{3}}:\n\n"
                "- Horários disponíveis aos sábados\n"
                "- Alternativas durante a semana com condições diferenciadas\n\n"
                "Posso te apresentar?"
            ),
            "example": {
                "body_text": [[
                    "Warley",
                    "estrabismo",
                    "Dra. Karla Delalíbera",
                ]]
            },
        },
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Quero conhecer"},
                {"type": "QUICK_REPLY", "text": "Outro momento"},
            ],
        },
    ],
}


def submeter(template: dict) -> dict:
    url = f"https://graph.facebook.com/{API_VERSION}/{WABA_ID}/message_templates"
    body = json.dumps(template).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return {"status": resp.status, "body": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "body": (e.read().decode("utf-8", errors="replace")[:1500]),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "exception", "body": str(e)}


def main() -> int:
    if not TOKEN:
        print("ERRO: WHATSAPP_CLOUD_TOKEN nao setado no env. Aborta.")
        return 2

    print(f"WABA_ID: {WABA_ID}")
    print(f"Token: {TOKEN[:10]}...{TOKEN[-6:]} ({len(TOKEN)} chars)\n")

    for label, tpl in [
        ("K1 Asa Norte", TEMPLATE_K1),
        ("K2 Aguas Claras", TEMPLATE_K2),
        ("R1 Recuperacao apos valor", TEMPLATE_R1),
    ]:
        print(f"=== Submetendo {label} ({tpl['name']}) ===")
        res = submeter(tpl)
        print(f"  Status: {res['status']}")
        print(f"  Body:   {json.dumps(res['body']) if isinstance(res['body'], dict) else res['body'][:500]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
