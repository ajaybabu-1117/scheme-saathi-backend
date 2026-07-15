from app.services.dataset_service import dataset_service

if __name__ == "__main__":
    for result in dataset_service.ingest_all(force=False):
        if result["file"].endswith(".txt"):
            print(result)
