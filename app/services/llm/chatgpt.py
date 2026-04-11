from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.db.models.user_input import UserInput
from app.services.llm.base import _SYSTEM_PROMPT, LLMService, MessageDict

_DEFAULT_MODEL = "gpt-4o-mini"


class ChatGPTService(LLMService):
    """OpenAI ChatGPT implementation using AsyncOpenAI streaming."""

    _client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazily initialise the AsyncOpenAI client.

        Returns:
            Shared AsyncOpenAI instance.

        Raises:
            SecondBrainException: If OPENAI_API_KEY is not configured.
        """
        if not settings.openai_api_key:
            raise SecondBrainException(
                "OpenAI API-Schlüssel nicht konfiguriert.", status_code=503
            )
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def _prepare_messages(
        self,
        history: list[UserInput],
        prompt: str,
    ) -> list[MessageDict]:
        """Prepend the system message then build conversation messages.

        Args:
            history: Prior conversation records.
            prompt: Current user input.

        Returns:
            Full message list with system prompt first.
        """
        system_msg: MessageDict = {"role": "system", "content": _SYSTEM_PROMPT}
        return [system_msg, *self._build_messages(history, prompt)]

    @property
    def model_name(self) -> str:
        """Return the OpenAI model identifier."""
        return _DEFAULT_MODEL

    async def stream_response(
        self,
        history: list[UserInput],
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the OpenAI Chat Completions API.

        Args:
            history: Prior conversation records (oldest first).
            prompt: Current user input.

        Yields:
            Token strings from the streamed response.
        """
        client = self._get_client()
        messages = self._prepare_messages(history, prompt)

        async with client.chat.completions.create(
            model=_DEFAULT_MODEL,
            messages=messages,
            stream=True,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
