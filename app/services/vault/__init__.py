from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.vault.base import VaultService
from app.services.vault.hashicorp import HashiCorpVaultService
from app.services.vault.local import LocalVaultService


def get_vault_service(db: AsyncSession) -> VaultService:
    """Factory: return the configured vault backend.

    The backend is selected via the ``VAULT_BACKEND`` environment variable
    (default: ``"local"``).

    Args:
        db: Active async SQLAlchemy session (required by the local backend).

    Returns:
        A concrete VaultService instance.

    Raises:
        ValueError: If ``VAULT_BACKEND`` is ``"local"`` but ``VAULT_MASTER_KEY``
            is not set, or if an unknown backend name is given.
    """
    if settings.vault_backend == "local":
        if not settings.vault_master_key:
            raise ValueError("VAULT_MASTER_KEY must be set when VAULT_BACKEND=local")
        return LocalVaultService(db, settings.vault_master_key)
    if settings.vault_backend == "hashicorp":
        if not settings.vault_addr:
            raise ValueError("VAULT_ADDR must be set when VAULT_BACKEND=hashicorp")
        if not settings.vault_role_id:
            raise ValueError("VAULT_ROLE_ID must be set when VAULT_BACKEND=hashicorp")
        if not settings.vault_secret_id:
            raise ValueError("VAULT_SECRET_ID must be set when VAULT_BACKEND=hashicorp")
        return HashiCorpVaultService()
    raise ValueError(f"Unknown vault backend: {settings.vault_backend!r}")
