"""Cliente HTTP para Evolution API v2 (envio de mensagem e baixar mídia)."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class EvolutionError(RuntimeError):
    pass


@dataclass
class EvolutionClient:
    base_url: str
    api_key: str
    instance: str
    timeout: float = 30.0

    def _headers(self) -> dict:
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    # --------------------------------------------------------------- send

    def send_text(
        self,
        number: str,
        text: str,
        delay_ms: int = 1200,
        quoted_message_id: Optional[str] = None,
    ) -> dict:
        """Envia mensagem de texto. `number` no formato 55619... (com DDI, sem +)."""
        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload: dict = {
            "number": _normalize_number(number),
            "text": text,
            "delay": delay_ms,
        }
        if quoted_message_id:
            payload["quoted"] = {"key": {"id": quoted_message_id}}

        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.post(url, headers=self._headers(), json=payload)
        if r.status_code >= 400:
            raise EvolutionError(
                f"send_text falhou ({r.status_code}): {r.text[:300]}"
            )
        return r.json() if r.content else {}

    # --------------------------------------------------------------- media

    def get_audio_bytes(self, message: dict) -> bytes:
        """Tenta obter os bytes do áudio.

        Estratégia:
        1. Se o payload do webhook já trouxe `message.base64`, decodifica.
        2. Senão, chama POST /chat/getBase64FromMediaMessage/{instance}
           passando a chave da mensagem.
        """
        # Caminho 1 — webhook configurado com webhook_base64=true
        b64 = _deep_get(message, "message.base64") or message.get("base64")
        if b64:
            return base64.b64decode(b64)

        # Caminho 2 — buscar via API
        url = f"{self.base_url}/chat/getBase64FromMediaMessage/{self.instance}"
        payload = {"message": {"key": message["key"]}, "convertToMp4": False}
        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.post(url, headers=self._headers(), json=payload)
        if r.status_code >= 400:
            raise EvolutionError(
                f"getBase64FromMediaMessage falhou ({r.status_code}): {r.text[:300]}"
            )
        data = r.json()
        b64 = data.get("base64") or data.get("data", {}).get("base64")
        if not b64:
            raise EvolutionError(
                f"resposta sem campo base64: {str(data)[:200]}"
            )
        return base64.b64decode(b64)

    # --------------------------------------------------------------- presence

    def send_typing(self, number: str, duration_ms: int = 1500) -> None:
        """Faz o WhatsApp mostrar 'digitando...' (best-effort, ignora erros)."""
        url = f"{self.base_url}/chat/sendPresence/{self.instance}"
        payload = {
            "number": _normalize_number(number),
            "presence": "composing",
            "delay": duration_ms,
        }
        try:
            with httpx.Client(timeout=10.0) as cli:
                cli.post(url, headers=self._headers(), json=payload)
        except httpx.HTTPError as e:  # noqa: BLE001
            log.debug("send_typing ignorado: %s", e)


# ------------------------------------------------------------------ helpers


def _normalize_number(number: str) -> str:
    """Normaliza um JID/número para o formato esperado pelo Evolution."""
    if not number:
        return number
    # 5561996630710@s.whatsapp.net → 5561996630710
    if "@" in number:
        number = number.split("@", 1)[0]
    return number.lstrip("+").strip()


def _deep_get(obj: dict, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur
