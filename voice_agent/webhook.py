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
from fastapi.responses import JSONResponse, PlainTextResponse

from . import followup
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
    pipeline = VoicePipeline(
        transcriber, responder, evolution, settings,
        conversation_store=conversation_store,
    )

    # Cliente Medware (opcional) — usado pelo /health e futura integração de agenda.
    medware = None
    if settings.medware_enabled:
        from .medware import MedwareClient
        medware = MedwareClient(
            identificacao=settings.medware_user,
            senha=settings.medware_password,
        )
    # Liga o Medware ao pipeline — o agente consulta a agenda real e
    # oferece horários concretos quando o lead já tem médico definido.
    pipeline.medware = medware

    # Cliente WhatsApp Cloud API (Meta) — canal do número OFICIAL (8133).
    # Só é criado quando as credenciais estiverem nas variáveis de ambiente.
    wa_cloud = None
    if settings.whatsapp_cloud_enabled:
        from .whatsapp_cloud import WhatsAppCloudClient
        wa_cloud = WhatsAppCloudClient(
            token=settings.whatsapp_cloud_token,
            phone_number_id=settings.whatsapp_cloud_phone_number_id,
            waba_id=settings.whatsapp_cloud_waba_id,
            api_version=settings.whatsapp_cloud_api_version,
        )

    app = FastAPI(
        title="Agente Blink Oftalmologia — Voice + Text",
        version="0.2.0",
        description=(
            "Webhook que processa mensagens do WhatsApp (texto + áudio) "
            "com Whisper + Claude Sonnet/Haiku."
        ),
    )

    # Arquivos estáticos — imagens de cabeçalho de templates do WhatsApp etc.
    # Coloque o arquivo em voice_agent/static/ e ele fica público em /static.
    # Ex.: voice_agent/static/2020_feliz.jpg
    #      → https://blink-agent.6prkfn.easypanel.host/static/2020_feliz.jpg
    import os as _os
    from fastapi.staticfiles import StaticFiles
    _static_dir = _os.path.join(_os.path.dirname(__file__), "static")
    _os.makedirs(_static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

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
            "whatsapp_cloud": {"configured": settings.whatsapp_cloud_enabled},
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
    # WHATSAPP CLOUD API (META) — canal do número OFICIAL (8133)
    # ================================================================
    # Caminho direto e oficial: a Meta entrega a mensagem no webhook abaixo
    # e o agente responde pela Graph API. Sem Kommo nem Salesbot no meio —
    # espelha o que a Evolution faz para o 0710.
    #   GET  /whatsapp  → verificação do webhook (handshake da Meta)
    #   POST /whatsapp  → recebe a mensagem do paciente
    from .whatsapp_cloud import parse_webhook as _wa_parse

    def _process_whatsapp_cloud(user_text: str, phone: str, msg_id: str) -> None:
        """Gera a resposta da Lia e envia pela WhatsApp Cloud API."""
        if wa_cloud is None:
            return
        convo_key = _conversation_key(phone)
        # Onboarding: o que o CRM já sabe deste contato (pelo telefone).
        caller_context = None
        if pipeline.kommo is not None and phone:
            try:
                caller_context = pipeline.kommo.get_caller_context(phone)
            except Exception as e:  # noqa: BLE001
                log.warning("WA Cloud onboarding falhou: %s", e)
        # Convivência humano × agente: silêncio em cirurgias / handoff humano.
        if pipeline.kommo is not None and caller_context:
            motivo = pipeline.kommo.agent_paused_for_lead(
                caller_context, settings.agent_handoff_window_min,
            )
            if motivo:
                log.info(
                    "WA Cloud: agente em silêncio (%s) para %s", motivo, phone,
                )
                return
        # Follow-up pós-valor: o paciente interagiu → limpa o marcador.
        try:
            followup.clear_pending(pipeline._redis, convo_key)
        except Exception:  # noqa: BLE001
            pass
        # Agenda Medware: injeta horários reais se o lead já tem médico.
        if (
            pipeline.medware is not None
            and caller_context
            and (caller_context.get("known") or {}).get("medico")
        ):
            try:
                known = caller_context["known"]
                slots = pipeline.medware.horarios_para_agente(
                    known.get("medico"), known.get("unidade"),
                )
                if slots:
                    caller_context["agenda"] = slots
            except Exception as e:  # noqa: BLE001
                log.warning("WA Cloud Medware horários falhou: %s", e)
        try:
            result = responder.reply(
                convo_key, user_text, caller_context=caller_context
            )
            answer = result.get("answer") or ""
        except Exception as e:  # noqa: BLE001
            log.exception("WA Cloud: Claude falhou")
            answer = (
                "Tive uma instabilidade aqui. Pode me reenviar sua última "
                "mensagem, por favor?"
            )
        if not answer:
            return
        try:
            wa_cloud.send_text(phone, answer)
        except Exception as e:  # noqa: BLE001
            log.warning("WA Cloud envio falhou: %s", e)
            return
        # Follow-up pós-valor: se a resposta apresentou o valor, arma o marcador.
        try:
            if followup.answer_has_value(answer):
                followup.set_pending(pipeline._redis, convo_key)
        except Exception:  # noqa: BLE001
            pass
        # Sincroniza o lead no Kommo (best-effort, em background): grava a
        # nota, atualiza os campos extraídos e carimba o canal 8133.
        if pipeline.kommo is not None and phone:
            threading.Thread(
                target=pipeline._sync_kommo_safely,
                args=(phone, convo_key, user_text, answer, "81331005"),
                daemon=True,
            ).start()

    def _process_wa_cloud_audio(
        media_id: str, mime: str, phone: str, msg_id: str,
    ) -> None:
        """Baixa o áudio da Cloud API, transcreve e processa como texto."""
        if wa_cloud is None:
            return
        try:
            audio_bytes, real_mime = wa_cloud.get_media_bytes(media_id)
            text = transcriber.transcribe(
                audio_bytes, mime_type=real_mime or mime or "audio/ogg"
            )
        except Exception as e:  # noqa: BLE001
            log.warning("WA Cloud áudio falhou: %s", e)
            return
        if text and text.strip():
            _process_whatsapp_cloud(text, phone, msg_id)

    @app.get("/whatsapp")
    def whatsapp_cloud_verify(request: Request):
        """Verificação do webhook exigida pela Meta (handshake)."""
        p = request.query_params
        token = settings.whatsapp_cloud_verify_token
        if (
            token
            and p.get("hub.mode") == "subscribe"
            and p.get("hub.verify_token") == token
        ):
            return PlainTextResponse(p.get("hub.challenge") or "")
        raise HTTPException(403, "verificação do webhook falhou")

    @app.post("/whatsapp")
    async def whatsapp_cloud_webhook(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"ignored": "body não-JSON"})
        if wa_cloud is None:
            log.warning("/whatsapp recebido, mas WhatsApp Cloud não configurado")
            return JSONResponse({"ignored": "cloud não configurado"})

        for m in _wa_parse(payload):
            mid = m.get("id") or ""
            phone = m.get("from") or ""
            if not phone:
                continue
            # Dedup — a Meta reentrega o webhook em caso de timeout.
            if mid and not conversation_store.mark_seen(f"wa:{mid}"):
                continue
            mtype = m.get("type")
            if mtype == "text" and (m.get("text") or "").strip():
                threading.Thread(
                    target=_process_whatsapp_cloud,
                    args=(m["text"], phone, mid),
                    daemon=True,
                ).start()
            elif mtype == "audio" and m.get("media_id"):
                threading.Thread(
                    target=_process_wa_cloud_audio,
                    args=(m["media_id"], m.get("mime") or "", phone, mid),
                    daemon=True,
                ).start()
            elif mtype in ("image", "document", "video", "sticker"):
                cap = m.get("caption") or ""
                tipo = "uma imagem" if mtype == "image" else f"um {mtype}"
                sintetico = (
                    f"[O paciente enviou {tipo} pelo WhatsApp"
                    + (f', com a legenda: "{cap}"' if cap else "")
                    + ". Provavelmente é a carteirinha do convênio ou um "
                    "documento de identidade. Confirme o recebimento de forma "
                    "calorosa, diga que a equipe vai conferir, e siga o "
                    "atendimento normalmente.]"
                )
                threading.Thread(
                    target=_process_whatsapp_cloud,
                    args=(sintetico, phone, mid),
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
        wa_cloud=wa_cloud,
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

    # ================================================================
    # DISPARO DE UNIFICAÇÃO (broadcast do aviso de número único 8133)
    # ================================================================
    # Envia o template de unificação para a base do Kommo, dos contatos
    # mais recentes aos mais antigos, em lotes com teto diário.
    # Acionar: POST /broadcast/tick (?force=true ignora o horário).
    from .broadcast import BroadcastEngine

    broadcast = BroadcastEngine(
        settings=settings,
        kommo=pipeline.kommo,
        wa_cloud=wa_cloud,
        store=conversation_store,
    )

    @app.get("/broadcast/status")
    def broadcast_status() -> dict:
        return broadcast.status()

    @app.post("/broadcast/tick")
    async def broadcast_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        force = str(request.query_params.get("force", "")).lower() in (
            "1", "true", "yes", "sim",
        )
        report = broadcast.tick(force=force)
        log.info("[BROADCAST tick force=%s] %s", force, report.as_dict())
        return JSONResponse(report.as_dict())

    # ================================================================
    # FOLLOW-UP PÓS-VALOR (retomada quando o paciente some após o valor)
    # ================================================================
    # O pipeline marca quando o agente apresenta o valor; este motor
    # dispara o template de retomada após o tempo de silêncio.
    # Acionar: POST /followup/tick a cada poucos minutos.
    from .followup import FollowupEngine

    followup_engine = FollowupEngine(
        settings=settings,
        kommo=pipeline.kommo,
        wa_cloud=wa_cloud,
        store=conversation_store,
    )

    @app.get("/followup/status")
    def followup_status() -> dict:
        return followup_engine.status()

    @app.post("/followup/tick")
    async def followup_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        force = str(request.query_params.get("force", "")).lower() in (
            "1", "true", "yes", "sim",
        )
        report = followup_engine.tick(force=force)
        log.info("[FOLLOWUP tick force=%s] %s", force, report.as_dict())
        return JSONResponse(report.as_dict())

    # ================================================================
    # RECONCILIAÇÃO DE ETAPAS (Medware × Kommo)
    # ================================================================
    # Cruza quem consultou em 2026 com os leads abertos e ajusta a etapa.
    # Acionar: POST /reconciliation/run  — ?dry_run=false aplica de verdade;
    # sem o parâmetro, usa o modo definido em settings.
    from .reconciliation import ReconciliationEngine

    reconciliation = ReconciliationEngine(
        kommo=pipeline.kommo,
        medware=medware,
        enabled=settings.reconciliation_enabled,
        dry_run=settings.reconciliation_dry_run,
    )

    @app.get("/reconciliation/status")
    def reconciliation_status() -> dict:
        """Estado + último relatório da reconciliação (consultável por GET)."""
        return reconciliation.status()

    @app.post("/reconciliation/run")
    async def reconciliation_run(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if reconciliation.running:
            return JSONResponse({"started": False, "reason": "já em execução"})
        dr_param = request.query_params.get("dry_run")
        dry_run: Optional[bool] = None
        if dr_param is not None:
            dry_run = str(dr_param).lower() not in ("0", "false", "no", "nao")

        # Roda em segundo plano — a varredura é longa; o resultado fica
        # disponível em GET /reconciliation/status quando terminar.
        def _run() -> None:
            try:
                rep = reconciliation.run(dry_run=dry_run)
                log.info("[RECONCILIACAO] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("Reconciliação falhou: %s", e)

        threading.Thread(target=_run, daemon=True).start()
        return JSONResponse({"started": True, "dry_run": dry_run})

    @app.get("/reconciliation/run")
    def reconciliation_run_get() -> JSONResponse:
        """Atalho SEGURO por GET — aciona a reconciliação sempre em
        DRY-RUN (só monta o relatório, não altera nenhuma etapa).
        O resultado fica em GET /reconciliation/status quando terminar.
        Para aplicar de verdade, use POST /reconciliation/run?dry_run=false.
        """
        if reconciliation.running:
            return JSONResponse({"started": False, "reason": "já em execução"})

        def _run_dry() -> None:
            try:
                rep = reconciliation.run(dry_run=True)
                log.info("[RECONCILIACAO dry-run] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("Reconciliação dry-run falhou: %s", e)

        threading.Thread(target=_run_dry, daemon=True).start()
        return JSONResponse({"started": True, "dry_run": True})

    # ================================================================
    # TEMPLATES DO WHATSAPP OFICIAL (8133)
    # ================================================================
    # GET  /whatsapp/templates       → lista os templates aprovados da WABA
    # POST /whatsapp/send-template   → envia um template (teste/disparo)
    @app.get("/whatsapp/templates")
    def whatsapp_list_templates() -> JSONResponse:
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        try:
            return JSONResponse({"templates": wa_cloud.list_templates()})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:300]})

    @app.get("/whatsapp/phone-info")
    def whatsapp_phone_info() -> JSONResponse:
        """Dados do número na Cloud API: limite de mensagens iniciadas
        pela empresa (messaging_limit_tier) e qualidade."""
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        try:
            return JSONResponse({"phone": wa_cloud.get_phone_info()})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:300]})

    @app.get("/whatsapp/submit-template")
    def whatsapp_submit_template(name: str) -> JSONResponse:
        """Submete um template à Meta para aprovação.

        Lê a definição de voice_agent/templates/<name>.json (formato da
        Graph API: name/language/category/components) e cria o template
        na WABA. Uso: GET /whatsapp/submit-template?name=atendimento_unificado_oficial
        """
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-"))
        if not safe or safe != name:
            return JSONResponse({"ok": False, "error": "nome de template inválido"})
        path = _os.path.join(_os.path.dirname(__file__), "templates", f"{safe}.json")
        if not _os.path.exists(path):
            return JSONResponse(
                {"ok": False, "error": f"arquivo não encontrado: {safe}.json"}
            )
        try:
            with open(path, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
            resp = wa_cloud.create_template(
                name=spec["name"],
                category=spec["category"],
                components=spec["components"],
                language=spec.get("language", "pt_BR"),
            )
            log.info("[WA TEMPLATE] submetido '%s'", spec.get("name"))
            return JSONResponse(
                {"ok": True, "submitted": spec.get("name"), "response": resp}
            )
        except Exception as e:  # noqa: BLE001
            log.warning("submit-template falhou: %s", e)
            return JSONResponse({"ok": False, "error": str(e)[:400]})

    @app.get("/whatsapp/template-image")
    def whatsapp_template_image(name: str) -> JSONResponse:
        """Extrai a imagem de cabeçalho de um template aprovado.

        Baixa a imagem-amostra direto da Meta, salva em /static e devolve
        a URL pública + o conteúdo em base64 (para arquivar no repo).
        Uso: GET /whatsapp/template-image?name=2020_feliz_xxxxxx
        """
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        try:
            img_url = wa_cloud.get_template_header_image_url(name)
            if not img_url:
                return JSONResponse({
                    "ok": False,
                    "error": f"template '{name}' não tem cabeçalho de imagem",
                })
            content, ctype = wa_cloud.fetch_url_bytes(img_url)
            ext = "jpg"
            if "png" in ctype:
                ext = "png"
            elif "webp" in ctype:
                ext = "webp"
            fname = f"{name}.{ext}"
            fpath = _os.path.join(_static_dir, fname)
            with open(fpath, "wb") as fh:
                fh.write(content)
            import base64 as _b64
            return JSONResponse({
                "ok": True,
                "name": name,
                "content_type": ctype,
                "size": len(content),
                "saved_as": fname,
                "public_url": f"/static/{fname}",
                "base64": _b64.b64encode(content).decode("ascii"),
            })
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(e)[:300]})

    @app.post("/whatsapp/send-template")
    async def whatsapp_send_template(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "body inválido (esperado JSON)"})
        data = data or {}
        to = data.get("to") or ""
        name = data.get("name") or ""
        if not to or not name:
            return JSONResponse({"error": "informe 'to' e 'name'"})
        try:
            resp = wa_cloud.send_template(
                to=to,
                name=name,
                language=(data.get("language") or "pt_BR"),
                body_params=data.get("body_params"),
                header_image_url=data.get("header_image_url"),
            )
            log.info("[WA TEMPLATE] enviado '%s' para %s", name, to)
            return JSONResponse({"ok": True, "response": resp})
        except Exception as e:  # noqa: BLE001
            log.warning("send_template falhou: %s", e)
            return JSONResponse({"ok": False, "error": str(e)[:300]})

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
