from __future__ import annotations


class LLMService:
    """
    Offline response generator.
    Uses only retrieved schemes from ChromaDB/database.
    No OpenRouter or external APIs.
    """

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:

        # Accept both markers
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

        return self._format_answer(context)

    def _format_answer(self, context: str) -> str:
        """
        Convert retrieved schemes into a readable response.
        """

        lines = [
            "# Recommended Schemes",
            "",
            context,
        ]

        return "\n".join(lines)


llm_service = LLMService()
