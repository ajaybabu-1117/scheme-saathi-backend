from __future__ import annotations

from typing import Any, Dict, List

from app.repositories.analytics_repository import analytics_repository


class AnalyticsService:
    def log_search(self, query: str, state: str | None, results: List[Dict[str, Any]]) -> None:
        analytics_repository.log_event(
            "scheme_search",
            {"query": query, "state": state, "result_count": len(results), "scheme_ids": [item.get("scheme_id") for item in results]},
        )

    def log_chat(self, query: str, conversation_id: str | None, user_id: str | None) -> None:
        analytics_repository.log_event(
            "chat_query",
            {"query": query, "conversation_id": conversation_id, "user_id": user_id},
        )


analytics_service = AnalyticsService()
