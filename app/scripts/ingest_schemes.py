from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from project root
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database.chromadb import chroma_client


DATASETS_DIR = ROOT / "datasets"


def build_document(scheme: dict) -> str:
    parts = []

    for key in [
        "scheme_name",
        "description",
        "category",
        "state",
        "level",
    ]:
        value = scheme.get(key)
        if value:
            parts.append(str(value))

    for key in [
        "benefits",
        "eligibility",
        "documents",
        "keywords",
    ]:
        value = scheme.get(key)

        if isinstance(value, list):
            parts.extend([str(v) for v in value if v])

    return "\n".join(parts)


def load_all_schemes():
    all_schemes = []

    for json_file in DATASETS_DIR.rglob("schemes.json"):

        print(f"Loading {json_file}")

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                all_schemes.extend(data)

        except Exception as e:
            print(f"Failed: {json_file}")
            print(e)

    return all_schemes


def main():

    print("=" * 60)
    print("Building ChromaDB")
    print("=" * 60)

    schemes = load_all_schemes()

    print(f"\nLoaded {len(schemes)} schemes")

    print("Clearing old vectors...")

    try:
        chroma_client.delete()
    except Exception:
        pass

    ids = []
    documents = []
    metadatas = []

    seen = set()

    for idx, scheme in enumerate(schemes):

        scheme_id = (
            scheme.get("id")
            or scheme.get("scheme_id")
            or f"scheme_{idx}"
        )

        if scheme_id in seen:
            continue

        seen.add(scheme_id)

        ids.append(str(scheme_id))

        documents.append(build_document(scheme))

        metadata = {
            "id": str(scheme_id),
            "scheme_name": str(
                scheme.get("scheme_name", "")
            ),
            "state": str(
                scheme.get("state", "")
            ),
            "category": str(
                scheme.get("category", "")
            ),
            "level": str(
                scheme.get("level", "")
            ),
            "website": str(
                scheme.get("website", "")
            ),
        }

        metadatas.append(metadata)

    print(f"Unique schemes : {len(ids)}")

    BATCH = 100

    for i in range(0, len(ids), BATCH):

        chroma_client.upsert(
            ids=ids[i:i + BATCH],
            documents=documents[i:i + BATCH],
            metadatas=metadatas[i:i + BATCH],
        )

        print(
            f"Inserted {min(i+BATCH,len(ids))}/{len(ids)}"
        )

    print("\nDone.")
    print(
        f"Total vectors in ChromaDB: {chroma_client.count()}"
    )


if __name__ == "__main__":
    main()
