from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import SecondBrainException
from app.services.llm import get_llm_service
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
