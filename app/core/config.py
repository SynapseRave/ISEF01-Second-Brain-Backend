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
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: str = "openai"  # "openai" | "anthropic"
    vault_backend: str = "local"  # "local" | "hashicorp"
    # Required when vault_backend="local"; 32-byte URL-safe base64 Fernet key
    vault_master_key: str | None = None
    vault_url: str | None = None  # HashiCorp Vault server URL
    vault_token: str | None = None  # HashiCorp Vault token

    @property
    def keycloak_browser_url(self) -> str:
        """Returns keycloak_public_url if set, otherwise falls back to keycloak_url."""
        return self.keycloak_public_url or self.keycloak_url


settings = Settings()
