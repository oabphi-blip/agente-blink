"""Servidor FastAPI que recebe webhook da Evolution API.

Eventos tratados:
- messages.upsert com fromMe=false:
    * audioMessage / pttMessage → Whisper transcreve → Claude responde
    * conversation / extendedTextMessage → Claude responde direto

Whitelist é aplicada no pipeline (pipeline.py). Em modo soft launch, só
números autorizados recebem resposta.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

import httpx
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

    # ================================================================
    # ENDPOINT KOMMO — integração com o número oficial (WhatsApp Business)
    # ================================================================
    # O número 8133-1005 está na API oficial via Kommo. Um Salesbot do Kommo,
    # no passo "Widget" (widget_request), faz POST aqui a cada mensagem do
    # paciente. Fluxo:
    #   1. Kommo POST /kommo  {token, data:{message,...}, return_url}
    #   2. respondemos 200 em <2s (exigência do Kommo)
    #   3. em background: Claude gera a resposta
    #   4. POST no return_url com execute_handlers=[show/text] → o Salesbot
    #      envia a resposta no WhatsApp do paciente
    # Doc: https://developers.kommo.com/docs/private-chatbot-integration

    def _process_kommo(
        message: str, convo_key: str, return_url: str, lead_id: str = "",
    ) -> None:
        """Processa a mensagem do Kommo e devolve a resposta ao Salesbot."""
        # Onboarding: já temos o lead_id — busca o que o CRM sabe do contato
        # (convênio, médico, unidade já preenchidos) para o agente não reperguntar.
        caller_context = None
        if pipeline.kommo is not None and lead_id:
            try:
                caller_context = pipeline.kommo.get_caller_context_by_lead(lead_id)
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo onboarding (/kommo) falhou: %s", e)
        try:
            result = responder.reply(convo_key, message, caller_context=caller_context)
            answer = result.get("answer") or ""
        except Exception as e:  # noqa: BLE001
            log.exception("Kommo: Claude falhou")
            answer = (
                "Tive uma instabilidade aqui. Pode me reenviar sua última "
                "mensagem, por favor?"
            )
        # Continua o fluxo do Salesbot. A resposta vai SÓ no campo `data`,
        # na variável `agent_answer`. O `execute_handlers` com 'show/text'
        # foi removido: o Kommo impõe limite de 80 caracteres em
        # `execute_handlers.params.value` e fazia o POST inteiro falhar com
        # HTTP 400 — bloqueando QUALQUER resposta longa. O Salesbot deve
        # enviar a mensagem usando a variável {{agent_answer}}.
        body = {
            "data": {"agent_answer": answer},
        }
        headers = {"Content-Type": "application/json"}
        if settings.kommo_token:
            headers["Authorization"] = f"Bearer {settings.kommo_token}"
        try:
            with httpx.Client(timeout=15) as c:
                r = c.post(return_url, json=body, headers=headers)
            if r.status_code // 100 != 2:
                log.warning(
                    "Kommo continue falhou: HTTP %d — %s",
                    r.status_code, (r.text or "")[:200],
                )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo continue erro: %s", e)

        # Auto-preenchimento dos campos do lead no Kommo (mesmo que o caminho
        # Evolution faz). Aqui já temos o lead_id direto — não precisa buscar.
        if pipeline.kommo is not None and lead_id:
            try:
                fields = responder.extract_lead_fields(convo_key)
                if fields:
                    pipeline.kommo.update_lead_fields(int(lead_id), fields)
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo auto-fill (/kommo) falhou: %s", e)

    @app.post("/kommo")
    async def kommo_webhook(request: Request) -> JSONResponse:
        # Lê o corpo CRU e loga sempre — precisamos ver exatamente o que o
        # Salesbot do Kommo envia. E NUNCA devolve 400: um 400 faz o Salesbot
        # marcar o passo como falho, e a Lia nunca responde o paciente.
        raw = await request.body()
        ctype = request.headers.get("content-type", "")
        log.info(
            "/kommo IN: ctype=%s len=%d body=%.900s",
            ctype, len(raw or b""), (raw or b"").decode("utf-8", "ignore"),
        )
        payload = None
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8", "ignore"))
            except Exception:  # noqa: BLE001
                try:
                    from urllib.parse import parse_qs
                    payload = {
                        k: (v[0] if len(v) == 1 else v)
                        for k, v in parse_qs(raw.decode("utf-8", "ignore")).items()
                    } or None
                except Exception:  # noqa: BLE001
                    payload = None
        if not isinstance(payload, dict):
            log.warning("/kommo: corpo vazio ou não-parseável — ignorado (sem 400)")
            return JSONResponse({"ignored": "corpo nao-parseavel"})

        # Extração TOLERANTE: aceita os campos no topo OU dentro de 'data'.
        data = payload.get("data")
        if not isinstance(data, dict):
            data = payload
        return_url = payload.get("return_url") or data.get("return_url") or ""
        message = str(data.get("message") or payload.get("message") or "").strip()
        # Chave de conversa: lead id do Kommo (estável por paciente)
        lead_id = str(
            data.get("lead_id") or data.get("lead")
            or payload.get("lead_id") or ""
        ).strip()
        contact = str(
            data.get("phone") or data.get("contact")
            or payload.get("phone") or ""
        ).strip()
        convo_key = (
            f"kommo:{lead_id}" if lead_id
            else (_conversation_key(contact) if contact else "kommo:unknown")
        )

        if not return_url:
            log.warning("Kommo webhook sem return_url — ignorado")
            return JSONResponse({"ignored": "sem return_url"})
        if not message:
            # Sem texto (ex.: imagem) — devolve aviso curto pra não travar o bot
            threading.Thread(
                target=_process_kommo,
                args=(
                    "[O paciente enviou uma mensagem sem texto — imagem, áudio "
                    "ou documento. Confirme o recebimento de forma calorosa e "
                    "siga o atendimento.]",
                    convo_key, return_url, lead_id,
                ),
                daemon=True,
            ).start()
            return JSONResponse({"ok": True, "note": "sem texto"})

        # Responde 200 já (exigência <2s) e processa em background
        threading.Thread(
            target=_process_kommo,
            args=(message, convo_key, return_url, lead_id),
            daemon=True,
        ).start()
        return JSONResponse({"ok": True})

    # ================================================================
    # REATIVAÇÃO DE LEADS FRIOS
    # ================================================================
    # Motor que retoma contato com leads parados nas etapas frias do funil.
    # Disparo DESLIGADO por padrão (reactivation_enabled / reactivation_dry_run).
    # Cadência: um agendamento externo chama POST /reactivation/tick a cada
    # N minutos; cada chamada processa no máximo 1 lead.
    from .reactivation import ReactivationEngine

    reactivation = ReactivationEngine(
        settings=settings,
        kommo=pipeline.kommo,
        evolution=evolution,
        store=conversation_store,
    )

    @app.get("/reactivation/status")
    def reactivation_status() -> dict:
        return reactivation.status()

    @app.post("/reactivation/tick")
    async def reactivation_tick(request: Request) -> JSONResponse:
        # Mesma autenticação opcional do /webhook
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        # ?force=true → teste manual: ignora horário comercial e intervalo
        # mínimo. NÃO ignora dry-run nem o enabled — segue seguro.
        force = str(request.query_params.get("force", "")).lower() in (
            "1", "true", "yes", "sim",
        )
        report = reactivation.tick(force=force)
        log.info("[REATIVACAO tick force=%s] %s", force, report.as_dict())
        return JSONResponse(report.as_dict())

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
