"""Transcrição de áudio usando OpenAI Whisper."""

from __future__ import annotations

import io
import logging
from typing import Optional

from openai import OpenAI

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        language: Optional[str] = "pt",
    ):
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._language = language

    def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        filename_hint: str = "audio.ogg",
    ) -> str:
        """Devolve o texto transcrito do áudio.

        Whisper aceita: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac, oga.
        Como o WhatsApp envia OGG/Opus por padrão, esse é o default.
        """
        if not audio_bytes:
            raise ValueError("audio_bytes vazio")

        # OpenAI SDK aceita um tuple (filename, fileobj, content_type)
        file_tuple = (filename_hint, io.BytesIO(audio_bytes), mime_type)

        kwargs: dict = {"model": self._model, "file": file_tuple}
        if self._language:
            kwargs["language"] = self._language

        result = self._client.audio.transcriptions.create(**kwargs)
        text = (result.text or "").strip()
        log.info("Whisper transcreveu %d bytes em %d chars", len(audio_bytes), len(text))
        return text
