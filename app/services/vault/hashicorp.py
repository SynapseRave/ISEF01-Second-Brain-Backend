import httpx

from app.core.config import settings
from app.services.vault.base import VaultService

class HashiCorpVaultService(VaultService):
    """HashiCorp Vault integration using AppRole authentication.

    Authenticates via the AppRole method (role_id + secret_id) on every
    operation. Secrets are stored under the KV v2 engine at
    ``{MOUNT}/data/{path}`` where path is ``{user_id}/{service}``.
    """

    def __init__(self) -> None:
        self._addr = settings.vault_addr
        self._role_id = settings.vault_role_id
        self._secret_id = settings.vault_secret_id
        self._mount = settings.vault_mount

    async def _login(self) -> str:
        """Authenticate via AppRole and return a short-lived client token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._addr}/v1/auth/approle/login",
                json={"role_id": self._role_id, "secret_id": self._secret_id},
            )
            resp.raise_for_status()
            return resp.json()["auth"]["client_token"]

    async def store(self, path: str, value: str) -> None:
        """Write or update a secret at ``path``.

        Args:
            path: Secret path in the format ``{user_id}/{service}``.
            value: Plaintext value to store (typically a JSON string).
        """
        token = await self._login()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._addr}/v1/{self._mount}/data/{path}",
                json={"data": {"value": value}},
                headers={"X-Vault-Token": token},
            )
            resp.raise_for_status()

    async def retrieve(self, path: str) -> str:
        """Read a secret from ``path``.

        Args:
            path: Secret path in the format ``{user_id}/{service}``.

        Returns:
            The stored plaintext value.

        Raises:
            KeyError: If no secret exists at ``path``.
        """
        token = await self._login()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._addr}/v1/{self._mount}/data/{path}",
                headers={"X-Vault-Token": token},
            )
            if resp.status_code == 404:
                raise KeyError(path)
            resp.raise_for_status()
            return resp.json()["data"]["data"]["value"]

    async def delete(self, path: str) -> None:
        """Permanently delete all versions of the secret at ``path``.

        Args:
            path: Secret path in the format ``{user_id}/{service}``.
        """
        token = await self._login()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self._addr}/v1/{self._mount}/metadata/{path}",
                headers={"X-Vault-Token": token},
            )
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()
