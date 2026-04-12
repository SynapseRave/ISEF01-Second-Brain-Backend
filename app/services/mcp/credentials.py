import json

from app.schemas.credential import ApplicationService
from app.services.vault.base import VaultService


async def get_user_credentials_for_services(
    user_id: str,
    services: list[ApplicationService],
    vault: VaultService,
) -> dict[ApplicationService, dict]:
    """Retrieve and deserialise credentials for multiple services.

    Services without stored credentials are silently omitted so callers can
    treat the returned dict as the authoritative set of configured services.

    Args:
        user_id: Keycloak subject ID.
        services: Services to fetch credentials for.
        vault: Decryption backend.

    Returns:
        Mapping of service → decrypted credentials dict. Only contains entries
        for services that have credentials stored in the vault.
    """
    result: dict[ApplicationService, dict] = {}
    for service in services:
        path = f"{user_id}/{service.value}"
        try:
            raw = await vault.retrieve(path)
            result[service] = json.loads(raw)
        except KeyError:
            pass  # User has not configured this service — skip silently
    return result
