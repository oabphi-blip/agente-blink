"""Servidor FastAPI que recebe webhook da Evolution API.

Eventos tratados:
- messages.upsert com fromMe=false:
    * audioMessage / pttMessage → Whisper transcreve → Claude responde
    * conversation / extendedTextMessage → Claude responde direto

Whitelist é aplicada no pipeline (pipeline.py). Em modo soft launch, só
números autorizados recebem resposta.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .evolution import EvolutionClient
from .pipeline import VoicePipeline
from .responder import Responder
from .settings import Settings
from .store import ConversationStore
from .transcribe import Transcriber


def _conversation_key(jid: str) -> str:
    """Chave de conversa ESTÁVEL — só os dígitos do telefone.

    O WhatsApp/Evolution entrega o remetente ora como '<num>@s.whatsapp.net',
    ora como '<id>@lid', ora com/sem o 9 extra de celular BR. Se a chave
    variar, o histórico "se perde" no meio da conversa. Normalizamos para
    apenas dígitos — e, para celulares BR de 13 dígitos, removemos o 9 extra
    para que 55619... e 5561 9... colidam na MESMA conversa.
    """
    if not jid:
        return jid
    digits = "".join(c for c in jid.split("@", 1)[0] if c.isdigit())
    # Normaliza BR: 13 díg (55 + DDD + 9 + 8) → 12 díg (remove o 9)
    if digits.startswith("55") and len(digits) == 13 and digits[4] == "9":
        digits = digits[:4] + digits[5:]
    return digits or jid

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.load()

    transcriber = Transcriber(api_key=settings.openai_api_key, model=settings.whisper_model)
    # Store compartilhado — persistente em Redis se REDIS_URL estiver setado.
    conversation_store = ConversationStore(redis_url=settings.redis_url or None)
    responder = Responder(
        api_key=settings.anthropic_api_key,
        sonnet_model=settings.claude_sonnet_model,
        haiku_model=settings.claude_haiku_model,
        max_response_chars=settings.max_response_chars,
        conversation_store=conversation_store,
    )
    evolution = EvolutionClient(
        base_url=settings.evolution_base_url,
        api_key=settings.evolution_api_key,
        instance=settings.evolution_default_instance,
    )
    pipeline = VoicePipeline(transcriber, responder, evolution, settings)

    # Cliente Medware (opcional) — usado pelo /health e futura integração de agenda.
    medware = None
    if settings.medware_enabled:
        from .medware import MedwareClient
        medware = MedwareClient(
            identificacao=settings.medware_user,
            senha=settings.medware_password,
        )

    app = FastAPI(
        title="Agente Blink Oftalmologia — Voice + Text",
        version="0.2.0",
        description=(
            "Webhook que processa mensagens do WhatsApp (texto + áudio) "
            "com Whisper + Claude Sonnet/Haiku."
        ),
    )

    @app.get("/health")
    def health() -> dict:
        # Redis: tenta um round-trip rápido pelo store
        redis_status = {"configured": bool(settings.redis_url)}
        try:
            store_redis = getattr(conversation_store, "_redis", None)
            if store_redis is not None:
                store_redis.ping()
                redis_status["connected"] = True
            else:
                redis_status["connected"] = False
                redis_status["mode"] = "memória (fallback — NÃO persiste entre restarts)"
        except Exception as e:  # noqa: BLE001
            redis_status["connected"] = False
            redis_status["error"] = str(e)[:120]

        # Medware: status de login
        medware_status = {"configured": settings.medware_enabled}
        if medware is not None:
            medware_status.update(medware.status())

        # Kommo: apenas se está configurado (sem chamada de rede pesada)
        kommo_status = {"configured": settings.kommo_enabled}

        return {
            "status": "ok",
            "whitelist_strict": settings.whitelist_strict,
            "whitelist_count": len(settings.whitelist_numbers),
            "models": {
                "transcription": settings.whisper_model,
                "sonnet": settings.claude_sonnet_model,
                "haiku": settings.claude_haiku_model,
            },
            "redis": redis_status,
            "medware": medware_status,
            "kommo": kommo_status,
        }

    @app.post("/webhook")
    @app.post("/webhook/{instance}")
    async def webhook(request: Request, instance: Optional[str] = None) -> JSONResponse:
        # Autenticação opcional
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Body não-JSON")

        event = payload.get("event") or payload.get("eventType")
        if event not in ("messages.upsert", "MESSAGES_UPSERT"):
            return JSONResponse({"ignored": event or "unknown"})

        data = payload.get("data") or {}
        key = data.get("key") or {}
        msg_id = key.get("id") or ""
        from_me = key.get("fromMe", False)
        raw_remote_jid = key.get("remoteJid", "") or ""
        # WhatsApp pode mandar remoteJid no formato novo @lid (LinkedID).
        # Nesse caso, key.remoteJidAlt traz o número PN real (@s.whatsapp.net).
        # Usamos o PN para enviar resposta + whitelist + chave de conversa,
        # mantendo o histórico estável independente do formato.
        remote_jid_alt = key.get("remoteJidAlt") or ""
        remote_jid = (
            remote_jid_alt if raw_remote_jid.endswith("@lid") and remote_jid_alt
            else raw_remote_jid
        )
        message = data.get("message") or {}
        msg_type = data.get("messageType") or _detect_type(message)

        if from_me:
            return JSONResponse({"ignored": "fromMe"})
        if not remote_jid:
            return JSONResponse({"ignored": "sem remoteJid"})

        # Dedup por id — agora persistente (Redis). Sobrevive a restart e
        # bloqueia reentrega de webhook mesmo após redeploy.
        if msg_id and not conversation_store.mark_seen(msg_id):
            return JSONResponse({"ignored": "duplicate"})

        if instance:
            evolution.instance = instance

        # Chave de conversa ESTÁVEL (só dígitos do telefone) — garante que
        # o histórico não se perca quando o WhatsApp alterna @lid/@s.whatsapp.net.
        convo_key = _conversation_key(remote_jid)

        # ÁUDIO → transcrever + responder
        if msg_type in ("audioMessage", "pttMessage"):
            try:
                audio_bytes = evolution.get_audio_bytes(data)
            except Exception as e:  # noqa: BLE001
                log.exception("falha ao obter áudio")
                return JSONResponse({"error": f"get_audio: {e}"}, status_code=502)

            mime = (
                message.get("audioMessage", {}).get("mimetype")
                or "audio/ogg"
            )
            result = pipeline.process_audio_bytes(
                audio_bytes=audio_bytes,
                mime_type=mime,
                conversation_key=convo_key,
                reply_to_number=remote_jid,
                quoted_message_id=msg_id,
            )

        # TEXTO → responder direto
        elif msg_type in ("conversation", "extendedTextMessage"):
            text = _extract_text(message)
            if not text:
                return JSONResponse({"ignored": "texto vazio"})
            result = pipeline.process_text(
                text=text,
                conversation_key=convo_key,
                reply_to_number=remote_jid,
                quoted_message_id=msg_id,
            )

        # IMAGEM / DOCUMENTO → o paciente provavelmente mandou carteirinha ou
        # identidade. Roteia como texto sintético para o agente reconhecer e
        # responder (em vez de ignorar e ficar mudo).
        elif msg_type in ("imageMessage", "documentMessage"):
            legenda = ""
            for k in ("imageMessage", "documentMessage"):
                cap = (message.get(k) or {}).get("caption")
                if cap:
                    legenda = cap
                    break
            tipo = "uma imagem/foto" if msg_type == "imageMessage" else "um documento/arquivo"
            sintetico = (
                f"[O paciente acabou de enviar {tipo} pelo WhatsApp"
                + (f', com a legenda: \"{legenda}\"' if legenda else "")
                + ". Provavelmente é a carteirinha do convênio ou um documento "
                "de identidade. Confirme o recebimento de forma calorosa, diga "
                "que a equipe vai conferir, e prossiga normalmente o atendimento.]"
            )
            result = pipeline.process_text(
                text=sintetico,
                conversation_key=convo_key,
                reply_to_number=remote_jid,
                quoted_message_id=msg_id,
            )

        # OUTROS TIPOS (figurinha, vídeo, localização, contato...) → não ignora
        # em silêncio: envia um aviso curto pedindo texto ou áudio.
        else:
            try:
                evolution.send_text(
                    number=remote_jid,
                    text=(
                        "Recebi sua mensagem! 🙂 Para eu conseguir te ajudar com "
                        "o agendamento, pode me escrever uma mensagem de texto ou "
                        "enviar um áudio?"
                    ),
                    quoted_message_id=msg_id,
                )
            except Exception:  # noqa: BLE001
                log.exception("falha ao enviar aviso de tipo não suportado")
            return JSONResponse({"handled": f"messageType={msg_type}", "sent_hint": True})

        return JSONResponse({
            "ok": result.error is None,
            "transcript": result.transcript,
            "answer": result.answer,
            "sent": result.sent,
            "model_used": result.model_used,
            "articles_used": result.articles_used,
            "blocked_by_whitelist": result.blocked_by_whitelist,
            "error": result.error,
        })

    return app


def _detect_type(message: dict[str, Any]) -> str:
    for k in (
        "audioMessage", "pttMessage", "imageMessage", "videoMessage",
        "documentMessage", "conversation", "extendedTextMessage",
    ):
        if k in message:
            return k
    return "unknown"


def _extract_text(message: dict[str, Any]) -> str:
    if "conversation" in message:
        return message["conversation"]
    if "extendedTextMessage" in message:
        return message["extendedTextMessage"].get("text", "")
    return ""


app = create_app() if __name__ != "__main__" else None


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "voice_agent.webhook:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
