from pprint import pprint

from app.services.dataset_service import dataset_service

if __name__ == "__main__":
    pprint(dataset_service.stats())
