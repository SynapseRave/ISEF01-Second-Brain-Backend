from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    keycloak_url: str
    keycloak_realm: str
    keycloak_client_id: str
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
