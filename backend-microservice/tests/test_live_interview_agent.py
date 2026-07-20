"""
Regression tests for LiveInterviewAgent._stream_turn's wall-clock timeout.

Business rule: a hung upstream generation must not block a live-interview turn
(and the websocket) forever. The 300s receive-timeout in run() only covers
waiting for the candidate's next answer, not generation itself — _stream_turn
needs its own bound.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.live_interview_agent import LiveInterviewAgent


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
