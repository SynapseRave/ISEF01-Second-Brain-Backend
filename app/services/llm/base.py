from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from app.db.models.user_input import UserInput

_SYSTEM_PROMPT = (
    "Du bist ein intelligenter persönlicher Assistent namens 'Second Brain'. "
    "Du hilfst dem Nutzer dabei, Notizen zu verwalten, Aufgaben zu planen und "
    "Termine zu organisieren. Antworte immer präzise, hilfreich und auf Deutsch. "
    "Nutze den bisherigen Gesprächsverlauf, um Kontext zu berücksichtigen."
)

MessageDict = dict[str, str]


class LLMService(ABC):
    """Interface every concrete LLM backend must implement."""

    def _build_messages(
        self,
        history: list[UserInput],
        prompt: str,
    ) -> list[MessageDict]:
        """Convert DB history + current prompt to a role/content message list.

        Args:
            history: Prior conversation records (oldest first). Must NOT include
                     the current turn's record (it has no response yet).
            prompt: The user's current input.

        Returns:
            List of role/content dicts suitable for OpenAI or Anthropic messages.
        """
        messages: list[MessageDict] = []
        for record in history:
            messages.append({"role": "user", "content": record.prompt})
            if record.response:
                messages.append({"role": "assistant", "content": record.response})
        messages.append({"role": "user", "content": prompt})
        return messages

    @abstractmethod
    async def stream_response(
        self,
        history: list[UserInput],
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time.

        Args:
            history: All previous messages in the conversation (oldest first).
            prompt: The current user input to respond to.

        Yields:
            Individual token/chunk strings from the LLM.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string used for this provider."""
        ...
