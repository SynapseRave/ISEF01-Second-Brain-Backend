from app.services.vault.base import VaultService

_NOT_IMPLEMENTED_MSG = (
    "HashiCorpVaultService is not yet implemented. "
    "Set VAULT_BACKEND=local in your environment to use the local encrypted DB vault."
)


class HashiCorpVaultService(VaultService):
    """Placeholder for a future HashiCorp Vault integration.

    All methods raise NotImplementedError until the integration is implemented.
    Set ``VAULT_BACKEND=local`` to use the local encrypted PostgreSQL vault.
    """

    async def store(self, path: str, value: str) -> None:
        """Not implemented."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def retrieve(self, path: str) -> str:
        """Not implemented."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def delete(self, path: str) -> None:
        """Not implemented."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
