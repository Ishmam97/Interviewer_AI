"""
Tests for the live-interview WebSocket concurrency cap.

Business rules being protected:
  - /ws/* is invisible to slowapi (an HTTP-request limiter), so these caps are
    the ONLY thing standing between a client and unbounded concurrent Gemini
    streams. That is real money per socket.
  - Two sockets on one session would drive the same interview twice and bill
    twice, so a session gets at most one live socket.
  - Registry slots must be released on every exit path, including the
    WebSocketDisconnect that ends a socket normally — otherwise the cap
    ratchets down to zero and locks the user out of their own product.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

SESSION_A = "ws-session-aaa"
SESSION_B = "ws-session-bbb"
UID = "test-uid-123"


def _session_doc(uid=UID):
    return {
        "user_id": uid,
        "interview_type": "behavioral",
        "question_plan": [{"question": "Tell me about yourself."}],
        "resume_file_uri": "files/resume",
        "resume_mime_type": "application/pdf",
        "jd_file_uri": "files/jd",
        "jd_mime_type": "text/plain",
        "resume_file_name": "resume",
        "jd_file_name": "jd",
        "created_at": "2026-01-01T00:00:00",
    }


@pytest.fixture()
def ws_env():
    """Clean registries + a mocked Firebase and LiveInterviewAgent."""
    import app.server as server

    server._ws_active_sessions.clear()
    server._ws_user_connections.clear()
    server._live_sessions.clear()

    fb = MagicMock()
    fb.verify_id_token.return_value = {"uid": UID}
    fb.create_interview_session.return_value = "sid"

    with patch("app.server.get_firebase_manager", return_value=fb):
        yield server

    server._ws_active_sessions.clear()
    server._ws_user_connections.clear()
    server._live_sessions.clear()


def _client():
    from app.server import app

    return TestClient(app)


def _agent_holding_socket_open(hold_seconds=3.0):
    """LiveInterviewAgent stand-in whose run() keeps the socket occupied."""
    async def _run(**_kwargs):
        await asyncio.sleep(hold_seconds)
        return []

    agent_cls = MagicMock()
    agent_cls.return_value.run = _run
    return agent_cls


def _agent_returning_immediately():
    async def _run(**_kwargs):
        return []          # empty transcript → handler returns early

    agent_cls = MagicMock()
    agent_cls.return_value.run = _run
    return agent_cls


def _wait_until(predicate, timeout=5.0):
    """Poll a condition — the handler's finally runs on the server task, which
    may land just after the client-side close returns."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TestSessionLevelCap:
    def test_second_socket_on_same_session_is_rejected(self, ws_env):
        ws_env._live_sessions[SESSION_A] = _session_doc()

        with patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_holding_socket_open(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws1:
                ws1.send_json({"token": "valid-token"})
                assert ws1.receive_json()["type"] == "authenticated"
                assert ws1.receive_json()["type"] == "ready"

                # Same session, second socket — must be refused, not served.
                with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws2:
                    ws2.send_json({"token": "valid-token"})
                    msg = ws2.receive_json()
                    assert msg["type"] == "error"
                    assert "already open" in msg["message"].lower()


class TestUserLevelCap:
    def test_socket_beyond_per_user_limit_is_rejected(self, ws_env):
        ws_env._live_sessions[SESSION_A] = _session_doc()
        ws_env._live_sessions[SESSION_B] = _session_doc()

        with patch.object(settings, "MAX_LIVE_WS_PER_USER", 1), patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_holding_socket_open(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws1:
                ws1.send_json({"token": "valid-token"})
                assert ws1.receive_json()["type"] == "authenticated"
                assert ws1.receive_json()["type"] == "ready"

                # Different session, same user, over the cap.
                with client.websocket_connect(f"/ws/interview/{SESSION_B}") as ws2:
                    ws2.send_json({"token": "valid-token"})
                    msg = ws2.receive_json()
                    assert msg["type"] == "error"
                    assert "too many" in msg["message"].lower()

    def test_a_second_socket_within_the_limit_is_allowed(self, ws_env):
        """The cap must not be so tight that the default case breaks."""
        ws_env._live_sessions[SESSION_A] = _session_doc()
        ws_env._live_sessions[SESSION_B] = _session_doc()

        with patch.object(settings, "MAX_LIVE_WS_PER_USER", 2), patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_holding_socket_open(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws1:
                ws1.send_json({"token": "valid-token"})
                ws1.receive_json(); ws1.receive_json()

                with client.websocket_connect(f"/ws/interview/{SESSION_B}") as ws2:
                    ws2.send_json({"token": "valid-token"})
                    assert ws2.receive_json()["type"] == "authenticated"
                    assert ws2.receive_json()["type"] == "ready"


class TestRelease:
    def test_slots_are_released_when_the_socket_ends(self, ws_env):
        """A cap that never releases silently locks the user out for good."""
        ws_env._live_sessions[SESSION_A] = _session_doc()

        with patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                ws.send_json({"token": "valid-token"})
                ws.receive_json(); ws.receive_json()

        assert _wait_until(lambda: SESSION_A not in ws_env._ws_active_sessions)
        assert _wait_until(lambda: ws_env._ws_user_connections.get(UID, 0) == 0)

    def test_live_session_entry_is_released_too(self, ws_env):
        """Regression: agent.run() used to sit outside any try/finally, so the
        _live_sessions entry leaked on the normal disconnect path."""
        ws_env._live_sessions[SESSION_A] = _session_doc()

        with patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                ws.send_json({"token": "valid-token"})
                ws.receive_json(); ws.receive_json()

        assert _wait_until(lambda: SESSION_A not in ws_env._live_sessions)

    def test_reconnect_after_release_succeeds(self, ws_env):
        """End-to-end proof the cap is not a one-shot lockout."""
        with patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            for _ in range(3):
                ws_env._live_sessions[SESSION_A] = _session_doc()
                with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                    ws.send_json({"token": "valid-token"})
                    assert ws.receive_json()["type"] == "authenticated"
                    assert ws.receive_json()["type"] == "ready"
                assert _wait_until(lambda: SESSION_A not in ws_env._ws_active_sessions)


class TestOwnershipStillEnforced:
    def test_another_users_session_is_refused_before_any_cap_bookkeeping(self, ws_env):
        ws_env._live_sessions[SESSION_A] = _session_doc(uid="someone-else")

        with patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                ws.send_json({"token": "valid-token"})
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "unauthorised" in msg["message"].lower()

        # A rejected connection must not consume a slot.
        assert SESSION_A not in ws_env._ws_active_sessions
        assert ws_env._ws_user_connections.get(UID, 0) == 0


class TestAuthErrorHygiene:
    """A failed WS auth must not echo the exception back over the socket."""

    def test_auth_failure_message_is_generic(self, ws_env):
        leaky = "Firebase token verify blew up: project interviewer-ea164 key AIzaLEAK"

        fb = MagicMock()
        fb.verify_id_token.side_effect = RuntimeError(leaky)

        with patch("app.server.get_firebase_manager", return_value=fb), patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                ws.send_json({"token": "whatever"})
                msg = ws.receive_json()

        assert msg["type"] == "error"
        assert msg["message"] == "Authentication failed. Please sign in again."
        assert leaky not in msg["message"]
        assert "AIzaLEAK" not in msg["message"]
        assert "RuntimeError" not in msg["message"]

    def test_failed_auth_consumes_no_slot(self, ws_env):
        fb = MagicMock()
        fb.verify_id_token.side_effect = RuntimeError("nope")

        with patch("app.server.get_firebase_manager", return_value=fb), patch(
            "app.services.live_interview_agent.LiveInterviewAgent",
            _agent_returning_immediately(),
        ):
            client = _client()
            with client.websocket_connect(f"/ws/interview/{SESSION_A}") as ws:
                ws.send_json({"token": "whatever"})
                ws.receive_json()

        assert SESSION_A not in ws_env._ws_active_sessions
        assert ws_env._ws_user_connections == {}
