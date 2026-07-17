from __future__ import annotations


class LLMService:
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:

        marker = None

        if "RETRIEVED SCHEMES:" in user_prompt:
            marker = "RETRIEVED SCHEMES:"
        elif "CONTEXT:" in user_prompt:
            marker = "CONTEXT:"

        if marker is None:
            return "No relevant schemes found in the available database."

        context = user_prompt.split(marker, 1)[1].strip()

        if not context:
            return "No relevant schemes found in the available database."

        return (
            "# Recommended Schemes\n\n"
            f"{context}"
        )


llm_service = LLMService()
