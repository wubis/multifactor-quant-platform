from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Multifactor Stock Ranking Platform"
    database_url: str = Field(
        default="postgresql+psycopg://multifactor:multifactor@localhost:5432/multifactor"
    )
    sample_universe_size: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MFP_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
