from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    keycloak_url: str
    keycloak_public_url: str = ""  # Browser-facing URL for Swagger OAuth2 redirect
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_admin_user: str
    keycloak_admin_password: str
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def keycloak_browser_url(self) -> str:
        """Returns keycloak_public_url if set, otherwise falls back to keycloak_url."""
        return self.keycloak_public_url or self.keycloak_url


settings = Settings()
