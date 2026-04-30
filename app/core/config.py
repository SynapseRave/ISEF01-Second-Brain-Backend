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
    # Required when vault_backend="hashicorp"
    vault_addr: str | None = (
        None  # HashiCorp Vault server URL, e.g. https://vault.example.com
    )
    vault_role_id: str | None = None  # AppRole Role ID
    vault_secret_id: str | None = None  # AppRole Secret ID
    # MCP server base URLs (Docker internal hostnames in production)
    mcp_notion_url: str = "http://localhost:3001"
    mcp_todoist_url: str = "http://localhost:3002"
    mcp_google_calendar_url: str = "http://localhost:3003"
    mcp_obsidian_url: str = "http://localhost:3004"
    mcp_onenote_url: str = "http://localhost:3005"
    mcp_timeout_seconds: int = 30
    mcp_enabled: bool = True
    # OAuth app credentials served to the frontend at runtime
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_tenant_id: str = "common"

    @property
    def mcp_server_urls(self) -> dict[str, str]:
        """Map ApplicationService values to MCP server base URLs."""
        return {
            "notion": self.mcp_notion_url,
            "todoist": self.mcp_todoist_url,
            "google_calendar": self.mcp_google_calendar_url,
            "obsidian": self.mcp_obsidian_url,
            "onenote": self.mcp_onenote_url,
        }

    @property
    def keycloak_browser_url(self) -> str:
        """Returns keycloak_public_url if set, otherwise falls back to keycloak_url."""
        return self.keycloak_public_url or self.keycloak_url


settings = Settings()
