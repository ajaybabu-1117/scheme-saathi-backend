from app.database.chromadb import chroma_client
from app.database.firebase import firebase_client

if __name__ == "__main__":
    chroma_client.delete(where={})
    print("Cleared vector collection")
