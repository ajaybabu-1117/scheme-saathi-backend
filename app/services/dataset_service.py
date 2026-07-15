from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.core.config import get_settings
from app.database.chromadb import chroma_client
from app.utils.hashing import sha256_file
from app.utils.ids import slugify
from app.utils.states import normalize_state
from app.utils.text import compact_join


class DatasetService:
    allowed_extensions = {".csv", ".txt", ".json", ".pdf"}

    def __init__(self):
        self.settings = get_settings()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=120,
        )

    def _registry(self) -> Dict[str, Any]:
        path = Path(self.settings.registry_file)
        if not path.exists():
            return {}

        return json.loads(
            path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            or "{}"
        )

    def _save_registry(self, data: Dict[str, Any]) -> None:
        Path(self.settings.registry_file).write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def discover_files(self) -> List[Path]:
        root = Path(self.settings.dataset_root)

        return sorted(
            [
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower()
                in self.allowed_extensions
            ]
        )

    def _state_from_path(self, path: Path) -> str:
        parent = path.parent.name.lower().strip()
        return normalize_state(parent) or "central"

    def _extract_section(
        self,
        text: str,
        keywords: List[str],
        max_chars: int = 1200,
    ) -> str:
        lower = text.lower()

        for keyword in keywords:
            idx = lower.find(keyword.lower())
            if idx != -1:
                return text[idx : idx + max_chars]

        return ""

    def _parse_txt_file(
        self,
        path: Path,
        state: str,
    ) -> Dict[str, Any]:

        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        scheme_name = (
            lines[0]
            if lines
            else path.stem.replace(
                "_",
                " ",
            ).title()
        )

        urls = re.findall(
            r"https?://[^\s]+",
            text,
            re.IGNORECASE,
        )

        website = ""

        for url in urls:
            if ".gov.in" in url.lower():
                website = url
                break

        if not website and urls:
            website = urls[-1]

        benefits = self._extract_section(
            text,
            [
                "benefits",
                "benefit",
                "financial assistance",
                "assistance provided",
                "financial support",
            ],
            max_chars=2000,
        )

        eligibility = self._extract_section(
            text,
            [
                "eligibility",
                "who can apply",
                "eligible beneficiaries",
                "beneficiaries",
            ],
            max_chars=2000,
        )

        application_process = self._extract_section(
            text,
            [
                "how to apply",
                "application process",
                "apply online",
                "procedure",
                "selection process",
            ],
            max_chars=2000,
        )

        documents = self._extract_section(
            text,
            [
                "documents required",
                "required documents",
            ],
            max_chars=1500,
        )

        helpline = self._extract_section(
            text,
            [
                "helpline",
                "contact details",
                "contact information",
            ],
            max_chars=1000,
        )

        return {
            "scheme_name": scheme_name,
            "description": text,
            "benefits": benefits,
            "eligibility": eligibility,
            "application_process": application_process,
            "documents_required": documents,
            "helpline": helpline,
            "website": website,
            "state": state,
            "level": (
                "central"
                if state == "central"
                else "state"
            ),
        }

    def _normalize_records(
        self,
        path: Path,
    ) -> List[Dict[str, Any]]:

        state = self._state_from_path(path)
        ext = path.suffix.lower()

        if ext == ".csv":
            frame = pd.read_csv(path)
            return frame.fillna("").to_dict(
                orient="records"
            )

        if ext == ".json":
            payload = json.loads(
                path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            )

            if isinstance(payload, dict):
                payload = payload.get(
                    "schemes",
                    [payload],
                )

            return payload

        if ext == ".txt":
            return [
                self._parse_txt_file(
                    path=path,
                    state=state,
                )
            ]

        if ext == ".pdf":
            reader = PdfReader(str(path))
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            return [
                {
                    "scheme_name": path.stem.replace(
                        "_",
                        " ",
                    ).title(),
                    "description": text,
                    "state": state,
                }
            ]

        return []

    def _record_to_chunks(
        self,
        record: Dict[str, Any],
        path: Path,
        default_state: str,
    ) -> List[Dict[str, Any]]:

        scheme_name = str(
            record.get("scheme_name")
            or record.get("name")
            or path.stem.replace(
                "_",
                " ",
            ).title()
        )

        scheme_id = slugify(
            str(
                record.get("id")
                or scheme_name
            )
        )

        state = (
            normalize_state(
                str(
                    record.get("state")
                    or default_state
                    or "central"
                )
            )
            or "central"
        )

        category = str(
            record.get("category")
            or record.get("theme")
            or "general"
        ).lower()

        level = str(
            record.get("level")
            or (
                "central"
                if state == "central"
                else "state"
            )
        ).lower()

        website = str(
            record.get("website")
            or record.get("url")
            or ""
        )

        description = compact_join(
            [
                record.get("summary"),
                record.get("description"),
                record.get("benefits"),
                record.get("eligibility"),
                record.get("application_process"),
                record.get("documents_required"),
                record.get("helpline"),
            ]
        )

        if not description:
            description = json.dumps(
                record,
                ensure_ascii=False,
            )

        chunks = self.splitter.split_text(
            description
        )

        rows = []

        for idx, chunk in enumerate(
            chunks
        ):
            rows.append(
                {
                    "id": f"{scheme_id}::{idx}",
                    "document": chunk,
                    "metadata": {
                        "id": scheme_id,
                        "scheme_id": scheme_id,
                        "scheme_name": scheme_name,
                        "state": state,
                        "category": category,
                        "level": level,
                        "source_file": str(
                            path.relative_to(
                                Path(self.settings.dataset_root)
                            )
                        ),
                        "website": website,
                        "eligibility": str(
                            record.get(
                                "eligibility",
                                "",
                            )
                        ),
                        "benefits": str(
                            record.get(
                                "benefits",
                                "",
                            )
                        ),
                        "application_process": str(
                            record.get(
                                "application_process",
                                "",
                            )
                        ),
                        "documents_required": str(
                            record.get(
                                "documents_required",
                                "",
                            )
                        ),
                        "helpline": str(
                            record.get(
                                "helpline",
                                "",
                            )
                        ),
                    },
                }
            )

        return rows

    def ingest_file(
        self,
        file_path: str | Path,
        force: bool = False,
    ) -> Dict[str, Any]:

        path = Path(file_path)

        registry = self._registry()

        file_hash = sha256_file(path)

        key = str(path)

        if (
            registry.get(key) == file_hash
            and not force
        ):
            return {
                "status": "skipped",
                "file": key,
                "reason": "unchanged",
            }

        records = self._normalize_records(
            path
        )

        default_state = self._state_from_path(
            path
        )

        chunks = []

        for record in records:
            chunks.extend(
                self._record_to_chunks(
                    record,
                    path,
                    default_state,
                )
            )

        if chunks:
            source_file = str(
                path.relative_to(
                    Path(
                        self.settings.dataset_root
                    )
                )
            )

            chroma_client.delete(
                where={
                    "source_file": source_file
                }
            )

            chroma_client.upsert(
                ids=[
                    x["id"]
                    for x in chunks
                ],
                documents=[
                    x["document"]
                    for x in chunks
                ],
                metadatas=[
                    x["metadata"]
                    for x in chunks
                ],
            )

        registry[key] = file_hash
        self._save_registry(registry)

        return {
            "status": "indexed",
            "file": key,
            "chunks": len(chunks),
            "records": len(records),
        }

    def ingest_all(
        self,
        force: bool = False,
    ) -> List[Dict[str, Any]]:

        files = self.discover_files()
        results = []

        print(f"\nFound {len(files)} files.\n")

        for i, path in enumerate(files, start=1):
            print(f"[{i}/{len(files)}] {path}")

            result = self.ingest_file(
                path,
                force=force,
            )

            results.append(result)

        return results

    def rebuild(self) -> Dict[str, Any]:
        chroma_client.delete(where={})
        self._save_registry({})

        results = self.ingest_all(force=True)

        return {
            "status": "rebuilt",
            "files": len(results),
            "indexed_chunks": chroma_client.count(),
            "results": results,
        }

    def stats(self) -> Dict[str, Any]:
        files = self.discover_files()

        return {
            "dataset_files": len(files),
            "indexed_chunks": chroma_client.count(),
            "files": [
                str(
                    path.relative_to(
                        Path(self.settings.dataset_root)
                    )
                )
                for path in files
            ],
        }

    def bootstrap(self) -> None:
        try:
            if (
                self.settings.auto_bootstrap_datasets
                and self.discover_files()
                and chroma_client.count() == 0
            ):
                print("\nBootstrapping datasets...\n")

                self.ingest_all(force=False)

                print(
                    f"\nIndexed {chroma_client.count()} chunks.\n"
                )

        except Exception as e:
            print(
                f"Bootstrap failed: {e}"
            )



dataset_service = DatasetService()