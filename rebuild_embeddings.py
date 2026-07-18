from app.services.dataset_service import get_dataset_service
from app.database.chromadb import get_chroma_client

print("Starting rebuild...")

result = get_dataset_service().rebuild()

print("\nRebuild completed.")
print("Indexed chunks:", get_chroma_client().count())
print(result)