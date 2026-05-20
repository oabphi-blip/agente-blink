"""Orquestrador: junta Whisper (OpenAI) + Claude (Anthropic) + Evolution.

Whitelist é aplicada ANTES de enviar — em modo soft launch, só os números
autorizados em settings recebem resposta. Demais ficam apenas logados.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from .evolution import EvolutionClient, EvolutionError
from .kommo import KommoClient
from .responder import Responder
from .settings import Settings
from .transcribe import Transcriber

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    transcript: str
    answer: str
    sent: bool
    model_used: str
    articles_used: list[str]
    blocked_by_whitelist: bool = False
    error: Optional[str] = None


class VoicePipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        responder: Responder,
        evolution: EvolutionClient,
        settings: Settings,
    ):
        self.transcriber = transcriber
        self.responder = responder
        self.evolution = evolution
        self.settings = settings
        self.kommo: Optional[KommoClient] = (
            KommoClient(subdomain=settings.kommo_subdomain, token=settings.kommo_token)
            if settings.kommo_enabled
            else None
        )

    def process_audio_bytes(
        self,
        audio_bytes: bytes,
        mime_type: str,
        conversation_key: str,
        reply_to_number: Optional[str] = None,
        quoted_message_id: Optional[str] = None,
        send_typing: bool = True,
    ) -> PipelineResult:
        return self._process_inner(
            user_input_factory=lambda: self.transcriber.transcribe(
                audio_bytes, mime_type=mime_type
            ),
            input_kind="audio",
            conversation_key=conversation_key,
            reply_to_number=reply_to_number,
            quoted_message_id=quoted_message_id,
            send_typing=send_typing,
        )

    def process_text(
        self,
        text: str,
        conversation_key: str,
        reply_to_number: Optional[str] = None,
        quoted_message_id: Optional[str] = None,
        send_typing: bool = True,
    ) -> PipelineResult:
        return self._process_inner(
            user_input_factory=lambda: text,
            input_kind="text",
            conversation_key=conversation_key,
            reply_to_number=reply_to_number,
            quoted_message_id=quoted_message_id,
            send_typing=send_typing,
        )

    # ----------------------------------------------------- internal

    def _process_inner(
        self,
        user_input_factory,
        input_kind: str,
        conversation_key: str,
        reply_to_number: Optional[str],
        quoted_message_id: Optional[str],
        send_typing: bool,
    ) -> PipelineResult:
        # 0) Whitelist primeiro — bloqueia ANTES de gastar token
        if reply_to_number and not self.settings.is_whitelisted(reply_to_number):
            log.warning(
                "[WHITELIST] Número %s NÃO está autorizado. Bloqueando envio. "
                "Adicione em settings.whitelist_numbers se desejar liberar.",
                reply_to_number,
            )
            return PipelineResult(
                transcript="", answer="", sent=False,
                model_used="", articles_used=[],
                blocked_by_whitelist=True,
                error=f"number_not_in_whitelist: {reply_to_number}",
            )

        # 1) Presença "digitando" (best-effort)
        if send_typing and reply_to_number:
            self.evolution.send_typing(reply_to_number)

        # 2) Extrai input do usuário (transcrição ou texto bruto)
        try:
            user_text = user_input_factory()
        except Exception as e:  # noqa: BLE001
            log.exception("falha ao obter input do usuário (%s)", input_kind)
            return PipelineResult(
                transcript="", answer="", sent=False,
                model_used="", articles_used=[],
                error=f"input_{input_kind}: {e}",
            )

        if not user_text or not user_text.strip():
            return PipelineResult(
                transcript="", answer="", sent=False,
                model_used="", articles_used=[],
                error="entrada vazia",
            )

        # 2b) Onboarding orquestrado — só na PRIMEIRA mensagem da conversa,
        # busca no Kommo o que já se sabe deste contato (evita reperguntar).
        caller_context = None
        if self.kommo is not None and reply_to_number:
            try:
                is_new_conversation = not self.responder._convos.get(conversation_key)
            except Exception:  # noqa: BLE001
                is_new_conversation = False
            if is_new_conversation:
                try:
                    caller_context = self.kommo.get_caller_context(reply_to_number)
                    if caller_context and caller_context.get("found"):
                        log.info(
                            "Onboarding: contato conhecido (lead %s, nome=%s)",
                            caller_context.get("lead_id"), caller_context.get("name"),
                        )
                except Exception as e:  # noqa: BLE001
                    log.warning("Onboarding lookup falhou: %s", e)
                    caller_context = None

        # 3) Resposta com Claude
        try:
            result = self.responder.reply(
                conversation_key, user_text, caller_context=caller_context
            )
            answer = result["answer"]
            model_used = result["model_used"]
            articles_used = result["articles_used"]
        except Exception as e:  # noqa: BLE001
            log.exception("Claude falhou")
            return PipelineResult(
                transcript=user_text, answer="", sent=False,
                model_used="", articles_used=[],
                error=f"claude: {e}",
            )

        # 4) Envio (se houver destino)
        if not reply_to_number:
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
            )

        try:
            self.evolution.send_text(
                number=reply_to_number,
                text=answer,
                quoted_message_id=quoted_message_id,
            )
        except EvolutionError as e:
            log.exception("envio Evolution falhou")
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
                error=f"evolution: {e}",
            )

        # 5) Auto-preenchimento do Kommo CRM (best-effort, em background)
        # — não bloqueia a resposta do WhatsApp se Kommo demorar/falhar.
        if self.kommo is not None and reply_to_number:
            threading.Thread(
                target=self._sync_kommo_safely,
                args=(reply_to_number, conversation_key),
                daemon=True,
            ).start()

        return PipelineResult(
            transcript=user_text, answer=answer, sent=True,
            model_used=model_used, articles_used=articles_used,
        )

    def _sync_kommo_safely(self, phone: str, conversation_key: str) -> None:
        """Atualiza o lead do Kommo com os dados extraídos da conversa.

        Roda em thread separada — qualquer erro é logado, não propaga.
        """
        if self.kommo is None:
            return
        try:
            # Recupera histórico via responder.extract_lead_fields
            fields = self.responder.extract_lead_fields(conversation_key)
            if not fields:
                log.debug("Kommo sync: nenhum campo extraído pra %s", conversation_key)
                return
            lead_id = self.kommo.find_lead_id_by_phone(phone)
            if not lead_id:
                log.info("Kommo sync: lead não encontrado pra %s", phone)
                return
            self.kommo.update_lead_fields(lead_id, fields)
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo sync falhou (%s): %s", phone, e)
