"""Conector WhatsApp Cloud API (Meta) — caminho oficial, direto.

É o canal do número OFICIAL (8133): recebe as mensagens pelo webhook da
Meta e responde pela Graph API, sem depender do Kommo nem de Salesbot.
Espelha o que a Evolution faz para o 0710 — corrente curta, toda no
código do agente.

Config (variáveis de ambiente):
  WHATSAPP_CLOUD_TOKEN            — token permanente (Usuário do Sistema)
  WHATSAPP_CLOUD_PHONE_NUMBER_ID  — ID do número na Cloud API
  WHATSAPP_CLOUD_VERIFY_TOKEN     — string escolhida p/ verificar o webhook
  WHATSAPP_CLOUD_API_VERSION      — versão da Graph API (padrão v21.0)

Doc: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


class WhatsAppCloudError(RuntimeError):
    pass


def _digits(number: str) -> str:
    return "".join(ch for ch in (number or "") if ch.isdigit())


@dataclass
class WhatsAppCloudClient:
    """Cliente da WhatsApp Cloud API da Meta (envio + download de mídia)."""

    token: str
    phone_number_id: str
    waba_id: str = ""
    api_version: str = "v21.0"
    timeout: float = 30.0

    @property
    def _base(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    # --------------------------------------------------------------- envio

    def send_text(self, to: str, text: str) -> dict:
        """Envia uma mensagem de texto pelo número oficial."""
        url = f"{self._base}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _digits(to),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(url, headers=self._headers(), json=payload)
        if r.status_code >= 400:
            raise WhatsAppCloudError(
                f"send_text falhou ({r.status_code}): {(r.text or '')[:300]}"
            )
        return r.json() if r.content else {}

    # ----------------------------------------------------------- templates

    def send_template(
        self,
        to: str,
        name: str,
        language: str = "pt_BR",
        body_params: Optional[list] = None,
        header_image_url: Optional[str] = None,
    ) -> dict:
        """Envia uma mensagem de TEMPLATE aprovado pela Meta.

        Usado para iniciar contato ou falar FORA da janela de 24h
        (aniversário, reativação, lembretes). O template precisa estar
        APROVADO no WhatsApp Manager.

        body_params       — valores das variáveis {{1}}, {{2}}... do corpo.
        header_image_url  — URL da imagem, se o template tiver cabeçalho
                            de imagem.
        """
        components: list = []
        if header_image_url:
            components.append({
                "type": "header",
                "parameters": [
                    {"type": "image", "image": {"link": header_image_url}}
                ],
            })
        if body_params:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p)} for p in body_params
                ],
            })
        template: dict = {"name": name, "language": {"code": language}}
        if components:
            template["components"] = components
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _digits(to),
            "type": "template",
            "template": template,
        }
        url = f"{self._base}/{self.phone_number_id}/messages"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(url, headers=self._headers(), json=payload)
        if r.status_code >= 400:
            raise WhatsAppCloudError(
                f"send_template '{name}' falhou ({r.status_code}): "
                f"{(r.text or '')[:300]}"
            )
        return r.json() if r.content else {}

    def list_templates(self) -> list:
        """Lista os templates da WABA (nome, idioma, status, categoria).

        Precisa do waba_id configurado. Permite carregar TODOS os templates
        aprovados de uma vez, sem cadastrar um a um no código.
        """
        if not self.waba_id:
            return []
        url = f"{self._base}/{self.waba_id}/message_templates"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                params={"limit": 200},
            )
        if r.status_code >= 400:
            raise WhatsAppCloudError(
                f"list_templates falhou ({r.status_code}): "
                f"{(r.text or '')[:300]}"
            )
        out: list = []
        for t in ((r.json() or {}).get("data") or []):
            out.append({
                "name": t.get("name"),
                "language": t.get("language"),
                "status": t.get("status"),
                "category": t.get("category"),
            })
        return out

    # --------------------------------------------------------------- mídia

    def get_media_bytes(self, media_id: str) -> tuple[bytes, str]:
        """Baixa uma mídia (áudio/imagem). Dois passos na Cloud API:
        1) GET /{media_id} → devolve a URL temporária e o mime.
        2) GET nessa URL (com o token) → bytes do arquivo.
        """
        with httpx.Client(timeout=self.timeout) as c:
            r1 = c.get(f"{self._base}/{media_id}", headers=self._headers())
            if r1.status_code >= 400:
                raise WhatsAppCloudError(
                    f"media metadata falhou ({r1.status_code})"
                )
            info = r1.json() or {}
            media_url = info.get("url")
            mime = info.get("mime_type") or "application/octet-stream"
            if not media_url:
                raise WhatsAppCloudError("resposta de mídia sem 'url'")
            r2 = c.get(
                media_url,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if r2.status_code >= 400:
                raise WhatsAppCloudError(
                    f"download da mídia falhou ({r2.status_code})"
                )
            return r2.content, mime


def parse_webhook(payload: dict) -> list[dict]:
    """Extrai as mensagens RECEBIDAS do payload de webhook da Meta.

    Estrutura: entry[] → changes[] → value → messages[].
    Eventos de status (entregue/lido), em value.statuses, são ignorados.

    Retorna lista de dicts:
      {id, from, type, name, text, media_id, mime, caption}
    type já normalizado: 'text' | 'audio' | 'image' | 'document' |
    'video' | 'sticker' | outros.
    """
    out: list[dict] = []
    if not isinstance(payload, dict):
        return out
    for entry in (payload.get("entry") or []):
        for change in (entry.get("changes") or []):
            value = change.get("value") or {}
            contacts = value.get("contacts") or []
            name = ""
            if contacts:
                name = (contacts[0].get("profile") or {}).get("name") or ""
            for msg in (value.get("messages") or []):
                mtype = msg.get("type") or "unknown"
                item = {
                    "id": msg.get("id") or "",
                    "from": msg.get("from") or "",
                    "type": mtype,
                    "name": name,
                    "text": "",
                    "media_id": "",
                    "mime": "",
                    "caption": "",
                }
                if mtype == "text":
                    item["text"] = (msg.get("text") or {}).get("body") or ""
                elif mtype in ("audio", "voice"):
                    media = msg.get("audio") or msg.get("voice") or {}
                    item["type"] = "audio"
                    item["media_id"] = media.get("id") or ""
                    item["mime"] = media.get("mime_type") or "audio/ogg"
                elif mtype in ("image", "document", "video", "sticker"):
                    media = msg.get(mtype) or {}
                    item["media_id"] = media.get("id") or ""
                    item["mime"] = media.get("mime_type") or ""
                    item["caption"] = media.get("caption") or ""
                out.append(item)
    return out
