from app.database.chromadb import get_chroma_client

queries = [
    "I am a farmer from Andhra Pradesh",
    "I need scholarships",
    "I need pension schemes",
    "I need health insurance"
]

for query in queries:
    print("\n" + "=" * 80)
    print(query)
    print("-" * 80)

    results = get_chroma_client().query(
        query_texts=[query],
        n_results=5
    )

    docs = results["documents"][0]

    for i, doc in enumerate(docs, 1):
        print(f"\nResult {i}")
        print(doc[:300])