from __future__ import annotations

from typing import Any, Dict, List

from app.repositories.scheme_repository import scheme_repository
from app.schemas.chat import Citation
from app.schemas.profile import UserProfile
from app.services.llm_service import llm_service
from app.services.translation_service import translation_service
from app.utils.states import detect_state, normalize_state
from app.utils.text import clean_text


class RAGService:

    def enhance_query(
        self,
        query: str,
        profile: UserProfile | None = None,
        explicit_state: str | None = None,
    ) -> str:

        q = clean_text(query).lower()

        state = explicit_state or (
            profile.state if profile else None
        )

        # Farmer
        if any(
            word in q
            for word in [
                "farmer",
                "agriculture",
                "crop",
                "farming",
            ]
        ):
            q += """
            pm kisan
            ysr rythu bharosa
            kisan credit card
            crop insurance
            agriculture subsidy
            farmer welfare
            """

        # Student
        if any(
            word in q
            for word in [
                "student",
                "scholarship",
                "education",
                "college",
            ]
        ):
            q += """
            scholarship
            pre matric
            post matric
            merit scholarship
            education assistance
            student welfare
            """

        # Pension
        if any(
            word in q
            for word in [
                "pension",
                "old age",
                "senior citizen",
                "retirement",
            ]
        ):
            q += """
            old age pension
            widow pension
            retirement pension
            senior citizen pension
            social security
            """

        # Health
        if any(
            word in q
            for word in [
                "health",
                "medical",
                "insurance",
                "hospital",
            ]
        ):
            q += """
            health insurance
            ayushman bharat
            aarogyasri
            medical assistance
            health scheme
            """

        # Women
        if any(
            word in q
            for word in [
                "woman",
                "women",
                "female",
                "girl",
            ]
        ):
            q += """
            women empowerment
            girl child
            self employment
            financial assistance
            """

        # Business
        if any(
            word in q
            for word in [
                "business",
                "startup",
                "entrepreneur",
            ]
        ):
            q += """
            startup
            entrepreneur
            self employment
            loan subsidy
            business assistance
            """

        if state:
            q += f" state:{state}"

        return q

    def build_where_filter(
        self,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:

        where: Dict[str, Any] = {}

        if state:
            where["state"] = normalize_state(state)

        if filters:
            for key in ("category", "level"):
                if filters.get(key):
                    where[key] = str(filters[key]).lower()

        return where or None

    def retrieve(
        self,
        query: str,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:

        where = self.build_where_filter(
            state=state,
            filters=filters,
        )

        semantic = scheme_repository.search_semantic(
            query,
            where=where,
            top_k=top_k,
        )

        lexical = scheme_repository.search_keyword(
            query,
            where=where,
            top_k=top_k,
        )

        combined = semantic + lexical

        for row in combined:

            meta = row.get("metadata", {})

            boost = 0.0

            if (
                state
                and meta.get("state")
                == normalize_state(state)
            ):
                boost += 1.0

            text = (
                str(row.get("snippet", ""))
                + " "
                + str(row.get("scheme_name", ""))
            ).lower()

            for word in query.lower().split():
                if word in text:
                    boost += 0.20

            row["score"] = float(
                row.get("score", 0)
            ) + boost

        ranked = sorted(
            combined,
            key=lambda item: item.get("score", 0),
            reverse=True,
        )

        return scheme_repository.aggregate_ranked(
            ranked
        )[:top_k]

    async def answer(
        self,
        query: str,
        language: str = "en",
        user_profile: UserProfile | None = None,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        english_query = (
            translation_service.translate_to_english(
                query,
                source_language=language,
            )
        )

        detected_state = (
            state
            or detect_state(english_query)
            or (
                user_profile.state
                if user_profile
                else None
            )
        )

        if detected_state:
            detected_state = normalize_state(
                detected_state
    )
        
        
        

        enhanced_query = self.enhance_query(
            english_query,
            profile=user_profile,
            explicit_state=detected_state,
        )

        retrieved = self.retrieve(
            enhanced_query,
            state=detected_state,
            filters=filters,
            top_k=10,
        )

        print("\n==============================")
        print("==============================")
        for i, item in enumerate(retrieved):

            print(f"\nResult {i+1}")
            print("Scheme:",item.get("scheme_name"))
            print("State:",item.get("state"))
            print("Website:",item.get("website"))
        print("==============================\n")
        print("QUERY:", english_query)
        print("ENHANCED:", enhanced_query)
        print("STATE:", detected_state)
        print("RESULTS:", len(retrieved))
        print("==============================\n")

        context_lines = []
        citations: List[Citation] = []

        for item in retrieved:

            print(item)

            scheme_name = (
                item.get("scheme_name")
                or item.get("title")
                or "Unknown Scheme"
            )

            context_lines.append(
                f"""
Scheme: {scheme_name}
State: {item.get('state')}
Category: {item.get('category')}
Level: {item.get('level')}
Website: {item.get('website')}
Details: {item.get('snippet')}
"""
            )

            citations.append(
                Citation(
                    scheme_id=str(
                        item.get("scheme_id", "")
                    ),
                    scheme_name=str(
                        scheme_name
                    ),
                    website=item.get(
                        "website"
                    ),
                    source_file=item.get(
                        "metadata",
                        {},
                    ).get(
                        "source_file"
                    ),
                    state=item.get("state"),
                )
            )

        context = "\n".join(
            context_lines
        )

        system_prompt = """
You are SCHEME SAATHI, an AI assistant for Indian Government Schemes.

IMPORTANT RULES:
1. Use ONLY schemes present in RETRIEVED SCHEMES.
2. NEVER invent scheme names.
3. NEVER invent websites.
4. NEVER invent eligibility criteria.
5. If information is missing, say:
   "Not specified in available data."
6. If no schemes are retrieved, say:
   "No relevant schemes found in the available database."
7. Use the exact scheme name and website from the retrieved data.

- Scheme Name
- Benefits
- Eligibility
- Application Process
- Official Website (if available)

5. Answer in simple language.
6. If multiple schemes exist, rank them by relevance.
7. If eligibility or application process is not explicitly mentioned, write "Not specified in available data".
8. Include website links whenever they are available.
9. Focus on schemes matching the user's state and category.

Output format:

# Recommended Schemes

## Scheme Name
Benefits:
Eligibility:
How to Apply:
Website:

## Scheme Name
Benefits:
Eligibility:
How to Apply:
Website:
"""

        user_prompt = f"""
USER QUESTION:
{english_query}

RETRIEVED SCHEMES:
{context}

The retrieved schemes ARE the answer.

Instructions:
1. Recommend the most relevant schemes first.
2. Summarize benefits clearly.
3. Mention eligibility if available.
4. Explain how to apply.
5. Include official website links.
6. Do NOT say that information is unavailable if schemes are present.
7. If multiple schemes are found, rank them by relevance.
- Use ONLY the schemes shown below.
- Do NOT generate additional schemes.
- Do NOT generate websites that are not in the retrieved context.
- If information is missing, write:
  "Not specified in available data."
"""

        answer = await llm_service.generate(
            system_prompt,
            user_prompt,
        )

        answer = (
            translation_service.translate_from_english(
                answer,
                target_language=language,
            )
        )

        return {
            "answer": answer,
            "detected_state": detected_state,
            "citations": citations,
            "results": retrieved,
        }


rag_service = RAGService()