from collections.abc import AsyncGenerator

import anthropic as anthropic_sdk

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.db.models.user_input import UserInput
from app.services.llm.base import _SYSTEM_PROMPT, LLMService

_DEFAULT_MODEL = "claude-3-5-haiku-latest"
_MAX_TOKENS = 4096


class ClaudeService(LLMService):
    """Anthropic Claude implementation using AsyncAnthropic streaming."""

    _client: anthropic_sdk.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic_sdk.AsyncAnthropic:
        """Lazily initialise the AsyncAnthropic client.

        Returns:
            Shared AsyncAnthropic instance.

        Raises:
            SecondBrainException: If ANTHROPIC_API_KEY is not configured.
        """
        if not settings.anthropic_api_key:
            raise SecondBrainException(
                "Anthropic API-Schlüssel nicht konfiguriert.", status_code=503
            )
        if self._client is None:
            self._client = anthropic_sdk.AsyncAnthropic(
                api_key=settings.anthropic_api_key
            )
        return self._client

    @property
    def model_name(self) -> str:
        """Return the Anthropic model identifier."""
        return _DEFAULT_MODEL

    async def stream_response(
        self,
        history: list[UserInput],
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the Anthropic Messages API.

        The system prompt is passed via the separate ``system=`` parameter
        as required by Anthropic's API.

        Args:
            history: Prior conversation records (oldest first).
            prompt: Current user input.

        Yields:
            Token strings from the streamed response.
        """
        client = self._get_client()
        messages = self._build_messages(history, prompt)

        async with client.messages.stream(
            model=_DEFAULT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
