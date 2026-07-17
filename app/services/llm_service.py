from __future__ import annotations

import re


class LLMService:
    """
    Offline response generator.

    Uses only the retrieved scheme context from RAG.
    No external LLMs or APIs.
    """

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        marker = "CONTEXT:"

        if marker not in user_prompt:
            return "No relevant schemes found in the available database."

        context = user_prompt.split(marker, 1)[1].strip()

        if not context:
            return "No relevant schemes found in the available database."

        return self._format_response(context)

    def _format_response(self, context: str) -> str:
        """
        Converts retrieved context into a clean response.
        """

        text = context.strip()

        if not text:
            return "No relevant schemes found in the available database."

        # Split schemes if multiple schemes exist
        chunks = re.split(
            r"\n(?=(?:Scheme Name|Scheme|scheme_name|name)\s*:)",
            text,
        )

        answer = "# Recommended Schemes\n\n"

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            answer += f"{chunk}\n\n"

        return answer.strip()


llm_service = LLMService()
