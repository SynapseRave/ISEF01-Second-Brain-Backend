from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.services.llm.base import LLMService
from app.services.llm.chatgpt import ChatGPTService
from app.services.llm.claude import ClaudeService


def get_llm_service() -> LLMService:
    """Return the configured LLM service instance.

    Provider is selected via the LLM_PROVIDER environment variable.
    Supported values: ``openai`` (default), ``anthropic``.

    Returns:
        Concrete LLMService implementation.

    Raises:
        SecondBrainException: If LLM_PROVIDER is set to an unknown value.
    """
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return ChatGPTService()
    if provider == "anthropic":
        return ClaudeService()
    raise SecondBrainException(
        f"Unbekannter LLM-Anbieter: '{provider}'. Erlaubt: 'openai', 'anthropic'.",
        status_code=500,
    )
