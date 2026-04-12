from collections.abc import AsyncGenerator

import anthropic as anthropic_sdk

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
        messages: list[MessageDict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the Anthropic Messages API.

        The system prompt is passed via the separate ``system=`` parameter
        as required by Anthropic's API.

        Args:
            history: Prior conversation records (oldest first).
            prompt: Current user input.
            messages: Optional pre-built message list that bypasses
                      ``_build_messages``. Used by the agentic loop.

        Yields:
            Token strings from the streamed response.
        """
        client = self._get_client()
        msgs = (
            messages if messages is not None else self._build_messages(history, prompt)
        )

        async with client.messages.stream(
            model=_DEFAULT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=msgs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def complete_with_tools(
        self,
        messages: list[MessageDict],
        tools: list[ToolDefinition],
    ) -> LLMResponse:
        """Single non-streaming call that may return tool_use requests.

        Args:
            messages: Full conversation history.
            tools: Tool definitions in provider-agnostic format.

        Returns:
            LLMResponse with text and/or tool_calls populated.
        """
        client = self._get_client()
        anthropic_tools = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema", {}),
            }
            for t in tools
        ]

        response = await client.messages.create(
            model=_DEFAULT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=messages,
            tools=anthropic_tools,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
        )

    def build_assistant_tool_use_message(self, tool_call: ToolCall) -> MessageDict:
        """Build Anthropic assistant message containing a tool_use block.

        Args:
            tool_call: The tool call the assistant decided to make.

        Returns:
            Message dict in Anthropic's required format.
        """
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": tool_call.arguments,
                }
            ],
        }

    def build_tool_result_message(
        self,
        tool_call: ToolCall,
        result_content: list[dict],
        is_error: bool,
    ) -> MessageDict:
        """Build Anthropic tool_result block to append after tool execution.

        Args:
            tool_call: The tool call that produced this result.
            result_content: MCP content blocks as dicts.
            is_error: Whether the tool call failed.

        Returns:
            Message dict in Anthropic's tool_result format.
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result_content,
                    "is_error": is_error,
                }
            ],
        }
