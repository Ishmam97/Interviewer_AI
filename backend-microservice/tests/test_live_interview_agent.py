"""
Regression tests for LiveInterviewAgent._stream_turn's wall-clock timeout.

Business rule: a hung upstream generation must not block a live-interview turn
(and the websocket) forever. The 300s receive-timeout in run() only covers
waiting for the candidate's next answer, not generation itself — _stream_turn
needs its own bound.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from google.genai import types

from app.services.live_interview_agent import (
    LiveInterviewAgent,
    _MAX_HISTORY_TURNS,
    _trim_history,
)


class _FakeChunk:
    def __init__(self, text):
        self.text = text


async def _fake_stream(chunks):
    for c in chunks:
        yield _FakeChunk(c)


async def _never_ending_stream():
    while True:
        await asyncio.sleep(1)
    yield _FakeChunk("unreachable")  # pragma: no cover


class TestStreamTurnTimeout:
    async def test_normal_stream_returns_full_text(self):
        agent = LiveInterviewAgent(api_key="test-key")
        agent.client = MagicMock()
        agent.client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream(["Hello", " there"])
        )
        ws = AsyncMock()

        text = await agent._stream_turn("system", [], ws)

        assert text == "Hello there"
        done_call = ws.send_json.call_args_list[-1]
        assert done_call.args[0]["done"] is True

    async def test_hung_stream_times_out_gracefully(self, monkeypatch):
        monkeypatch.setattr("app.services.live_interview_agent._STREAM_TIMEOUT", 0.05)
        agent = LiveInterviewAgent(api_key="test-key")
        agent.client = MagicMock()
        agent.client.aio.models.generate_content_stream = AsyncMock(
            return_value=_never_ending_stream()
        )
        ws = AsyncMock()

        text = await agent._stream_turn("system", [], ws)

        assert text, "must fall back to a graceful message rather than raise or return empty"
        done_call = ws.send_json.call_args_list[-1]
        assert done_call.args[0]["done"] is True


def _make_content(i):
    return types.Content(role="user", parts=[types.Part(text=f"turn {i}")])


class TestTrimHistory:
    """Regression for #31: resending the whole `contents` list every turn
    makes per-request token cost grow quadratically with interview length.
    `_trim_history` must cap what's actually sent while preserving the first
    entry (it carries the resume/JD file parts) and the tail of recent turns.
    """

    def test_short_history_is_returned_unchanged(self):
        contents = [_make_content(i) for i in range(_MAX_HISTORY_TURNS)]

        assert _trim_history(contents) == contents

    def test_long_history_keeps_first_entry_and_recent_tail(self):
        first = _make_content("opening-with-files")
        contents = [first] + [_make_content(i) for i in range(30)]

        trimmed = _trim_history(contents)

        assert trimmed[0] is first
        assert len(trimmed) == _MAX_HISTORY_TURNS + 1
        assert trimmed[1:] == contents[-_MAX_HISTORY_TURNS:]

    def test_does_not_mutate_original_contents(self):
        contents = [_make_content(i) for i in range(30)]
        original_len = len(contents)

        _trim_history(contents)

        assert len(contents) == original_len


class TestStreamTurnSendsTrimmedHistory:
    async def test_generate_content_stream_receives_trimmed_contents(self):
        """The actual API call must use the trimmed history, not the raw
        (unboundedly growing) `contents` list — otherwise the cap is
        computed but never applied."""
        agent = LiveInterviewAgent(api_key="test-key")
        agent.client = MagicMock()
        agent.client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream(["ok"])
        )
        ws = AsyncMock()
        first = _make_content("opening-with-files")
        long_contents = [first] + [_make_content(i) for i in range(30)]

        await agent._stream_turn("system", long_contents, ws)

        call_kwargs = agent.client.aio.models.generate_content_stream.call_args.kwargs
        sent_contents = call_kwargs["contents"]
        assert len(sent_contents) == _MAX_HISTORY_TURNS + 1
        assert sent_contents[0] is first
        # The full history the caller holds must be untouched — run() keeps
        # appending to it across the whole interview for the turn protocol.
        assert len(long_contents) == 31
