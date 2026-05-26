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
        version="0.2.1",
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
        for _tent in range(3):
            try:
                result = responder.reply(
                    convo_key, user_text, caller_context=caller_context
                )
                answer = result.get("answer") or ""
                break
            except Exception:  # noqa: BLE001
                log.warning("WA Cloud: responder.reply falhou (tentativa %d/3)",
                            _tent + 1)
                _time.sleep(1.5 * (_tent + 1))
        if not answer:
            log.error("WA Cloud: Claude falhou após 3 tentativas")
            answer = (
                "Oi! Tivemos uma instabilidade rápida por aqui 🙏 "
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
            if not phone:
                continue
            # Dedup — a Meta reentrega o webhook em caso de timeout.
            if mid and not conversation_store.mark_seen(f"wa:{mid}"):
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

    def _entrada_unif_scan() -> dict:
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
    def unificacao_entrada_scan() -> JSONResponse:
        """Diagnóstico/disparo manual da varredura de 0-ENTRADA."""
        return JSONResponse(_entrada_unif_scan())

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
    _TPL_CONFIRMAR = "1031_concluir_confirmar"
    _TPL_LOC_ASA_NORTE = "localiza_asa_norte_1005"
    _TPL_LOC_AGUAS_CLARAS = "local_aguas_claras_1005_aprovada"
    _TPL_COMO_CHEGAR_AC = "1012_como_chegar_na_blink_aguas_claras"
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
