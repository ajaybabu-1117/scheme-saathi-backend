from __future__ import annotations

from deep_translator import GoogleTranslator
from langdetect import detect


class TranslationService:
    def detect_language(self, text: str) -> str:
        try:
            return detect(text)
        except Exception:
            return "en"

    def translate_to_english(
        self,
        text: str,
        source_language: str | None = None,
    ) -> str:
        if not text:
            return text

        try:
            source = source_language or self.detect_language(text)

            if source == "en":
                return text

            return GoogleTranslator(
                source="auto",
                target="en",
            ).translate(text)

        except Exception as e:
            print("Translation to English failed:", e)
            return text

    def translate_from_english(
        self,
        text: str,
        target_language: str | None = None,
    ) -> str:
        if not text:
            return text

        target = target_language or "en"

        if target == "en":
            return text

        try:
            return GoogleTranslator(
                source="en",
                target=target,
            ).translate(text)

        except Exception as e:
            print("Translation from English failed:", e)
            return text


translation_service = TranslationService()