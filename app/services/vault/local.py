from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.credential import UserCredential
from app.services.vault.base import VaultService


class LocalVaultService(VaultService):
    """Development-grade vault that stores Fernet-encrypted secrets in PostgreSQL.

    The ``path`` parameter uses the format ``"{user_id}/{service}"``, which is
    split to look up or write the ``UserCredential`` row.
    """

    def __init__(self, db: AsyncSession, master_key: str) -> None:
        """Initialise the vault with a database session and a Fernet master key.

        Args:
            db: Active async SQLAlchemy session.
            master_key: 32-byte URL-safe base64-encoded Fernet key string.
        """
        self._db = db
        self._cipher = Fernet(master_key.encode())

    def _parse_path(self, path: str) -> tuple[str, str]:
        """Split ``"{user_id}/{service}"`` into its components.

        Args:
            path: Vault path string.

        Returns:
            Tuple of (user_id, service).
        """
        user_id, service = path.split("/", 1)
        return user_id, service

    async def _get_row(self, user_id: str, service: str) -> UserCredential | None:
        result = await self._db.execute(
            select(UserCredential).where(
                UserCredential.user_id == user_id,
                UserCredential.service == service,
            )
        )
        return result.scalar_one_or_none()

    async def store(self, path: str, value: str) -> None:
        """Encrypt and upsert the secret for the given path.

        Args:
            path: ``"{user_id}/{service}"`` vault path.
            value: Plaintext secret (JSON string).
        """
        user_id, service = self._parse_path(path)
        encrypted = self._cipher.encrypt(value.encode())

        row = await self._get_row(user_id, service)
        if row:
            row.encrypted_value = encrypted
        else:
            row = UserCredential(
                user_id=user_id,
                service=service,
                encrypted_value=encrypted,
            )
            self._db.add(row)

        await self._db.commit()

    async def retrieve(self, path: str) -> str:
        """Decrypt and return the secret at the given path.

        Args:
            path: ``"{user_id}/{service}"`` vault path.

        Returns:
            Decrypted plaintext value.

        Raises:
            KeyError: If no credential exists for this path.
        """
        user_id, service = self._parse_path(path)
        row = await self._get_row(user_id, service)
        if row is None:
            raise KeyError(path)
        return self._cipher.decrypt(row.encrypted_value).decode()

    async def delete(self, path: str) -> None:
        """Delete the credential row for the given path.

        Args:
            path: ``"{user_id}/{service}"`` vault path.

        Raises:
            KeyError: If no credential exists for this path.
        """
        user_id, service = self._parse_path(path)
        row = await self._get_row(user_id, service)
        if row is None:
            raise KeyError(path)
        await self._db.delete(row)
        await self._db.commit()
