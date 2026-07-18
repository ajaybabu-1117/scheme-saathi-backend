from pprint import pprint

from app.services.dataset_service import get_dataset_service

if __name__ == "__main__":
    pprint(get_dataset_service().stats())
