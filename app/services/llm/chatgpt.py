import json
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.db.models.user_input import UserInput
from app.services.llm.base import (
    _SYSTEM_PROMPT,
    LLMResponse,
    LLMService,
    MessageDict,
    ToolCall,
    ToolDefinition,
)

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
        messages: list[MessageDict] | None = None,
    ) -> list[MessageDict]:
        """Prepend the system message then build conversation messages.

        Args:
            history: Prior conversation records.
            prompt: Current user input.
            messages: Optional pre-built message list that bypasses history building.

        Returns:
            Full message list with system prompt first.
        """
        system_msg: MessageDict = {"role": "system", "content": _SYSTEM_PROMPT}
        base = (
            messages if messages is not None else self._build_messages(history, prompt)
        )
        # Avoid double system message if already present in pre-built messages
        if base and base[0].get("role") == "system":
            return list(base)
        return [system_msg, *base]

    @property
    def model_name(self) -> str:
        """Return the OpenAI model identifier."""
        return _DEFAULT_MODEL

    async def stream_response(
        self,
        history: list[UserInput],
        prompt: str,
        messages: list[MessageDict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the OpenAI Chat Completions API.

        Args:
            history: Prior conversation records (oldest first).
            prompt: Current user input.
            messages: Optional pre-built message list that bypasses history
                      building. Used by the agentic loop.

        Yields:
            Token strings from the streamed response.
        """
        client = self._get_client()
        msgs = self._prepare_messages(history, prompt, messages)

        async with client.chat.completions.create(
            model=_DEFAULT_MODEL,
            messages=msgs,
            stream=True,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

    async def complete_with_tools(
        self,
        messages: list[MessageDict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        """Single non-streaming call that may return tool_call requests.

        Args:
            messages: Full conversation history (system message must be first
                      or will be prepended automatically).
            tools: Tool definitions in provider-agnostic format.

        Returns:
            LLMResponse with text and/or tool_calls populated.
        """
        client = self._get_client()
        # Ensure system message is present
        if not messages or messages[0].get("role") != "system":
            system_msg: MessageDict = {"role": "system", "content": _SYSTEM_PROMPT}
            messages = [system_msg, *messages]

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

        response = await client.chat.completions.create(
            model=_DEFAULT_MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            stream=False,
        )

        choice = response.choices[0]
        text = choice.message.content
        tool_calls: list[ToolCall] = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason="tool_calls" if tool_calls else "stop",
        )

    def build_assistant_tool_use_message(self, tool_call: ToolCall) -> MessageDict:
        """Build OpenAI assistant message containing a tool_calls array.

        Args:
            tool_call: The tool call the assistant decided to make.

        Returns:
            Message dict in OpenAI's required format.
        """
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
            ],
        }

    def build_tool_result_message(
        self,
        tool_call: ToolCall,
        result_content: list[dict],
        is_error: bool,
    ) -> MessageDict:
        """Build OpenAI tool message to append after tool execution.

        Args:
            tool_call: The tool call that produced this result.
            result_content: MCP content blocks as dicts.
            is_error: Whether the tool call failed.

        Returns:
            Message dict in OpenAI's tool role format.
        """
        text = self._content_blocks_to_text(result_content)
        if is_error:
            text = f"[Fehler] {text}"
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": text,
        }
