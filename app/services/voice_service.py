from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings


class VoiceService:
    def transcribe(self, audio_file: UploadFile) -> str:
        try:
            import whisper
        except Exception:
            return "Speech transcription unavailable: install Whisper dependencies or send text directly."

        settings = get_settings()
        model = whisper.load_model(settings.whisper_model)
        suffix = Path(audio_file.filename or "audio.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(audio_file.file.read())
            temp_path = handle.name
        result = model.transcribe(temp_path)
        return result.get("text", "").strip()

    def synthesize(self, text: str, language: str = "en") -> str | None:
        settings = get_settings()
        if not settings.tts_enabled:
            return None
        try:
            from gtts import gTTS
        except Exception:
            return None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as handle:
            tts = gTTS(text=text[:2000], lang=language if len(language) == 2 else "en")
            tts.save(handle.name)
            data = Path(handle.name).read_bytes()
        return base64.b64encode(data).decode("utf-8")


voice_service = VoiceService()
