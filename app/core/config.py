from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SCHEME SAATHI"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    cors_origins: List[str] | str = ["*"]

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-r1-0528:free"
    embedding_model: str = "intfloat/multilingual-e5-small"

    firebase_project_id: str = ""
    firebase_credentials_path: str = ""
    enable_firebase: bool = False
    enable_push_notifications: bool = False

    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma")
    chroma_collection_name: str = "schemes"
    dataset_root: str = str(BASE_DIR / "datasets")
    registry_file: str = str(BASE_DIR / "data" / "ingestion_registry.json")
    default_top_k: int = 5
    auto_bootstrap_datasets: bool = True

    enable_redis: bool = False
    redis_url: str = "redis://redis:6379/0"

    admin_api_key: str = "hackathon-admin-key"
    whisper_model: str = "base"
    tts_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            if value.strip() == "*":
                return ["*"]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.dataset_root).mkdir(parents=True, exist_ok=True)
    Path(settings.registry_file).parent.mkdir(parents=True, exist_ok=True)
    return settings
