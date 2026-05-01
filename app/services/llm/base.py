import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime

from app.db.models.user_input import UserInput

_SYSTEM_PROMPT_TEMPLATE = (
    "Du bist ein intelligenter persönlicher Assistent namens 'Second Brain'. "
    "Du hilfst dem Nutzer dabei, Notizen zu verwalten, Aufgaben zu planen und "
    "Termine zu organisieren. Antworte immer präzise, hilfreich und auf Deutsch. "
    "Nutze den bisherigen Gesprächsverlauf, um Kontext zu berücksichtigen. "
    "Aktuelles Datum und Uhrzeit: {now}."
)


def _SYSTEM_PROMPT() -> str:
    now = datetime.now().strftime("%A, %d. %B %Y, %H:%M Uhr")
    return _SYSTEM_PROMPT_TEMPLATE.format(now=now)


# content can be str or list (for tool result blocks)
MessageDict = dict[str, object]

# Provider-agnostic tool definition format
# {"name": str, "description": str, "input_schema": dict}
ToolDefinition = dict


@dataclass
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Non-streaming LLM response that may contain tool calls."""

    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


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
        messages: list[MessageDict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one at a time.

        Args:
            history: All previous messages in the conversation (oldest first).
            prompt: The current user input to respond to.
            messages: Optional pre-built message list. When provided, ``history``
                      and ``prompt`` are ignored and these messages are sent directly.
                      Used by the agentic tool-use loop to pass enriched history.

        Yields:
            Individual token/chunk strings from the LLM.
        """
        ...

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[MessageDict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        """Single non-streaming LLM call that may return tool_use requests.

        Args:
            messages: Full conversation history including any tool results.
            tools: Tool definitions to expose to the model.

        Returns:
            LLMResponse with either text or tool_calls populated.
        """
        ...

    @abstractmethod
    def build_tool_result_message(
        self,
        tool_call: ToolCall,
        result_content: list[dict],
        is_error: bool,
    ) -> MessageDict:
        """Build a provider-specific tool result message to append to history.

        Args:
            tool_call: The tool call that produced this result.
            result_content: MCP content blocks as dicts.
            is_error: Whether the tool call failed.

        Returns:
            A message dict ready to append to the conversation.
        """
        ...

    @abstractmethod
    def build_assistant_tool_use_message(self, tool_call: ToolCall) -> MessageDict:
        """Build a provider-specific assistant message representing a tool call.

        This must be appended to the message history before the tool result so
        providers that require alternating roles (Anthropic) do not reject the
        request.

        Args:
            tool_call: The tool call the assistant decided to make.

        Returns:
            A message dict representing the assistant's tool invocation.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string used for this provider."""
        ...

    @staticmethod
    def _content_blocks_to_text(content: list[dict]) -> str:
        """Extract plain text from a list of MCP content block dicts."""
        parts = []
        for block in content:
            text = block.get("text") or json.dumps(block)
            parts.append(str(text))
        return "\n".join(parts)
