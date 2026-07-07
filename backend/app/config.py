from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    docuengine_env: str = "development"
    secret_key: str = "dev-secret-do-not-use-in-production"
    api_base_url: str = "http://localhost:8000"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "docuengine"
    postgres_user: str = "docuengine"
    postgres_password: str = "docuengine-dev-password"
    # Overrides the postgres_* fields when set (tests use sqlite here).
    database_url_override: str = ""

    redis_url: str = "redis://localhost:6379/0"

    data_dir: Path = Path("./data")
    models_dir: Path = Path("./models")

    ocr_engine: str = "mock"  # paddleocr-vl | ppocrv5-cpu | rapidocr | easyocr | mock
    ocr_model_size: str = "medium"  # rapidocr PP-OCRv6 variant: tiny | small | medium
    # GPU acceleration for the rapidocr engine via DirectML (Windows; any GPU).
    # Requires onnxruntime-directml instead of onnxruntime; falls back to CPU
    # automatically when the provider is unavailable.
    ocr_use_gpu: bool = False
    # Camera-photo enhancement (perspective + illumination) for image inputs.
    # PDFs are always left on the deskew-only path.
    ocr_photo_enhance: bool = True
    ocr_dpi: int = 200
    ocr_max_long_edge: int = 2600

    superadmin_email: str = "admin@sonasu.co.jp"
    superadmin_password: str = "change-me-on-first-login"
    superadmin_name: str = "Sonasu Admin"

    access_token_minutes: int = 15
    refresh_token_days: int = 7

    training_enabled: bool = False
    training_min_corrections: int = 200
    training_schedule_hour_jst: int = 2
    training_wall_clock_hours: int = 4

    ingest_max_queue_depth: int = 2000

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
