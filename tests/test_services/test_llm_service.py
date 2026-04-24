from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import SecondBrainException
from app.services.llm import get_llm_service
from app.services.llm.base import LLMResponse, ToolCall
from app.services.llm.chatgpt import ChatGPTService
from app.services.llm.claude import ClaudeService


def _make_history(pairs: list[tuple[str, str | None]]) -> list[MagicMock]:
    """Build minimal UserInput stubs from (prompt, response) pairs."""
    records = []
    for prompt, response in pairs:
        m = MagicMock()
        m.prompt = prompt
        m.response = response
        records.append(m)
    return records


# ---------------------------------------------------------------------------
# LLMService._build_messages
# ---------------------------------------------------------------------------


def test_build_messages_empty_history() -> None:
    svc = ChatGPTService()
    msgs = svc._build_messages([], "Hallo")
    assert msgs == [{"role": "user", "content": "Hallo"}]


def test_build_messages_with_completed_history() -> None:
    history = _make_history([("Frage 1", "Antwort 1"), ("Frage 2", "Antwort 2")])
    svc = ChatGPTService()
    msgs = svc._build_messages(history, "Frage 3")
    assert msgs == [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1"},
        {"role": "user", "content": "Frage 2"},
        {"role": "assistant", "content": "Antwort 2"},
        {"role": "user", "content": "Frage 3"},
    ]


def test_build_messages_skips_missing_response() -> None:
    """Records without a response must not add an assistant message."""
    history = _make_history([("Frage 1", None)])
    svc = ChatGPTService()
    msgs = svc._build_messages(history, "Frage 2")
    assert msgs == [
        {"role": "user", "content": "Frage 1"},
        {"role": "user", "content": "Frage 2"},
    ]


# ---------------------------------------------------------------------------
# ChatGPTService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chatgpt_raises_when_no_api_key() -> None:
    with patch("app.services.llm.chatgpt.settings") as mock_cfg:
        mock_cfg.openai_api_key = None
        svc = ChatGPTService()
        svc._client = None
        with pytest.raises(SecondBrainException, match="OpenAI"):
            async for _ in svc.stream_response([], "test"):
                pass


@pytest.mark.asyncio
async def test_chatgpt_streams_tokens() -> None:
    async def _fake_chunks():
        for text in ["Hallo", " ", "Welt"]:
            chunk = MagicMock()
            chunk.choices[0].delta.content = text
            yield chunk

    fake_stream = AsyncMock()
    fake_stream.__aenter__ = AsyncMock(return_value=fake_stream)
    fake_stream.__aexit__ = AsyncMock(return_value=False)
    fake_stream.__aiter__ = lambda self: _fake_chunks()

    with (
        patch("app.services.llm.chatgpt.settings") as mock_cfg,
        patch("app.services.llm.chatgpt.AsyncOpenAI") as MockOpenAI,
    ):
        mock_cfg.openai_api_key = "sk-test"
        MockOpenAI.return_value.chat.completions.create.return_value = fake_stream

        svc = ChatGPTService()
        svc._client = None
        tokens = [t async for t in svc.stream_response([], "Hi")]
        assert "".join(tokens) == "Hallo Welt"


@pytest.mark.asyncio
async def test_chatgpt_skips_none_delta_content() -> None:
    async def _fake_chunks():
        for text in ["Token", None, "!"]:
            chunk = MagicMock()
            chunk.choices[0].delta.content = text
            yield chunk

    fake_stream = AsyncMock()
    fake_stream.__aenter__ = AsyncMock(return_value=fake_stream)
    fake_stream.__aexit__ = AsyncMock(return_value=False)
    fake_stream.__aiter__ = lambda self: _fake_chunks()

    with (
        patch("app.services.llm.chatgpt.settings") as mock_cfg,
        patch("app.services.llm.chatgpt.AsyncOpenAI") as MockOpenAI,
    ):
        mock_cfg.openai_api_key = "sk-test"
        MockOpenAI.return_value.chat.completions.create.return_value = fake_stream

        svc = ChatGPTService()
        svc._client = None
        tokens = [t async for t in svc.stream_response([], "Hi")]
        assert "".join(tokens) == "Token!"


# ---------------------------------------------------------------------------
# ClaudeService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_raises_when_no_api_key() -> None:
    with patch("app.services.llm.claude.settings") as mock_cfg:
        mock_cfg.anthropic_api_key = None
        svc = ClaudeService()
        svc._client = None
        with pytest.raises(SecondBrainException, match="Anthropic"):
            async for _ in svc.stream_response([], "test"):
                pass


@pytest.mark.asyncio
async def test_claude_streams_tokens() -> None:
    async def _fake_text():
        for text in ["Guten", " Tag"]:
            yield text

    fake_stream = AsyncMock()
    fake_stream.__aenter__ = AsyncMock(return_value=fake_stream)
    fake_stream.__aexit__ = AsyncMock(return_value=False)
    fake_stream.text_stream = _fake_text()

    with (
        patch("app.services.llm.claude.settings") as mock_cfg,
        patch("app.services.llm.claude.anthropic_sdk") as mock_sdk,
    ):
        mock_cfg.anthropic_api_key = "sk-ant-test"
        mock_sdk.AsyncAnthropic.return_value.messages.stream.return_value = fake_stream

        svc = ClaudeService()
        svc._client = None
        tokens = [t async for t in svc.stream_response([], "Hallo")]
        assert "".join(tokens) == "Guten Tag"


# ---------------------------------------------------------------------------
# get_llm_service factory
# ---------------------------------------------------------------------------


def test_get_llm_service_returns_chatgpt_for_openai() -> None:
    with patch("app.services.llm.settings") as mock_cfg:
        mock_cfg.llm_provider = "openai"
        assert isinstance(get_llm_service(), ChatGPTService)


def test_get_llm_service_returns_claude_for_anthropic() -> None:
    with patch("app.services.llm.settings") as mock_cfg:
        mock_cfg.llm_provider = "anthropic"
        assert isinstance(get_llm_service(), ClaudeService)


def test_get_llm_service_is_case_insensitive() -> None:
    with patch("app.services.llm.settings") as mock_cfg:
        mock_cfg.llm_provider = "OpenAI"
        assert isinstance(get_llm_service(), ChatGPTService)


def test_get_llm_service_raises_for_unknown_provider() -> None:
    with patch("app.services.llm.settings") as mock_cfg:
        mock_cfg.llm_provider = "gemini"
        with pytest.raises(SecondBrainException):
            get_llm_service()


# ---------------------------------------------------------------------------
# ClaudeService — complete_with_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_complete_with_tools_returns_tool_calls() -> None:
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "tu_abc"
    tool_use_block.name = "notion__create_page"
    tool_use_block.input = {"title": "Test", "content": "Body", "parent_page_id": "pid"}

    fake_response = MagicMock()
    fake_response.content = [tool_use_block]
    fake_response.stop_reason = "tool_use"

    with (
        patch("app.services.llm.claude.settings") as mock_cfg,
        patch("app.services.llm.claude.anthropic_sdk") as mock_sdk,
    ):
        mock_cfg.anthropic_api_key = "sk-ant-test"
        mock_sdk.AsyncAnthropic.return_value.messages.create = AsyncMock(
            return_value=fake_response
        )

        svc = ClaudeService()
        svc._client = None
        result = await svc.complete_with_tools(
            [{"role": "user", "content": "Erstelle eine Notiz"}],
            [{"name": "notion__create_page", "description": "...", "input_schema": {}}],
        )

    assert isinstance(result, LLMResponse)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "notion__create_page"
    assert result.tool_calls[0].id == "tu_abc"
    assert result.text is None


@pytest.mark.asyncio
async def test_claude_complete_with_tools_returns_text_when_no_tool() -> None:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Hier ist deine Antwort."

    fake_response = MagicMock()
    fake_response.content = [text_block]
    fake_response.stop_reason = "end_turn"

    with (
        patch("app.services.llm.claude.settings") as mock_cfg,
        patch("app.services.llm.claude.anthropic_sdk") as mock_sdk,
    ):
        mock_cfg.anthropic_api_key = "sk-ant-test"
        mock_sdk.AsyncAnthropic.return_value.messages.create = AsyncMock(
            return_value=fake_response
        )

        svc = ClaudeService()
        svc._client = None
        result = await svc.complete_with_tools([{"role": "user", "content": "Hi"}], [])

    assert result.text == "Hier ist deine Antwort."
    assert result.tool_calls == []


def test_claude_build_tool_result_message() -> None:
    svc = ClaudeService()
    tc = ToolCall(id="tu_1", name="create_page", arguments={})
    msg = svc.build_tool_result_message(tc, [{"type": "text", "text": "OK"}], False)
    assert msg["role"] == "user"
    content = msg["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "tool_result"
    assert content[0]["tool_use_id"] == "tu_1"
    assert content[0]["is_error"] is False


def test_claude_build_assistant_tool_use_message() -> None:
    svc = ClaudeService()
    tc = ToolCall(id="tu_2", name="create_page", arguments={"title": "T"})
    msg = svc.build_assistant_tool_use_message(tc)
    assert msg["role"] == "assistant"
    content = msg["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "tool_use"
    assert content[0]["id"] == "tu_2"
    assert content[0]["input"] == {"title": "T"}


# ---------------------------------------------------------------------------
# ChatGPTService — complete_with_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chatgpt_complete_with_tools_returns_tool_calls() -> None:
    import json as _json

    fake_tc = MagicMock()
    fake_tc.id = "call_xyz"
    fake_tc.function.name = "todoist__create_task"
    fake_tc.function.arguments = _json.dumps({"content": "Einkaufen"})

    fake_message = MagicMock()
    fake_message.content = None
    fake_message.tool_calls = [fake_tc]

    fake_choice = MagicMock()
    fake_choice.message = fake_message

    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    with (
        patch("app.services.llm.chatgpt.settings") as mock_cfg,
        patch("app.services.llm.chatgpt.AsyncOpenAI") as MockOpenAI,
    ):
        mock_cfg.openai_api_key = "sk-test"
        MockOpenAI.return_value.chat.completions.create = AsyncMock(
            return_value=fake_response
        )

        svc = ChatGPTService()
        svc._client = None
        result = await svc.complete_with_tools(
            [{"role": "user", "content": "Erstelle eine Aufgabe"}],
            [
                {
                    "name": "todoist__create_task",
                    "description": "...",
                    "input_schema": {},
                }
            ],  # noqa: E501
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "todoist__create_task"
    assert result.tool_calls[0].arguments == {"content": "Einkaufen"}


def test_chatgpt_build_tool_result_message() -> None:
    svc = ChatGPTService()
    tc = ToolCall(id="call_1", name="create_task", arguments={})
    msg = svc.build_tool_result_message(tc, [{"type": "text", "text": "Fertig"}], False)
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "call_1"
    assert "Fertig" in str(msg["content"])


def test_chatgpt_build_tool_result_message_marks_error() -> None:
    svc = ChatGPTService()
    tc = ToolCall(id="call_2", name="create_task", arguments={})
    msg = svc.build_tool_result_message(tc, [{"type": "text", "text": "Fehler!"}], True)
    assert "[Fehler]" in str(msg["content"])


def test_chatgpt_build_assistant_tool_use_message() -> None:
    import json as _json

    svc = ChatGPTService()
    tc = ToolCall(id="call_3", name="create_task", arguments={"content": "Aufgabe"})
    msg = svc.build_assistant_tool_use_message(tc)
    assert msg["role"] == "assistant"
    tool_calls = msg["tool_calls"]
    assert isinstance(tool_calls, list)
    assert tool_calls[0]["id"] == "call_3"
    assert tool_calls[0]["type"] == "function"
    assert _json.loads(tool_calls[0]["function"]["arguments"]) == {"content": "Aufgabe"}
