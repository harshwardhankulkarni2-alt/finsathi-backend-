from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_KEY = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # set ENV=production when deployed
    database_url: str = "sqlite:///./finsathi.db"
    secret_key: str = INSECURE_DEFAULT_KEY
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    max_upload_mb: int = 5
    max_import_rows: int = 5000
    default_min_reserve: float = 5000

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Render/Heroku style URLs use the legacy "postgres://" scheme.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key == INSECURE_DEFAULT_KEY:
        raise RuntimeError("SECRET_KEY must be set to a long random value when ENV=production")
    return s
