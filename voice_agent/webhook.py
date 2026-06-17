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
import os
import threading
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
        opus_model=settings.claude_opus_model,
        opus_agenda_enabled=settings.lia_opus_agenda_enabled,
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
        version="0.2.1",
        description=(
            "Webhook que processa mensagens do WhatsApp (texto + áudio) "
            "com Whisper + Claude Sonnet/Haiku."
        ),
    )

    # CORS — necessário pros artifacts Cowork chamarem /admin/* via fetch
    # do navegador. Endpoints /admin/* já são protegidos por WEBHOOK_SECRET,
    # então liberar GET/POST de qualquer origem é seguro.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
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

    # Aviso de unificação enviado a leads NOVOS que chegam no número antigo
    # (0710). É enviado UMA única vez por contato; depois segue o
    # atendimento normal no 0710 (não abandona o lead).
    _UNIF_AVISO_0710 = (
        "Olá! 😊 Aqui é da Blink Oftalmologia.\n\n"
        "Pra te atender com toda a atenção que você merece, nosso "
        "atendimento agora é unificado no número oficial: "
        "*(61) 98133-1005*.\n\n"
        "👉 É só me chamar por lá: https://wa.me/5561981331005\n\n"
        "Pode mandar sua dúvida por aqui também que eu já te ajudo. 💙"
    )

    _unif_notified_mem: set[str] = set()  # dedup em memória (fallback s/ Redis)

    def _aviso_unificacao_se_novo(convo_key: str, remote_jid: str,
                                  msg_type: str) -> None:
        """QUALQUER lead que escreve no 0710 (novo OU recorrente) recebe o
        aviso do número único — UMA única vez por contato. O marcador
        persistente em Redis garante que nunca repete. Assim a migração
        para o 81331005 acontece sozinha, sem transferência manual."""
        try:
            notified_key = f"blink:unif:notified:{convo_key}"
            r = getattr(conversation_store, "_redis", None)
            marcado = False
            if r is not None:
                try:
                    if not r.set(notified_key, "1", nx=True, ex=180 * 86400):
                        return  # já foi avisado antes
                    marcado = True
                except Exception:  # noqa: BLE001
                    pass
            if not marcado:
                # Sem Redis (ou falha) → dedup em memória, para NÃO repetir
                # o aviso a cada mensagem do mesmo contato.
                if convo_key in _unif_notified_mem:
                    return
                _unif_notified_mem.add(convo_key)
            evolution.send_text(number=remote_jid, text=_UNIF_AVISO_0710)
            log.info("[UNIF] aviso de numero unico enviado a %s (%s)",
                     convo_key, msg_type)
        except Exception:  # noqa: BLE001
            log.exception("[UNIF] falha no aviso de unificacao")

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

        # UNIFICAÇÃO — lead novo no 0710 recebe o aviso do número único
        # ANTES da resposta normal. Roda só para tipos de mensagem reais.
        if msg_type in (
            "audioMessage", "pttMessage", "conversation",
            "extendedTextMessage", "imageMessage", "documentMessage",
        ):
            _aviso_unificacao_se_novo(convo_key, remote_jid, msg_type)

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
                "[VA-KOMMO-FB] Tive uma instabilidade aqui. Pode me reenviar "
                "sua última mensagem, por favor?"
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
                # Handoff humano → carimba a IA como DESATIVADA no lead.
                lid = caller_context.get("lead_id")
                if lid:
                    try:
                        pipeline.kommo.update_lead_fields(
                            lid, {"ativado_ia": "DESATIVADO"}
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning("WA Cloud carimbo ATIVADO IA? (off): %s", e)
                return
        # Etapa A CLASSIFICAR (task #96): paciente respondeu → limpa marcador
        # pra o cron classificar-tick não mover o lead.
        try:
            from voice_agent.classificar import limpar_aguardando_resposta
            if caller_context:
                lid = caller_context.get("lead_id")
                if lid:
                    limpar_aguardando_resposta(pipeline._redis, int(lid))
        except Exception as e:  # noqa: BLE001
            log.debug("classificar.limpar_aguardando_resposta: %s", e)
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
        # Humanização: acende "digitando…" + marca como lida antes de
        # gerar a resposta. O paciente vê "lida" → "digitando…".
        import time as _time
        _t0 = _time.time()
        if settings.humanize_enabled and msg_id:
            try:
                wa_cloud.mark_read_typing(msg_id)
            except Exception as e:  # noqa: BLE001
                log.debug("WA Cloud typing falhou: %s", e)
        # Gera a resposta com até 3 tentativas — uma falha transitória da
        # API (timeout, 5xx, rate-limit) NÃO deve virar mensagem de erro
        # para o paciente. Só cai no fallback se as 3 falharem.
        answer = ""
        _last_exc_repr = ""
        for _tent in range(3):
            try:
                result = responder.reply(
                    convo_key, user_text, caller_context=caller_context
                )
                answer = result.get("answer") or ""
                break
            except Exception as _exc:  # noqa: BLE001
                _last_exc_repr = repr(_exc)[:300]
                log.warning(
                    "WA Cloud: responder.reply falhou (tentativa %d/3): %s",
                    _tent + 1, _last_exc_repr,
                )
                _time.sleep(1.5 * (_tent + 1))
        if not answer:
            log.error(
                "WA Cloud: Claude falhou após 3 tentativas — convo=%s "
                "user_text=%r last_exc=%s",
                convo_key, user_text[:200], _last_exc_repr or "(sem exc)",
            )
            # DEDUP do fallback: 24h por convo_key.
            # Antes era 30 min — mas paciente Patricia Somera (lead 24041465,
            # 29/05) recebeu 2 fallbacks em 35 min porque TTL expirou entre as
            # falhas. 24h elimina repetição total. Se Claude continuar caindo,
            # silêncio é melhor que robô quebrado.
            _fallback_key = f"blink:fallback:instab:{convo_key}"
            try:
                _redis = getattr(pipeline, "_redis", None)
                if _redis is not None and _redis.exists(_fallback_key):
                    log.warning(
                        "WA Cloud: fallback instabilidade suprimido "
                        "(já enviado nas últimas 24h para %s)",
                        convo_key,
                    )
                    return
                if _redis is not None:
                    _redis.set(_fallback_key, "1", ex=300)  # 5 min DEBUG 30-mai
            except Exception as e:  # noqa: BLE001
                log.debug("dedup fallback ignorado: %s", e)
            answer = (
                "[VA-FB-2025] Oi! Tivemos uma instabilidade rápida por aqui 🙏 "
                "Já voltei — me conta de novo como posso te ajudar?"
            )
        if not answer:
            return
        # Pausa natural — tempo total proporcional ao tamanho da resposta
        # (descontando o que o modelo já levou para gerar). Evita resposta
        # instantânea, que entrega que é um robô.
        if settings.humanize_enabled:
            try:
                alvo = min(
                    float(settings.humanize_delay_max_sec),
                    max(float(settings.humanize_delay_min_sec),
                        len(answer) / 20.0),
                )
                resto = alvo - (_time.time() - _t0)
                if resto > 0:
                    _time.sleep(resto)
            except Exception:  # noqa: BLE001
                pass
        try:
            wa_cloud.send_text(phone, answer)
        except Exception as e:  # noqa: BLE001
            log.warning("WA Cloud envio falhou: %s", e)
            return
        # Follow-up: valor → marcador pós-valor; senão → primeiro contato.
        try:
            if followup.answer_has_value(answer):
                followup.set_pending(pipeline._redis, convo_key)
            else:
                followup.set_firstcontact(pipeline._redis, convo_key)
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

    # Debounce — junta mensagens seguidas do mesmo paciente numa janela
    # curta antes de processar, para a Lia ler tudo e responder uma vez só.
    _debounce: dict = {}
    _debounce_lock = threading.Lock()

    def _flush_debounce_cloud(ckey: str) -> None:
        with _debounce_lock:
            entry = _debounce.pop(ckey, None)
        if not entry:
            return
        texto = "\n".join(t for t in entry["texts"] if t)
        if texto.strip():
            # Roda dentro de um Timer — sem este try/except, uma exceção
            # morreria silenciosa no thread do Timer e a mensagem do
            # paciente se perderia sem registro.
            try:
                _process_whatsapp_cloud(texto, entry["phone"], entry["msg_id"])
            except Exception:  # noqa: BLE001
                log.exception("WA Cloud: _flush_debounce_cloud falhou")

    def _enqueue_cloud(text: str, phone: str, msg_id: str) -> None:
        """Coloca a mensagem na janela de debounce; mensagens que chegam
        dentro da janela são juntadas e processadas de uma vez só."""
        if (not settings.humanize_enabled
                or settings.humanize_debounce_sec <= 0):
            threading.Thread(
                target=_process_whatsapp_cloud,
                args=(text, phone, msg_id), daemon=True,
            ).start()
            return
        ckey = _conversation_key(phone)
        with _debounce_lock:
            entry = _debounce.get(ckey)
            if entry and entry.get("timer"):
                entry["timer"].cancel()
            if not entry:
                entry = {"texts": [], "phone": phone}
                _debounce[ckey] = entry
            entry["texts"].append(text)
            entry["msg_id"] = msg_id
            t = threading.Timer(
                settings.humanize_debounce_sec,
                _flush_debounce_cloud, args=(ckey,),
            )
            t.daemon = True
            entry["timer"] = t
            t.start()

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

    # ================================================================
    # INGESTÃO DE ÁUDIOS — recebe os áudios da Dra. Karla pelo 8133
    # ================================================================
    # O WhatsApp não deixa baixar nota de voz pela tela. Solução: o
    # admin ENCAMINHA os áudios para o 8133; com o modo armado, cada
    # áudio é salvo em /static/audios/ e fica disponível para o
    # follow-up multimídia. Estado em memória (some no restart — por
    # isso /audios/export devolve os arquivos para arquivar no repo).
    _audios_dir = _os.path.join(_static_dir, "audios")
    _os.makedirs(_audios_dir, exist_ok=True)
    _ingest = {
        "armed": False, "next_label": None, "saved": [], "admin": "",
        "seq": 0,
    }
    _ingest_lock = threading.Lock()

    def _ingest_admin() -> str:
        """Número autorizado a ingerir áudios: o passado no /arm tem
        prioridade; senão cai no AUDIO_INGEST_ADMIN das settings."""
        return _ingest.get("admin") or settings.audio_ingest_admin or ""

    def _ingest_label_from_text(text: str):
        """Extrai o número do áudio de um texto tipo 'Áudio 7' / '7'."""
        import re as _re
        mm = _re.search(r"\d{1,2}", text or "")
        return int(mm.group()) if mm else None

    def _ingest_audio(media_id: str, mime: str) -> None:
        """Baixa o áudio encaminhado e salva em /static/audios/."""
        if wa_cloud is None:
            return
        try:
            audio_bytes, real_mime = wa_cloud.get_media_bytes(media_id)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest áudio falhou: %s", e)
            return
        rm = (real_mime or mime or "").lower()
        ext = "ogg" if ("ogg" in rm or "opus" in rm) else (
            "mp3" if "mpeg" in rm or "mp3" in rm else "ogg")
        # Nome sequencial à prova de colisão (contador protegido por lock).
        # A ORDEM de chegada é a ordem do encaminhamento; o mapa final
        # para os números do roteiro é feito depois (por transcrição).
        with _ingest_lock:
            _ingest["seq"] += 1
            idx = _ingest["seq"]
        fname = f"karla_in_{idx:03d}.{ext}"
        try:
            with open(_os.path.join(_audios_dir, fname), "wb") as fh:
                fh.write(audio_bytes)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest gravar %s falhou: %s", fname, e)
            return
        _ingest["saved"].append({"name": fname, "size": len(audio_bytes)})
        log.info("[INGEST] áudio salvo: %s (%d bytes)", fname, len(audio_bytes))
        try:
            wa_cloud.send_text(
                _ingest_admin(),
                f"✅ Áudio {idx} salvo  ({len(_ingest['saved'])} no total)",
            )
        except Exception:  # noqa: BLE001
            pass

    @app.api_route("/audios/ingest/{action}", methods=["GET", "POST"])
    def audios_ingest_ctl(action: str, admin: str = "") -> JSONResponse:
        """arm | disarm | status — controla o modo de ingestão de áudios.

        Em /arm, passe ?admin=<telefone> (com DDI) do número que vai
        ENCAMINHAR os áudios — só ele é ingerido."""
        if action == "arm":
            _ingest["armed"] = True
            digits = "".join(ch for ch in (admin or "") if ch.isdigit())
            if digits:
                _ingest["admin"] = digits
        elif action == "disarm":
            _ingest["armed"] = False
        elif action == "clear":
            # Apaga os áudios já ingeridos e zera o contador — para
            # recomeçar a ingestão do zero, sem colisão de nomes.
            for fn in list(_os.listdir(_audios_dir)):
                if fn.lower().endswith((".ogg", ".mp3", ".opus")):
                    try:
                        _os.remove(_os.path.join(_audios_dir, fn))
                    except Exception:  # noqa: BLE001
                        pass
            _ingest["saved"] = []
            _ingest["seq"] = 0
            _ingest["next_label"] = None
        return JSONResponse({
            "armed": _ingest["armed"],
            "admin": _ingest_admin() or None,
            "saved": _ingest["saved"],
            "count": len(_ingest["saved"]),
        })

    @app.get("/audios/list")
    def audios_list() -> JSONResponse:
        """Lista os arquivos de áudio presentes em /static/audios/."""
        try:
            files = sorted(_os.listdir(_audios_dir))
        except Exception:  # noqa: BLE001
            files = []
        return JSONResponse({"dir": "/static/audios", "files": files})

    @app.get("/audios/export")
    def audios_export() -> JSONResponse:
        """Devolve os áudios ingeridos em base64, para arquivar no repo."""
        import base64 as _b64
        out = []
        try:
            for fn in sorted(_os.listdir(_audios_dir)):
                fp = _os.path.join(_audios_dir, fn)
                if not _os.path.isfile(fp):
                    continue
                with open(fp, "rb") as fh:
                    out.append({"name": fn, "b64": _b64.b64encode(
                        fh.read()).decode("ascii")})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse({"count": len(out), "files": out})

    @app.get("/audios/transcribe")
    def audios_transcribe(offset: int = 0, limit: int = 6) -> JSONResponse:
        """Transcreve um lote de áudios de /static/audios/ — usado para
        identificar qual áudio do roteiro é cada arquivo ingerido."""
        try:
            files = sorted(
                fn for fn in _os.listdir(_audios_dir)
                if fn.lower().endswith((".ogg", ".mp3", ".opus"))
            )
        except Exception:  # noqa: BLE001
            files = []
        out = []
        for fn in files[offset:offset + limit]:
            fp = _os.path.join(_audios_dir, fn)
            try:
                with open(fp, "rb") as fh:
                    data = fh.read()
                text = transcriber.transcribe(data, mime_type="audio/ogg")
            except Exception as e:  # noqa: BLE001
                text = f"[erro: {str(e)[:120]}]"
            out.append({"name": fn, "text": text})
        return JSONResponse({
            "total": len(files), "offset": offset,
            "returned": len(out), "items": out,
        })

    @app.get("/medware/horarios")
    def medware_horarios(medico: str = "Dra. Karla Delalibera",
                         unidade: str = "", dias: int = 14) -> JSONResponse:
        """Diagnóstico Fase A: vagas REAIS que a Lia consegue oferecer."""
        if medware is None:
            return JSONResponse({"error": "medware desligado"}, status_code=503)
        try:
            slots = medware.horarios_para_agente(medico, unidade or None, dias)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:200]}, status_code=500)
        return JSONResponse({"medico": medico, "unidade": unidade or None,
                             "count": len(slots), "slots": slots[:30]})

    @app.get("/medware/diag-agendar")
    def medware_diag_agendar(path: str = "Medware/Agendamento/Salvar"
                             ) -> JSONResponse:
        """Diagnóstico Fase B: verifica se o endpoint de GRAVAÇÃO do Medware
        existe, SEM criar agendamento real.

        Envia um corpo VAZIO ({}), que jamais cria um agendamento válido.
        Interessa só o código HTTP da resposta:
          • 400/422  → endpoint existe, corpo recusado pela validação (ok!)
          • 404      → o caminho informado está errado, testar outro
          • 200/201  → improvável; reportar antes de seguir
        """
        if medware is None:
            return JSONResponse({"error": "medware desligado"}, status_code=503)
        ok, payload = medware._post(path, {})
        return JSONResponse({"path": path, "aceitou_corpo_vazio": ok,
                             "resposta": str(payload)[:400]})

    @app.get("/medware/agendar-teste")
    def medware_agendar_teste(
        cod_agenda: int = 0, cod_unidade: int = 0, cod_medico: int = 12080,
        data_hora: str = "", nome: str = "", cpf: str = "",
        nascimento: str = "", celular: str = "", convenio: str = "particular",
        confirmar: str = "",
    ) -> JSONResponse:
        """Teste controlado da gravação no Medware (Fase B).

        Sem ?confirmar=SIM apenas ECOA o payload (não grava). Com
        ?confirmar=SIM chama medware.criar_agendamento de verdade — usar
        somente no teste supervisionado com dados reais.
        """
        if medware is None:
            return JSONResponse({"error": "medware desligado"}, status_code=503)
        preview = {
            "cod_medico": cod_medico, "cod_unidade": cod_unidade,
            "cod_agenda": cod_agenda, "data_hora": data_hora, "nome": nome,
            "cpf": cpf, "nascimento": nascimento, "convenio": convenio,
        }
        if confirmar.strip().upper() != "SIM":
            return JSONResponse({
                "preview": preview,
                "aviso": "nada gravado — passe &confirmar=SIM para gravar",
            })
        res = medware.criar_agendamento(
            cod_medico=cod_medico, cod_unidade=cod_unidade,
            cod_agenda=cod_agenda, data_hora=data_hora, nome=nome,
            cpf=cpf, data_nascimento=nascimento, celular=celular,
            convenio=convenio,
            obs="Agendamento de teste controlado — Lia/Fase B",
        )
        return JSONResponse({"enviado": preview, "resultado": res})

    @app.api_route("/whatsapp/reativar", methods=["GET", "POST"])
    def whatsapp_reativar(lead: int = 0, phone: str = "",
                          template: str = "", param: str = "",
                          noparam: int = 0) -> JSONResponse:
        """Reabre a conversa de UM lead com um template aprovado.

        Uso: /whatsapp/reativar?lead=23995869&template=1089_mens_ativar_conv_parada_qz7kbz
        Por padrão envia o primeiro nome do paciente como variável {{1}};
        passe ?noparam=1 se o template não tiver variáveis."""
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud off"}, status_code=503)
        tname = template or "1089_mens_ativar_conv_parada_qz7kbz"
        dest = "".join(c for c in (phone or "") if c.isdigit())
        nome = param
        if (not dest or not nome) and lead:
            try:
                if not dest:
                    dest = pipeline.kommo.get_lead_main_phone(int(lead)) or ""
                if not nome:
                    ctx = pipeline.kommo.get_caller_context_by_lead(
                        int(lead)) or {}
                    nome = ctx.get("name") or ""
            except Exception as e:  # noqa: BLE001
                log.warning("reativar: contexto lead %s falhou: %s", lead, e)
        if not dest:
            return JSONResponse(
                {"error": "telefone não encontrado"}, status_code=400)
        first = nome.strip().split()[0].capitalize() if nome.strip() else ""
        body = None if noparam else ([first] if first else None)
        try:
            resp = wa_cloud.send_template(to=dest, name=tname, body_params=body)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"sent": False, "to": dest, "template": tname,
                 "error": str(e)[:300]}, status_code=502)
        log.info("[REATIVAR] template '%s' para %s (lead %s)", tname, dest, lead)
        return JSONResponse(
            {"sent": True, "to": dest, "template": tname, "nome": first,
             "response": resp})

    @app.api_route("/audios/send", methods=["GET", "POST"])
    def audios_send(lead: int = 0, phone: str = "",
                    audio: str = "") -> JSONResponse:
        """Envia UM áudio da Dra. Karla para um lead/telefone específico.

        Uso: /audios/send?lead=24004241&audio=karla_17
        ou   /audios/send?phone=5561...&audio=karla_17
        Só funciona dentro da janela de 24h (mensagem livre)."""
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud off"}, status_code=503)
        if not audio:
            return JSONResponse(
                {"error": "informe ?audio=karla_NN"}, status_code=400)
        fname = audio if audio.lower().endswith(
            (".ogg", ".mp3", ".opus")) else f"{audio}.ogg"
        if not _os.path.isfile(_os.path.join(_audios_dir, fname)):
            return JSONResponse(
                {"error": f"áudio {fname} não existe"}, status_code=404)
        dest = "".join(c for c in (phone or "") if c.isdigit())
        if not dest and lead:
            try:
                dest = pipeline.kommo.get_lead_main_phone(int(lead)) or ""
            except Exception as e:  # noqa: BLE001
                log.warning("audios_send: telefone do lead falhou: %s", e)
        if not dest:
            return JSONResponse(
                {"error": "telefone não encontrado"}, status_code=400)
        base = (settings.audio_base_url or "").rstrip("/")
        if not base:
            return JSONResponse(
                {"error": "AUDIO_BASE_URL não configurado"}, status_code=503)
        try:
            wa_cloud.send_audio(dest, f"{base}/{fname}")
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": str(e)[:240]}, status_code=502)
        log.info("[AUDIO] enviado %s para %s (lead %s)", fname, dest, lead)
        return JSONResponse({"sent": True, "to": dest, "audio": fname})

    @app.api_route("/audios/fixnames", methods=["GET", "POST"])
    def audios_fixnames() -> JSONResponse:
        """Renomeia karla_in_NNN.ogg → karla_NN.ogg conforme o roteiro.

        NNN = ordem de chegada na ingestão; NN = número do áudio no
        roteiro da Dra. Karla (identificado por transcrição). Operação
        única, idempotente."""
        mapa = {
            1: 1, 2: 2, 3: 3, 4: 5, 5: 4, 6: 6, 7: 7, 8: 8, 9: 9,
            10: 11, 11: 10, 12: 12, 13: 13, 14: 14, 15: 15, 16: 16,
            17: 17, 18: 19, 19: 18, 20: 21, 21: 20, 22: 22, 23: 23,
            24: 24,
        }
        done, errs = [], []
        for src_n, dst_n in mapa.items():
            src = _os.path.join(_audios_dir, f"karla_in_{src_n:03d}.ogg")
            dst = _os.path.join(_audios_dir, f"karla_{dst_n:02d}.ogg")
            if not _os.path.isfile(src):
                continue
            try:
                _os.rename(src, dst)
                done.append(f"karla_{dst_n:02d}.ogg")
            except Exception as e:  # noqa: BLE001
                errs.append(f"{src_n}: {str(e)[:80]}")
        try:
            files = sorted(_os.listdir(_audios_dir))
        except Exception:  # noqa: BLE001
            files = []
        return JSONResponse({
            "renamed": len(done), "errors": errs, "files": files,
        })

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
            _txt_dbg = (m.get("text") or "")[:80] if isinstance(m.get("text"), str) else ""
            log.info(
                "[WA_INBOUND] mid=%s phone=%s type=%s text=%r",
                mid, phone, m.get("type"), _txt_dbg,
            )
            if not phone:
                log.info("[WA_INBOUND] skip sem phone mid=%s", mid)
                continue
            # Dedup — a Meta reentrega o webhook em caso de timeout.
            if mid and not conversation_store.mark_seen(f"wa:{mid}"):
                log.info("[WA_INBOUND] DEDUP block mid=%s phone=%s", mid, phone)
                continue
            mtype = m.get("type")
            # MODO INGESTÃO — áudios encaminhados pelo admin viram arquivos
            # em /static/audios/, NÃO entram no atendimento da Lia.
            if _ingest["armed"]:
                _admin = _ingest_admin()
                if not _admin:
                    # Sem admin definido: trava no 1º remetente que aparecer.
                    _ingest["admin"] = phone
                    _admin = phone
                    log.info("[INGEST] travado no remetente %s", phone)
                if phone == _admin:
                    if mtype == "audio" and m.get("media_id"):
                        threading.Thread(
                            target=_ingest_audio,
                            args=(m["media_id"], m.get("mime") or ""),
                            daemon=True,
                        ).start()
                        continue
                    if mtype == "text":
                        _ingest["next_label"] = _ingest_label_from_text(
                            m.get("text") or "")
                        continue
            if mtype == "text" and (m.get("text") or "").strip():
                # marca healthz — última mensagem inbound recebida
                try:
                    pipeline._redis.setex(
                        "blink:healthz:last_inbound",
                        7 * 24 * 3600,
                        int(__import__("time").time()),
                    )
                except Exception:  # noqa: BLE001
                    pass
                _enqueue_cloud(m["text"], phone, mid)
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

    # ================================================================
    # CRON INTERNO — DESATIVADO 29/05/2026 a pedido do Fábio.
    # Motivo: template 1089_mens_ativar_conv_parada teve 0% conversão,
    # gerou alerta spam Meta + impediu aprovação de novos templates.
    # Não religar até (1) desligar prestador externo, (2) reescrever
    # template com CTA forte e validar conversão em teste pequeno.
    # Código preservado em git history (commit f4a9329).
    # ================================================================

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

    # Agendador interno do disparo de unificação — chama tick() a cada
    # 15 min, sem depender de cron externo. O teto diário (200) e o
    # horário comercial seguram o ritmo. Liga se o broadcast estiver
    # habilitado.
    if settings.broadcast_enabled:
        def _broadcast_scheduler() -> None:
            import time as _t
            _t.sleep(40)  # espera o app terminar de subir
            while True:
                try:
                    rep = broadcast.tick()
                    if rep.sent:
                        log.info("[BROADCAST auto] %s", rep.as_dict())
                except Exception as e:  # noqa: BLE001
                    log.warning("Broadcast scheduler erro: %s", e)
                _t.sleep(900)  # 15 minutos

        threading.Thread(target=_broadcast_scheduler, daemon=True).start()

    # ================================================================
    # UNIFICAÇÃO AUTOMÁTICA — leads novos em 0-ETAPA ENTRADA
    # ================================================================
    # Varre a etapa 0-ENTRADA a cada 10 min e envia o template de
    # unificação para todo lead ainda não avisado. Lead novo é migrado
    # para o 81331005 sozinho — sem transferência manual. Dedup pelo
    # mesmo marcador da regra do 0710 (blink:unif:notified) → nunca
    # repete, venha por onde vier.
    _PIPELINE_ATENDE = 8601819
    _STATUS_ENTRADA = 96441724
    _ENTRADA_UNIF_CAP = 60  # teto por rodada (segurança contra surto)

    def _entrada_primeiro_nome(nome: Optional[str]) -> str:
        n = (nome or "").strip()
        if not n or n.lower().startswith("lead") or n.startswith("#"):
            return "tudo bem"
        return n.split()[0].capitalize()

    def _entrada_unif_scan(hoje_only: bool = False) -> dict:
        """Varre 0-ENTRADA e dispara o aviso de unificação aos novos."""
        if pipeline.kommo is None or wa_cloud is None:
            return {"ran": False, "reason": "kommo/wa_cloud ausente"}
        if not settings.broadcast_template_name:
            return {"ran": False, "reason": "template de unificação não configurado"}
        try:
            leads = pipeline.kommo.list_leads_by_status(
                _PIPELINE_ATENDE, [_STATUS_ENTRADA], limit=250)
        except Exception as e:  # noqa: BLE001
            return {"ran": False, "reason": f"listar leads falhou: {e}"}
        r = getattr(conversation_store, "_redis", None)
        sent = 0
        skipped = 0
        for ld in leads:
            if sent >= _ENTRADA_UNIF_CAP:
                break
            lead_id = int(ld["id"])
            try:
                phone = pipeline.kommo.get_lead_main_phone(lead_id)
            except Exception:  # noqa: BLE001
                phone = None
            if not phone:
                continue
            digits = _conversation_key(phone)
            nkey = f"blink:unif:notified:{digits}"
            if r is not None:
                try:
                    if not r.set(nkey, "1", nx=True, ex=180 * 86400):
                        skipped += 1
                        continue   # já avisado (por aqui ou pela regra do 0710)
                except Exception:  # noqa: BLE001
                    pass
            try:
                wa_cloud.send_template(
                    to=phone,
                    name=settings.broadcast_template_name,
                    language=settings.broadcast_template_lang,
                    body_params=[_entrada_primeiro_nome(ld.get("name"))],
                )
                sent += 1
                # Nota no Kommo — para visibilidade no painel
                try:
                    pipeline.kommo.add_note(
                        lead_id,
                        f"🔁 Aviso de unificação para o 81331005 enviado "
                        f"a {ld.get('name') or 'lead'}."
                    )
                except Exception:  # noqa: BLE001
                    pass
            except Exception as e:  # noqa: BLE001
                log.warning("[ENTRADA-UNIF] envio falhou lead %s: %s", lead_id, e)
        if sent:
            log.info("[ENTRADA-UNIF] %d aviso(s) enviado(s), %d já avisado(s)",
                     sent, skipped)
        return {"ran": True, "sent": sent, "skipped": skipped,
                "total_entrada": len(leads)}

    @app.get("/diag/anthropic")
    def diag_anthropic() -> JSONResponse:
        """Diagnóstico: chama a API Anthropic com os modelos configurados
        e devolve o erro EXATO de cada um (status HTTP + mensagem). É o
        que revela se o responder.reply está falhando por modelo inválido,
        chave/billing ou rate-limit."""
        out: dict = {}
        for label, model in (("sonnet", getattr(responder, "_sonnet", "?")),
                              ("haiku", getattr(responder, "_haiku", "?"))):
            try:
                responder._client.messages.create(
                    model=model, max_tokens=16,
                    messages=[{"role": "user", "content": "ping"}],
                )
                out[label] = {"model": model, "ok": True}
            except Exception as e:  # noqa: BLE001
                out[label] = {"model": model, "ok": False,
                              "erro": f"{type(e).__name__}: {str(e)[:400]}"}
        return JSONResponse(out)

    @app.api_route("/unificacao/entrada/scan", methods=["GET", "POST"])
    def unificacao_entrada_scan(request: Request) -> JSONResponse:
        """Diagnóstico/disparo manual da varredura de 0-ENTRADA."""
        return JSONResponse(_entrada_unif_scan(hoje_only=request.query_params.get("hoje") in ("1","true","True")))

    if wa_cloud is not None:
        def _entrada_unif_scheduler() -> None:
            import time as _t
            _t.sleep(60)  # espera o app subir
            while True:
                try:
                    threading.Thread(target=_entrada_unif_scan,
                                     daemon=True).start()
                except Exception as e:  # noqa: BLE001
                    log.warning("[ENTRADA-UNIF] scheduler erro: %s", e)
                _t.sleep(600)  # 10 minutos

        threading.Thread(target=_entrada_unif_scheduler, daemon=True).start()

    # ================================================================
    # CONFIRMAÇÃO DE CONSULTAS (3 toques automáticos)
    # ================================================================
    # 1) 08h do dia ANTERIOR  → template 1031 (confirmação)
    # 2) 06h do dia da consulta → template de localização (AN ou AC)
    # 3) ~1h antes da consulta  → template "como chegar" (apenas AC)
    # Fonte oficial: Medware/Agendamento/Listar. Telefone do paciente
    # vem do registro do Medware (paciente.telefone). Casa com o lead
    # no Kommo para escrever a nota de visibilidade.
    from datetime import datetime as _dt, timedelta as _td
    from zoneinfo import ZoneInfo as _ZI
    _TZBR = _ZI("America/Sao_Paulo")

    # Códigos das unidades atendidas
    _COD_UNID_ASA_NORTE = 5
    _COD_UNID_AGUAS_CLARAS = 3
    # Status ativos: 1=Agendado, 2=Confirmado, 3=Recebido
    _STATUS_ATIVOS = {1, 2, 3}

    # Slugs dos templates (formato Meta — minúsculo, underscores)
    _TPL_CONFIRMAR = "1031_concluir_confirmar_nsc5f6"
    _TPL_LOC_ASA_NORTE = "1010_link_localizacao_asa_norte_oy3704"
    _TPL_LOC_AGUAS_CLARAS = "1035_google_aguas_claras_rm5ra0"
    _TPL_COMO_CHEGAR_AC = "1035_google_aguas_claras_rm5ra0"
    _TPL_LANG = "pt_BR"

    def _phone_e164(raw: str) -> str:
        """Normaliza telefone do Medware ('(61)999999999 (cel)') para E.164
        sem o '+': 5561999999999."""
        if not raw:
            return ""
        d = "".join(ch for ch in str(raw) if ch.isdigit())
        if not d:
            return ""
        # remove DDI duplicado
        if len(d) >= 13 and d.startswith("55"):
            return d
        if 10 <= len(d) <= 11:
            return "55" + d
        return d

    def _fmt_data_hora_br(dh: str) -> str:
        if not dh:
            return ""
        s = str(dh)
        try:
            if "T" in s:
                dt = _dt.fromisoformat(s)
            else:
                dt = _dt.strptime(s[:16], "%d/%m/%Y %H:%M")
            return dt.strftime("%d/%m/%Y às %H:%M")
        except Exception:  # noqa: BLE001
            return s

    def _parse_data_hora(dh: str):
        if not dh:
            return None
        s = str(dh)
        try:
            if "T" in s:
                return _dt.fromisoformat(s).replace(tzinfo=_TZBR)
            return _dt.strptime(s[:16], "%d/%m/%Y %H:%M").replace(tzinfo=_TZBR)
        except Exception:  # noqa: BLE001
            return None

    def _agendamentos_do_dia(data_br: str) -> list:
        if pipeline.medware is None:
            return []
        try:
            apps = pipeline.medware.listar_agendamentos(data_br, data_br)
        except Exception as e:  # noqa: BLE001
            log.warning("[CONFIRM] listar_agendamentos falhou: %s", e)
            return []
        return [a for a in apps
                if a.get("codUnidade") in (_COD_UNID_ASA_NORTE,
                                            _COD_UNID_AGUAS_CLARAS)
                and a.get("codStatusAgendamento") in _STATUS_ATIVOS]

    def _kommo_note_safe(phone: str, texto: str) -> None:
        if pipeline.kommo is None:
            return
        try:
            lead_id = pipeline.kommo.find_lead_id_by_phone(phone)
            if lead_id:
                pipeline.kommo.add_note(lead_id, texto)
        except Exception:  # noqa: BLE001
            pass

    def _confirmar_consultas(data_consulta: _dt) -> dict:
        """Dispara o template 1031 (confirmação) para todos os agendamentos
        do dia informado. Agrupa por telefone — se a mesma pessoa tem 2+
        agendamentos no dia, recebe UM template listando os pacientes."""
        if wa_cloud is None:
            return {"ran": False, "reason": "wa_cloud ausente"}
        data_br = data_consulta.strftime("%d/%m/%Y")
        apps = _agendamentos_do_dia(data_br)
        # agrupa por telefone
        grupos: dict = {}
        for a in apps:
            phone = _phone_e164((a.get("paciente") or {}).get("telefone"))
            if not phone:
                continue
            grupos.setdefault(phone, []).append(a)
        r = getattr(conversation_store, "_redis", None)
        dia_key = _dt.now(_TZBR).strftime("%Y%m%d")
        sent = 0
        failed = 0
        detalhes = []
        for phone, lista in grupos.items():
            dedup = f"blink:confirm:1031:{dia_key}:{phone}"
            if r is not None:
                try:
                    if not r.set(dedup, "1", nx=True, ex=2 * 86400):
                        continue  # já enviou hoje
                except Exception:  # noqa: BLE001
                    pass
            first = lista[0]
            pac_nome = (first.get("paciente") or {}).get("nome", "") or ""
            contato = pac_nome.split()[0].capitalize() if pac_nome else "paciente"
            data_hora = _fmt_data_hora_br(first.get("dataHoraAgendada"))
            nomes = ", ".join(
                ((a.get("paciente") or {}).get("nome") or "")
                for a in lista if (a.get("paciente") or {}).get("nome")
            )
            medico = (first.get("medico") or {}).get("nome", "") or ""
            ppo = first.get("procedimentoPlanoOperadora") or {}
            plano = ppo.get("descricaoPlano", "") or "Particular"
            especialidade = ""  # Medware nem sempre tem
            params = [contato, data_hora, nomes, medico, especialidade, plano]
            try:
                wa_cloud.send_template(
                    to=phone, name=_TPL_CONFIRMAR,
                    language=_TPL_LANG, body_params=params,
                )
                sent += 1
                _kommo_note_safe(
                    phone,
                    f"📅 Confirmação de consulta enviada (1031) — "
                    f"{data_hora} | {medico}"
                )
                detalhes.append({"phone": phone, "nome": pac_nome, "ok": True})
            except Exception as e:  # noqa: BLE001
                failed += 1
                detalhes.append({"phone": phone, "nome": pac_nome,
                                 "ok": False, "erro": str(e)[:240]})
                log.warning("[CONFIRM] envio falhou %s: %s", phone, e)
        log.info("[CONFIRM] %s: %d enviados, %d falhas, %d grupos",
                 data_br, sent, failed, len(grupos))
        return {"ran": True, "data_consulta": data_br, "total_apps": len(apps),
                "grupos": len(grupos), "sent": sent, "failed": failed,
                "details": detalhes[:30]}

    def _enviar_localizacao(data_consulta: _dt) -> dict:
        """6h do dia da consulta: localização específica de cada unidade."""
        if wa_cloud is None:
            return {"ran": False, "reason": "wa_cloud ausente"}
        data_br = data_consulta.strftime("%d/%m/%Y")
        apps = _agendamentos_do_dia(data_br)
        r = getattr(conversation_store, "_redis", None)
        dia_key = _dt.now(_TZBR).strftime("%Y%m%d")
        sent = 0
        failed = 0
        # evita reenviar para mesmo telefone+unidade no dia
        enviados = set()
        for a in apps:
            phone = _phone_e164((a.get("paciente") or {}).get("telefone"))
            if not phone:
                continue
            unidade = a.get("codUnidade")
            chave = (phone, unidade)
            if chave in enviados:
                continue
            enviados.add(chave)
            template = (_TPL_LOC_ASA_NORTE if unidade == _COD_UNID_ASA_NORTE
                        else _TPL_LOC_AGUAS_CLARAS)
            dedup = f"blink:confirm:loc:{dia_key}:{phone}:{unidade}"
            if r is not None:
                try:
                    if not r.set(dedup, "1", nx=True, ex=2 * 86400):
                        continue
                except Exception:  # noqa: BLE001
                    pass
            pac_nome = (a.get("paciente") or {}).get("nome", "") or "paciente"
            contato = pac_nome.split()[0].capitalize() if pac_nome else "paciente"
            try:
                wa_cloud.send_template(
                    to=phone, name=template, language=_TPL_LANG,
                    body_params=[contato],  # tentativa; se header-only, ignorado
                )
                sent += 1
                _kommo_note_safe(
                    phone,
                    f"📍 Localização enviada ({'Asa Norte' if unidade==5 else 'Águas Claras'})"
                )
            except Exception as e:  # noqa: BLE001
                failed += 1
                log.warning("[CONFIRM-LOC] envio falhou %s/%s: %s",
                            phone, unidade, e)
        log.info("[CONFIRM-LOC] %s: %d enviados, %d falhas",
                 data_br, sent, failed)
        return {"ran": True, "data_consulta": data_br,
                "sent": sent, "failed": failed}

    def _como_chegar_proximas() -> dict:
        """A cada N minutos: para cada agendamento de Águas Claras de HOJE
        cujo horário está ~1h à frente, envia o template 'como chegar'."""
        if wa_cloud is None:
            return {"ran": False, "reason": "wa_cloud ausente"}
        agora = _dt.now(_TZBR)
        data_br = agora.strftime("%d/%m/%Y")
        apps = _agendamentos_do_dia(data_br)
        r = getattr(conversation_store, "_redis", None)
        sent = 0
        failed = 0
        for a in apps:
            if a.get("codUnidade") != _COD_UNID_AGUAS_CLARAS:
                continue
            dh = _parse_data_hora(a.get("dataHoraAgendada"))
            if not dh:
                continue
            delta = (dh - agora).total_seconds() / 60.0
            # janela 50–70 minutos à frente
            if not (50 <= delta <= 70):
                continue
            phone = _phone_e164((a.get("paciente") or {}).get("telefone"))
            if not phone:
                continue
            dedup = f"blink:confirm:chegar:{a.get('codAgendamento')}"
            if r is not None:
                try:
                    if not r.set(dedup, "1", nx=True, ex=86400):
                        continue
                except Exception:  # noqa: BLE001
                    pass
            pac_nome = (a.get("paciente") or {}).get("nome", "") or "paciente"
            contato = pac_nome.split()[0].capitalize() if pac_nome else "paciente"
            try:
                wa_cloud.send_template(
                    to=phone, name=_TPL_COMO_CHEGAR_AC,
                    language=_TPL_LANG, body_params=[contato],
                )
                sent += 1
                _kommo_note_safe(
                    phone,
                    "🧭 Como chegar (Águas Claras) enviado — 1h antes da consulta."
                )
            except Exception as e:  # noqa: BLE001
                failed += 1
                log.warning("[CONFIRM-CHEGAR] envio falhou %s: %s", phone, e)
        if sent:
            log.info("[CONFIRM-CHEGAR] %d enviados", sent)
        return {"ran": True, "sent": sent, "failed": failed}

    @app.api_route("/confirmacao/confirmar", methods=["GET", "POST"])
    def confirmacao_confirmar() -> JSONResponse:
        """Disparo manual: confirmação 1031 para a data informada (?data=DD/MM/YYYY)
        ou para AMANHÃ se não informada."""
        from fastapi import Request as _Req  # noqa: F401
        params = {}
        # GET: usa query param data
        from starlette.requests import Request as _SReq  # noqa: F401
        # Aqui usamos data="" → amanhã
        amanha = _dt.now(_TZBR) + _td(days=1)
        return JSONResponse(_confirmar_consultas(amanha))

    @app.api_route("/confirmacao/localizar", methods=["GET", "POST"])
    def confirmacao_localizar() -> JSONResponse:
        """Disparo manual: localização para os agendamentos de HOJE."""
        hoje = _dt.now(_TZBR)
        return JSONResponse(_enviar_localizacao(hoje))

    @app.api_route("/confirmacao/como-chegar", methods=["GET", "POST"])
    def confirmacao_como_chegar() -> JSONResponse:
        """Disparo manual: 'como chegar' para AC nas próximas ~1h."""
        return JSONResponse(_como_chegar_proximas())

    if wa_cloud is not None and pipeline.medware is not None:
        def _confirmacao_scheduler() -> None:
            import time as _t
            _t.sleep(90)  # espera o app subir
            ultima_8h = ""  # YYYY-MM-DD em que já rodou
            ultima_6h = ""
            while True:
                try:
                    agora = _dt.now(_TZBR)
                    hoje_str = agora.strftime("%Y-%m-%d")
                    # 08h dia-anterior — uma vez por dia
                    if agora.hour == 8 and ultima_8h != hoje_str:
                        ultima_8h = hoje_str
                        threading.Thread(
                            target=lambda: _confirmar_consultas(
                                agora + _td(days=1)),
                            daemon=True,
                        ).start()
                    # 06h dia-da-consulta — uma vez por dia
                    if agora.hour == 6 and ultima_6h != hoje_str:
                        ultima_6h = hoje_str
                        threading.Thread(
                            target=lambda: _enviar_localizacao(agora),
                            daemon=True,
                        ).start()
                    # "como chegar" — a cada ciclo (~5 min)
                    threading.Thread(
                        target=_como_chegar_proximas, daemon=True).start()
                except Exception as e:  # noqa: BLE001
                    log.warning("[CONFIRM] scheduler erro: %s", e)
                import time as _t2
                _t2.sleep(300)  # 5 minutos

        threading.Thread(target=_confirmacao_scheduler, daemon=True).start()

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

    # Agendador interno do follow-up — chama tick() a cada 2 min, sem
    # depender de cron externo. Liga se o follow-up (pós-valor OU primeiro
    # contato) estiver habilitado.
    if settings.followup_enabled or settings.followup_firstcontact_enabled:
        def _fu_tick_once() -> None:
            try:
                rep = followup_engine.tick()
                if rep.sent:
                    log.info("[FOLLOWUP auto] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.warning("Follow-up tick erro: %s", e)

        def _followup_scheduler() -> None:
            import time as _t
            _t.sleep(20)  # espera o app subir
            while True:
                # Cada tick roda em thread PRÓPRIA: se um tick travar num
                # I/O lento, o laço NÃO congela — continua disparando os
                # próximos a cada 120s. Era esse o bug do follow-up.
                try:
                    threading.Thread(
                        target=_fu_tick_once, daemon=True).start()
                except Exception as e:  # noqa: BLE001
                    log.warning("Follow-up scheduler erro: %s", e)
                _t.sleep(120)

        threading.Thread(target=_followup_scheduler, daemon=True).start()

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

    @app.get("/reconciliation/apply")
    def reconciliation_apply_get(request: Request) -> JSONResponse:
        """Aciona a reconciliação APLICANDO de verdade as mudanças de etapa
        (dry_run=false). Exige ?confirmar=sim para não disparar por engano.
        O resultado fica em GET /reconciliation/status quando terminar.
        """
        confirmar = str(request.query_params.get("confirmar", "")).lower()
        if confirmar not in ("sim", "yes", "true", "1"):
            return JSONResponse({
                "started": False,
                "reason": "para aplicar de verdade, chame com ?confirmar=sim",
            })
        if reconciliation.running:
            return JSONResponse({"started": False, "reason": "já em execução"})

        def _run_apply() -> None:
            try:
                rep = reconciliation.run(dry_run=False)
                log.info("[RECONCILIACAO apply] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("Reconciliação apply falhou: %s", e)

        threading.Thread(target=_run_apply, daemon=True).start()
        return JSONResponse({"started": True, "dry_run": False})

    # ================================================================
    # CAMPO "ATIVADO IA?" — carimbo do estado da IA nos leads
    # ================================================================
    # sweep   → varre só os leads recentes (leve; ideal como tarefa agendada)
    # backfill→ varre a base inteira uma vez
    from .ia_status import IaStatusEngine

    ia_status_engine = IaStatusEngine(
        kommo=pipeline.kommo,
        enabled=settings.ia_status_enabled,
        dry_run=settings.ia_status_dry_run,
    )

    # Backfill na inicialização — contorna a coordenação por endpoint
    # (que sofre com múltiplas réplicas). Cada réplica roda o backfill uma
    # vez ao subir; como é idempotente, rodar em várias réplicas é inócuo.
    if settings.ia_status_enabled and settings.ia_status_backfill_on_boot:
        def _backfill_on_boot() -> None:
            try:
                import time as _t
                _t.sleep(8)  # deixa o app terminar de subir
                rep = ia_status_engine.run(dry_run=False, mode="backfill")
                log.info("[IA-STATUS backfill-on-boot] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("IA-status backfill-on-boot falhou: %s", e)

        threading.Thread(target=_backfill_on_boot, daemon=True).start()

    @app.get("/ia-status/status")
    def ia_status_status() -> dict:
        """Estado + último relatório do carimbo ATIVADO IA?."""
        return ia_status_engine.status()

    @app.get("/ia-status/sweep")
    def ia_status_sweep(request: Request) -> JSONResponse:
        """Varredura dos leads recentes. Sem ?confirmar=sim roda em dry-run.
        O resultado fica em GET /ia-status/status quando terminar."""
        confirmar = str(request.query_params.get("confirmar", "")).lower()
        aplica = confirmar in ("sim", "yes", "true", "1")
        if ia_status_engine.running:
            return JSONResponse({"started": False, "reason": "já em execução"})

        def _run() -> None:
            try:
                rep = ia_status_engine.run(dry_run=not aplica, mode="sweep")
                log.info("[IA-STATUS sweep] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("IA-status sweep falhou: %s", e)

        threading.Thread(target=_run, daemon=True).start()
        return JSONResponse({"started": True, "dry_run": not aplica})

    @app.get("/ia-status/backfill")
    def ia_status_backfill(request: Request) -> JSONResponse:
        """Varredura da base inteira. Sem ?confirmar=sim roda em dry-run.
        O resultado fica em GET /ia-status/status quando terminar."""
        confirmar = str(request.query_params.get("confirmar", "")).lower()
        aplica = confirmar in ("sim", "yes", "true", "1")
        if ia_status_engine.running:
            return JSONResponse({"started": False, "reason": "já em execução"})

        def _run() -> None:
            try:
                rep = ia_status_engine.run(dry_run=not aplica, mode="backfill")
                log.info("[IA-STATUS backfill] %s", rep.as_dict())
            except Exception as e:  # noqa: BLE001
                log.exception("IA-status backfill falhou: %s", e)

        threading.Thread(target=_run, daemon=True).start()
        return JSONResponse({"started": True, "dry_run": not aplica})

    # ================================================================
    # ASAAS — LINK DE PAGAMENTO DA CONSULTA
    # ================================================================
    # GET /pagamento/link?lead_id=123&metodo=cartao&parcelas=3[&valor=480]
    #   Gera um link de pagamento no Asaas e envia ao paciente (8133).
    #   metodo: cartao (parcelado) | pix | flexivel
    from .asaas import AsaasClient, valor_consulta

    asaas = (
        AsaasClient(api_key=settings.asaas_api_key, env=settings.asaas_env)
        if settings.asaas_enabled else None
    )

    @app.get("/pagamento/link")
    def pagamento_link(request: Request) -> JSONResponse:
        # Sempre responde 200 com {ok: bool} — facilita diagnóstico.
        if asaas is None or not asaas.configured:
            return JSONResponse(
                {"ok": False,
                 "erro": "Asaas não configurado (ASAAS_ENABLED / ASAAS_API_KEY)."},
            )
        qp = request.query_params
        try:
            lead_id = int(qp.get("lead_id") or 0)
        except (TypeError, ValueError):
            lead_id = 0
        if not lead_id:
            return JSONResponse({"ok": False, "erro": "informe ?lead_id="})
        metodo = (qp.get("metodo") or "cartao").lower()
        try:
            parcelas = int(qp.get("parcelas") or 3)
        except (TypeError, ValueError):
            parcelas = 3
        enviar = str(qp.get("enviar", "sim")).lower() not in (
            "0", "false", "nao", "no",
        )

        # Contexto do lead no Kommo (médico, nomes).
        ctx: dict = {}
        if pipeline.kommo is not None:
            try:
                ctx = pipeline.kommo.get_caller_context_by_lead(lead_id) or {}
            except Exception as e:  # noqa: BLE001
                log.warning("Pagamento: contexto lead %s falhou: %s", lead_id, e)
        known = ctx.get("known") or {}
        medico = known.get("medico") or ""
        nome_paciente = known.get("nome_paciente") or ""
        nome_contato = ctx.get("name") or nome_paciente or "paciente"

        # Valor: parâmetro explícito tem prioridade; senão, tabela (artigo 19).
        valor = None
        if qp.get("valor"):
            try:
                valor = float(str(qp.get("valor")).replace(",", "."))
            except ValueError:
                valor = None
        if valor is None:
            valor = valor_consulta(medico, metodo, parcelas)
        if not valor or valor <= 0:
            return JSONResponse(
                {"ok": False, "medico": medico,
                 "erro": "valor não determinado para este médico — informe ?valor="},
            )

        descricao = "Consulta de avaliação oftalmológica"
        if medico:
            descricao += f" — {medico}"
        res = asaas.criar_link_pagamento(
            nome=f"Consulta {nome_paciente or nome_contato}".strip(),
            valor=valor, metodo=metodo, parcelas=parcelas, descricao=descricao,
        )
        if not res or not res.get("url"):
            return JSONResponse(
                {"ok": False, "valor": valor,
                 "erro": (res or {}).get("erro")
                 or "falha ao criar o link no Asaas"},
            )
        url = res["url"]
        valor_fmt = f"{valor:.2f}".replace(".", ",")

        if metodo == "cartao":
            forma = f"💳 Cartão em até {parcelas}x"
        elif metodo == "pix":
            forma = "🔑 Pix"
        else:
            forma = "💳 Cartão, Pix ou boleto (você escolhe no link)"
        msg = (
            f"Olá, {nome_contato}! 😊 Aqui está o link de pagamento da sua "
            f"consulta:\n\n{forma}\n💰 Valor: R$ {valor_fmt}\n🔗 {url}\n\n"
            "Assim que o pagamento for concluído, sua consulta fica "
            "confirmada. Qualquer dúvida, é só chamar por aqui!"
        )

        sent = False
        if enviar and wa_cloud is not None and pipeline.kommo is not None:
            try:
                phone = pipeline.kommo.get_lead_main_phone(lead_id)
                if phone:
                    wa_cloud.send_text(phone, msg)
                    sent = True
            except Exception as e:  # noqa: BLE001
                log.warning("Pagamento: envio ao paciente falhou: %s", e)
        if pipeline.kommo is not None:
            try:
                obs = " — enviado ao paciente" if sent else (
                    " — NÃO enviado (envie o link manualmente)"
                )
                pipeline.kommo.add_note(
                    lead_id,
                    f"💳 Link de pagamento gerado (Asaas)\n"
                    f"Valor: R$ {valor_fmt} ({metodo}"
                    + (f" {parcelas}x" if metodo == "cartao" else "")
                    + f"){obs}\n{url}",
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Pagamento: nota no Kommo falhou: %s", e)

        return JSONResponse(
            {"ok": True, "url": url, "valor": valor, "enviado": sent},
        )

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

    # ================================================================
    # DIAG/FIX: re-inscrever este App na WABA via Graph API
    # ================================================================
    # Sintoma 30/05/2026: WhatsApp 8133 entrega mensagens para o Kommo
    # mas Meta não dispara mais o callback /whatsapp pra voice_agent.
    # Causa raiz: a inscrição App↔WABA caiu (camada acima do webhook
    # field subscription). Fix: POST /{WABA_ID}/subscribed_apps com o
    # bearer token do App. Idempotente — chamar de novo se necessário.
    @app.get("/admin/whatsapp-subscribe-status")
    def admin_whatsapp_subscribe_status(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        waba_id = request.query_params.get("waba_id") or "1990931811727552"
        token = settings.whatsapp_cloud_token
        if not token:
            return JSONResponse({"error": "WHATSAPP_CLOUD_TOKEN ausente"})
        import httpx as _httpx
        url = f"https://graph.facebook.com/v22.0/{waba_id}/subscribed_apps"
        try:
            with _httpx.Client(timeout=15.0) as c:
                r = c.get(url, headers={"Authorization": f"Bearer {token}"})
            return JSONResponse({
                "status": r.status_code,
                "body": r.json() if r.content else None,
            })
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:400]})

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: debug do extrator de campos Kommo
    # ================================================================
    # GET /admin/debug-extract?phone=5561xxx
    # Mostra: tamanho do histórico Redis, últimas mensagens, o que
    # responder.extract_lead_fields() devolve, e o que SERIA postado
    # pra Kommo via update_lead_fields. Útil pra entender por que
    # custom_fields vem vazio no painel mesmo a Lia tendo conversado
    # com o paciente.
    @app.get("/admin/debug-extract")
    def admin_debug_extract(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        phone = request.query_params.get("phone") or ""
        convo_key = (
            request.query_params.get("convo_key")
            or (_conversation_key(phone) if phone else "")
        )
        if not convo_key:
            return JSONResponse({
                "error": "informe ?phone=5561xxx ou ?convo_key=...",
            })
        # Lê histórico do Redis via conversation_store do responder
        history = responder._convos.get(convo_key) or []
        last_msgs = [
            {"role": m.get("role"), "content": (m.get("content") or "")[:200]}
            for m in history[-6:]
        ]
        try:
            extracted = responder.extract_lead_fields(convo_key)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({
                "convo_key": convo_key,
                "phone": phone,
                "hist_len": len(history),
                "last_msgs": last_msgs,
                "extract_error": str(e)[:300],
            })
        return JSONResponse({
            "convo_key": convo_key,
            "phone": phone,
            "hist_len": len(history),
            "last_msgs": last_msgs,
            "extracted_fields": extracted,
            "extracted_keys": sorted((extracted or {}).keys()),
            "would_post_kommo": bool(extracted),
        })

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: fluxo Medware (agendamento)
    # ================================================================
    # Replica os 3 endpoints chave do padrão Lia pro fluxo Medware:
    #   /admin/dry-medware-agendar     → payload SEM postar
    #   /admin/force-medware-agendar   → POST real (sandbox/teste)
    #   /admin/medware-schema-check    → cods de médico/unidade/plano
    @app.get("/admin/dry-medware-agendar")
    def admin_dry_medware_agendar(request: Request) -> JSONResponse:
        """Monta o body que SERIA enviado ao Medware sem postar.

        Útil pra validar mapeamento médico/unidade/plano antes de
        gravar um agendamento real. Ex.:
        /admin/dry-medware-agendar?medico=Dra+Karla+Delalibera
           &unidade=Asa+Norte&data=2026-06-10&hora=14:30
           &nome=Joao+Teste&cpf=12345678900&convenio=particular
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if pipeline.medware is None:
            return JSONResponse({"error": "Medware não configurado"})
        from .medware import (
            MEDICO_CODES, UNIDADE_CODES, _code_lookup,
            PLANO_PARTICULAR, PROC_CONSULTA_PARTICULAR,
            PROC_CONSULTA_PARTICULAR_DEFAULT, PROC_CONSULTA_CONVENIO,
            resolver_plano, _data_hora_iso, _data_nasc_iso,
        )
        q = request.query_params
        medico = q.get("medico") or ""
        unidade = q.get("unidade") or ""
        data = q.get("data") or ""
        hora = q.get("hora") or ""
        nome = q.get("nome") or ""
        cpf = q.get("cpf") or ""
        data_nasc = q.get("data_nascimento") or ""
        celular = q.get("celular") or ""
        convenio = q.get("convenio") or "particular"
        cod_agenda = int(q.get("cod_agenda") or 0)

        cod_medico = _code_lookup(MEDICO_CODES, medico)
        cod_unidade = _code_lookup(UNIDADE_CODES, unidade)
        cod_plano = (
            PLANO_PARTICULAR
            if str(convenio).strip().lower() in (
                "particular", "sem convenio", "sem convênio"
            )
            else resolver_plano(convenio)
        )
        cod_proc = (
            PROC_CONSULTA_PARTICULAR.get(
                cod_medico or 0, PROC_CONSULTA_PARTICULAR_DEFAULT
            )
            if cod_plano == PLANO_PARTICULAR
            else PROC_CONSULTA_CONVENIO
        )
        cel = "".join(ch for ch in (celular or "") if ch.isdigit())
        if len(cel) > 11 and cel.startswith("55"):
            cel = cel[2:]
        cel_ddd = cel[:2] if len(cel) >= 10 else ""
        cel_num = cel[2:] if len(cel) >= 10 else cel
        cpf_digits = "".join(ch for ch in (cpf or "") if ch.isdigit())
        body = {
            "codAgenda": cod_agenda,
            "codMedico": cod_medico,
            "codProcedimento": cod_proc,
            "codPlano": cod_plano,
            "dataHoraAgendada": _data_hora_iso(f"{data}T{hora}") if (data and hora) else "",
            "paciente": {
                "nome": (nome or "").strip().upper(),
                "dataNascimento": _data_nasc_iso(data_nasc),
                "cpf": cpf_digits,
                "numeroCelularddd": cel_ddd,
                "numeroCelular": cel_num,
            },
        }
        # Sinais de saúde do payload (alertas)
        warnings = []
        if not cod_medico:
            warnings.append(f"medico '{medico}' não mapeado em MEDICO_CODES")
        if not cod_unidade:
            warnings.append(f"unidade '{unidade}' não mapeada em UNIDADE_CODES")
        if not cod_plano:
            warnings.append(f"convenio '{convenio}' não mapeado")
        if not cpf_digits:
            warnings.append("CPF vazio — Medware exige")
        if not (data and hora):
            warnings.append("data/hora ausente")
        return JSONResponse({
            "would_post_to": "Medware/Agendamento/Salvar",
            "body": body,
            "warnings": warnings,
            "ready_to_send": len(warnings) == 0,
        })

    @app.post("/admin/force-medware-agendar")
    @app.get("/admin/force-medware-agendar")
    def admin_force_medware_agendar(request: Request) -> JSONResponse:
        """Executa POST real ao Medware. Use SÓ com paciente de teste.

        Aceita mesmos params do dry-medware-agendar. Devolve cod_agendamento
        em sucesso ou motivo+detalhe em falha.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if pipeline.medware is None:
            return JSONResponse({"error": "Medware não configurado"})
        from .medware import MEDICO_CODES, UNIDADE_CODES, _code_lookup
        q = request.query_params
        cod_medico = _code_lookup(MEDICO_CODES, q.get("medico") or "")
        cod_unidade = _code_lookup(UNIDADE_CODES, q.get("unidade") or "")
        if not cod_medico:
            return JSONResponse({
                "ok": False, "motivo": "medico_nao_mapeado",
                "medico": q.get("medico"),
            })
        try:
            result = pipeline.medware.criar_agendamento(
                cod_medico=cod_medico,
                cod_unidade=cod_unidade or 0,
                cod_agenda=int(q.get("cod_agenda") or 0),
                data_hora=f"{q.get('data')}T{q.get('hora')}",
                nome=q.get("nome") or "",
                cpf=q.get("cpf") or "",
                data_nascimento=q.get("data_nascimento") or "",
                celular=q.get("celular") or "",
                convenio=q.get("convenio") or None,
            )
            log.info("[ADMIN FORCE-MEDWARE] result=%s", str(result)[:200])
            return JSONResponse(result)
        except Exception as e:  # noqa: BLE001
            log.warning("[ADMIN FORCE-MEDWARE] exception: %s", e)
            return JSONResponse({"ok": False, "exception": str(e)[:300]})

    @app.get("/admin/medware-pacientes-sem-retorno")
    def admin_medware_pacientes_sem_retorno(request: Request) -> JSONResponse:
        """Server-side: lista pacientes Medware que não consultam há mais de
        N meses (default 12). Filtra por status==5 (Realizado), telefone E.164
        válido, e deduplica por codPaciente. (Fábio 11/06/2026 — usado pela
        campanha 'retorno > 1 ano' pra ter Medware como fonte da verdade.)

        Query params:
          - secret (obrigatório) = WEBHOOK_SECRET
          - meses_min (default 12) = mínimo de meses desde a última consulta
          - meses_busca (default 30) = janela retroativa de busca
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if pipeline.medware is None:
            return JSONResponse({"error": "Medware não configurado"})

        import re
        from collections import defaultdict
        from datetime import datetime as _dt, timedelta as _td

        try:
            meses_min = int(request.query_params.get("meses_min") or "12")
            meses_busca = int(request.query_params.get("meses_busca") or "30")
        except ValueError:
            meses_min, meses_busca = 12, 30

        hoje = _dt.now()
        limite = hoje - _td(days=meses_min * 30)
        inicio_busca = hoje - _td(days=meses_busca * 30)

        def _norm_phone(raw):
            if not raw:
                return ""
            digitos = re.sub(r"\D", "", str(raw))
            if not digitos:
                return ""
            if not digitos.startswith("55") and len(digitos) >= 10:
                digitos = "55" + digitos
            if len(digitos) < 12 or len(digitos) > 13:
                return ""
            return digitos

        todos_ag = []
        cursor = inicio_busca
        paginas = 0
        while cursor < hoje:
            prox = cursor + _td(days=30)
            if prox > hoje:
                prox = hoje
            di = cursor.strftime("%d/%m/%Y")
            df = prox.strftime("%d/%m/%Y")
            try:
                # Buscar Karla (12080) + Fabrício (12081) separadamente
                for cod_med in (12080, 12081):
                    novos = pipeline.medware.listar_agendamentos(
                        di, df, cod_medico=cod_med,
                    )
                    if isinstance(novos, list):
                        todos_ag.extend(novos)
                paginas += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Medware listar_agendamentos %s-%s: %s", di, df, e)
            cursor = prox

        # Indexar por paciente
        por_paciente = {}
        for ag in todos_ag:
            if (ag or {}).get("codStatusAgendamento") != 5:
                continue
            paciente = ag.get("paciente") or {}
            cod = paciente.get("codPaciente")
            if not cod:
                continue
            try:
                data_ag = _dt.strptime(
                    ag.get("dataHoraAgendada", ""), "%d/%m/%Y %H:%M",
                )
            except Exception:
                continue
            bucket = por_paciente.setdefault(cod, {
                "codPaciente": cod,
                "nome": paciente.get("nome", ""),
                "telefone_bruto": paciente.get("telefone", ""),
                "dataNascimento": paciente.get("dataNascimento", ""),
                "cpf": paciente.get("cpf", ""),
                "ultima_data": data_ag,
                "ultima_codMedico": (ag.get("medico") or {}).get("codMedico"),
                "ultima_codUnidade": ag.get("codUnidade"),
                "total_consultas": 0,
            })
            bucket["total_consultas"] += 1
            if data_ag > bucket["ultima_data"]:
                bucket["ultima_data"] = data_ag
                bucket["ultima_codMedico"] = (ag.get("medico") or {}).get("codMedico")
                bucket["ultima_codUnidade"] = ag.get("codUnidade")

        elegiveis = []
        for p in por_paciente.values():
            if p["ultima_data"] >= limite:
                continue
            tel = _norm_phone(p["telefone_bruto"])
            if not tel:
                continue
            elegiveis.append({
                "codPaciente": p["codPaciente"],
                "nome": p["nome"],
                "telefone": tel,
                "dataNascimento": p["dataNascimento"],
                "cpf": p["cpf"],
                "ultimaConsulta": p["ultima_data"].strftime("%d/%m/%Y"),
                "ultimaConsulta_iso": p["ultima_data"].strftime("%Y-%m-%d"),
                "totalConsultas": p["total_consultas"],
                "codMedico": p["ultima_codMedico"],
                "codUnidade": p["ultima_codUnidade"],
            })

        return JSONResponse({
            "ok": True,
            "paginas_varridas": paginas,
            "total_agendamentos": len(todos_ag),
            "pacientes_unicos": len(por_paciente),
            "elegiveis": len(elegiveis),
            "meses_min": meses_min,
            "data_corte": limite.strftime("%d/%m/%Y"),
            "pacientes": elegiveis,
        })

    @app.get("/admin/medware-schema-check")
    def admin_medware_schema_check(request: Request) -> JSONResponse:
        """Bate os cods hardcoded (MEDICO_CODES, UNIDADE_CODES, PLANO_CODES)
        com os cods reais no Medware. Reporta divergências.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if pipeline.medware is None:
            return JSONResponse({"error": "Medware não configurado"})
        from .medware import MEDICO_CODES, UNIDADE_CODES, PLANO_CODES
        report: dict = {
            "medicos_hardcoded": len(MEDICO_CODES),
            "unidades_hardcoded": len(UNIDADE_CODES),
            "planos_hardcoded": len(PLANO_CODES),
            "warnings": [],
        }
        try:
            medicos_real = pipeline.medware.listar_medicos()
            real_codes = {int(m.get("codMedico") or 0) for m in medicos_real
                          if m.get("codMedico")}
            hardcoded_codes = {v for v in MEDICO_CODES.values()}
            faltando = hardcoded_codes - real_codes
            if faltando:
                report["warnings"].append({
                    "campo": "MEDICO_CODES",
                    "codigos_orfaos": sorted(faltando),
                })
            report["medicos_real_count"] = len(real_codes)
        except Exception as e:  # noqa: BLE001
            report["warnings"].append({"erro_listar_medicos": str(e)[:200]})
        try:
            unidades_real = pipeline.medware.listar_unidades()
            real_uni = {int(u.get("codUnidade") or 0) for u in unidades_real
                        if u.get("codUnidade")}
            hardcoded_uni = {v for v in UNIDADE_CODES.values()}
            faltando = hardcoded_uni - real_uni
            if faltando:
                report["warnings"].append({
                    "campo": "UNIDADE_CODES",
                    "codigos_orfaos": sorted(faltando),
                })
            report["unidades_real_count"] = len(real_uni)
        except Exception as e:  # noqa: BLE001
            report["warnings"].append({"erro_listar_unidades": str(e)[:200]})
        return JSONResponse(report)

    # ================================================================
    # OBSERVABILIDADE: painel operacional /admin/healthz
    # ================================================================
    # GET /admin/healthz
    # Dashboard JSON consolidado pra equipe ver "Lia ok / Lia falhou"
    # sem precisar tail de logs Easypanel. Junta:
    #   - última atividade de cada caminho (whatsapp inbound, kommo PATCH,
    #     extract Haiku, reactivation tick)
    #   - blacklist de campos órfãos detectados em runtime
    #   - estado de cada integração (kommo/medware/anthropic/whatsapp)
    # ================================================================
    # HEALTHCHECK KOMMO DEDICADO (Bug C-10 — 05/06/2026)
    # Faz UMA chamada real list_leads_by_status pra detectar token
    # expirado / cache stale / rate limit. Expõe resultado detalhado.
    # ================================================================
    @app.get("/admin/healthz-kommo")
    def admin_healthz_kommo(request: Request) -> JSONResponse:
        """Diagnóstico Kommo: chama list_leads_by_status pra cada etapa
        ativa do funil ATENDE e expõe contagem real.

        Sem auth — operação read-only.
        """
        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse({"error": "kommo_client indisponível"}, status_code=500)

        STATUS_PROVA = {
            96441724: "0-ETAPA ENTRADA",
            106919911: "0-a classificar",
            101508307: "2.LEADS FRIO",
            102560495: "3-AGENDAR",
            106184631: "4.REAGENDAR",
            101507507: "5-AGENDADO",
            101109455: "6-CONFIRMAR",
            106653499: "7.CONFIRMADO",
            106184983: "7.1-NO-SHOW",
        }
        out: dict = {"ok": True, "etapas": {}, "total_sum": 0}
        import time as _time
        for sid, nome in STATUS_PROVA.items():
            t0 = _time.time()
            try:
                leads = kommo_client.list_leads_by_status(
                    pipeline_id=8601819, status_ids=[sid], limit=5, page=1,
                )
                dt = round(_time.time() - t0, 2)
                count = len(leads or [])
                out["etapas"][str(sid)] = {
                    "nome": nome, "count": count, "elapsed_s": dt,
                    "sample_ids": [l.get("id") for l in (leads or [])[:3]],
                }
                out["total_sum"] += count
            except Exception as e:  # noqa: BLE001
                dt = round(_time.time() - t0, 2)
                out["etapas"][str(sid)] = {
                    "nome": nome, "erro": str(e)[:200], "elapsed_s": dt,
                }
        # Plus testa search direto (paginação básica)
        try:
            t0 = _time.time()
            with __import__("httpx").Client(timeout=10) as c:
                r = c.get(
                    f"{kommo_client._base}/leads",
                    params={"limit": 1, "page": 1},
                    headers=kommo_client._headers,
                )
            out["leads_basic"] = {
                "status": r.status_code,
                "elapsed_s": round(_time.time() - t0, 2),
                "body_len": len(r.text or ""),
                "body_preview": (r.text or "")[:200],
            }
        except Exception as e:  # noqa: BLE001
            out["leads_basic"] = {"erro": str(e)[:200]}
        return JSONResponse(out)

    @app.get("/admin/healthz")
    def admin_healthz(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        import voice_agent.kommo as _km
        import time as _t
        # Lê marcadores Redis de última atividade (best-effort).
        last_ts: dict = {}
        try:
            r = pipeline._redis
            for key, alias in [
                ("blink:healthz:last_inbound", "last_inbound_ts"),
                ("blink:healthz:last_lia_reply", "last_lia_reply_ts"),
                ("blink:healthz:last_kommo_patch_ok", "last_kommo_patch_ok_ts"),
                ("blink:healthz:last_kommo_patch_fail", "last_kommo_patch_fail_ts"),
                ("blink:healthz:last_extract", "last_extract_ts"),
            ]:
                try:
                    v = r.get(key)
                    if v:
                        last_ts[alias] = int(v)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        now = int(_t.time())
        return JSONResponse({
            "status": "ok",
            "now_ts": now,
            "last_activity": last_ts,
            "seconds_since": {
                k: now - v for k, v in last_ts.items() if isinstance(v, int)
            },
            "kommo_dead_field_ids": sorted(_km._KOMMO_DEAD_FIELD_IDS),
            "integrations": {
                "kommo": pipeline.kommo is not None,
                "medware": pipeline.medware is not None,
                "wa_cloud": wa_cloud is not None,
                "redis": pipeline._redis is not None,
            },
            "settings": {
                "humanize_enabled": settings.humanize_enabled,
                "humanize_debounce_sec": settings.humanize_debounce_sec,
                "reactivation_enabled": settings.reactivation_enabled,
                "reactivation_dry_run": settings.reactivation_dry_run,
                # Auditoria do switch Opus (07/06/2026 — caso Karla Pacheco).
                # Antes faltava aqui e eu não conseguia provar pro Fábio se
                # o fix estava on/off em prod. Agora expõe os 2 campos.
                "lia_opus_agenda_enabled": settings.lia_opus_agenda_enabled,
                "claude_opus_model": settings.claude_opus_model,
                "claude_sonnet_model": settings.claude_sonnet_model,
                "claude_haiku_model": settings.claude_haiku_model,
            },
        })

    # ================================================================
    # AUDIT: leads com IA silenciada há mais de N dias em etapa não-humana
    # ================================================================
    # GET /admin/audit/ia-desativada-orfa?dias=7&limit=200
    # Origem: lead 21392947 Elisa (Fábio 02/06/2026). IA ficou em
    # silêncio desde 13/04 porque última service_message foi "🛑" e
    # ninguém reativou. Com a nova regra (silêncio temporário 30min
    # + etapa = único critério permanente), leads como esse SÃO
    # auto-curados. Este endpoint conta quantos existem pra Fábio
    # decidir batch de reativação manual no Kommo se quiser.
    @app.get("/admin/audit/ia-desativada-orfa")
    def admin_audit_ia_orfa(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        import voice_agent.kommo as _km
        try:
            dias = int(request.query_params.get("dias", "7"))
            limit = int(request.query_params.get("limit", "200"))
        except (TypeError, ValueError):
            dias = 7
            limit = 200
        kommo = pipeline.kommo
        if kommo is None:
            return JSONResponse(
                {"erro": "Kommo não configurado"}, status_code=500,
            )
        # Etapas ONDE A IA DEVE estar ativa por padrão (qualquer
        # uma que NÃO esteja em ST_AGENT_OFF)
        from voice_agent.kommo import ST_AGENT_OFF
        # Lista leads ativos do pipeline ATENDE em etapas IA-on
        # (Closed-lost inclusive — está fora de ST_AGENT_OFF)
        etapas_iaOn = [
            96441724,   # 0-ENTRADA
            106919911,  # 0-A CLASSIFICAR
            101508307,  # 2-FRIO
            102560495,  # 3-AGENDAR
            106184631,  # 4-REAGENDAR
            106184983,  # 7.1-NO-SHOW
            101507507,  # 5-AGENDADO
            91486864,   # 8-REALIZADO CONSULTA
            143,        # Closed-lost
        ]
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=dias)
        orfaos = []
        for sid in etapas_iaOn:
            if sid in ST_AGENT_OFF:
                continue
            try:
                leads = kommo.list_leads_by_status(
                    pipeline_id=8601819, status_ids=[sid],
                    limit=100, page=1,
                ) or []
            except Exception:  # noqa: BLE001
                continue
            for ld in leads[:50]:  # cap por etapa
                lid = ld.get("id")
                if not lid:
                    continue
                try:
                    ts_humano = kommo._ts_ultimo_humano_escreveu(lid)
                except Exception:  # noqa: BLE001
                    continue
                if not ts_humano:
                    continue
                if ts_humano > cutoff.timestamp():
                    continue  # humano escreveu recente — não é órfão
                orfaos.append({
                    "lead_id": lid,
                    "nome": ld.get("name") or f"Lead #{lid}",
                    "status_id": sid,
                    "humano_escreveu_em": datetime.fromtimestamp(
                        ts_humano, tz=timezone.utc,
                    ).isoformat(),
                    "dias_em_silencio": int(
                        (datetime.now(timezone.utc).timestamp()
                         - ts_humano) / 86400,
                    ),
                    "url": (
                        f"https://univeja.kommo.com/leads/detail/{lid}"
                    ),
                })
                if len(orfaos) >= limit:
                    break
            if len(orfaos) >= limit:
                break
        orfaos.sort(key=lambda x: -x["dias_em_silencio"])
        return JSONResponse({
            "criterio_dias": dias,
            "etapas_iaOn_varridas": etapas_iaOn,
            "total_orfaos": len(orfaos),
            "leads": orfaos,
            "observacao": (
                "Com a nova regra (sileêncio TEMPORÁRIO de 30min, não "
                "permanente), TODOS os leads listados aqui voltam a "
                "ter IA respondendo automaticamente quando paciente "
                "escrever. Lista mantida só pra Fábio ver tamanho do "
                "buraco anterior."
            ),
        })

    # ================================================================
    # PILAR #1: detector de leads-fantasma (cron + endpoint manual)
    # ================================================================
    # Cron interno roda a cada 5 min (se LEADS_FANTASMA_ENABLED=1).
    # POST /admin/leads-fantasma-tick?secret=... — força tick manual.
    @app.post("/admin/leads-fantasma-tick")
    def admin_leads_fantasma_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        dry = request.query_params.get("dry_run", "0") == "1"
        try:
            from voice_agent.leads_fantasma import tick
            res = tick(
                pipeline.kommo,
                pipeline._redis,
                dry_run=dry,
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"erro": f"tick falhou: {e}"}, status_code=500,
            )
        return JSONResponse({
            "dry_run": dry,
            "varridos": res.varridos,
            "fantasmas_encontrados": res.fantasmas_encontrados,
            "alertados": res.alertados,
            "ja_alertados_dedup": res.ja_alertados_dedup,
            "erros": res.erros,
            "detalhes": res.detalhes[:50],
        })

    # ================================================================
    # PILAR #4: watchdog "Lia muda" — detecta inbound sem outbound
    # ================================================================
    # POST /admin/watchdog-lia-tick?secret=...&dry_run=1
    @app.post("/admin/watchdog-lia-tick")
    def admin_watchdog_lia_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        dry = request.query_params.get("dry_run", "0") == "1"
        forc = request.query_params.get("forcar_horario", "0") == "1"
        try:
            from voice_agent.watchdog_lia import tick
            res = tick(
                pipeline.kommo, pipeline._redis,
                dry_run=dry, forcar_horario=forc,
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"erro": f"tick falhou: {e}"}, status_code=500,
            )
        return JSONResponse({
            "dry_run": dry,
            "forcar_horario": forc,
            "varridos": res.varridos,
            "suspeitos": res.suspeitos,
            "alertados": res.alertados,
            "ja_alertados_dedup": res.ja_alertados_dedup,
            "fora_horario": res.fora_horario,
            "ia_pausada": res.ia_pausada,
            "erros": res.erros,
            "detalhes": res.detalhes[:50],
        })

    # ================================================================
    # PILAR #5: canary lead diário — fluxo completo ponta-a-ponta
    # ================================================================
    # POST /admin/canary-tick?secret=...&dry_run=1&alertar_sempre=0
    @app.post("/admin/canary-tick")
    def admin_canary_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        dry = request.query_params.get("dry_run", "0") == "1"
        alertar = request.query_params.get("alertar_sempre", "0") == "1"
        # Wrapper sobre o pipeline pra ser chamado pelo canary
        def _simular(phone: str, texto: str) -> dict:
            try:
                ans = pipeline.responder.reply(
                    user_text=texto,
                    conversation_key=phone[-12:],
                    channel="81331005",
                )
                return {"resposta_lia": ans or ""}
            except Exception as e:  # noqa: BLE001
                return {"resposta_lia": "", "erro": str(e)}
        try:
            from voice_agent.canary_lead import tick
            res = tick(
                _simular, pipeline._redis,
                dry_run=dry, alertar_sempre=alertar,
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"erro": f"canary falhou: {e}"}, status_code=500,
            )
        return JSONResponse({
            "canary_phone": res.canary_phone,
            "steps_total": res.steps_total,
            "steps_ok": res.steps_ok,
            "steps_falhou": res.steps_falhou,
            "duracao_total_ms": res.duracao_total_ms,
            "detalhes": res.steps_detalhe,
        })

    # ================================================================
    # REPLAY: histórico de turnos do lead (tracing estruturado)
    # ================================================================
    # GET /admin/replay/{lead_id}?secret=...&limit=100
    # Devolve todos os traces salvos pelo TraceBuilder (Redis list
    # `blink:trace:{lead_id}`, TTL 30 dias). Cada item tem:
    # ts, user_text, ctx_resumo, tools, juiz_veredict, output,
    # filtros disparados, elapsed_ms. Substitui o ritual
    # "abre Kommo + abre logs + adivinha" por 1 curl.
    @app.get("/admin/replay/{lead_id}")
    def admin_replay(lead_id: int, request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        try:
            limit = int(request.query_params.get("limit", "100"))
        except (TypeError, ValueError):
            limit = 100
        limit = max(min(limit, 500), 1)
        try:
            from voice_agent.tracing import carregar_traces
            redis_client = pipeline._redis
            traces = carregar_traces(redis_client, lead_id, limit=limit)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"erro": f"Erro lendo traces: {e}"}, status_code=500,
            )
        return JSONResponse({
            "lead_id": lead_id,
            "url_kommo": f"https://univeja.kommo.com/leads/detail/{lead_id}",
            "total_turnos": len(traces),
            "turnos": [t.to_dict() for t in traces],
            "observacao": (
                "Lista em ordem cronológica (mais antigo primeiro). "
                "TTL 30 dias por turno. Para ativar coleta: "
                "TRACING_ENABLED=1 no Easypanel."
            ),
        })

    # ================================================================
    # AUDITORIA: leads em 2.LEADS FRIO com 1.DIA CONSULTA preenchido
    # ================================================================
    # GET /admin/audit/frios-com-agendamento?secret=...&limit=500
    # Origem: Fábio 01/06/2026 — observou 372 leads em 2.LEADS FRIO
    # (101508307) e quis saber quantos já têm consulta marcada (campo
    # 1.DIA CONSULTA, field_id 1255723). Inconsistência: paciente foi
    # agendado mas o status do funil não foi movido para 5-AGENDADO
    # (101507507) — fica preso em FRIO recebendo reativação indevida.
    #
    # Devolve: total varrido, total com agendamento, total com data
    # futura (= ainda relevante), total com data passada (= no-show
    # antigo), e lista detalhada (id, nome, dia_consulta_iso, url).
    @app.get("/admin/audit/frios-com-agendamento")
    def admin_audit_frios_agendados(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        import voice_agent.kommo as _km
        from datetime import datetime as _dt, timezone as _tz
        try:
            limit = int(request.query_params.get("limit", "500"))
        except (TypeError, ValueError):
            limit = 500
        limit = max(min(limit, 1000), 50)
        # Lista TODOS os leads de 101508307 (paginado, ordem updated_at asc)
        # OBS: kommo.list_leads_by_status devolve no máximo 250 por page;
        # paginamos até 4 vezes pra cobrir 1000 leads.
        kommo = pipeline.kommo
        if kommo is None:
            return JSONResponse(
                {"erro": "Kommo client não configurado"},
                status_code=500,
            )
        coletados: list[dict] = []
        for page in range(1, 5):  # até 1000
            batch = kommo.list_leads_by_status(
                pipeline_id=8601819,
                status_ids=[101508307],
                limit=250,
                page=page,
            )
            if not batch:
                break
            coletados.extend(batch)
            if len(batch) < 250:
                break
            if len(coletados) >= limit:
                break
        coletados = coletados[:limit]
        agora_ts = int(_dt.now(_tz.utc).timestamp())
        com_agendamento: list[dict] = []
        sem_agendamento = 0
        for ld in coletados:
            try:
                detalhe = kommo.get_lead(ld["id"])
            except Exception:  # noqa: BLE001
                detalhe = None
            dia_ts: int | None = None
            if detalhe:
                for f in detalhe.get("custom_fields_values") or []:
                    if f.get("field_id") == 1255723:
                        vals = f.get("values") or []
                        if vals and vals[0].get("value"):
                            try:
                                dia_ts = int(vals[0]["value"])
                            except (TypeError, ValueError):
                                dia_ts = None
                        break
            if dia_ts:
                dt_iso = _dt.fromtimestamp(dia_ts, tz=_tz.utc).isoformat()
                com_agendamento.append({
                    "id": ld["id"],
                    "name": ld.get("name") or f"Lead #{ld['id']}",
                    "dia_consulta_ts": dia_ts,
                    "dia_consulta_iso": dt_iso,
                    "futuro": dia_ts > agora_ts,
                    "url": f"https://univeja.kommo.com/leads/detail/{ld['id']}",
                })
            else:
                sem_agendamento += 1
        futuros = sum(1 for x in com_agendamento if x["futuro"])
        passados = len(com_agendamento) - futuros
        # ordena: futuros primeiro (mais urgentes), depois passados
        com_agendamento.sort(
            key=lambda x: (not x["futuro"], x["dia_consulta_ts"]),
        )
        return JSONResponse({
            "varridos": len(coletados),
            "com_agendamento": len(com_agendamento),
            "agendamento_futuro": futuros,
            "agendamento_passado": passados,
            "sem_agendamento": sem_agendamento,
            "leads": com_agendamento[:200],  # limita payload
            "observacao": (
                "futuros = inconsistência crítica (paciente tem consulta "
                "marcada mas está em FRIO recebendo reativação). "
                "passados = no-show antigo / arquivamento OK em FRIO."
            ),
        })

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: status do schema Kommo
    # ================================================================
    # GET /admin/schema-check
    # Lista os field_ids que o auto-skip da Kommo blacklist neste runtime.
    # Mostra os campos órfãos que o Kommo rejeitou em algum momento, e que
    # agora são ignorados automaticamente. Self-healing visível.
    @app.get("/admin/schema-check")
    def admin_schema_check(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        import voice_agent.kommo as _km
        dead = sorted(_km._KOMMO_DEAD_FIELD_IDS)
        return JSONResponse({
            "kommo_dead_field_ids": dead,
            "count": len(dead),
            "note": (
                "Field_ids que o Kommo rejeitou com NotSupportedChoice e "
                "que o builder agora pula automaticamente. Pra reativar "
                "um campo após corrigir no Kommo: reiniciar o container."
            ),
        })

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: FORÇA o sync real de um lead
    # ================================================================
    # GET /admin/force-resync?lead_id=24045059
    # 1. Lê phone do contato Kommo do lead
    # 2. Roda extract_lead_fields no convo_key
    # 3. Faz PATCH REAL no Kommo (não dry)
    # 4. Devolve resposta completa: phone, hist_len, extracted_keys,
    #    payload_cfs_count, kommo_status_code, kommo_response_text
    # Diagnóstico definitivo de por que custom_fields fica vazio em
    # produção.
    @app.get("/admin/force-resync")
    def admin_force_resync(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        try:
            lead_id = int(request.query_params.get("lead_id") or 0)
        except ValueError:
            lead_id = 0
        if not lead_id or pipeline.kommo is None:
            return JSONResponse({"error": "informe ?lead_id=NNNN"})
        # 1) Lê o lead com contacts pra descobrir o phone
        import httpx as _httpx
        try:
            with _httpx.Client(timeout=15.0) as c:
                r = c.get(
                    f"{pipeline.kommo._base}/leads/{lead_id}",
                    params={"with": "contacts"},
                    headers=pipeline.kommo._headers,
                )
            if r.status_code != 200:
                return JSONResponse({
                    "error": f"GET lead falhou HTTP {r.status_code}",
                    "body": (r.text or "")[:300],
                })
            lead_json = r.json()
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": f"GET lead exception: {e}"})
        # Phone do primeiro contato
        contacts = (
            lead_json.get("_embedded", {}).get("contacts") or []
        )
        phones: list[str] = []
        if contacts:
            cid = contacts[0].get("id")
            try:
                with _httpx.Client(timeout=15.0) as c:
                    rc = c.get(
                        f"{pipeline.kommo._base}/contacts/{cid}",
                        headers=pipeline.kommo._headers,
                    )
                if rc.status_code == 200:
                    cj = rc.json()
                    for cf in (cj.get("custom_fields_values") or []):
                        if cf.get("field_code") == "PHONE":
                            for v in (cf.get("values") or []):
                                if v.get("value"):
                                    phones.append(v["value"])
            except Exception as e:  # noqa: BLE001
                log.warning("[force-resync] GET contact falhou: %s", e)
        if not phones:
            return JSONResponse({
                "error": "nenhum phone encontrado no contato",
                "lead_id": lead_id,
                "contacts_count": len(contacts),
            })
        # Usa o primeiro phone, normalizado (só dígitos)
        phone_raw = phones[0]
        phone = "".join(ch for ch in phone_raw if ch.isdigit())
        convo_key = _conversation_key(phone)
        history = responder._convos.get(convo_key) or []
        # 2) Roda extract
        try:
            extracted = responder.extract_lead_fields(convo_key) or {}
        except Exception as e:  # noqa: BLE001
            return JSONResponse({
                "lead_id": lead_id, "phone": phone, "convo_key": convo_key,
                "hist_len": len(history),
                "extract_error": str(e)[:300],
            })
        # 3) Enriquece e tenta PATCH REAL
        fields = dict(extracted)
        fields.setdefault("numero_telefone", "81331005")
        fields["ativado_ia"] = "ATIVADO"
        fields["atendente"] = "Lia"
        # Captura status code do PATCH
        captured: dict = {"status": None, "body": "", "called": False}
        import voice_agent.kommo as _km
        real_client_cls = _km.httpx.Client

        class _CapturingClient:
            def __init__(self, *a, **kw):
                self._real = real_client_cls(*a, **kw)

            def __enter__(self):
                self._real.__enter__()
                return self

            def __exit__(self, *a):
                return self._real.__exit__(*a)

            def patch(self, url, json=None, headers=None):
                captured["called"] = True
                captured["url"] = url
                captured["payload_keys"] = list((json or {}).keys())
                captured["payload_full"] = json
                resp = self._real.patch(url, json=json, headers=headers)
                captured["status"] = resp.status_code
                captured["body"] = (resp.text or "")[:600]
                return resp

            def get(self, *a, **kw):
                return self._real.get(*a, **kw)

            def post(self, *a, **kw):
                return self._real.post(*a, **kw)

        _km.httpx.Client = _CapturingClient  # type: ignore[misc]
        try:
            ok = pipeline.kommo.update_lead_fields(lead_id, fields)
        finally:
            _km.httpx.Client = real_client_cls  # type: ignore[misc]
        return JSONResponse({
            "lead_id": lead_id,
            "phone_from_contact": phone_raw,
            "phone_normalized": phone,
            "convo_key": convo_key,
            "hist_len": len(history),
            "extracted_keys": sorted(extracted.keys()),
            "fields_sent_keys": sorted(fields.keys()),
            "update_returned": ok,
            "patch_called": captured.get("called"),
            "patch_status": captured.get("status"),
            "patch_body_preview": captured.get("body"),
            "patch_payload_keys": captured.get("payload_keys"),
            "patch_payload_full": captured.get("payload_full"),
        })

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: simular sync Kommo SEM postar (dry)
    # ================================================================
    # GET /admin/dry-sync?phone=5561xxx[&lead_id=24045059]
    # Captura o estado COMPLETO do que aconteceria no sync Kommo:
    #   - histórico Redis disponível pra extract
    #   - fields extraídos pelo Haiku
    #   - payload custom_fields_values que SERIA enviado ao Kommo
    #   - warnings de enum não casado (causa típica de PATCH 400)
    # NÃO executa o PATCH no Kommo. Para diagnosticar custom_fields=[]
    # em lead real, basta rodar dry-sync com phone do mesmo paciente.
    @app.get("/admin/dry-sync")
    def admin_dry_sync(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        phone = request.query_params.get("phone") or ""
        convo_key = (
            request.query_params.get("convo_key")
            or (_conversation_key(phone) if phone else "")
        )
        if not convo_key:
            return JSONResponse({"error": "informe ?phone=5561xxx"})
        # 1) Pega histórico
        history = responder._convos.get(convo_key) or []
        # 2) Roda extrator
        try:
            extracted = responder.extract_lead_fields(convo_key) or {}
        except Exception as e:  # noqa: BLE001
            return JSONResponse({
                "convo_key": convo_key, "hist_len": len(history),
                "extract_error": str(e)[:300],
            })
        # 3) Reproduz o enriquecimento que _sync_kommo_safely faz
        enriched = dict(extracted)
        enriched["numero_telefone"] = "81331005"
        enriched["ativado_ia"] = "ATIVADO"
        enriched["atendente"] = "Lia"
        # 4) Calcula o payload custom_fields_values que SERIA enviado
        #    capturando warnings de enum não casado.
        import io as _io
        import logging as _logging
        log_buf = _io.StringIO()
        h = _logging.StreamHandler(log_buf)
        h.setLevel(_logging.WARNING)
        root = _logging.getLogger("voice_agent.kommo")
        root.addHandler(h)
        try:
            # Monkey-patch httpx.Client.patch pra capturar sem enviar
            cfs_capturado: list = []

            class _FakeResp:
                status_code = 200
                text = "DRY-RUN"

                def json(self):
                    return {}

            class _FakeClient:
                def __init__(self, **kw):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def patch(self, url, json=None, headers=None):
                    cfs_capturado.append(json or {})
                    return _FakeResp()

            import voice_agent.kommo as _km
            real_client = _km.httpx.Client
            _km.httpx.Client = _FakeClient  # type: ignore[misc]
            try:
                pipeline.kommo.update_lead_fields(
                    int(request.query_params.get("lead_id") or 999999999),
                    enriched,
                )
            finally:
                _km.httpx.Client = real_client  # type: ignore[misc]
        finally:
            root.removeHandler(h)
            h.flush()
        payload = cfs_capturado[0] if cfs_capturado else {}
        cfs_list = payload.get("custom_fields_values", []) if isinstance(
            payload, dict
        ) else []
        return JSONResponse({
            "convo_key": convo_key,
            "phone": phone,
            "hist_len": len(history),
            "extracted_keys": sorted(extracted.keys()),
            "enriched_keys": sorted(enriched.keys()),
            "payload_cfs_count": len(cfs_list),
            "payload_field_ids":
                [c.get("field_id") for c in cfs_list],
            "kommo_warnings_log": log_buf.getvalue()[-2000:],
            "payload_preview": cfs_list[:30],
        })

    # ================================================================
    # AMBIENTE DE TESTE/VALIDAÇÃO: simular inbound do WhatsApp Cloud
    # ================================================================
    # POST /admin/simulate-inbound  { phone, text, [dry_run] }
    # Dispara o pipeline REAL do /whatsapp como se o paciente tivesse
    # mandado a mensagem agora. Útil pra validar Lia em produção sem
    # depender de Meta entregar payload de teste, e pra rodar smoke
    # tests sem precisar mensagem real de paciente.
    #
    # dry_run=true → roda responder.reply mas NÃO envia WhatsApp nem
    # posta nota Kommo (devolve o texto que a Lia geraria).
    # dry_run=false → envia de verdade pelo número informado.
    @app.post("/admin/simulate-inbound")
    @app.get("/admin/simulate-inbound")
    async def admin_simulate_inbound(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        if wa_cloud is None:
            return JSONResponse({"error": "WhatsApp Cloud não configurado"})
        # Aceita body JSON OU query params
        data: dict[str, Any] = {}
        try:
            if request.method == "POST":
                body = await request.body()
                if body:
                    data = json.loads(body) or {}
        except Exception:  # noqa: BLE001
            data = {}
        if not data:
            data = {
                "phone": request.query_params.get("phone") or "",
                "text": request.query_params.get("text") or "",
                "dry_run": request.query_params.get("dry_run") in
                ("1", "true", "True"),
            }
        phone = str(data.get("phone") or "").strip()
        text = str(data.get("text") or "").strip()
        dry_run = bool(data.get("dry_run", False))
        if not phone or not text:
            return JSONResponse({
                "error": "informe 'phone' (E.164 sem +) e 'text'",
                "exemplo": {"phone": "5561999999999", "text": "oi"},
            })
        # Em dry_run, só roda responder.reply sem efeitos colaterais.
        if dry_run:
            convo_key = _conversation_key(phone)
            caller_context = None
            try:
                if pipeline.kommo is not None:
                    caller_context = pipeline.kommo.get_caller_context(phone)
            except Exception as e:  # noqa: BLE001
                log.warning("[SIMULATE] caller_context falhou: %s", e)
            try:
                result = responder.reply(
                    convo_key, text, caller_context=caller_context
                )
                answer = result.get("answer") or ""
                log.info(
                    "[SIMULATE DRY] convo=%s text=%r answer=%r",
                    convo_key, text[:80], answer[:200],
                )
                return JSONResponse({
                    "ok": True,
                    "dry_run": True,
                    "convo_key": convo_key,
                    "phone": phone,
                    "input_text": text,
                    "answer": answer,
                    "caller_context_found": bool(
                        caller_context and caller_context.get("found")
                    ),
                })
            except Exception as e:  # noqa: BLE001
                log.warning("[SIMULATE DRY] responder.reply falhou: %s", e)
                return JSONResponse({
                    "ok": False, "error": str(e)[:400],
                })
        # Modo "ao vivo": chama exatamente o mesmo pipeline do /whatsapp.
        # Roda em background pra responder rápido (igual webhook real).
        import uuid as _uuid
        fake_mid = f"sim_{_uuid.uuid4().hex[:16]}"
        threading.Thread(
            target=_process_whatsapp_cloud,
            args=(text, phone, fake_mid),
            daemon=True,
        ).start()
        log.info(
            "[SIMULATE LIVE] enfileirado convo=%s mid=%s text=%r",
            _conversation_key(phone), fake_mid, text[:80],
        )
        return JSONResponse({
            "ok": True,
            "dry_run": False,
            "mid": fake_mid,
            "phone": phone,
            "input_text": text,
            "note": "pipeline rodando em background — Lia responderá pelo "
                    "WhatsApp e postará nota no lead (se identificado).",
        })

    # ================================================================
    # ETAPA A CLASSIFICAR — task #96
    # ================================================================
    @app.post("/admin/classificar-tick")
    @app.get("/admin/classificar-tick")
    def admin_classificar_tick(request: Request) -> JSONResponse:
        """Cron: move leads que receberam renovação e não responderam.

        Params:
          - dry_run (default true) — não move, só lista.
          - lead_id (opcional) — checar APENAS um lead específico.
          - timeout_h (opcional) — override do default.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.classificar import (
            REDIS_KEY_AGUARDA_FMT,
            get_status_a_classificar_id,
            get_timeout_classificar_horas,
            mover_lead_para_classificar,
        )
        import time as _t

        # Leitura LAZY — env vista no momento da chamada (fix 31/05/2026).
        STATUS_DESTINO = get_status_a_classificar_id()
        TIMEOUT_DEFAULT = get_timeout_classificar_horas()

        q = request.query_params
        dry_run = (q.get("dry_run") or "true").lower() in ("1", "true", "yes")
        try:
            timeout_h = int(q.get("timeout_h") or TIMEOUT_DEFAULT)
        except ValueError:
            timeout_h = TIMEOUT_DEFAULT

        redis_cli = getattr(pipeline, "_redis", None)
        kommo_cli = getattr(pipeline, "kommo", None)
        agora = _t.time()

        if STATUS_DESTINO is None:
            return JSONResponse({
                "ok": False,
                "error": "KOMMO_STATUS_A_CLASSIFICAR_ID não configurado",
                "hint": "Crie etapa 'A CLASSIFICAR' no Kommo e seta no Easypanel.",
                "debug_env_value": os.environ.get("KOMMO_STATUS_A_CLASSIFICAR_ID", "<UNSET>"),
            }, status_code=501)

        # Lead específico
        lead_id_raw = q.get("lead_id")
        if lead_id_raw:
            try:
                lead_id = int(lead_id_raw)
            except ValueError:
                return JSONResponse({"error": "lead_id inválido"}, status_code=400)
            chave = REDIS_KEY_AGUARDA_FMT.format(lead_id=lead_id)
            disparo_ts = None
            if redis_cli is not None:
                try:
                    raw = redis_cli.get(chave)
                    if raw:
                        disparo_ts = float(raw)
                except Exception:  # noqa: BLE001
                    pass
            r = mover_lead_para_classificar(
                lead_id=lead_id,
                disparo_renovacao_ts=disparo_ts,
                ultima_resposta_paciente_ts=None,  # TODO: ler do Redis
                kommo_client=None if dry_run else kommo_cli,
                agora=agora, dry_run=dry_run,
                timeout_horas=timeout_h,
            )
            return JSONResponse({"resultados": [r.__dict__]})

        # Varredura em lote — scan keys
        if redis_cli is None:
            return JSONResponse({
                "ok": False,
                "error": "Redis ausente — varredura em lote indisponível",
            }, status_code=503)

        resultados = []
        try:
            cursor = 0
            pattern = "blink:classificar:aguardando_resposta:*"
            while True:
                cursor, batch = redis_cli.scan(
                    cursor=cursor, match=pattern, count=200,
                )
                for k in batch:
                    key_str = k.decode() if isinstance(k, bytes) else k
                    try:
                        lead_id = int(key_str.rsplit(":", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    try:
                        raw = redis_cli.get(key_str)
                        disparo_ts = float(raw) if raw else None
                    except Exception:  # noqa: BLE001
                        disparo_ts = None
                    r = mover_lead_para_classificar(
                        lead_id=lead_id,
                        disparo_renovacao_ts=disparo_ts,
                        ultima_resposta_paciente_ts=None,
                        kommo_client=None if dry_run else kommo_cli,
                        agora=agora, dry_run=dry_run,
                        timeout_horas=timeout_h,
                    )
                    if r.movido or r.razao == "timeout_excedido":
                        resultados.append({
                            "lead_id": r.lead_id, "movido": r.movido,
                            "razao": r.razao, "horas": r.horas_passadas,
                            "erro": r.erro,
                        })
                if cursor == 0:
                    break
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({
                "ok": False, "erro": str(exc)[:300],
                "parciais": resultados,
            })

        return JSONResponse({
            "ok": True, "dry_run": dry_run, "timeout_h": timeout_h,
            "status_destino_id": STATUS_DESTINO,
            "total_candidatos": len(resultados),
            "resultados": resultados,
        })

    # ================================================================
    # DISPATCHER DE RENOVAÇÃO 24h — task #94
    # Decide free-form vs template_1039 vs skip, dispara via wa_cloud.
    # ================================================================
    @app.post("/admin/renovacao-dispatch")
    @app.get("/admin/renovacao-dispatch")
    def admin_renovacao_dispatch(request: Request) -> JSONResponse:
        """Dispara renovação para UM lead (snapshot via querystring).

        Params obrigatórios:
          - lead_id, telefone, nome_contato, status_id
        Opcionais:
          - horas_desde_paciente (float, default None → lead frio)
          - ja_respondeu_na_vida (true/false, default false)
          - dry_run (true/false, default true — segurança)
          - forcar (true/false, ignora dedup Redis)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        import time as _t
        from voice_agent.renovacao_dispatcher import (
            SnapshotLead, dispatch_renovacao,
        )

        q = request.query_params

        def _bool(name, default=False):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        try:
            lead_id = int(q.get("lead_id") or 0)
            status_id_raw = q.get("status_id")
            status_id = int(status_id_raw) if status_id_raw else None
        except ValueError:
            return JSONResponse({"error": "lead_id/status_id inválidos"}, status_code=400)
        telefone = q.get("telefone") or ""
        nome_contato = q.get("nome_contato") or ""
        horas_raw = q.get("horas_desde_paciente")
        try:
            horas = float(horas_raw) if horas_raw else None
        except ValueError:
            horas = None

        if not lead_id or not telefone or not nome_contato:
            return JSONResponse({
                "error": "obrigatórios: lead_id, telefone, nome_contato",
            }, status_code=400)

        ultima_ts = (_t.time() - horas * 3600) if horas is not None else None
        dry_run = _bool("dry_run", default=True)  # padrão seguro: dry
        forcar = _bool("forcar", default=False)

        snap = SnapshotLead(
            lead_id=lead_id,
            telefone_e164=telefone,
            nome_contato=nome_contato,
            status_id=status_id,
            ultima_msg_paciente_ts=ultima_ts,
            paciente_ja_respondeu_na_vida=_bool("ja_respondeu_na_vida"),
        )

        # Em dry_run, NÃO passa wa_client/redis/kommo (zero side-effect).
        wa = None if dry_run else wa_cloud
        redis_cli = None if dry_run else getattr(pipeline, "_redis", None)
        kommo_writer = None if dry_run else getattr(pipeline, "kommo", None)

        res = dispatch_renovacao(
            snap,
            wa_client=wa,
            redis_client=redis_cli,
            kommo_note_writer=kommo_writer,
            agora=_t.time(),
            dry_run=dry_run,
            forcar_redispatch=forcar,
        )
        return JSONResponse(res.to_dict())

    # ================================================================
    # LEADS ABANDONADOS — caso 24107106 (05/06/2026)
    # Lia promete agenda, paciente espera, ninguém volta. Watchdog
    # estava lá mas não disparou alerta. Endpoint varre rajada-órfã:
    # último inbound > X min sem outbound subsequente AND IA Ativada.
    # ================================================================
    # ================================================================
    # MÉTRICAS LIVE DE FUNCIONAMENTO (task #260, 06/06/2026)
    # Resposta direta à pergunta "o que GARANTE o funcionamento" — número
    # em vez de promessa. Counters Redis simples + endpoint que lê.
    # ================================================================
    @app.get("/admin/funcionamento")
    def admin_funcionamento(request: Request, dias: int = 1) -> JSONResponse:
        """Métricas live do funcionamento da Lia.

        ?dias=1 → snapshot de hoje (default)
        ?dias=7 → série dos últimos 7 dias

        Retorna contadores brutos + taxas calculadas + alarmes ativos.
        """
        if settings.webhook_secret:
            _got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if _got != settings.webhook_secret:
                return JSONResponse({"erro": "unauthorized"}, status_code=401)
        try:
            from . import metricas_funcionamento as mf
            redis_c = getattr(pipeline, "_redis", None) if pipeline else None
            if dias <= 1:
                return JSONResponse(mf.funcionamento_hoje(redis_c))
            return JSONResponse(mf.funcionamento_ultimos_n_dias(redis_c, n=dias))
        except Exception as e:  # noqa: BLE001
            log.exception("[admin/funcionamento] crash: %s", e)
            return JSONResponse(
                {"erro": "crash", "detalhe": str(e)[:200]}, status_code=500,
            )

    @app.post("/admin/funcionamento/checar-alarmes")
    @app.get("/admin/funcionamento/checar-alarmes")
    def admin_checar_alarmes(request: Request) -> JSONResponse:
        """Roda checagem de alarmes — se taxa caiu, envia Slack.

        Chamado por cron interno (a cada 1h) OU manualmente.
        Idempotente: dedup Redis 1h por alarme pra não floodar Slack.
        """
        if settings.webhook_secret:
            _got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if _got != settings.webhook_secret:
                return JSONResponse({"erro": "unauthorized"}, status_code=401)
        try:
            from . import metricas_funcionamento as mf
            import os as _os
            redis_c = getattr(pipeline, "_redis", None) if pipeline else None
            snap = mf.funcionamento_hoje(redis_c)
            alarmes = snap.get("alarmes_ativos") or []
            if not alarmes:
                return JSONResponse({
                    "ok": True, "alarmes": [], "msg": "tudo dentro do target",
                })
            slack_url = _os.environ.get("SLACK_WEBHOOK_URL") or ""
            enviados = []
            for a in alarmes:
                # Dedup 1h por alarme — mesmo texto não floods
                dedup_k = f"blink:alarme_funcionamento:{hash(a) & 0xFFFFFFFF}"
                try:
                    if redis_c is not None and redis_c.get(dedup_k):
                        enviados.append({"alarme": a, "skipped": "dedup_1h"})
                        continue
                except Exception:  # noqa: BLE001
                    pass
                if slack_url:
                    try:
                        import httpx as _httpx
                        with _httpx.Client(timeout=8.0) as cli:
                            cli.post(slack_url, json={
                                "text": f":rotating_light: *Funcionamento Lia* {a}\n"
                                        f"Snapshot: {snap.get('contadores')}",
                            })
                        if redis_c is not None:
                            redis_c.setex(dedup_k, 3600, "1")
                        enviados.append({"alarme": a, "slack": "ok"})
                    except Exception as e:  # noqa: BLE001
                        enviados.append({"alarme": a, "slack_erro": str(e)[:120]})
                else:
                    enviados.append({"alarme": a, "slack": "SLACK_WEBHOOK_URL vazia"})
            return JSONResponse({
                "ok": True, "alarmes": alarmes, "enviados": enviados,
            })
        except Exception as e:  # noqa: BLE001
            log.exception("[admin/funcionamento/checar-alarmes] crash: %s", e)
            return JSONResponse(
                {"erro": "crash", "detalhe": str(e)[:200]}, status_code=500,
            )

    @app.get("/admin/leads-abandonados")
    def admin_leads_abandonados(
        request: Request,
        minutos: int = 30,
        max_leads: int = 50,
    ) -> JSONResponse:
        """Lista leads onde paciente mandou msg há >= `minutos` sem Lia responder.

        Critério (interseção):
        - status_id ∈ etapas ativas (não fechadas, não em handoff humano)
        - ATIVADO IA? = Ativado (field 1260817, enum 927031)
        - ÚLTIMA MENS LIA (1260860) < (timestamp_now - minutos*60)
          OU campo vazio + lead atualizado nos últimos `minutos*4` min

        Retorna detalhes pra ação humana imediata.
        """
        if settings.webhook_secret:
            _got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if _got != settings.webhook_secret:
                return JSONResponse({"erro": "unauthorized"}, status_code=401)
        # Bug fix (06/06/2026): kommo_client estava fora de escopo
        kommo_client = getattr(pipeline, "kommo", None)
        if kommo_client is None:
            return JSONResponse({"erro": "kommo_indisponivel"}, status_code=500)
        try:
            import time as _t
            limite_ts = int(_t.time()) - (minutos * 60)
            statuses_ativos = [
                96441724, 106919911, 102560495, 106184631,
                101507507, 101109455, 106653499, 106184983,
            ]
            abandonados: list[dict] = []
            for status_id in statuses_ativos:
                try:
                    # Bug fix: assinatura real é status_ids=[sid] + pipeline_id
                    leads = kommo_client.list_leads_by_status(
                        pipeline_id=8601819,
                        status_ids=[status_id],
                        limit=max_leads,
                    )
                except Exception:  # noqa: BLE001
                    continue
                for lead in leads:
                    lid = lead.get("id")
                    cfs = lead.get("custom_fields_values") or []
                    ativado_ia = None
                    ultima_lia_ts = None
                    for cf in cfs:
                        fid = cf.get("field_id")
                        vals = cf.get("values") or [{}]
                        v = vals[0].get("value") if vals else None
                        if fid == 1260817:
                            ativado_ia = v
                        elif fid == 1260860:
                            ultima_lia_ts = v
                    if ativado_ia != "Ativado":
                        continue
                    if ultima_lia_ts and isinstance(ultima_lia_ts, (int, float)):
                        if int(ultima_lia_ts) > limite_ts:
                            continue  # Lia respondeu dentro da janela, ok
                    abandonados.append({
                        "lead_id": lid,
                        "name": lead.get("name"),
                        "status_id": status_id,
                        "ultima_lia_ts": ultima_lia_ts,
                        "minutos_sem_resposta": (
                            int((_t.time() - ultima_lia_ts) / 60)
                            if ultima_lia_ts else None
                        ),
                        "url": f"https://univeja.kommo.com/leads/detail/{lid}",
                    })
                    if len(abandonados) >= max_leads:
                        break
                if len(abandonados) >= max_leads:
                    break
            # Ordena pelos mais antigos primeiro
            abandonados.sort(
                key=lambda x: x.get("minutos_sem_resposta") or 0, reverse=True,
            )
            return JSONResponse({
                "ok": True,
                "total": len(abandonados),
                "janela_min": minutos,
                "leads": abandonados,
            })
        except Exception as e:  # noqa: BLE001
            log.exception("[leads-abandonados] crash: %s", e)
            return JSONResponse(
                {"erro": "crash", "detalhe": str(e)[:200]}, status_code=500,
            )

    # ================================================================
    # DISPARO AUTOMÁTICO POR LEAD (task #212 — 04/06/2026)
    # ================================================================
    # ================================================================
    # ATIVAÇÃO INTELIGENTE — preview da saudação (Fábio 12/06/2026)
    # ================================================================
    # Dado um lead, retorna a saudação personalizada que a Lia DEVE usar
    # quando o paciente voltar. Demonstra que sabe quem é, recapitula
    # onde parou. Substitui triagem genérica em leads recorrentes.
    @app.get("/admin/ativacao-inteligente/{lead_id}")
    def admin_ativacao_inteligente_preview(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Preview da saudação personalizada pra um lead.

        Query params:
          - secret (obrigatório)

        Retorna:
          {
            "lead_id", "nome_lead",
            "tipo": "generica" | "personalizada" | "lacuna_longa",
            "saudacao": "<texto pronto>",
            "campos_usados": [...],
            "ancora_principal": "<dado citado mais forte>",
            "pergunta_aberta": "<pergunta única no fim>"
          }
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        try:
            lead = kommo_client.get_lead(lead_id) or {}
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"falha buscar lead {lead_id}: {exc}"},
                status_code=500,
            )

        # Normaliza custom_fields_values → custom_fields (formato esperado)
        cfs_raw = lead.get("custom_fields_values") or lead.get("custom_fields") or []
        lead_norm = {
            "id": lead.get("id"),
            "name": lead.get("name"),
            "updated_at": lead.get("updated_at"),
            "custom_fields": cfs_raw,
        }

        from voice_agent.ativacao_inteligente import (
            gerar_saudacao_personalizada,
        )
        resultado = gerar_saudacao_personalizada(lead_norm)
        resultado["lead_id"] = lead_id
        resultado["nome_lead"] = lead.get("name")
        return JSONResponse(resultado)

    # ================================================================
    # DEDUP MERGE POR TELEFONE (Bug C-27 — Fábio 12/06/2026)
    # ================================================================
    # Webhook Kommo cria lead novo a cada nova conversa por chat_id
    # não mapeado, mesmo quando já existe lead ativo do mesmo telefone.
    # Endpoint dado um lead, busca outros leads do mesmo telefone,
    # ordena por relevância (ativos primeiro), retorna pra atendente
    # decidir merge. Não merge automático — só lista candidatos
    # explicitamente, com sumário pra decisão informada.
    @app.get("/admin/dedup-merge-por-telefone/{lead_id}")
    def admin_dedup_merge_por_telefone(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Dado um lead, busca outros leads com mesmo telefone E retorna
        candidatos pra merge ranqueados.

        Query params:
          - secret (obrigatório)

        Retorna:
          {
            "lead_id": <ID consultado>,
            "telefone": "<telefone E.164>",
            "nome": "<nome do contato>",
            "status_atual": <status_id do lead consultado>,
            "candidatos_merge": [
              {"id", "nome", "status_id", "status_nome",
               "created_at", "updated_at", "is_ativo", "prioridade"},
              ...
            ],
            "sugestao": "merge_para_lead_X" | "nenhum_match" | "manter_separado",
            "racional": "<explicação>"
          }

        Status considerados ATIVOS (não merge se estão sendo trabalhados):
          0-ENTRADA (96441724), 0-a classificar (106919911),
          2.LEADS FRIO (101508307), 3-AGENDAR (102560495),
          4.REAGENDAR (106184631), 5-AGENDADO (101507507),
          6-CONFIRMAR (101109455), 7.CONFIRMADO (106653499),
          7.1-NO-SHOW (106184983).

        Status considerados FINALIZADOS (peso baixo na priorização):
          8-REALIZADO (91486864), Closed-won (142), Closed-lost (143),
          1-ATENDIMENTO HUMANO (106563343).
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        # 1. Pega telefone do lead consultado
        try:
            info = kommo_client.get_lead_main_contact(lead_id)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"falha buscar contato do lead {lead_id}: {exc}"},
                status_code=500,
            )

        telefone = (info or {}).get("telefone") or ""
        nome = (info or {}).get("nome") or ""
        status_atual = (info or {}).get("status_id")
        if not telefone:
            return JSONResponse({
                "ok": False, "lead_id": lead_id,
                "erro": "lead sem telefone — impossível buscar duplicatas",
            })

        # 2. Busca outros leads com mesmo telefone via /contacts→/leads
        try:
            resultados = kommo_client.get_leads_by_phone(
                telefone, pipeline_id=8601819,
            ) or []
        except Exception:  # noqa: BLE001
            resultados = []

        STATUS_ATIVOS = {
            96441724, 106919911, 101508307, 102560495, 106184631,
            101507507, 101109455, 106653499, 106184983,
        }
        STATUS_FINALIZADOS = {
            91486864, 142, 143, 106563343,
        }
        STATUS_NOMES = {
            96441724: "0-ETAPA ENTRADA",
            106919911: "0-a classificar",
            101508307: "2.LEADS FRIO",
            102560495: "3-AGENDAR",
            106184631: "4.REAGENDAR",
            101507507: "5-AGENDADO",
            101109455: "6-CONFIRMAR",
            106653499: "7.CONFIRMADO",
            106184983: "7.1-NO-SHOW",
            91486864: "8-REALIZADO",
            142: "Closed-won",
            143: "Closed-lost",
            106563343: "1-ATENDIMENTO HUMANO",
        }

        candidatos = []
        for r in resultados:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if not rid or int(rid) == int(lead_id):
                continue  # exclui o próprio
            r_status = r.get("status_id")
            r_ativo = r_status in STATUS_ATIVOS
            # Prioridade: ativos > finalizados; entre ativos, mais recente
            prio = 0
            if r_ativo:
                prio += 1000
            try:
                prio += int(str(r.get("updated_at") or "0").replace("-", "").replace(":", "").replace("T", "").replace("Z", "")[:14])
            except Exception:  # noqa: BLE001
                pass
            candidatos.append({
                "id": rid,
                "nome": r.get("name") or "",
                "status_id": r_status,
                "status_nome": STATUS_NOMES.get(r_status, f"id={r_status}"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "is_ativo": r_ativo,
                "prioridade": prio,
            })

        candidatos.sort(key=lambda x: x["prioridade"], reverse=True)

        # 3. Decide sugestão
        ativos = [c for c in candidatos if c["is_ativo"]]
        sugestao = "manter_separado"
        racional = "Sem leads ativos do mesmo telefone — manter este lead."
        if not candidatos:
            sugestao = "nenhum_match"
            racional = "Nenhum outro lead do mesmo telefone encontrado."
        elif len(ativos) == 1:
            outro = ativos[0]
            if outro["id"] != lead_id:
                sugestao = f"merge_para_lead_{outro['id']}"
                racional = (
                    f"Há 1 lead ativo do mesmo telefone (#{outro['id']} em "
                    f"{outro['status_nome']}). Merge SUGERIDO pra esse "
                    f"lead pra preservar histórico."
                )
        elif len(ativos) > 1:
            sugestao = "merge_para_ativo_mais_recente"
            racional = (
                f"Há {len(ativos)} leads ativos do mesmo telefone. "
                f"Mais recente: #{ativos[0]['id']} em {ativos[0]['status_nome']}. "
                f"Atendimento humano deve auditar e decidir."
            )

        return JSONResponse({
            "ok": True,
            "lead_id": lead_id,
            "telefone": telefone,
            "nome": nome,
            "status_atual": status_atual,
            "total_candidatos": len(candidatos),
            "candidatos_merge": candidatos[:10],
            "sugestao": sugestao,
            "racional": racional,
        })

    @app.post("/admin/disparar-lead/{lead_id}")
    @app.get("/admin/disparar-lead/{lead_id}")
    def admin_disparar_lead(lead_id: int, request: Request) -> JSONResponse:
        """Dispara renovação pra UM lead específico.

        Diferença vs /admin/renovacao-dispatch: NÃO exige telefone/nome
        na request — busca tudo via Kommo automaticamente. Pensado pra
        uso operacional direto (Cowork / Stephany) sem montar payload.

        Query params:
          - dry_run (true/false, default false — dispara real)
          - forcar (true/false, default true — ignora dedup Redis)

        Retorna:
          - {ok, lead_id, telefone, nome, status_id, dispatch_result}
          - ou {error, lead_id, ...} em falhas
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        import time as _t
        from voice_agent.renovacao_dispatcher import (
            SnapshotLead, dispatch_renovacao,
        )

        q = request.query_params

        def _bool(name, default=False):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        dry_run = _bool("dry_run", default=False)
        forcar = _bool("forcar", default=True)

        # Busca tudo via Kommo
        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível", "lead_id": lead_id},
                status_code=500,
            )

        info = kommo_client.get_lead_main_contact(lead_id)
        if not info or not info.get("telefone"):
            return JSONResponse({
                "error": "lead sem telefone OU contato não encontrado",
                "lead_id": lead_id,
                "info_recebida": info,
            }, status_code=400)

        telefone = info["telefone"]
        nome = info.get("nome") or f"Lead {lead_id}"
        status_id = info.get("status_id")

        # E.164: WhatsApp Cloud espera DDI 55 prefixo
        if not telefone.startswith("55") and len(telefone) >= 10:
            telefone = "55" + telefone

        snap = SnapshotLead(
            lead_id=lead_id,
            telefone_e164=telefone,
            nome_contato=nome,
            status_id=status_id,
            ultima_msg_paciente_ts=None,  # lead frio
            paciente_ja_respondeu_na_vida=False,
        )

        # Em dry_run, NÃO passa wa/redis/kommo (zero side-effect)
        wa = None if dry_run else wa_cloud
        redis_cli = None if dry_run else getattr(pipeline, "_redis", None)
        kommo_writer = None if dry_run else kommo_client

        res = dispatch_renovacao(
            snap,
            wa_client=wa,
            redis_client=redis_cli,
            kommo_note_writer=kommo_writer,
            agora=_t.time(),
            dry_run=dry_run,
            forcar_redispatch=forcar,
        )
        return JSONResponse({
            "ok": True,
            "lead_id": lead_id,
            "telefone": telefone,
            "nome": nome,
            "status_id": status_id,
            "dry_run": dry_run,
            "forcar": forcar,
            "dispatch_result": res.to_dict(),
        })

    # ================================================================
    # DISPARO EM BATCH (task #213 — Opção A — 04/06/2026)
    # ================================================================
    def _primeiro_nome_lead(nome: str) -> str:
        """Primeiro nome em Title Case pra variável {{1}} do template."""
        if not nome:
            return "Você"
        primeiro = nome.strip().split(" ")[0]
        return primeiro.title() if primeiro else "Você"

    def _disparar_template_aprovado_para_lead(
        lead_id: int,
        kommo_client,
        wa_cloud_client,
        dry_run: bool = False,
        template_override: Optional[str] = None,
        body_params_override: Optional[list] = None,
        categoria_lf: Optional[str] = None,
    ) -> dict:
        """Helper: dispara template aprovado direto pra cold lead.

        Bypass do dispatcher (que rejeita "paciente nunca falou").
        Pra REAGENDAR/REATIVAR leads frios, este é o caminho.

        Args:
          template_override: nome do template Meta (default = 1089...)
          body_params_override: lista de strings pras variáveis {{1}}, {{2}}...
                                Se None, usa [primeiro_nome] (1 variável).
          categoria_lf: letra A-H — se setada, resolve TemplateMeta + params
                        via templates_meta.resolver_template_lf() lendo dados
                        do lead. Vence default 1089. Vence override quando
                        ambos são passados? NÃO: override explícito vence.

        Sequência:
          1. Pega contato (telefone+nome+status_id) via Kommo
          2. (opcional) Resolve template LF por categoria
          3. Envia template aprovado via WhatsApp Cloud
          4. Grava nota Kommo com o texto + timestamp
          5. Marca dedup Redis (24h)

        Retorna {ok, telefone, nome, primeiro_nome, wamid, motivo}.
        """
        import time as _t
        info = kommo_client.get_lead_main_contact(lead_id)
        if not info or not info.get("telefone"):
            return {
                "ok": False, "motivo": "sem_telefone_ou_contato",
                "info_recebida": info,
            }
        telefone = info["telefone"]
        if not telefone.startswith("55") and len(telefone) >= 10:
            telefone = "55" + telefone
        nome = info.get("nome") or ""
        primeiro = _primeiro_nome_lead(nome)

        # Resolver template LF por categoria (vence default, perde pra override)
        template_lf_resolved_name = None
        template_lf_resolved_params = None
        if categoria_lf and not template_override:
            try:
                from voice_agent.templates_meta import resolver_template_lf
                # Buscar convênio do Kommo p/ categoria A (precisa do nome)
                convenio = None
                if categoria_lf.upper() == "A":
                    try:
                        full = kommo_client.get_lead(lead_id)
                        for cf in (full.get("custom_fields_values") or []):
                            if (cf.get("field_name") or "").upper() == "CONVÊNIO":
                                vals = cf.get("values") or []
                                if vals:
                                    convenio = vals[0].get("value")
                                break
                    except Exception:  # noqa: BLE001
                        pass
                resolved = resolver_template_lf(
                    categoria_lf,
                    nome_paciente=primeiro,
                    nome_contato=primeiro,
                    nome_convenio=convenio,
                )
                if resolved is None:
                    return {
                        "ok": False,
                        "motivo": f"categoria_lf={categoria_lf} sem dados "
                                  f"suficientes (ex: convênio vazio p/ A)",
                        "telefone": telefone, "primeiro_nome": primeiro,
                    }
                tpl_meta, params_resolved = resolved
                template_lf_resolved_name = tpl_meta.template_name
                template_lf_resolved_params = params_resolved
            except Exception as exc:  # noqa: BLE001
                log.warning("[DISPARAR-CAT-LF] resolver falhou lead=%s cat=%s: %s",
                            lead_id, categoria_lf, exc)

        template_name = (
            template_override
            or template_lf_resolved_name
            or settings.reactivation_template_name
            or "1089_mens_ativar_conv_parada_qz7kbz"
        )
        template_lang = getattr(settings, "reactivation_template_lang", "pt_BR")
        if body_params_override is not None:
            body_params = body_params_override
        elif template_lf_resolved_params is not None:
            body_params = template_lf_resolved_params
        elif "1020" in template_name:
            # Template 1020_retorno_mais_de_1_ano_v1 espera 3 vars:
            # {{1}}=nome contato, {{2}}=nome paciente, {{3}}=data anterior
            body_params = [primeiro, primeiro, "consulta anterior"]
        else:
            body_params = [primeiro]

        if dry_run:
            return {
                "ok": True, "dry_run": True,
                "telefone": telefone, "nome": nome,
                "primeiro_nome": primeiro,
                "template": template_name,
                "msg": "dry_run — não enviou nem gravou",
            }

        # Envio real
        try:
            resp = wa_cloud_client.send_template(
                to=telefone,
                name=template_name,
                language=template_lang,
                body_params=body_params,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "motivo": f"send_template falhou: {str(exc)[:120]}",
                "telefone": telefone, "primeiro_nome": primeiro,
            }

        wamid = None
        try:
            wamid = (resp.get("messages") or [{}])[0].get("id")
        except Exception:  # noqa: BLE001
            pass

        # Grava nota Kommo automática — Fábio 11/06 noite: atendente
        # precisa saber TEXTO da mensagem + PRÓXIMO PASSO claro.
        try:
            ts_br = _t.strftime("%d/%m/%Y %H:%M", _t.localtime())
            params_str = " | ".join(
                f"{{{{{i+1}}}}}={p}" for i, p in enumerate(body_params)
            )
            # Texto provável renderizado + próximo passo sugerido por template.
            # Buscar via Meta Graph seria ideal mas custa req extra por disparo.
            # Templates principais hardcoded — atualizar quando Fábio mudar.
            from voice_agent.template_texts import (
                renderizar_texto_template, proximo_passo_atendente,
            )
            texto_renderizado = renderizar_texto_template(
                template_name, body_params, primeiro,
            )
            proximo_passo = proximo_passo_atendente(template_name)
            nota = (
                f"📨 [Lia — disparo automático {ts_br}]\n\n"
                f"CANAL: WhatsApp Cloud 8133\n"
                f"TEMPLATE: {template_name}\n"
                f"PARÂMETROS: {params_str}\n"
                f"TELEFONE: {telefone}\n"
                f"wamid: {wamid or 'n/a'}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 MENSAGEM ENVIADA AO PACIENTE:\n\n"
                f"{texto_renderizado}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎯 PRÓXIMO PASSO PRA ATENDIMENTO HUMANO:\n\n"
                f"{proximo_passo}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Lia continua ativa (ATIVADO IA? = Ativado). Se paciente "
                f"responder, ela conduz conversa e grava agendamento "
                f"autônomo no Medware (task #208). Atendente entra apenas "
                f"se houver dúvida específica ou caso complexo."
            )
            kommo_client.add_note(lead_id=lead_id, text=nota)
        except Exception as exc:  # noqa: BLE001
            log.warning("[DISPARAR-BATCH] gravação nota falhou lead=%s: %s",
                        lead_id, exc)

        return {
            "ok": True,
            "telefone": telefone, "nome": nome,
            "primeiro_nome": primeiro,
            "template": template_name,
            "wamid": wamid,
        }

    # ================================================================
    # DISPARO DIRETO (task #243, 05/06/2026) — bypass total do Kommo
    # ================================================================
    # Quando agent→Kommo retorna 403 (Bug #240/C-10 IP banlist?), o caminho
    # `_disparar_template_aprovado_para_lead` falha em `get_lead_main_contact`
    # ANTES de chegar no Meta. Esse endpoint aceita telefone + nome direto
    # no body — não toca Kommo pra buscar contato. Só usa Meta Cloud API.
    @app.post("/admin/disparar-direto")
    async def admin_disparar_direto(request: Request) -> JSONResponse:
        """Dispara template Meta direto sem passar por Kommo lookup.

        Body JSON obrigatório:
            {
              "telefone": "5561999990000",       # E.164 SEM '+'
              "primeiro_nome": "Maria",          # vai em {{1}} se template tiver 1 var
              "template": "blink_lf_b_particular_v1",
              "body_params": ["Maria"]           # opcional; default = [primeiro_nome]
            }

        Opcional:
            "lead_id": 22789618                  # se setado, grava nota Kommo via MCP
            "language": "pt_BR"                  # default pt_BR
            "dry_run": false

        Retorna: { ok, wamid, telefone, template, status_meta, body_preview }.

        Não toca get_lead_main_contact — bypass do Bug #240/#240.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "JSON inválido"}, status_code=400)

        telefone = (body.get("telefone") or "").strip()
        primeiro = (body.get("primeiro_nome") or "").strip() or "você"
        template = (body.get("template") or "").strip()
        body_params = body.get("body_params")
        language = body.get("language") or "pt_BR"
        dry_run = bool(body.get("dry_run", False))
        lead_id = body.get("lead_id")

        # Validações mínimas
        digits = "".join(c for c in telefone if c.isdigit())
        if not digits or len(digits) < 10:
            return JSONResponse(
                {"error": "telefone inválido — precisa de E.164 com DDI+DDD"},
                status_code=400,
            )
        if not digits.startswith("55") and len(digits) in (10, 11):
            digits = "55" + digits
        if not template:
            return JSONResponse(
                {"error": "template é obrigatório"}, status_code=400,
            )
        if body_params is not None and not isinstance(body_params, list):
            return JSONResponse(
                {"error": "body_params deve ser lista"}, status_code=400,
            )
        if body_params is None:
            body_params = [primeiro]

        if dry_run:
            return JSONResponse({
                "ok": True, "dry_run": True,
                "telefone": digits, "primeiro_nome": primeiro,
                "template": template, "body_params": body_params,
                "msg": "dry_run — não enviou",
            })

        # Envio real via Meta Cloud (wa_cloud já está injetado no app)
        try:
            resp = wa_cloud.send_template(
                to=digits, name=template, language=language,
                body_params=body_params,
            )
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({
                "ok": False, "telefone": digits, "template": template,
                "motivo": f"send_template falhou: {str(exc)[:200]}",
            }, status_code=500)

        wamid = None
        try:
            wamid = (resp.get("messages") or [{}])[0].get("id")
        except Exception:  # noqa: BLE001
            pass

        # Se lead_id passado, grava nota Kommo via add_note (esse endpoint
        # tipicamente funciona mesmo quando outros 403, pois POST diferente)
        nota_id = None
        if lead_id:
            try:
                import time as _t
                ts_br = _t.strftime("%d/%m/%Y %H:%M", _t.localtime())
                params_str = " | ".join(
                    f"{{{{{i+1}}}}}={p}" for i, p in enumerate(body_params)
                )
                nota = (
                    f"[Disparo direto {ts_br}]\n\n"
                    f"Template: {template}\n"
                    f"Parâmetros: {params_str}\n"
                    f"Telefone: {digits}\n"
                    f"wamid: {wamid or 'n/a'}\n\n"
                    f"Enviado via /admin/disparar-direto "
                    f"(bypass de get_lead_main_contact). Bug #240/C-10."
                )
                kommo_client = getattr(pipeline, "kommo", None)
                if kommo_client:
                    nota_id = kommo_client.add_note(lead_id=int(lead_id), text=nota)
            except Exception as exc:  # noqa: BLE001
                log.warning("[DISPARAR-DIRETO] nota Kommo falhou lead=%s: %s",
                            lead_id, exc)

        return JSONResponse({
            "ok": True, "wamid": wamid, "telefone": digits,
            "template": template, "body_params": body_params,
            "lead_id": lead_id, "kommo_nota_id": nota_id,
        })

    @app.get("/admin/backfill-nota-disparo/{lead_id}")
    def admin_backfill_nota_disparo(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Adiciona nota Kommo enriquecida (TEXTO + PRÓXIMO PASSO) num lead
        que já recebeu disparo automático antes do fix de 11/06 noite.

        Não dispara nada — só grava nota retroativa com texto provável do
        template e próximo passo pro atendente humano.

        Query params:
          - template (str, obrigatório) — nome do template aprovado
          - primeiro (str, opcional, default 'Você') — nome do contato
          - secret (obrigatório)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        import time as _t
        from voice_agent.template_texts import (
            renderizar_texto_template, proximo_passo_atendente,
        )

        q = request.query_params
        template = q.get("template")
        primeiro = (q.get("primeiro") or "Você").strip() or "Você"
        if not template:
            return JSONResponse(
                {"error": "query param 'template' obrigatório"},
                status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        texto_renderizado = renderizar_texto_template(
            template, [primeiro], primeiro,
        )
        proximo = proximo_passo_atendente(template)
        ts_br = _t.strftime("%d/%m/%Y %H:%M", _t.localtime())
        nota = (
            f"📨 [Lia — back-fill nota disparo {ts_br}]\n\n"
            f"Disparo automático anterior NÃO incluía texto/próximo passo. "
            f"Esta nota é retroativa pra ajudar atendimento.\n\n"
            f"TEMPLATE USADO: {template}\n"
            f"PARÂMETRO {{1}}: {primeiro}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 MENSAGEM ENVIADA AO PACIENTE:\n\n"
            f"{texto_renderizado}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 PRÓXIMO PASSO PRA ATENDIMENTO HUMANO:\n\n"
            f"{proximo}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Lia ativa (ATIVADO IA? = Ativado). Se paciente responder, "
            f"Lia conduz. Atendente só intervém se travar."
        )
        try:
            kommo_client.add_note(lead_id=lead_id, text=nota)
            return JSONResponse({
                "ok": True, "lead_id": lead_id, "template": template,
                "primeiro": primeiro,
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("[BACKFILL-NOTA] falhou lead=%s: %s", lead_id, exc)
            return JSONResponse(
                {"ok": False, "lead_id": lead_id, "erro": str(exc)[:200]},
                status_code=500,
            )

    @app.api_route("/admin/wa-send-text/{lead_id}", methods=["GET", "POST"])
    async def admin_wa_send_text(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Envia texto livre via WhatsApp Cloud 8133 (sessão 24h ativa).

        Pra resgate de mensagens com erro de envio do Kommo onde a sessão de
        24h ainda está aberta (paciente respondeu nas últimas 24h).

        Body JSON ou query params:
          - text (str, obrigatório) — texto livre da mensagem
          - secret (obrigatório)
          - kommo_note (bool, default true) — grava nota Kommo confirmando

        Retorna {ok, lead_id, telefone, primeiro_nome, wamid, nota_kommo_id}.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        text = request.query_params.get("text")
        kommo_note_flag = (
            request.query_params.get("kommo_note", "1").lower()
            in ("1", "true", "yes")
        )

        if request.method == "POST":
            try:
                body = await request.json()
                if not text:
                    text = body.get("text")
                if "kommo_note" in body:
                    kommo_note_flag = bool(body.get("kommo_note"))
            except Exception:  # noqa: BLE001
                pass

        if not text:
            return JSONResponse(
                {"error": "param 'text' obrigatório"}, status_code=400,
            )

        if not wa_cloud:
            return JSONResponse(
                {"error": "wa_cloud indisponível"}, status_code=500,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        try:
            info = kommo_client.get_lead_main_contact(lead_id)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": f"get_lead_main_contact falhou: {str(e)[:200]}"},
                status_code=500,
            )

        telefone = (info or {}).get("telefone") or ""
        nome = (info or {}).get("nome") or ""
        primeiro_nome = nome.split()[0] if nome else ""

        if not telefone:
            return JSONResponse(
                {
                    "error": "lead sem telefone",
                    "info_recebida": info,
                },
                status_code=400,
            )

        digits = "".join(ch for ch in telefone if ch.isdigit())
        if not digits.startswith("55"):
            digits = "55" + digits

        try:
            resp = wa_cloud.send_text(digits, text)
        except Exception as e:  # noqa: BLE001
            log.warning("[WA-SEND-TEXT] falhou lead=%s: %s", lead_id, e)
            return JSONResponse(
                {
                    "ok": False,
                    "lead_id": lead_id,
                    "telefone": digits,
                    "erro": str(e)[:300],
                },
                status_code=500,
            )

        wamid = None
        try:
            wamid = (
                ((resp or {}).get("messages") or [{}])[0].get("id")
            )
        except Exception:  # noqa: BLE001
            pass

        nota_kommo_id = None
        if kommo_note_flag:
            try:
                from datetime import datetime as _dt
                from datetime import timezone as _tz, timedelta as _td
                brt = _tz(_td(hours=-3))
                ts = _dt.now(brt).strftime("%d/%m/%Y %H:%M BRT")
                preview = text[:400]
                if len(text) > 400:
                    preview = preview + "..."
                nota_txt = (
                    f"[Lia · Resgate WhatsApp 8133] · {ts}\n"
                    f"Canal: WhatsApp Cloud 8133 (texto livre na sessão 24h)\n"
                    f"Para: {nome or '(sem nome)'} · {digits}\n\n"
                    f"📝 MENSAGEM ENVIADA:\n{preview}\n\n"
                    f"wamid: {wamid or '(n/a)'}"
                )
                nota = kommo_client.add_note(lead_id, nota_txt)
                if isinstance(nota, dict):
                    nota_kommo_id = nota.get("id")
            except Exception as e:  # noqa: BLE001
                log.warning("[WA-SEND-TEXT] add_note falhou: %s", e)

        return JSONResponse({
            "ok": True,
            "lead_id": lead_id,
            "telefone": digits,
            "primeiro_nome": primeiro_nome,
            "wamid": wamid,
            "nota_kommo_id": nota_kommo_id,
        })

    @app.get("/admin/disparar-template-get/{lead_id}")
    def admin_disparar_template_get(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Variante GET de /admin/disparar-template — aceita query params:

          - template (str, obrigatório) — nome do template aprovado Meta
          - body_params (str, opcional) — CSV separado por '|' (pipe)
            ex: body_params=Cecilia|Cecilia|consulta%20anterior
          - dry_run (bool, default false)
          - secret (obrigatório)

        Pensado pra disparo autônomo via web_fetch (que só faz GET).
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        q = request.query_params
        template = q.get("template")
        body_params_raw = q.get("body_params")
        dry_run = (q.get("dry_run") or "").lower() in ("1", "true", "yes")

        if not template:
            return JSONResponse(
                {"error": "query param 'template' obrigatório"},
                status_code=400,
            )

        body_params = None
        if body_params_raw:
            body_params = [p.strip() for p in body_params_raw.split("|") if p.strip()]

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        res = _disparar_template_aprovado_para_lead(
            lead_id, kommo_client, wa_cloud, dry_run=dry_run,
            template_override=template,
            body_params_override=body_params,
        )
        res["lead_id"] = lead_id
        return JSONResponse(res)

    @app.post("/admin/disparar-template/{lead_id}")
    async def admin_disparar_template_custom(
        lead_id: int, request: Request,
    ) -> JSONResponse:
        """Dispara TEMPLATE CUSTOM com body_params dinâmicos pra 1 lead.

        Body JSON:
          {
            "template": "captar_paciente",
            "body_params": ["Maria", "Águas Claras", "Dra. Karla Delalibera", "09/06", "09:00"],
            "dry_run": false
          }

        Diferença vs /admin/disparar-lead/{lead_id}:
          - Aceita template_name custom (default = 1089...)
          - Aceita lista de body_params custom (default = [primeiro_nome])
          - Pensado pra templates específicos com múltiplas variáveis

        Retorna {ok, lead_id, telefone, primeiro_nome, template, wamid}.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "JSON body inválido"}, status_code=400,
            )

        template = body.get("template")
        body_params = body.get("body_params")
        dry_run = bool(body.get("dry_run", False))

        if not template:
            return JSONResponse(
                {"error": "body precisa de 'template'"}, status_code=400,
            )
        if body_params is not None and not isinstance(body_params, list):
            return JSONResponse(
                {"error": "'body_params' deve ser lista"}, status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        res = _disparar_template_aprovado_para_lead(
            lead_id, kommo_client, wa_cloud, dry_run=dry_run,
            template_override=template,
            body_params_override=body_params,
        )
        res["lead_id"] = lead_id
        return JSONResponse(res)

    @app.post("/admin/disparar-batch")
    async def admin_disparar_batch(request: Request) -> JSONResponse:
        """Dispara TEMPLATE APROVADO pra N leads de uma vez.

        Body JSON:
          {
            "lead_ids": [22982854, 21710873, ...],
            "dry_run": false (default false)
          }

        Usa template aprovado direto (bypass dispatcher de renovação) —
        pensado pra COLD leads (REAGENDAR/REATIVAR) que nunca responderam.

        Pra cada lead:
          1. Pega contato via Kommo
          2. Envia template aprovado via WhatsApp Cloud 8133
          3. Grava nota Kommo automática
          4. Marca ATIVADO IA? = Ativado

        Retorna:
          {
            "total": N,
            "ok": M,
            "falhas": K,
            "detalhes": [{lead_id, ok, telefone, wamid, motivo}, ...]
          }
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "JSON body inválido"}, status_code=400,
            )

        lead_ids = body.get("lead_ids") or []
        if not isinstance(lead_ids, list) or not lead_ids:
            return JSONResponse(
                {"error": "lead_ids deve ser lista não-vazia"},
                status_code=400,
            )
        dry_run = bool(body.get("dry_run", False))

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        ok_count = 0
        falhas_count = 0
        detalhes = []

        for raw_id in lead_ids:
            try:
                lead_id = int(raw_id)
            except (ValueError, TypeError):
                falhas_count += 1
                detalhes.append({
                    "lead_id": raw_id, "ok": False,
                    "motivo": "lead_id_invalido",
                })
                continue

            res = _disparar_template_aprovado_para_lead(
                lead_id, kommo_client, wa_cloud, dry_run=dry_run,
            )
            res["lead_id"] = lead_id
            if res.get("ok"):
                ok_count += 1
            else:
                falhas_count += 1
            detalhes.append(res)

        return JSONResponse({
            "total": len(lead_ids),
            "ok": ok_count,
            "falhas": falhas_count,
            "dry_run": dry_run,
            "detalhes": detalhes,
        })

    # ================================================================
    # DISPARO FRIO DIRETO (task #309 — Fábio 11/06/2026)
    # ================================================================
    # Caso urgente: "estamos sem leads pra atendimento". Endpoint
    # `/admin/disparar-categoria` retorna 0 porque (a) renomear leads
    # (#227) tirou prefixo [R]/[E]/[C] do nome, (b) dedup Redis 24h
    # ainda vigente. Este endpoint:
    #   1. Lista leads em 2.LEADS FRIO (sem filtrar por keywords no nome)
    #   2. Exclui SÓ leads cujo nome menciona convênio bloqueado
    #   3. Dispara template aprovado (default 1020_retorno_mais_de_1_ano_v1)
    #   4. Dedup Redis 24h per-lead (chave própria — bypassa disparar-categoria)
    @app.post("/admin/disparar-leads-frio-direto")
    @app.get("/admin/disparar-leads-frio-direto")
    def admin_disparar_leads_frio_direto(request: Request) -> JSONResponse:
        """Dispara template aprovado pra leads em 2.LEADS FRIO sem filtro
        de prefixo no nome.

        Query params:
          - max (default 30, max 100)
          - template (default 1020_retorno_mais_de_1_ano_v1)
          - dry_run (true/false, default false)
          - skip_dedup (true/false, default false — pula dedup Redis)
          - status_id (default 101508307 = 2.LEADS FRIO)
          - secret (obrigatório se WEBHOOK_SECRET setado)

        body_params do template 1020:
          {{1}} = primeiro_nome_contato
          {{2}} = primeiro_nome_paciente (=mesmo)
          {{3}} = "data anterior" (fallback — não há data precisa no Kommo)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        import time as _t

        q = request.query_params
        try:
            max_leads = min(int(q.get("max") or "30"), 100)
        except ValueError:
            max_leads = 30
        try:
            status_id = int(q.get("status_id") or "101508307")
        except ValueError:
            status_id = 101508307
        template_name = (q.get("template") or "1020_retorno_mais_de_1_ano_v1").strip()
        dry_run = (q.get("dry_run") or "").lower() in ("1", "true", "yes")
        skip_dedup = (q.get("skip_dedup") or "").lower() in ("1", "true", "yes")

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        # Convênios bloqueados — exclusão por keyword no nome do lead
        excluir_keywords = [
            "INAS", "GDF", "CASSI", "SULAMERICA", "SUL AMERICA",
            "BRADESCO", "UNIMED",
        ]

        try:
            leads = kommo_client.list_stale_leads(
                pipeline_id=8601819, limit=max_leads * 5,
            ) or []
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"falha buscando leads: {exc}"}, status_code=500,
            )

        # Filtra apenas leads no status alvo (list_stale_leads pode
        # devolver de vários status do pipeline)
        leads = [
            l for l in leads
            if isinstance(l, dict) and l.get("status_id") == status_id
        ]

        # Dedup Redis 24h — chave própria pra não conflitar com /disparar-categoria
        _r = getattr(pipeline, "_redis", None)

        candidatos = []
        descartados = {"excluido_convenio": 0, "dedup_24h": 0}
        for lead in leads:
            if len(candidatos) >= max_leads:
                break
            nome_lead = (lead.get("name") or "").upper()
            if any(ex in nome_lead for ex in excluir_keywords):
                descartados["excluido_convenio"] += 1
                continue
            lead_id = lead.get("id")
            if not lead_id:
                continue
            if not skip_dedup and _r is not None:
                key = f"blink:disparo_frio_direto:{lead_id}"
                try:
                    if _r.get(key):
                        descartados["dedup_24h"] += 1
                        continue
                except Exception:  # noqa: BLE001
                    pass
            candidatos.append(int(lead_id))

        if not candidatos:
            return JSONResponse({
                "ok": True, "total": 0,
                "msg": "Nenhum lead casou os filtros",
                "encontrados": len(leads),
                "descartados": descartados,
                "filtros": {"status_id": status_id, "max": max_leads},
            })

        ok_count = 0
        falhas_count = 0
        detalhes = []
        # Helper detecta template 1020 internamente e monta 3 body_params
        # automaticamente. Não precisamos fazer lookup extra aqui.
        for lead_id in candidatos:
            res = _disparar_template_aprovado_para_lead(
                lead_id, kommo_client, wa_cloud,
                dry_run=dry_run,
                template_override=template_name,
            )
            if not dry_run and res.get("ok") and _r is not None:
                try:
                    _r.setex(
                        f"blink:disparo_frio_direto:{lead_id}",
                        24 * 60 * 60, "1",
                    )
                except Exception:  # noqa: BLE001
                    pass
            res["lead_id"] = lead_id
            if res.get("ok"):
                ok_count += 1
            else:
                falhas_count += 1
            detalhes.append(res)

        return JSONResponse({
            "ok": True,
            "template": template_name,
            "status_id": status_id,
            "encontrados": len(leads),
            "candidatos": len(candidatos),
            "disparados_ok": ok_count,
            "falhas": falhas_count,
            "descartados": descartados,
            "dry_run": dry_run,
            "detalhes": detalhes,
        })

    # ================================================================
    # DISPARO POR CATEGORIA (task #214 — Opção C — 04/06/2026)
    # ================================================================
    @app.post("/admin/disparar-categoria")
    @app.get("/admin/disparar-categoria")
    def admin_disparar_categoria(request: Request) -> JSONResponse:
        """Filtra leads por categoria + médico + unidade e dispara em batch.

        Categorias suportadas:
          - R: Reagendar/Remarcação (nome contém REAGENDAR / REMARCAÇÃO / FALTOU / DESMARCOU)
          - E: Com convênio aceito (CONVÊNIO ≠ Não se aplica, ≠ Inas)
          - C: Particular (CONVÊNIO = Não se aplica)
          - X: Excluir (Inas GDF ou Ñ ACEITO CONVÊNIO preenchido)

        Query params:
          - categoria (R/E/C — obrigatório)
          - unidade (Asa Norte / Águas Claras — opcional)
          - medico (Karla / Fabricio — opcional)
          - max (default 30, max 200)
          - dry_run (true/false, default false)
          - secret (obrigatório se WEBHOOK_SECRET setado)

        Configurar no Easypanel pra rodar semanal segunda 9h:
          curl POST /admin/disparar-categoria?categoria=R&unidade=Asa%20Norte&max=10&secret=$WS
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        import time as _t
        from voice_agent.renovacao_dispatcher import (
            SnapshotLead, dispatch_renovacao,
        )

        q = request.query_params
        categoria = (q.get("categoria") or "").upper()
        unidade_filtro = (q.get("unidade") or "").lower()
        medico_filtro = (q.get("medico") or "").lower()
        # NOVO: template_lf=A..H roteia pra template específico aprovado
        template_lf = (q.get("template_lf") or "").upper().strip() or None
        try:
            max_leads = min(int(q.get("max") or "30"), 200)
        except ValueError:
            max_leads = 30
        dry_run = (q.get("dry_run") or "").lower() in ("1", "true", "yes")

        if categoria not in ("R", "E", "C"):
            return JSONResponse(
                {"error": "categoria deve ser R, E ou C"}, status_code=400,
            )
        if template_lf and template_lf not in {"A","B","C","D","E","F","G","H"}:
            return JSONResponse(
                {"error": "template_lf deve ser uma letra A-H"},
                status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        # Heurística por categoria — palavras-chave no nome do lead
        keywords_por_categoria = {
            "R": ["REAGENDAR", "REMARCAÇÃO", "REMARCACAO", "FALTOU", "DESMARCOU", "DESMARCAÇÃO", "DESMARCACAO"],
            "E": ["COM CONVÊNIO", "COM CONVENIO"],
            "C": ["SEM CONVÊNIO", "SEM CONVENIO", "PARTICULAR"],
        }
        excluir_keywords = ["INAS", "GDF", "CASSI", "SULAMERICA", "BRADESCO"]

        # Busca via list_stale_leads (já existe em kommo client) ou similar
        leads = []
        try:
            if hasattr(kommo_client, "list_stale_leads"):
                leads = kommo_client.list_stale_leads(
                    pipeline_id=8601819, limit=max_leads * 3,  # busca 3x pra filtrar
                ) or []
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"falha buscando leads: {exc}"}, status_code=500,
            )

        kw_cat = keywords_por_categoria[categoria]

        candidatos = []
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            if len(candidatos) >= max_leads:
                break

            nome_lead = (lead.get("name") or "").upper()

            # Exclusão por convênio não aceito
            if any(ex in nome_lead for ex in excluir_keywords):
                continue
            # Match categoria
            if not any(kw in nome_lead for kw in kw_cat):
                continue
            # Filtro unidade (opcional, no nome ou via custom_field — heurística no nome)
            if unidade_filtro and unidade_filtro not in nome_lead.lower():
                # se filtro unidade ativo mas não consegue confirmar pelo nome,
                # incluímos mesmo assim (custom_field UNIDADE não é trivial sem fetch)
                pass
            # Filtro médico (heurística)
            if medico_filtro and medico_filtro not in nome_lead.lower():
                pass

            lead_id = lead.get("id")
            if lead_id:
                candidatos.append(int(lead_id))

        if not candidatos:
            return JSONResponse({
                "ok": True, "categoria": categoria, "total": 0,
                "msg": "Nenhum lead casou os filtros",
                "filtros": {"unidade": unidade_filtro, "medico": medico_filtro,
                            "max": max_leads},
            })

        # Dispara em batch — usa template aprovado direto (bypass dispatcher)
        ok_count = 0
        detalhes = []
        for lead_id in candidatos:
            res = _disparar_template_aprovado_para_lead(
                lead_id, kommo_client, wa_cloud, dry_run=dry_run,
                categoria_lf=template_lf,
            )
            res["lead_id"] = lead_id
            if res.get("ok"):
                ok_count += 1
            detalhes.append(res)

        return JSONResponse({
            "ok": True,
            "categoria": categoria,
            "template_lf": template_lf,
            "filtros": {"unidade": unidade_filtro, "medico": medico_filtro,
                        "max": max_leads},
            "candidatos_encontrados": len(candidatos),
            "disparados_ok": ok_count,
            "dry_run": dry_run,
            "detalhes": detalhes,
        })

    # ================================================================
    # RENOMEAR LEADS FRIO (task #227 — 04/06/2026)
    # ================================================================
    @app.post("/admin/renomear-leads-frio")
    @app.get("/admin/renomear-leads-frio")
    def admin_renomear_leads_frio(request: Request) -> JSONResponse:
        """Renomeia leads em 2.LEADS FRIO pra padrão [CAT] <nome_limpo>.

        Query params:
          - dry_run (true/false, default true)
          - max_leads (default 500, max 800)
          - status_id (default 101508307 = 2.LEADS FRIO)
          - skip_padronizado (true/false, default true)

        Categorias: R/E/V/C/A/X — heurística pelo nome atual.

        Retorna sumário com contadores por categoria + amostra de 20 leads
        do preview (sempre, mesmo em dry_run).
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.renomear_leads import renomear_batch

        q = request.query_params

        def _bool(name, default):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        try:
            max_leads = min(int(q.get("max_leads") or "500"), 800)
        except ValueError:
            max_leads = 500
        try:
            status_id = int(q.get("status_id") or "101508307")
        except ValueError:
            status_id = 101508307
        dry_run = _bool("dry_run", True)
        skip_padronizado = _bool("skip_padronizado", True)

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        resultado = renomear_batch(
            kommo_client,
            pipeline_id=8601819,
            status_id=status_id,
            max_leads=max_leads,
            dry_run=dry_run,
            skip_ja_padronizado=skip_padronizado,
        )
        return JSONResponse(resultado)

    # ================================================================
    # DEDUPLICAR LEADS FRIO POR TELEFONE (task #228 — 05/06/2026)
    # Origem: Fábio — lead Lene 22398836 (96121-411) tem 7+ duplicados.
    # Master = mais notas + mais campos + mais recente.
    # Duplicados: rename [DUP→X] + nota + move pra Closed-lost (143).
    # Reversível. NÃO deleta.
    # ================================================================
    @app.post("/admin/deduplicar-leads-frio")
    @app.get("/admin/deduplicar-leads-frio")
    def admin_deduplicar_leads_frio(request: Request) -> JSONResponse:
        """Agrupa leads de 2.LEADS FRIO por telefone e marca duplicados.

        Query params:
          - dry_run (true/false, default true)
          - max_leads (default 500, max 800)
          - status_id (default 101508307 = 2.LEADS FRIO)
          - status_destino (default 143 = Closed-lost)

        Retorno: contadores + amostra de até 30 grupos detectados.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.deduplicar_leads import deduplicar_batch

        q = request.query_params

        def _bool(name, default):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        try:
            max_leads = min(int(q.get("max_leads") or "500"), 800)
        except ValueError:
            max_leads = 500
        try:
            status_id = int(q.get("status_id") or "101508307")
        except ValueError:
            status_id = 101508307
        try:
            status_destino = int(q.get("status_destino") or "143")
        except ValueError:
            status_destino = 143
        dry_run = _bool("dry_run", True)

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        resultado = deduplicar_batch(
            kommo_client,
            pipeline_id=8601819,
            status_id=status_id,
            status_destino_duplicado=status_destino,
            max_leads=max_leads,
            dry_run=dry_run,
        )
        return JSONResponse(resultado)

    # ================================================================
    # DEDUP ASSÍNCRONO COM BARRA DE PROGRESSO (task #229 — 05/06/2026)
    # Fábio pediu pra rodar em background + poder fazer outras coisas.
    # ================================================================
    @app.post("/admin/dedup-async-start")
    @app.get("/admin/dedup-async-start")
    def admin_dedup_async_start(request: Request) -> JSONResponse:
        """Dispara dedup em background. Retorna job_id pra polling.

        Query params:
          - dry_run (default true)
          - max_leads (default 500, max 1000)
          - status_ids (CSV de etapas; default = STATUS_IDS_DEDUP_SEGUROS)
          - status_destino (default 143)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.dedup_job import iniciar_job
        from voice_agent.deduplicar_leads import STATUS_IDS_DEDUP_SEGUROS

        q = request.query_params

        def _bool(name, default):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        try:
            max_leads = min(int(q.get("max_leads") or "500"), 1000)
        except ValueError:
            max_leads = 500
        try:
            status_destino = int(q.get("status_destino") or "143")
        except ValueError:
            status_destino = 143

        sids_raw = (q.get("status_ids") or "").strip()
        if sids_raw:
            try:
                sids = [
                    int(x) for x in sids_raw.split(",")
                    if x.strip().isdigit()
                ]
            except ValueError:
                sids = list(STATUS_IDS_DEDUP_SEGUROS)
        else:
            sids = list(STATUS_IDS_DEDUP_SEGUROS)

        dry_run = _bool("dry_run", True)
        kommo_client = getattr(pipeline, "kommo", None)
        redis_cli = getattr(pipeline, "_redis", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )
        if redis_cli is None:
            return JSONResponse(
                {"error": "redis indisponível — sem como rastrear job"},
                status_code=500,
            )

        job_id = iniciar_job(
            redis_cli, kommo_client,
            pipeline_id=8601819,
            status_ids=sids,
            status_destino=status_destino,
            max_leads=max_leads,
            dry_run=dry_run,
        )
        return JSONResponse({
            "ok": True,
            "job_id": job_id,
            "status_url": f"/admin/dedup-async-status?job_id={job_id}",
            "params": {
                "status_ids": sids, "max_leads": max_leads,
                "dry_run": dry_run, "status_destino": status_destino,
            },
        })

    @app.get("/admin/dedup-async-status")
    def admin_dedup_async_status(request: Request) -> JSONResponse:
        """Devolve estado atual do job. Usado pelo artifact via polling.

        Query params:
          - job_id (obrigatório)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.dedup_job import get_status, calcular_eta
        job_id = (request.query_params.get("job_id") or "").strip()
        if not job_id:
            return JSONResponse({"error": "job_id obrigatório"}, status_code=400)

        redis_cli = getattr(pipeline, "_redis", None)
        if redis_cli is None:
            return JSONResponse(
                {"error": "redis indisponível"}, status_code=500,
            )

        estado = get_status(redis_cli, job_id)
        if not estado:
            return JSONResponse(
                {"error": "job_id não encontrado ou expirou"}, status_code=404,
            )

        # adiciona ETA
        estado["eta_segundos"] = calcular_eta(estado)
        if estado.get("iniciado_em"):
            estado["decorrido_segundos"] = max(
                0,
                int(__import__("time").time()) - int(estado["iniciado_em"]),
            )
        return JSONResponse(estado)

    # ================================================================
    # LISTAR TEMPLATES META (task #221 — 04/06/2026)
    # Pra debugar nome exato + status dos templates aprovados
    # ================================================================
    @app.get("/admin/listar-templates-meta")
    def admin_listar_templates_meta(request: Request) -> JSONResponse:
        """Lista todos os templates da WABA com nome/status/categoria.

        Usa wa_cloud.list_templates() que chama Meta Graph API.
        Útil pra descobrir nome EXATO de templates aprovados quando
        send_template retorna 132001 (template não existe).

        Query params opcionais:
          - filtro (str): substring case-insensitive no nome
          - status (str): APPROVED, PENDING, REJECTED, PAUSED
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        if not wa_cloud:
            return JSONResponse(
                {"error": "wa_cloud indisponível"}, status_code=500,
            )

        try:
            templates = wa_cloud.list_templates()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"error": f"list_templates falhou: {exc}"},
                status_code=500,
            )

        q = request.query_params
        filtro = (q.get("filtro") or "").lower()
        status_filtro = (q.get("status") or "").upper()

        if filtro:
            templates = [
                t for t in templates
                if filtro in (t.get("name") or "").lower()
            ]
        if status_filtro:
            templates = [
                t for t in templates
                if (t.get("status") or "").upper() == status_filtro
            ]

        return JSONResponse({
            "ok": True,
            "total": len(templates),
            "templates": templates,
        })

    # ================================================================
    # WEBHOOK KOMMO TRIGGER (task #219 — 04/06/2026)
    # ================================================================
    # ================================================================
    # WEBHOOK Kommo Automation — carimba ULTIMA MENS HUMANO (task #232)
    # Dispara quando usuário humano envia mensagem ao lead. Atualiza o
    # campo date_time 1260862 (ULTIMA MENS HUMANO) com o timestamp atual.
    # ================================================================
    @app.post("/admin/smoke-deploy")
    @app.get("/admin/smoke-deploy")
    def admin_smoke_deploy(request: Request) -> JSONResponse:
        """FIX DEFINITIVO (task #265) — bate em todas as rotas /admin/* GET e
        reporta 500. Cron pós-deploy roda isso e alerta Slack se algo crashou.

        Endpoint NÃO exige secret (read-only, lê estrutura, não dados).
        """
        from fastapi.testclient import TestClient
        client = TestClient(app)
        results = []
        for r in app.routes:
            path = getattr(r, "path", "") or ""
            if not path.startswith("/admin/"):
                continue
            if "{" in path:  # path params — skip
                continue
            methods = getattr(r, "methods", None) or {"GET"}
            if "GET" not in methods:
                continue
            try:
                resp = client.get(path)
                results.append({
                    "path": path, "status": resp.status_code,
                    "crash": resp.status_code == 500,
                })
            except Exception as e:  # noqa: BLE001
                results.append({
                    "path": path, "exception": str(e)[:150], "crash": True,
                })
        crashes = [r for r in results if r.get("crash")]
        return JSONResponse({
            "ok": len(crashes) == 0,
            "total_endpoints": len(results),
            "crashes": crashes,
            "details": results,
        })

    @app.post("/admin/kommo-trigger-msg-humano")
    @app.get("/admin/kommo-trigger-msg-humano")
    async def admin_kommo_trigger_msg_humano(request: Request) -> JSONResponse:
        """Webhook Kommo Automation pra carimbar 'ULTIMA MENS HUMANO'.

        Aceita JSON {lead_id: N} ou form-urlencoded
        leads[update][0][id]=N (formato nativo Kommo Automation).

        Auth: SECRET OPCIONAL — esse endpoint só atualiza 1 timestamp,
        operação não-destrutiva. Se WEBHOOK_SECRET configurado, aceita
        secret. Sem secret também aceita (pra simplificar config do
        webhook Kommo Automation que não suporta headers customizados).
        Filtro de segurança: lead_id deve ser inteiro positivo válido.
        """
        # Secret é opcional aqui
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            # Aceita se secret correto OU se ausente (Kommo Automation)
            if got and got != settings.webhook_secret:
                raise HTTPException(401, "Secret inválido")

        # Extrai lead_id (JSON OU form) — Bug C-13 (05/06/2026):
        # Kommo Automation no evento `add_outgoing_message` envia o lead_id
        # em `message[add][0][element_id]`, NÃO em `leads[update]`. Sem
        # esse parser, todo webhook de mensagem humana retornava 400 e o
        # campo ULTIMA MENS HUMANO ficava vazio.
        lead_id = None
        try:
            ct = (request.headers.get("content-type") or "").lower()
            if "json" in ct:
                body = await request.json()
                lead_id = body.get("lead_id") or body.get("id")
            else:
                form = await request.form()
                # Formato Kommo "leads[update]" (status, custom_fields)
                lead_id = (
                    form.get("leads[update][0][id]")
                    or form.get("leads[add][0][id]")
                    # Formato Kommo "message[add]" — add_outgoing_message
                    # element_id = id do lead, element_type=2 = lead
                    or form.get("message[add][0][element_id]")
                    or form.get("lead_id") or form.get("id")
                )
        except Exception:  # noqa: BLE001
            pass
        if not lead_id:
            lead_id = request.query_params.get("lead_id")
        try:
            lead_id_int = int(lead_id) if lead_id else 0
        except (ValueError, TypeError):
            lead_id_int = 0
        if lead_id_int <= 0:
            return JSONResponse(
                {"error": "lead_id obrigatório"}, status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )
        ts_now = int(time.time())
        try:
            ok = kommo_client.update_lead_fields(
                lead_id_int, {"ts_ultima_msg_humano": ts_now},
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": f"update falhou: {e}"}, status_code=500,
            )

        # OBSERVABILIDADE (task #264, 06/06/2026) — busca texto da última msg
        # outbound (humano) e grava como nota. Antes, webhook só carimbava
        # timestamp, deixando equipe humana cega sobre o que foi falado.
        # Caso real: lead 21860523 (Adriana catarata) — ULTIMA MENS HUMANO
        # 05/06 19:46 mas nenhuma nota com o texto.
        msg_texto = None
        try:
            msgs = kommo_client.get_lead_messages(lead_id_int, limit=20)
            # Filtra outgoing chat messages + criados nos últimos 5min (deve
            # ser a mensagem que disparou este webhook)
            recentes_outgoing = [
                m for m in msgs
                if (m.get("note_type") or "").lower().startswith("outgoing")
                and m.get("text")
            ]
            if recentes_outgoing:
                # Ordena por created_at desc se vier
                recentes_outgoing.sort(
                    key=lambda m: m.get("created_at") or 0, reverse=True,
                )
                msg_texto = recentes_outgoing[0].get("text") or ""
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[trigger-msg-humano] get_lead_messages falhou lead=%s: %s",
                lead_id_int, e,
            )
        nota_id = None
        if msg_texto:
            try:
                from datetime import datetime, timedelta, timezone
                brt = datetime.now(timezone(timedelta(hours=-3)))
                stamp = brt.strftime("%H:%M %d/%m")
                # Trunca pra 500 chars pra não estourar Kommo
                txt_trunc = msg_texto[:500]
                if len(msg_texto) > 500:
                    txt_trunc += "..."
                nota_texto = (
                    f"[ATENDENTE {stamp}] {txt_trunc}"
                )
                nota_id = kommo_client.add_note(lead_id_int, nota_texto)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[trigger-msg-humano] add_note falhou lead=%s: %s",
                    lead_id_int, e,
                )
        return JSONResponse({
            "ok": bool(ok), "lead_id": lead_id_int,
            "ts_ultima_msg_humano": ts_now,
            "texto_capturado": bool(msg_texto),
            "nota_gravada_id": nota_id,
        })

    # ================================================================
    # WEBHOOK Kommo — reativa IA quando humano move lead pra etapa ativa
    # (task #233, 05/06/2026). Sugestão Fábio: humano move pra
    # AGENDAR/FRIO/AGENDADO → IA volta automaticamente.
    # ================================================================
    # Etapas onde IA deve estar SEMPRE ativa.
    # Revisado 11/06/2026 (Fábio): incluir REALIZADO, PRÓXIMA, Closed-won/lost
    # — Lia faz follow-up / NPS / reativação nessas etapas.
    _STATUS_ATIVOS_IA = {
        96441724,   # 0-ETAPA ENTRADA
        106919911,  # 0-a classificar
        101508307,  # 2.LEADS FRIO
        102560495,  # 3-AGENDAR
        106184631,  # 4.REAGENDAR
        101507507,  # 5-AGENDADO
        101109455,  # 6-CONFIRMAR
        106653499,  # 7.CONFIRMADO
        106184983,  # 7.1-NO-SHOW
        91486864,   # 8-REALIZADO CONSULTA
        106157327,  # 09-PRÓXIMA CONSULTA
        142,        # Closed - won
        143,        # Closed - lost
    }

    # Etapas onde IA deve ser AUTO-DESATIVADA quando lead entra
    # (Bug C-24a, Fábio 11/06/2026 revisado 13:40 BRT): lista RESTRITA
    # a 4 etapas — humano queixou que mesmo movendo pra essas etapas
    # operacionais, Lia continuava respondendo. Outras etapas (8-REALIZADO,
    # 09-PRÓXIMA, Closed-won/lost) MANTÊM IA ativada porque Lia faz
    # follow-up / NPS / reativação nesses estados.
    _STATUS_INATIVOS_IA = {
        106563343,  # 1-ATENDIMENTO HUMANO
        106157139,  # 10-CIRURGIAS ANDAMENTO
        106484343,  # 11-LENTES ANDAMENTO
        106484347,  # 12-FORNECEDORES
    }

    @app.post("/admin/kommo-trigger-status-change")
    @app.get("/admin/kommo-trigger-status-change")
    async def admin_kommo_trigger_status_change(request: Request) -> JSONResponse:
        """Webhook Kommo 'Status do lead alterado'. Se nova etapa é uma
        das etapas ativas, reativa IA (ATIVADO IA? = Ativado).

        Aceita JSON {lead_id, status_id} OU form-urlencoded
        leads[status][0][id]=N&leads[status][0][status_id]=NN
        (formato nativo Kommo).
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got and got != settings.webhook_secret:
                raise HTTPException(401, "Secret inválido")

        lead_id = None
        new_status = None
        try:
            ct = (request.headers.get("content-type") or "").lower()
            if "json" in ct:
                body = await request.json()
                lead_id = body.get("lead_id") or body.get("id")
                new_status = body.get("status_id") or body.get("status")
            else:
                form = await request.form()
                lead_id = (
                    form.get("leads[status][0][id]")
                    or form.get("leads[update][0][id]")
                    or form.get("lead_id") or form.get("id")
                )
                new_status = (
                    form.get("leads[status][0][status_id]")
                    or form.get("leads[update][0][status_id]")
                    or form.get("status_id")
                )
        except Exception:  # noqa: BLE001
            pass
        if not lead_id:
            lead_id = request.query_params.get("lead_id")
        if not new_status:
            new_status = request.query_params.get("status_id")
        try:
            lead_id_int = int(lead_id) if lead_id else 0
            status_int = int(new_status) if new_status else 0
        except (ValueError, TypeError):
            lead_id_int, status_int = 0, 0
        if lead_id_int <= 0:
            return JSONResponse(
                {"error": "lead_id obrigatório"}, status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        # Bug C-24a (Fábio 11/06/2026): se nova etapa é INATIVA pra IA,
        # força ATIVADO IA = Desativado. Cobre 1-ATENDIMENTO HUMANO,
        # 8-REALIZADO, 09-PRÓX, 10-CIRURGIAS, 11-LENTES, 12-FORNECEDORES,
        # 142, 143.
        if status_int and status_int in _STATUS_INATIVOS_IA:
            try:
                ok_off = kommo_client.update_lead_fields(
                    lead_id_int, {"ativado_ia": "Desativado"},
                )
            except Exception as e:  # noqa: BLE001
                return JSONResponse(
                    {"error": f"desativacao falhou: {e}"}, status_code=500,
                )
            return JSONResponse({
                "ok": bool(ok_off), "lead_id": lead_id_int,
                "status_id": status_int, "acao": "ia_desativada",
                "motivo": "etapa inativa pra IA (Bug C-24a)",
            })

        # Se nova etapa não é uma das ativas nem inativas conhecidas,
        # ignora silenciosamente.
        if status_int and status_int not in _STATUS_ATIVOS_IA:
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int, "status_id": status_int,
                "acao": "ignorado", "motivo": "etapa não está na lista ativa nem inativa",
            })

        try:
            ok = kommo_client.update_lead_fields(
                lead_id_int, {"ativado_ia": "Ativado"},
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": f"update falhou: {e}"}, status_code=500,
            )
        return JSONResponse({
            "ok": bool(ok), "lead_id": lead_id_int,
            "status_id": status_int, "acao": "ia_reativada",
        })

    # ========================================================================
    # TRIGGER GOOGLE REVIEW (Fábio 15/06/2026)
    # ========================================================================
    # Webhook Kommo Automation: quando lead vai pra 8-REALIZADO CONSULTA
    # (status_id 91486864) E médico = Dra. Karla Delalíbera, dispara o
    # template Meta blink_pos_avaliacao_{asa_norte|aguas_claras}_v1 pedindo
    # avaliação no Google Maps. Dedup Redis 90 dias por lead_id pra não
    # mandar 2x pro mesmo paciente.
    # ------------------------------------------------------------------------

    # Status final que sinaliza consulta realizada
    _STATUS_REALIZADO_CONSULTA = 91486864
    # Field IDs Kommo
    _FIELD_UNIDADE = 1245125
    _FIELD_MEDICOS = 1256257
    _FIELD_ESPECIALIDADE = 1259130
    # Templates Meta aprovados
    _TEMPLATE_GOOGLE_ASA_NORTE = "blink_pos_avaliacao_asa_norte_v1"
    _TEMPLATE_GOOGLE_AGUAS_CLARAS = "blink_pos_avaliacao_aguas_claras_v1"
    # Dedup TTL — 90 dias (paciente que faz nova consulta em <3m não recebe 2x)
    _DEDUP_GOOGLE_REVIEW_TTL = 90 * 24 * 3600

    def _ler_custom_field_values(lead: dict, field_id: int) -> list[str]:
        """Extrai valores de um custom_field do lead. Retorna [] se ausente."""
        cfs = (lead or {}).get("custom_fields") or (lead or {}).get(
            "custom_fields_values"
        ) or []
        for cf in cfs:
            if cf.get("field_id") == field_id:
                vals = cf.get("values") or []
                out = []
                for v in vals:
                    val = v.get("value")
                    if val is not None:
                        out.append(str(val))
                return out
        return []

    def _medico_e_karla(lead: dict) -> bool:
        """True se o campo MEDICOS contém 'Karla' (case-insensitive)."""
        vals = _ler_custom_field_values(lead, _FIELD_MEDICOS)
        joined = " ".join(vals).lower()
        return "karla" in joined

    def _resolver_template_google(lead: dict) -> Optional[str]:
        """Asa Norte → asa_norte_v1; Águas Claras → aguas_claras_v1; outro → None."""
        vals = _ler_custom_field_values(lead, _FIELD_UNIDADE)
        for v in vals:
            v_norm = v.strip().lower()
            if v_norm in ("asa norte", "asa-norte"):
                return _TEMPLATE_GOOGLE_ASA_NORTE
            if v_norm in ("águas claras", "aguas claras"):
                return _TEMPLATE_GOOGLE_AGUAS_CLARAS
        return None

    def _resolver_especialidade(lead: dict) -> str:
        """Pega 1ª especialidade do campo ESPECIALID. Fallback 'Oftalmologia'."""
        vals = _ler_custom_field_values(lead, _FIELD_ESPECIALIDADE)
        if vals:
            return vals[0]
        return "Oftalmologia"

    @app.post("/admin/kommo-trigger-google-review")
    @app.get("/admin/kommo-trigger-google-review")
    async def admin_kommo_trigger_google_review(
        request: Request,
    ) -> JSONResponse:
        """Webhook Kommo Automation: quando lead vai pra 8-REALIZADO CONSULTA
        (91486864) E médico = Dra. Karla, dispara template Meta
        blink_pos_avaliacao_{asa_norte|aguas_claras}_v1 pedindo avaliação
        no Google Maps.

        Aceita JSON {lead_id, status_id} OU form-urlencoded
        leads[status][0][id]=N&leads[status][0][status_id]=NN (Kommo nativo).

        Dedup Redis 90 dias por lead_id. Forcar=1 ignora dedup.

        Retorna decisão:
          - {ok:true, acao:"disparado", template, wamid}
          - {ok:true, acao:"ignorado", motivo:"..."} (status errado / médico
            errado / unidade desconhecida / dedup hit)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got and got != settings.webhook_secret:
                raise HTTPException(401, "Secret inválido")

        # ----- 1. Extrair lead_id + status_id (JSON ou form Kommo) -----
        lead_id = None
        new_status = None
        try:
            ct = (request.headers.get("content-type") or "").lower()
            if "json" in ct:
                body = await request.json()
                lead_id = body.get("lead_id") or body.get("id")
                new_status = body.get("status_id") or body.get("status")
            else:
                form = await request.form()
                lead_id = (
                    form.get("leads[status][0][id]")
                    or form.get("leads[update][0][id]")
                    or form.get("lead_id") or form.get("id")
                )
                new_status = (
                    form.get("leads[status][0][status_id]")
                    or form.get("leads[update][0][status_id]")
                    or form.get("status_id")
                )
        except Exception:  # noqa: BLE001
            pass
        if not lead_id:
            lead_id = request.query_params.get("lead_id")
        if not new_status:
            new_status = request.query_params.get("status_id")
        forcar = (request.query_params.get("forcar") or "").lower() in (
            "1", "true", "yes",
        )
        dry_run = (request.query_params.get("dry_run") or "").lower() in (
            "1", "true", "yes",
        )

        try:
            lead_id_int = int(lead_id) if lead_id else 0
            status_int = int(new_status) if new_status else 0
        except (ValueError, TypeError):
            lead_id_int, status_int = 0, 0

        if lead_id_int <= 0:
            return JSONResponse(
                {"error": "lead_id obrigatório"}, status_code=400,
            )

        # ----- 2. Validar status_id (só dispara se 8-REALIZADO) -----
        # status_int=0 (Kommo às vezes não manda) → busca o lead pra confirmar.
        # Caso contrário, valida direto.
        if status_int and status_int != _STATUS_REALIZADO_CONSULTA:
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int,
                "status_id": status_int, "acao": "ignorado",
                "motivo": (
                    f"status_id {status_int} ≠ 8-REALIZADO "
                    f"({_STATUS_REALIZADO_CONSULTA})"
                ),
            })

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        # ----- 3. Buscar lead pra ler médico + unidade -----
        try:
            lead = kommo_client.get_lead(lead_id_int)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": f"get_lead falhou: {e}"}, status_code=500,
            )
        if not lead:
            return JSONResponse({
                "ok": False, "lead_id": lead_id_int,
                "acao": "erro", "motivo": "lead inexistente no Kommo",
            }, status_code=404)

        # Confirma status (caso webhook não tenha mandado)
        lead_status = lead.get("status_id")
        if (
            status_int == 0
            and lead_status
            and lead_status != _STATUS_REALIZADO_CONSULTA
        ):
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int,
                "status_id": lead_status, "acao": "ignorado",
                "motivo": (
                    f"lead status atual {lead_status} ≠ 8-REALIZADO "
                    f"(webhook não mandou status_id)"
                ),
            })

        # ----- 4. Validar médico = Karla -----
        if not _medico_e_karla(lead):
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int,
                "acao": "ignorado",
                "motivo": "médico não é Dra. Karla — trigger só dispara pra ela",
            })

        # ----- 5. Resolver template por unidade -----
        template = _resolver_template_google(lead)
        if not template:
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int,
                "acao": "ignorado",
                "motivo": (
                    "unidade não é Asa Norte nem Águas Claras — "
                    "não tenho template Google pra outra unidade"
                ),
            })

        # ----- 6. Dedup Redis (90 dias por lead) -----
        redis_client = getattr(pipeline, "redis_client", None) or getattr(
            pipeline, "redis", None
        )
        dedup_key = f"blink:google_review:{lead_id_int}"
        if redis_client and not forcar:
            try:
                if redis_client.exists(dedup_key):
                    return JSONResponse({
                        "ok": True, "lead_id": lead_id_int,
                        "acao": "ignorado",
                        "motivo": "já recebeu avaliação Google nos últimos 90 dias",
                    })
            except Exception as e:  # noqa: BLE001
                log.warning("[GOOGLE-REVIEW] dedup check falhou: %s", e)

        # ----- 7. Buscar contato + montar body_params -----
        try:
            contato = kommo_client.get_lead_main_contact(lead_id_int)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({
                "ok": False, "lead_id": lead_id_int,
                "acao": "erro", "motivo": f"get_lead_main_contact falhou: {e}",
            }, status_code=500)
        if not contato or not contato.get("telefone"):
            return JSONResponse({
                "ok": False, "lead_id": lead_id_int,
                "acao": "erro", "motivo": "lead sem telefone no contato",
            }, status_code=400)

        nome_contato = (contato.get("nome") or "").strip().split(" ")[0] or "Olá"
        especialidade = _resolver_especialidade(lead)
        body_params = [
            nome_contato,
            "Dra. Karla Delalibera",
            especialidade,
        ]

        # ----- 8. Dry-run early-exit -----
        if dry_run:
            return JSONResponse({
                "ok": True, "lead_id": lead_id_int,
                "acao": "dry_run",
                "template": template,
                "body_params": body_params,
                "telefone": contato.get("telefone"),
            })

        # ----- 9. Disparar template via _disparar_template_aprovado_para_lead -----
        try:
            res = _disparar_template_aprovado_para_lead(
                lead_id_int, kommo_client, wa_cloud, dry_run=False,
                template_override=template,
                body_params_override=body_params,
            )
        except Exception as e:  # noqa: BLE001
            return JSONResponse({
                "ok": False, "lead_id": lead_id_int,
                "acao": "erro", "motivo": f"dispatch falhou: {e}",
            }, status_code=500)

        # ----- 10. Gravar dedup + nota Kommo -----
        if res.get("ok") and redis_client:
            try:
                redis_client.setex(
                    dedup_key, _DEDUP_GOOGLE_REVIEW_TTL, "1",
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[GOOGLE-REVIEW] dedup setex falhou: %s", e)

        if res.get("ok"):
            try:
                kommo_client.add_note(
                    lead_id_int,
                    (
                        f"[LIA] Template avaliação Google disparado "
                        f"({template}) — wamid={res.get('wamid','?')}. "
                        f"Trigger: 8-REALIZADO + Dra. Karla."
                    ),
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[GOOGLE-REVIEW] add_note falhou: %s", e)

        return JSONResponse({
            "ok": bool(res.get("ok")),
            "lead_id": lead_id_int,
            "acao": "disparado" if res.get("ok") else "erro",
            "template": template,
            "body_params": body_params,
            "telefone": contato.get("telefone"),
            "wamid": res.get("wamid"),
            "motivo": res.get("motivo"),
        })

    @app.post("/admin/reativar-ia-batch")
    @app.get("/admin/reativar-ia-batch")
    def admin_reativar_ia_batch(request: Request) -> JSONResponse:
        """Varre leads em etapas ativas que estão com ATIVADO IA = Desativado
        e reativa em batch. Operação one-shot pra limpar acumulado histórico.

        Query params:
          - dry_run (default true)
          - max_leads (default 500, max 2000)
          - status_ids (CSV; default = todas etapas ativas)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        q = request.query_params

        def _bool(name, default):
            v = (q.get(name) or "").lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            return default

        try:
            max_leads = min(int(q.get("max_leads") or "500"), 2000)
        except ValueError:
            max_leads = 500
        dry_run = _bool("dry_run", True)

        sids_raw = (q.get("status_ids") or "").strip()
        if sids_raw:
            try:
                sids = [int(x) for x in sids_raw.split(",") if x.strip().isdigit()]
            except ValueError:
                sids = list(_STATUS_ATIVOS_IA)
        else:
            sids = list(_STATUS_ATIVOS_IA)

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        total_lidos = 0
        desativados = 0
        reativados = 0
        falhas = 0
        amostra: list[dict] = []
        LIMITE = 250
        for sid in sids:
            if total_lidos >= max_leads:
                break
            page = 1
            while total_lidos < max_leads:
                try:
                    leads = kommo_client.list_leads_by_status(
                        pipeline_id=8601819, status_ids=[sid],
                        limit=LIMITE, page=page,
                    )
                except Exception:  # noqa: BLE001
                    break
                if not leads:
                    break
                for ld in leads:
                    if total_lidos >= max_leads:
                        break
                    total_lidos += 1
                    lid = ld.get("id")
                    if not lid:
                        continue
                    # Lê estado atual de ATIVADO IA via get_caller_context
                    try:
                        ctx = kommo_client.get_caller_context_by_lead(lid)
                        estado = str(
                            (ctx.get("known") or {}).get("ativado_ia") or ""
                        ).upper()
                    except Exception:  # noqa: BLE001
                        continue
                    if estado != "DESATIVADO":
                        continue
                    desativados += 1
                    if len(amostra) < 30:
                        amostra.append({
                            "id": lid, "nome": ld.get("name"),
                            "status_id": sid,
                        })
                    if not dry_run:
                        try:
                            if kommo_client.update_lead_fields(
                                lid, {"ativado_ia": "Ativado"},
                            ):
                                reativados += 1
                            else:
                                falhas += 1
                        except Exception:  # noqa: BLE001
                            falhas += 1
                if len(leads) < LIMITE:
                    break
                page += 1

        return JSONResponse({
            "ok": True, "total_lidos": total_lidos,
            "encontrados_desativados": desativados,
            "reativados": reativados, "falhas": falhas,
            "dry_run": dry_run, "status_ids_varridos": sids,
            "amostra": amostra,
        })

    @app.post("/admin/kommo-trigger-disparar")
    async def admin_kommo_trigger_disparar(request: Request) -> JSONResponse:
        """Recebe webhook do Kommo Automation e dispara template aprovado.

        Pra usar: criar Automation no Kommo que dispara webhook HTTP quando
        um lead muda pra status / quando campo 'Disparar Template' = Sim.

        Payload Kommo Automation (formato padrão):
          leads[update][0][id]=22982854
          leads[update][0][custom_fields][NOME_CAMPO]=valor

        OU JSON body:
          {
            "lead_id": 22982854,
            "template": "1089_mens_ativar_conv_parada_qz7kbz",
            "body_params": ["Noah"]
          }

        Aceita ambos formatos.

        Auth: secret via query (?secret=...) OU header X-Webhook-Secret.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        # Tenta JSON primeiro, depois form-urlencoded (formato Kommo padrão)
        lead_id = None
        template = None
        body_params = None
        try:
            body = await request.json()
            lead_id = body.get("lead_id") or body.get("leadId")
            template = body.get("template")
            body_params = body.get("body_params")
        except Exception:
            try:
                form = await request.form()
                # Formato Kommo: leads[update][0][id]
                for key, val in form.items():
                    if "[id]" in key and not lead_id:
                        try:
                            lead_id = int(val)
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

        if not lead_id:
            return JSONResponse(
                {"error": "lead_id não encontrado no payload"},
                status_code=400,
            )

        try:
            lead_id = int(lead_id)
        except (ValueError, TypeError):
            return JSONResponse(
                {"error": f"lead_id inválido: {lead_id}"},
                status_code=400,
            )

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        log.info(
            "[KOMMO-TRIGGER] disparando lead=%s template=%s params=%s",
            lead_id, template, body_params,
        )

        res = _disparar_template_aprovado_para_lead(
            lead_id, kommo_client, wa_cloud,
            dry_run=False,
            template_override=template,
            body_params_override=body_params,
        )
        res["lead_id"] = lead_id
        res["origem"] = "kommo_automation_webhook"
        return JSONResponse(res)

    # ================================================================
    # SETUP CAMPOS ACOMPANHAMENTO LIA (task #216 — 04/06/2026)
    # ================================================================
    @app.post("/admin/setup-campos-acompanhamento")
    @app.get("/admin/setup-campos-acompanhamento")
    def admin_setup_campos_acompanhamento(request: Request) -> JSONResponse:
        """Cria os 3 campos de acompanhamento na entidade Leads do Kommo.

        Campos criados (idempotente — se já existirem, retorna ID atual):
          1. STATUS CONVERSA (select, 15 valores)
          2. ULTIMA MSG OUTBOUND (textarea)
          3. PROXIMA ACAO (select, 12 valores)

        Retorna {ok, campos: {nome: {id, action: created|exists|failed}}}.

        Aproveita KOMMO_TOKEN já carregado no app produção (Easypanel).
        Fábio dispara 1 vez via curl, todos os 3 campos ficam prontos.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        kommo_client = getattr(pipeline, "kommo", None)
        if not kommo_client:
            return JSONResponse(
                {"error": "kommo_client indisponível"}, status_code=500,
            )

        STATUS_CONVERSA_ENUMS = [
            "aguardando_paciente_responder",
            "aguardando_humano_intervir",
            "coletando_dados",
            "validando_convenio",
            "agenda_oferecida",
            "confirmando_horario",
            "gravando_medware",
            "aguardando_sinal_pix",
            "agendado_aguarda_consulta",
            "consulta_realizada_aguarda_pos",
            "faltou_consulta",
            "parado_sem_acao_7d",
            "parado_sem_acao_30d",
            "convenio_nao_aceito",
            "desistiu_explicito",
        ]

        PROXIMA_ACAO_ENUMS = [
            "aguardar_resposta_paciente",
            "disparar_template_reativacao",
            "oferecer_agenda",
            "coletar_dados_minimos",
            "validar_convenio",
            "cobrar_sinal_pix",
            "confirmar_horario_d-1",
            "confirmar_chegada_d-0",
            "escalar_humano",
            "desativar_lead",
            "pos_consulta_avaliacao",
            "agendar_proxima_consulta",
        ]

        campos_definicao = [
            {
                "name": "STATUS CONVERSA",
                "type": "select",
                "enums": STATUS_CONVERSA_ENUMS,
            },
            {
                "name": "ULTIMA MSG OUTBOUND",
                "type": "textarea",
                "enums": None,
            },
            {
                "name": "PROXIMA ACAO",
                "type": "select",
                "enums": PROXIMA_ACAO_ENUMS,
            },
        ]

        resultado: dict[str, Any] = {}
        for definicao in campos_definicao:
            try:
                res = kommo_client.ensure_custom_field(
                    name=definicao["name"],
                    field_type=definicao["type"],
                    enums=definicao.get("enums"),
                )
                resultado[definicao["name"]] = {
                    "action": res.get("action"),
                    "field_id": (res.get("field") or {}).get("id"),
                    "tipo": (res.get("field") or {}).get("type"),
                    "enums_count": len(
                        (res.get("field") or {}).get("enums") or []
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                resultado[definicao["name"]] = {
                    "action": "failed", "erro": str(exc)[:200],
                }

        all_ok = all(
            v.get("action") in ("created", "exists")
            for v in resultado.values()
        )
        return JSONResponse({
            "ok": all_ok,
            "campos": resultado,
            "msg": (
                "OK — todos os campos prontos." if all_ok
                else "Atenção: 1 ou mais campos falharam. Ver detalhes."
            ),
        })

    # ================================================================
    # MENSAGEM DE RENOVAÇÃO DE JANELA 24h WhatsApp 8133 (task #87)
    # ================================================================
    @app.get("/admin/renovar-janela-preview")
    def admin_renovar_janela_preview(request: Request) -> JSONResponse:
        """Pré-visualiza a mensagem + elegibilidade (task #87+#88).

        Query params:
          - nome=<contato>                     (renderização)
          - status_id=<int>                    (filtro etapa antes AGENDADO)
          - horas_desde_paciente=<float>       (idade da última msg do paciente)
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        from voice_agent.mensagens_janela import (
            elegivel_renovar_janela,
            render_mensagem_renovar_janela,
            validar_mensagem_renovacao,
        )
        import time as _t

        nome = request.query_params.get("nome") or ""
        msg = render_mensagem_renovar_janela(nome)
        validacao = validar_mensagem_renovacao(msg)

        elegibilidade = None
        status_id_raw = request.query_params.get("status_id")
        horas_raw = request.query_params.get("horas_desde_paciente")
        if status_id_raw is not None or horas_raw is not None:
            try:
                status_id = int(status_id_raw) if status_id_raw else None
            except ValueError:
                status_id = None
            try:
                horas = float(horas_raw) if horas_raw else None
            except ValueError:
                horas = None
            ultima_ts = (
                _t.time() - horas * 3600 if horas is not None else None
            )
            elegibilidade = elegivel_renovar_janela(
                status_id=status_id,
                ultima_msg_paciente_ts=ultima_ts,
                agora=_t.time(),
            )

        return JSONResponse({
            "nome_contato": nome,
            "mensagem": msg,
            "tamanho_chars": len(msg),
            "validacao": validacao,
            "elegibilidade": elegibilidade,
        })

    # ================================================================
    # MEMÓRIA ATIVA NÍVEL 1 — RAG TF-IDF (task #85)
    # ================================================================
    # Diagnóstico do índice e busca por similaridade contra
    # lia-atendimento-blink/memoria/bugs-licoes/ + voice_agent/knowledge_base/
    @app.get("/admin/rag-status")
    def admin_rag_status(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        try:
            from voice_agent import memoria_rag as _rag
            return JSONResponse(_rag.diagnostico())
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)[:300]})

    @app.get("/admin/rag-query")
    def admin_rag_query(request: Request) -> JSONResponse:
        """Top-K trechos para uma consulta livre.

        Query params: q=texto, k=int (default 3), tipo=licao|kb (opcional).
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        q = request.query_params.get("q") or ""
        if not q.strip():
            return JSONResponse({"error": "q obrigatório"}, status_code=400)
        try:
            from voice_agent import memoria_rag as _rag
            k_raw = request.query_params.get("k") or "3"
            try:
                k = max(1, min(int(k_raw), 20))
            except ValueError:
                k = 3
            tipo = request.query_params.get("tipo")
            if tipo not in (None, "licao", "kb"):
                return JSONResponse({"error": "tipo deve ser licao ou kb"}, status_code=400)
            trechos = _rag.recuperar_licoes_relevantes(
                q, k=k, filtrar_tipo=tipo,
            )
            return JSONResponse({
                "query": q, "k": k, "filtrar_tipo": tipo,
                "total_recuperado": len(trechos),
                "trechos": [
                    {
                        "fonte": t.fonte, "titulo": t.titulo,
                        "fonte_tipo": t.fonte_tipo,
                        "similaridade": round(t.similaridade, 4),
                        "preview": t.conteudo[:300],
                    }
                    for t in trechos
                ],
            })
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": str(exc)[:300]})

    @app.post("/admin/rag-rebuild")
    def admin_rag_rebuild(request: Request) -> JSONResponse:
        """Força reconstrução do índice (depois de adicionar lições novas)."""
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        try:
            from voice_agent import memoria_rag as _rag
            _rag.limpar_cache()
            idx = _rag.obter_indice()
            return JSONResponse({"ok": True, "total_trechos": idx.total()})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)[:300]})

    # ================================================================
    # AUDITORIA PÓS-CONSULTA — task #82 (seções 24 e 25 do prompt)
    # ================================================================
    # Dispara comparação planejado vs realizado por paciente do lead,
    # posta no Slack #auditoria-autorização e atualiza o Kommo.
    def _auditoria_check_secret(request: Request) -> None:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

    @app.post("/admin/auditoria-tick")
    @app.get("/admin/auditoria-tick")
    async def admin_auditoria_tick(request: Request) -> JSONResponse:
        """Roda a auditoria para UM lead específico.

        Query:
          - lead_id (obrigatório)
          - dry_run=true (não posta Slack nem grava Kommo)
        Body JSON (opcional, pra simular sem Medware real):
          - pacientes: [{idx, nome, medico_nome, unidade, convenio,
                         agrupador_planejado, planejado_codigos[],
                         realizado_codigos[]}, ...]
        """
        _auditoria_check_secret(request)
        import voice_agent.auditoria as _aud

        lead_id_raw = request.query_params.get("lead_id")
        if not lead_id_raw:
            return JSONResponse({"error": "lead_id obrigatório"}, status_code=400)
        try:
            lead_id = int(lead_id_raw)
        except ValueError:
            return JSONResponse({"error": "lead_id inválido"}, status_code=400)
        dry_run = (request.query_params.get("dry_run") or "").lower() in ("1", "true", "yes")

        # 1) Snapshot dos pacientes:
        pacientes: list[_aud.PacienteAuditoria] = []
        body_pacientes = None
        try:
            body = await request.json()
            body_pacientes = (body or {}).get("pacientes")
        except Exception:  # noqa: BLE001
            pass

        if body_pacientes:
            # Modo simulação — usa o que o caller mandou.
            for p in body_pacientes:
                pacientes.append(_aud.PacienteAuditoria(
                    idx=int(p.get("idx", 1)),
                    nome=str(p.get("nome", "?")),
                    medico_nome=str(p.get("medico_nome", "?")),
                    unidade=str(p.get("unidade", "?")),
                    convenio=str(p.get("convenio", "?")),
                    agrupador_planejado=str(p.get("agrupador_planejado", "?")),
                    planejado_codigos=list(p.get("planejado_codigos") or []),
                    realizado_codigos=list(p.get("realizado_codigos") or []),
                    nomes_procedimentos=p.get("nomes_procedimentos") or {},
                ))
        else:
            # Modo prod (#82.2): lê o lead no Kommo (N.EXAMES + N.NOME +
            # médico/unidade/convênio + cod_agendamento) e o realizado no
            # Medware, monta os snapshots via auditoria.montar_snapshot_pacientes.
            if not pipeline.kommo:
                return JSONResponse({
                    "status": "kommo_indisponivel",
                    "lead_id": lead_id,
                    "hint": "Sem cliente Kommo. Envie body JSON com `pacientes`.",
                }, status_code=503)
            lead_json = pipeline.kommo.get_lead(lead_id)
            if not lead_json:
                return JSONResponse({
                    "status": "lead_nao_encontrado",
                    "lead_id": lead_id,
                }, status_code=404)
            fetcher = None
            if pipeline.medware:
                fetcher = pipeline.medware.listar_procedimentos_realizados
            pacientes = _aud.montar_snapshot_pacientes(
                lead_json, realizado_fetcher=fetcher,
            )
            if not pacientes:
                return JSONResponse({
                    "status": "sem_pacientes_auditaveis",
                    "lead_id": lead_id,
                    "hint": "Nenhum paciente com N.EXAMES preenchido neste lead.",
                })

        # 2) Senders — dry_run desliga I/O real.
        if dry_run:
            slack_sender = lambda msg: {  # noqa: E731
                "ok": True, "skipped": True, "ts": None,
                "channel": _aud.SLACK_AUDITORIA_CHANNEL_ID,
                "reason": "dry_run", "preview": msg,
            }
            kommo_writer = None
        else:
            slack_sender = _aud.enviar_slack_auditoria
            def kommo_writer(lid, p_idx, enum_id, alterado):
                if not pipeline.kommo or not enum_id:
                    return {"ok": False, "skipped": True, "reason": "kommo ausente"}
                try:
                    fid_status = _aud.kommo_field_id(p_idx, "status")
                    fid_alt = _aud.kommo_field_id(p_idx, "alterado")
                    fields = []
                    if fid_status:
                        fields.append({"field_id": fid_status,
                                       "values": [{"enum_id": enum_id}]})
                    if fid_alt:
                        fields.append({"field_id": fid_alt,
                                       "values": [{"value": bool(alterado)}]})
                    if not fields:
                        return {"ok": False, "reason": "campos não mapeados"}
                    # PATCH direto via kommo client.
                    pipeline.kommo.update_lead_custom_fields(lid, fields)
                    return {"ok": True}
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": str(exc)[:300]}

        # 3) Roda orquestrador.
        kommo_url = (
            f"https://univeja.kommo.com/leads/detail/{lead_id}"
        )
        resultados = _aud.processar_lead_realizado(
            lead_id=lead_id, pacientes=pacientes, kommo_url=kommo_url,
            slack_sender=slack_sender, kommo_writer=kommo_writer,
        )

        # 4) Serializa pra JSON.
        out = []
        for r in resultados:
            out.append({
                "paciente_idx": r.paciente_idx,
                "status": r.status.value,
                "coincide": r.comparacao.coincide,
                "exames_a_mais": r.comparacao.exames_a_mais,
                "exames_a_menos": r.comparacao.exames_a_menos,
                "fonte_vazia": r.comparacao.fonte_vazia,
                "razao_fonte_vazia": r.comparacao.razao_fonte_vazia,
                "slack": r.slack,
                "kommo": r.kommo,
            })
        return JSONResponse({
            "lead_id": lead_id, "dry_run": dry_run,
            "resultados": out,
        })

    @app.post("/admin/auditoria-confirma")
    @app.get("/admin/auditoria-confirma")
    def admin_auditoria_confirma(request: Request) -> JSONResponse:
        """Registra a assinatura (secretaria ou médico) e avança status."""
        _auditoria_check_secret(request)
        import voice_agent.auditoria as _aud
        q = request.query_params
        try:
            lead_id = int(q.get("lead_id") or 0)
            paciente_idx = int(q.get("paciente_idx") or 0)
        except ValueError:
            return JSONResponse({"error": "lead_id/paciente_idx inválidos"}, status_code=400)
        papel = q.get("papel") or ""
        decisao = q.get("decisao") or "ok"
        autor = q.get("autor") or "?"
        status_atual_raw = q.get("status_atual") or "aguardando_secretaria"

        try:
            decisao_result = _aud.confirmar_assinatura(
                lead_id=lead_id, paciente_idx=paciente_idx,
                papel=papel, decisao=decisao, autor=autor,
                status_atual=status_atual_raw,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        # Persiste no Kommo se possível.
        kommo_resp = None
        novo_status = decisao_result["novo_status"]
        if pipeline.kommo:
            try:
                fid_status = _aud.kommo_field_id(paciente_idx, "status")
                enum_id = _aud.kommo_status_enum_id(paciente_idx, novo_status)
                campo_ass = decisao_result.get("campo_assinatura")
                assinatura = decisao_result.get("assinatura")
                fields = []
                if fid_status and enum_id:
                    fields.append({"field_id": fid_status,
                                   "values": [{"enum_id": enum_id}]})
                if campo_ass and assinatura:
                    fid_ass = _aud.kommo_field_id(paciente_idx, campo_ass)
                    if fid_ass:
                        fields.append({"field_id": fid_ass,
                                       "values": [{"value": assinatura}]})
                if fields:
                    pipeline.kommo.update_lead_custom_fields(lead_id, fields)
                kommo_resp = {"ok": True, "campos_gravados": len(fields)}
            except Exception as exc:  # noqa: BLE001
                kommo_resp = {"ok": False, "error": str(exc)[:300]}

        return JSONResponse({
            "lead_id": lead_id,
            "paciente_idx": paciente_idx,
            "papel": papel,
            "decisao": decisao,
            "novo_status": novo_status.value if hasattr(novo_status, "value") else str(novo_status),
            "campo_assinatura": decisao_result.get("campo_assinatura"),
            "assinatura": decisao_result.get("assinatura"),
            "criar_tarefa_humana": decisao_result.get("criar_tarefa_humana"),
            "ja_assinado": decisao_result.get("ja_assinado", False),
            "ciclo_fechado": decisao_result.get("ciclo_fechado", False),
            "erro": decisao_result.get("erro"),
            "kommo": kommo_resp,
        })

    # ----------------------------------------------------------------
    # SLACK EVENTS API → assinatura de auditoria (task #82 + #131)
    # POST /admin/slack-event
    # ----------------------------------------------------------------
    @app.post("/admin/slack-event")
    async def admin_slack_event(request: Request) -> JSONResponse:
        """Recebe POST do Slack Events API (subscription do app).

        Trata 3 tipos de payload:
          - url_verification (handshake inicial Slack) → echo challenge
          - reaction_added (white_check_mark no canal de auditoria) →
            converte em chamada a confirmar_assinatura
          - outros → ignorar silenciosamente
        """
        import os as _os
        from voice_agent import slack_auditoria as _sa
        import voice_agent.auditoria as _aud
        import httpx as _httpx

        # Parse JSON body
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse(
                {"error": "json inválido"}, status_code=400,
            )

        # Handshake Slack — URL Verification
        if payload.get("type") == "url_verification":
            return JSONResponse({"challenge": payload.get("challenge", "")})

        # (Opcional) verificação por Verification Token legacy
        verification = _os.environ.get("SLACK_VERIFICATION_TOKEN") or ""
        if verification:
            got = payload.get("token") or ""
            if got != verification:
                return JSONResponse(
                    {"error": "verification token inválido"},
                    status_code=401,
                )

        # Buscador de mensagem original via Slack conversations.history
        slack_bot_token = (
            _os.environ.get("SLACK_BOT_TOKEN_AUDITORIA") or ""
        ).strip()

        def buscar_mensagem(channel_id: str, ts: str) -> str | None:
            if not slack_bot_token:
                return None
            try:
                with _httpx.Client(timeout=10.0) as cli:
                    r = cli.get(
                        "https://slack.com/api/conversations.history",
                        params={
                            "channel": channel_id,
                            "latest": ts,
                            "limit": 1,
                            "inclusive": "true",
                        },
                        headers={
                            "Authorization": f"Bearer {slack_bot_token}",
                        },
                    )
                if r.status_code != 200:
                    return None
                data = r.json() or {}
                if not data.get("ok"):
                    return None
                msgs = data.get("messages") or []
                if not msgs:
                    return None
                return str(msgs[0].get("text") or "")
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[SLACK-EVENT] buscar_mensagem falhou: %s", e,
                )
                return None

        mapping = _sa.carregar_mapping_env()
        canal_esperado = (
            _os.environ.get("SLACK_AUDITORIA_CHANNEL_ID")
            or "C0B83BK5SMN"
        )
        reaction = (
            _os.environ.get("SLACK_AUDITORIA_REACTION")
            or "white_check_mark"
        )
        resultado = _sa.processar_evento_slack(
            payload,
            mapping=mapping,
            reaction_esperada=reaction,
            canal_esperado=canal_esperado,
            buscar_mensagem=buscar_mensagem,
        )

        log.info(
            "[SLACK-EVENT] acao=%s motivo=%s user=%s lead=%s paciente=%s",
            resultado.acao, resultado.motivo,
            resultado.reaction_user_id,
            resultado.lead_id, resultado.paciente_idx,
        )

        if resultado.acao != "assinar":
            return JSONResponse({
                "ok": True,
                "acao": resultado.acao,
                "motivo": resultado.motivo,
            })

        # Status atual lido do Kommo (papel:secretaria_*→inicial; medico_*→precisa
        # estar em aguardando_medico). Pra simplificar, deixamos
        # confirmar_assinatura inferir pelo papel + status default.
        status_atual = "aguardando_secretaria"
        if resultado.papel and resultado.papel.startswith("medico_"):
            status_atual = "aguardando_medico"

        try:
            decisao = _aud.confirmar_assinatura(
                lead_id=resultado.lead_id,
                paciente_idx=resultado.paciente_idx,
                papel=resultado.papel,
                decisao="ok",
                autor=resultado.autor or "?",
                status_atual=status_atual,
            )
        except ValueError as exc:
            return JSONResponse({
                "ok": False, "error": str(exc),
            }, status_code=400)

        # Persiste no Kommo se possível (mesmo padrão de auditoria-confirma)
        kommo_resp = None
        novo_status = decisao["novo_status"]
        if pipeline.kommo:
            try:
                fid_status = _aud.kommo_field_id(
                    resultado.paciente_idx, "status",
                )
                enum_id = _aud.kommo_status_enum_id(
                    resultado.paciente_idx, novo_status,
                )
                campo_ass = decisao.get("campo_assinatura")
                assinatura = decisao.get("assinatura")
                fields = []
                if fid_status and enum_id:
                    fields.append({
                        "field_id": fid_status,
                        "values": [{"enum_id": enum_id}],
                    })
                if campo_ass and assinatura:
                    fid_ass = _aud.kommo_field_id(
                        resultado.paciente_idx, campo_ass,
                    )
                    if fid_ass:
                        fields.append({
                            "field_id": fid_ass,
                            "values": [{"value": assinatura}],
                        })
                if fields:
                    pipeline.kommo.update_lead_custom_fields(
                        resultado.lead_id, fields,
                    )
                kommo_resp = {
                    "ok": True, "campos_gravados": len(fields),
                }
            except Exception as exc:  # noqa: BLE001
                kommo_resp = {"ok": False, "error": str(exc)[:300]}

        return JSONResponse({
            "ok": True,
            "acao": "assinar",
            "lead_id": resultado.lead_id,
            "paciente_idx": resultado.paciente_idx,
            "papel": resultado.papel,
            "autor": resultado.autor,
            "novo_status": (
                novo_status.value if hasattr(novo_status, "value")
                else str(novo_status)
            ),
            "ja_assinado": decisao.get("ja_assinado", False),
            "ciclo_fechado": decisao.get("ciclo_fechado", False),
            "kommo": kommo_resp,
        })

    # Pipeline + etapa onde buscar leads pós-consulta para auditar.
    # Default: ATENDE 8601819 / "8-REALIZADO CONSULTA" 91486864 (CLAUDE.md §4).
    _AUDITORIA_PIPELINE_ID = int(os.getenv("KOMMO_PIPELINE_ATENDE_ID", "8601819"))
    _AUDITORIA_STATUS_REALIZADO = int(os.getenv("KOMMO_STATUS_REALIZADO_ID", "91486864"))
    _AUDITORIA_FILA_MAX = int(os.getenv("AUDITORIA_FILA_MAX_LEADS", "60"))

    def _coletar_leads_auditaveis() -> list[dict]:
        """Lê os leads em REALIZADO e busca cada um completo (custom fields).

        Bounded por AUDITORIA_FILA_MAX_LEADS pra não martelar a API do Kommo.
        """
        if not pipeline.kommo:
            return []
        resumos = pipeline.kommo.list_leads_by_status(
            _AUDITORIA_PIPELINE_ID, [_AUDITORIA_STATUS_REALIZADO],
            limit=_AUDITORIA_FILA_MAX,
        )
        leads = []
        for r in resumos[:_AUDITORIA_FILA_MAX]:
            lid = r.get("id")
            if not lid:
                continue
            full = pipeline.kommo.get_lead(lid)
            if full:
                leads.append(full)
        return leads

    @app.get("/admin/secretaria-auditoria")
    def admin_secretaria_auditoria(request: Request) -> JSONResponse:
        """Fila da secretaria — pacientes aguardando 1ª assinatura (#82.3)."""
        _auditoria_check_secret(request)
        import voice_agent.auditoria as _aud
        unidade = (request.query_params.get("unidade") or "").lower()
        if unidade not in {"asa-norte", "aguas-claras", ""}:
            return JSONResponse({"error": "unidade deve ser asa-norte ou aguas-claras"}, status_code=400)
        if not pipeline.kommo:
            return JSONResponse({"unidade": unidade or "todas", "fila": [],
                                 "status": "kommo_indisponivel"}, status_code=503)
        leads = _coletar_leads_auditaveis()
        fila = _aud.montar_fila_auditoria(
            leads, status_alvo="aguardando_secretaria",
            unidade=unidade or None,
        )
        return JSONResponse({
            "unidade": unidade or "todas",
            "leads_varridos": len(leads),
            "fila": fila,
        })

    @app.get("/admin/medico-auditoria")
    def admin_medico_auditoria(request: Request) -> JSONResponse:
        """Fila do médico — pacientes aguardando 2ª assinatura (#82.3)."""
        _auditoria_check_secret(request)
        import voice_agent.auditoria as _aud
        medico = (request.query_params.get("medico") or "").lower()
        if medico and medico not in {"karla", "fabricio", "katia"}:
            return JSONResponse({"error": "medico deve ser karla, fabricio ou katia"}, status_code=400)
        if not pipeline.kommo:
            return JSONResponse({"medico": medico or "todos", "fila": [],
                                 "status": "kommo_indisponivel"}, status_code=503)
        leads = _coletar_leads_auditaveis()
        fila = _aud.montar_fila_auditoria(
            leads, status_alvo="aguardando_medico",
            medico=medico or None,
        )
        return JSONResponse({
            "medico": medico or "todos",
            "leads_varridos": len(leads),
            "fila": fila,
        })

    @app.post("/admin/whatsapp-subscribe-waba")
    @app.get("/admin/whatsapp-subscribe-waba")
    def admin_whatsapp_subscribe_waba(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        waba_id = request.query_params.get("waba_id") or "1990931811727552"
        token = settings.whatsapp_cloud_token
        if not token:
            return JSONResponse({"error": "WHATSAPP_CLOUD_TOKEN ausente"})
        import httpx as _httpx
        url = f"https://graph.facebook.com/v22.0/{waba_id}/subscribed_apps"
        try:
            with _httpx.Client(timeout=20.0) as c:
                r = c.post(url, headers={"Authorization": f"Bearer {token}"})
            log.info(
                "[ADMIN SUBSCRIBE WABA] waba=%s status=%s body=%.200s",
                waba_id, r.status_code, r.text or "",
            )
            return JSONResponse({
                "status": r.status_code,
                "body": r.json() if r.content else None,
            })
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:400]})

    # ================================================================
    # CRON INTERNO (task #105) — sobe workers em thread daemon.
    # Liga apenas se BLINK_CRON_ENABLED=1. Idempotente.
    # Hook de startup do FastAPI.
    # ================================================================
    @app.on_event("startup")
    def _bootstrap_cron_interno() -> None:
        try:
            from voice_agent.cron_interno import iniciar_cron
            res = iniciar_cron(pipeline)
            log.info("[CRON BOOT] %s", res)
        except Exception as e:  # noqa: BLE001
            log.warning("[CRON BOOT] falha: %s", e)

    # ================================================================
    # SMOKE TEST CONTÍNUO (task #124) — worker valida 5 cenarios core
    # a cada SMOKE_INTERVALO_SEG (default 3600). Liga só se SMOKE_ENABLED=1.
    # ================================================================
    @app.on_event("startup")
    def _bootstrap_smoke_continuous() -> None:
        try:
            from voice_agent.smoke_continuous import iniciar_smoke_worker
            stop = iniciar_smoke_worker()
            log.info("[SMOKE BOOT] worker_iniciado=%s", bool(stop))
        except Exception as e:  # noqa: BLE001
            log.warning("[SMOKE BOOT] falha: %s", e)

    @app.post("/admin/smoke-tick")
    @app.get("/admin/smoke-tick")
    def admin_smoke_tick(request: Request) -> JSONResponse:
        """Trigger manual dos 5 cenarios core. Devolve relatorio JSON."""
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        try:
            from voice_agent.smoke_continuous import rodar_batch_completo
            rel = rodar_batch_completo()
            return JSONResponse(rel.como_dict())
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:400]}, status_code=500)

    @app.post("/admin/renovacao-varredura")
    @app.get("/admin/renovacao-varredura")
    def admin_renovacao_varredura(request: Request) -> JSONResponse:
        """Roda manualmente a varredura de leads pré-AGENDADO.

        Use pra ambiente de teste antes do cron ligar de verdade.
        Default dry_run=true.
        """
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        from voice_agent.cron_interno import _executar_renovacao_varredura
        dry_run = (request.query_params.get("dry_run") or "true").lower() in ("1", "true", "yes")
        return JSONResponse(
            _executar_renovacao_varredura(pipeline=pipeline, dry_run=dry_run)
        )

    @app.get("/admin/cron-status")
    def admin_cron_status(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")
        from voice_agent.cron_interno import (
            _enabled, _dry_run_default, _intervalo_classificar_seg,
            _threads_iniciadas,
        )
        return JSONResponse({
            "enabled": _enabled(),
            "dry_run": _dry_run_default(),
            "intervalo_classificar_seg": _intervalo_classificar_seg(),
            "threads_ativas": [t.name for t in _threads_iniciadas if t.is_alive()],
        })

    # ================================================================
    # WATCHDOG PROMESSA NÃO CUMPRIDA — cron 2 min
    # ================================================================
    # Detecta leads onde Lia disse "deixa eu consultar / um minutinho /
    # já volto / vou buscar" e silenciou. Move pra 1-ATENDIMENTO HUMANO,
    # desativa IA, grava nota. Equipe humana age. Sem mensagem automática.
    #
    # Liga via WATCHDOG_PROMESSA_ENABLED=1 + cron interno chama esse
    # endpoint a cada 2 min (CRON_WATCHDOG_PROMESSA_SEG default 120).
    @app.get("/admin/watchdog-promessa-tick")
    @app.post("/admin/watchdog-promessa-tick")
    async def admin_watchdog_promessa_tick(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            got = (
                request.headers.get("x-webhook-secret")
                or request.query_params.get("secret")
            )
            if got != settings.webhook_secret:
                raise HTTPException(401, "Unauthorized")

        from voice_agent.watchdog_promessa import (
            tick as watchdog_promessa_tick,
            silencio_min_seg_env,
            silencio_max_seg_env,
        )

        dr_param = request.query_params.get("dry_run", "true")
        dry_run = str(dr_param).lower() not in ("0", "false", "no", "nao")
        max_param = request.query_params.get("max_leads", "30")
        try:
            max_leads = max(1, min(int(max_param), 100))
        except (TypeError, ValueError):
            max_leads = 30

        # Redis opcional pra dedup
        redis_client = None
        try:
            redis_client = pipeline.redis
        except Exception:
            redis_client = None

        try:
            res = watchdog_promessa_tick(
                kommo_client=pipeline.kommo,
                redis_client=redis_client,
                dry_run=dry_run,
                max_leads=max_leads,
                silencio_min_seg=silencio_min_seg_env(),
                silencio_max_seg=silencio_max_seg_env(),
            )
            payload = res.as_dict()
            payload["dry_run"] = dry_run
            log.info("[WATCHDOG-PROMESSA tick dry_run=%s] %s", dry_run, payload)
            return JSONResponse(payload)
        except Exception as e:  # noqa: BLE001
            log.exception("Watchdog promessa tick erro: %s", e)
            return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)

    # Cron interno embutido — chama tick a cada CRON_WATCHDOG_PROMESSA_SEG (default 120s)
    from voice_agent.watchdog_promessa import esta_habilitado as _wp_habilitado

    if _wp_habilitado():
        def _wp_tick_once() -> None:
            try:
                from voice_agent.watchdog_promessa import (
                    tick as _wp_tick, silencio_min_seg_env, silencio_max_seg_env,
                )
                _dry = os.getenv("WATCHDOG_PROMESSA_DRY_RUN", "0") == "1"
                _max = int(os.getenv("WATCHDOG_PROMESSA_MAX_LEADS", "30"))
                _redis = getattr(pipeline, "redis", None)
                rep = _wp_tick(
                    kommo_client=pipeline.kommo,
                    redis_client=_redis,
                    dry_run=_dry,
                    max_leads=_max,
                    silencio_min_seg=silencio_min_seg_env(),
                    silencio_max_seg=silencio_max_seg_env(),
                )
                if rep.candidatos:
                    log.warning(
                        "[WATCHDOG-PROMESSA auto] candidatos=%d tratados=%d dedup=%d erros=%d",
                        rep.candidatos, rep.tratados, rep.ja_dedup, rep.erros,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("[WATCHDOG-PROMESSA auto] erro: %s", e)

        def _wp_scheduler() -> None:
            import time as _t
            _t.sleep(30)  # espera app subir
            intervalo = int(os.getenv("CRON_WATCHDOG_PROMESSA_SEG", "120"))
            while True:
                try:
                    threading.Thread(target=_wp_tick_once, daemon=True).start()
                except Exception as e:  # noqa: BLE001
                    log.warning("watchdog_promessa scheduler erro: %s", e)
                _t.sleep(max(60, intervalo))

        threading.Thread(
            target=_wp_scheduler, daemon=True, name="watchdog_promessa",
        ).start()
        log.info("[WATCHDOG-PROMESSA] worker iniciado (cron interno)")

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
