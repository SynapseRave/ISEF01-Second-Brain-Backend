from abc import ABC, abstractmethod


class VaultService(ABC):
    """Interface every concrete vault backend must implement.

    Paths use the format ``"{user_id}/{service}"`` so implementations can
    map them to their native key layout (DB rows, HashiCorp KV paths, etc.).
    """

    @abstractmethod
    async def store(self, path: str, value: str) -> None:
        """Persist a secret at the given path (insert or update).

        Args:
            path: Unique path for the secret, e.g. ``"user-123/notion"``.
            value: The plaintext secret to encrypt and store.
        """
        ...

    @abstractmethod
    async def retrieve(self, path: str) -> str:
        """Retrieve and decrypt a secret.

        Args:
            path: The path used when the secret was stored.

        Returns:
            The decrypted plaintext value.

        Raises:
            KeyError: If no secret exists at the given path.
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a secret.

        Args:
            path: The path of the secret to remove.

        Raises:
            KeyError: If no secret exists at the given path.
        """
        ...
