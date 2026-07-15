from __future__ import annotations

import httpx

from app.core.config import get_settings


class LLMService:
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        settings = get_settings()
        if not settings.openrouter_api_key:
            return self._fallback_answer(user_prompt)

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{settings.openrouter_base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _fallback_answer(self, user_prompt: str) -> str:
        marker = "CONTEXT:"
        if marker in user_prompt:
            context = user_prompt.split(marker, 1)[1].strip()[:2000]
            return (
                "Demo mode answer generated without external LLM. Based on the indexed scheme context, "
                f"here are the most relevant details: {context[:1200]}"
            )
        return "Demo mode answer: configure OPENROUTER_API_KEY to enable DeepSeek responses via OpenRouter."


llm_service = LLMService()
