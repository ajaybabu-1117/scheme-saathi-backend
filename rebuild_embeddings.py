from app.services.dataset_service import dataset_service
from app.database.chromadb import chroma_client

print("Starting rebuild...")

result = dataset_service.rebuild()

print("\nRebuild completed.")
print("Indexed chunks:", chroma_client.count())
print(result)