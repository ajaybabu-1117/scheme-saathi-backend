from __future__ import annotations

import httpx
from app.core.config import get_settings


class LLMService:
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        settings = get_settings()

        # No API key → use fallback
        if not settings.openrouter_api_key:
            return self._fallback_answer(user_prompt)

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", self._fallback_answer(user_prompt))
                )

        except Exception as e:
            print(f"OpenRouter failed: {e}")
            return self._fallback_answer(user_prompt)

    def _fallback_answer(self, user_prompt: str) -> str:
        marker = "CONTEXT:"

        if marker in user_prompt:
            context = user_prompt.split(marker, 1)[1].strip()

            if len(context) > 2000:
                context = context[:2000]

            return (
                "Based on the available scheme database, here are the most relevant details:\n\n"
                f"{context}"
            )

        return (
            "I could not find relevant information in the available scheme database. "
            "Please try asking your question differently."
        )


llm_service = LLMService()
