from __future__ import annotations

from typing import Iterable


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\n", " ").replace("\t", " ").split())


def compact_join(parts: Iterable[str | None]) -> str:
    return " ".join([clean_text(part) for part in parts if clean_text(part)])
