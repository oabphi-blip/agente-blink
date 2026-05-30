"""Pytest blindando o fluxo /whatsapp da Lia.

Cenários congelando o bug do dia 30/05/2026: voice_agent recebe
POST /whatsapp 200 OK mas não processa porque o payload é só
`value.statuses[]` (eventos de entrega/leitura das mensagens que A
empresa enviou) em vez de `value.messages[]` (mensagem real do
paciente). Sintoma: Lia parece silenciada, logs vazios.

Sem esses testes, qualquer regressão em parse_webhook ou na ordem
de checks do /whatsapp volta a esconder a causa.

Ver: lia-atendimento-blink/memoria/bugs-licoes/
lia-silenciosa-status-vs-messages-meta.md
"""
from __future__ import annotations

import pytest

from voice_agent.whatsapp_cloud import parse_webhook


# ----------------------------------------------------------------- payloads

def _payload_messages(phone: str = "5561999990001", text: str = "oi") -> dict:
    """Payload inbound real (paciente mandou mensagem)."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1990931811727552",  # WABA id Blink
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "556181331005",
                        "phone_number_id": "668422093022140",
                    },
                    "contacts": [{
                        "profile": {"name": "Paciente Teste"},
                        "wa_id": phone,
                    }],
                    "messages": [{
                        "from": phone,
                        "id": "wamid.test.inbound.001",
                        "timestamp": "1717070400",
                        "text": {"body": text},
                        "type": "text",
                    }],
                },
            }],
        }],
    }


def _payload_statuses_only() -> dict:
    """Payload de status update (sent/delivered/read) — não é mensagem nova.
    Esse é o payload que A Meta dispara depois que A empresa envia algo,
    e que confundiu o debugging do dia 30/05/2026.
    """
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1990931811727552",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "556181331005",
                        "phone_number_id": "668422093022140",
                    },
                    "statuses": [{
                        "id": "wamid.test.outbound.001",
                        "status": "delivered",
                        "timestamp": "1717070500",
                        "recipient_id": "5561999990001",
                        "conversation": {
                            "id": "fakeconv",
                            "origin": {"type": "service"},
                        },
                    }],
                },
            }],
        }],
    }


def _payload_mixed() -> dict:
    """Mistura: mensagem inbound + statuses no mesmo POST.
    Deve processar SÓ a mensagem inbound, ignorando statuses.
    """
    p = _payload_messages()
    p["entry"][0]["changes"][0]["value"]["statuses"] = [{
        "id": "wamid.test.outbound.002",
        "status": "read",
        "timestamp": "1717070550",
        "recipient_id": "5561999990001",
    }]
    return p


# ---------------------------------------------------------- testes parse


class TestPayloadStatusVsMessage:
    """Lock da causa raiz do incidente 30/05/2026."""

    def test_payload_so_statuses_devolve_lista_vazia(self):
        """Payload só com statuses não vira mensagem a processar.

        Esse é EXATAMENTE o cenário que enganou o debugging: Meta
        dispara POST /whatsapp toda vez que a empresa envia algo
        (sent → delivered → read). voice_agent recebe, retorna 200,
        e parse_webhook devolve [] — silenciosamente correto.
        """
        msgs = parse_webhook(_payload_statuses_only())
        assert msgs == [], (
            "parse_webhook DEVE devolver [] pra payload só com "
            "statuses[]. Se mudar, voice_agent vai tentar processar "
            "status update como mensagem e quebrar."
        )

    def test_payload_messages_inbound_processa_uma_vez(self):
        """Payload de mensagem inbound real vira 1 entry na lista."""
        msgs = parse_webhook(_payload_messages())
        assert len(msgs) == 1
        m = msgs[0]
        assert m["type"] == "text"
        assert m["text"] == "oi"
        assert m["from"] == "5561999990001"
        assert m["id"] == "wamid.test.inbound.001"
        assert m["name"] == "Paciente Teste"

    def test_payload_mixto_so_processa_messages(self):
        """Mistura messages + statuses — só processa messages."""
        msgs = parse_webhook(_payload_mixed())
        assert len(msgs) == 1, (
            "parse_webhook tem que IGNORAR statuses[] mesmo quando "
            "vem misturado com messages[] no mesmo POST."
        )
        assert msgs[0]["type"] == "text"
        assert msgs[0]["text"] == "oi"

    def test_payload_vazio_devolve_lista_vazia(self):
        """Robustez: payload sem entry não quebra."""
        assert parse_webhook({}) == []
        assert parse_webhook({"entry": []}) == []
        assert parse_webhook(
            {"entry": [{"changes": []}]}
        ) == []

    def test_payload_string_devolve_lista_vazia(self):
        """Robustez: payload não-dict não quebra."""
        assert parse_webhook("string") == []  # type: ignore[arg-type]
        assert parse_webhook(None) == []  # type: ignore[arg-type]


class TestPayloadAudio:
    """Áudio é o segundo caminho mais usado pelos pacientes (Karla
    e Fabricio recebem muito áudio). Garante que não regrediu."""

    def test_payload_audio_vira_audio_type(self):
        payload = _payload_messages()
        msgs_arr = payload["entry"][0]["changes"][0]["value"]["messages"]
        msgs_arr[0] = {
            "from": "5561999990001",
            "id": "wamid.test.audio.001",
            "timestamp": "1717070400",
            "type": "audio",
            "audio": {
                "id": "mediaid_xyz",
                "mime_type": "audio/ogg",
            },
        }
        msgs = parse_webhook(payload)
        assert len(msgs) == 1
        assert msgs[0]["type"] == "audio"
        assert msgs[0]["media_id"] == "mediaid_xyz"
        assert msgs[0]["mime"].startswith("audio/")


class TestPayloadMidia:
    """Imagem/documento — pacientes mandam carteirinha de convênio."""

    def test_payload_image_extrai_media_id_e_caption(self):
        payload = _payload_messages()
        msgs_arr = payload["entry"][0]["changes"][0]["value"]["messages"]
        msgs_arr[0] = {
            "from": "5561999990001",
            "id": "wamid.test.img.001",
            "timestamp": "1717070400",
            "type": "image",
            "image": {
                "id": "imgmedia_999",
                "mime_type": "image/jpeg",
                "caption": "minha carteirinha",
            },
        }
        msgs = parse_webhook(payload)
        assert len(msgs) == 1
        assert msgs[0]["type"] == "image"
        assert msgs[0]["media_id"] == "imgmedia_999"
        assert msgs[0]["caption"] == "minha carteirinha"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
