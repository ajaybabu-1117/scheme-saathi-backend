from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.text import clean_text


class SchemeRepository:
    DATA_FILE = Path(
        "datasets/central/sample_schemes.json"
    )

    def _load_schemes(self) -> List[Dict[str, Any]]:
        if not self.DATA_FILE.exists():
            return []

        try:
            with open(
                self.DATA_FILE,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            if isinstance(data, list):
                return data

            return []

        except Exception as e:
            print(f"Failed to load schemes: {e}")
            return []

    def list_chunks(
        self,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        schemes = self._load_schemes()

        items = []

        for scheme in schemes:
            if where:
                skip = False

                for key, value in where.items():
                    if scheme.get(key) != value:
                        skip = True
                        break

                if skip:
                    continue

            items.append(
                {
                    "id": scheme.get("scheme_id"),
                    "document": scheme.get(
                        "description",
                        ""
                    ),
                    "metadata": scheme,
                }
            )

        return items

    def search_semantic(
        self,
        query: str,
        where: Dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        # For hackathon deployment,
        # semantic search falls back to keyword search
        return self.search_keyword(
            query=query,
            where=where,
            top_k=top_k,
        )

    def search_keyword(
        self,
        query: str,
        where: Dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        tokens = {
            token
            for token in clean_text(query)
            .lower()
            .split()
            if len(token) > 2
        }

        scored: List[Dict[str, Any]] = []

        for item in self.list_chunks(
            where=where
        ):
            text = (
                clean_text(
                    item["document"]
                )
                + " "
                + clean_text(
                    str(
                        item["metadata"].get(
                            "scheme_name",
                            ""
                        )
                    )
                )
                + " "
                + clean_text(
                    str(
                        item["metadata"].get(
                            "category",
                            ""
                        )
                    )
                )
            ).lower()

            overlap = sum(
                1
                for token in tokens
                if token in text
            )

            if overlap:
                scored.append(
                    {
                        "document": item[
                            "document"
                        ],
                        "metadata": item[
                            "metadata"
                        ],
                        "score": float(
                            overlap
                        ),
                    }
                )

        return sorted(
            scored,
            key=lambda row: row[
                "score"
            ],
            reverse=True,
        )[:top_k]

    def get_scheme(
        self,
        scheme_id: str,
    ) -> Optional[Dict[str, Any]]:
        chunks = self.list_chunks(
            where={
                "scheme_id": scheme_id
            }
        )

        if not chunks:
            return None

        first = chunks[0]["metadata"]

        return {
            "scheme_id": scheme_id,
            "scheme_name": first.get(
                "scheme_name"
            ),
            "description": chunks[0][
                "document"
            ],
            "state": first.get(
                "state"
            ),
            "category": first.get(
                "category"
            ),
            "level": first.get(
                "level"
            ),
            "website": first.get(
                "website"
            ),
            "last_updated": first.get(
                "last_updated"
            ),
            "source_file": first.get(
                "source_file"
            ),
            "metadata": first,
            "chunks": [
                chunk["document"]
                for chunk in chunks
            ],
        }

    def aggregate_ranked(
        self,
        ranked_chunks: List[
            Dict[str, Any]
        ],
    ) -> List[Dict[str, Any]]:
        best: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for row in ranked_chunks:
            meta = row["metadata"]

            scheme_id = (
                meta.get(
                    "scheme_id"
                )
                or meta.get("id")
            )

            current = best.get(
                scheme_id
            )

            payload = {
                "scheme_id": scheme_id,
                "scheme_name": meta.get(
                    "scheme_name"
                ),
                "state": meta.get(
                    "state"
                ),
                "category": meta.get(
                    "category"
                ),
                "level": meta.get(
                    "level"
                ),
                "website": meta.get(
                    "website"
                ),
                "score": row[
                    "score"
                ],
                "snippet": row[
                    "document"
                ][:240],
                "metadata": meta,
            }

            if (
                not current
                or payload["score"]
                > current["score"]
            ):
                best[
                    scheme_id
                ] = payload

        return sorted(
            best.values(),
            key=lambda item: item[
                "score"
            ],
            reverse=True,
        )


scheme_repository = SchemeRepository()
