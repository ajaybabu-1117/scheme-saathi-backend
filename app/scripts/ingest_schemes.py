from __future__ import annotations

import json
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Project Root
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.database.chromadb import chroma_client

DATASETS_DIR = ROOT / "datasets"


def build_document(scheme: dict) -> str:
    """Create searchable text for embeddings."""
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

    print(f"\nProject Root : {ROOT}")
    print(f"Datasets Dir : {DATASETS_DIR}\n")

    if not DATASETS_DIR.exists():
        raise FileNotFoundError(
            f"Datasets directory not found:\n{DATASETS_DIR}"
        )

    json_files = list(DATASETS_DIR.rglob("schemes.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No schemes.json files found inside:\n{DATASETS_DIR}"
        )

    print(f"Found {len(json_files)} scheme files\n")

    for json_file in json_files:

        print(f"Loading -> {json_file}")

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                print(f"   {len(data)} schemes")
                all_schemes.extend(data)

            else:
                print("   Not a list. Skipped.")

        except Exception as e:
            print(f"Failed: {json_file}")
            print(e)

    return all_schemes


def main():

    print("=" * 60)
    print("Building ChromaDB")
    print("=" * 60)

    schemes = load_all_schemes()

    if not schemes:
        raise RuntimeError("No schemes were loaded.")

    print(f"\nLoaded {len(schemes)} schemes")

    print("\nClearing old vectors...")

    try:
        chroma_client.delete()
        print("Old vectors removed.")
    except Exception:
        print("Collection was already empty.")

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
            "scheme_name": str(scheme.get("scheme_name", "")),
            "state": str(scheme.get("state", "")),
            "category": str(scheme.get("category", "")),
            "level": str(scheme.get("level", "")),
            "website": str(scheme.get("website", "")),
        }

        metadatas.append(metadata)

    print(f"\nUnique schemes : {len(ids)}")

    BATCH_SIZE = 100

    for i in range(0, len(ids), BATCH_SIZE):

        chroma_client.upsert(
            ids=ids[i:i + BATCH_SIZE],
            documents=documents[i:i + BATCH_SIZE],
            metadatas=metadatas[i:i + BATCH_SIZE],
        )

        print(
            f"Inserted {min(i + BATCH_SIZE, len(ids))}/{len(ids)}"
        )

    print("\n" + "=" * 60)
    print("ChromaDB Build Complete")
    print("=" * 60)
    print(f"Total vectors : {chroma_client.count()}")


if __name__ == "__main__":
    main()