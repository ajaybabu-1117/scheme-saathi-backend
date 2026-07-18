from app.database.chromadb import get_chroma_client

if __name__ == "__main__":
    get_chroma_client().delete(where={})
    print("Cleared vector collection")
