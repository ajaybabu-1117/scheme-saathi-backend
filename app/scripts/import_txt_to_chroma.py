from app.services.dataset_service import get_dataset_service

if __name__ == "__main__":
    for result in get_dataset_service().ingest_all(force=False):
        if result["file"].endswith(".txt"):
            print(result)
