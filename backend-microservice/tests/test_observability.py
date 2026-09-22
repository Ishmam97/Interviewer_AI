"""
Tests for the global unhandled-exception handler and Sentry opt-in (#29).

Why these matter:
  - Before the catch-all handler, an unexpected exception produced a bare ASGI
    500 with no traceback log and no error-tracker event — the failure was
    invisible to the only operator (solo dev, no on-call).
  - Exception text on this codebase can carry resume content, prompt fragments
    or provider error detail. It must never reach the client.
  - Sentry must stay inert without a DSN so local runs and CI never phone home.
"""

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FAKE_USER, _make_firebase_mock

# Text that must never appear in a client-visible error body.
LEAKY_MESSAGE = "Firestore said: resume of Alice Smith at ACME-SECRET-PROJECT"


@pytest.fixture()
def failing_client():
    """Client whose resume-list query raises an unexpected (non-HTTP) error.

    raise_server_exceptions=False so the app's own handler produces the
    response instead of TestClient re-raising.
    """
    fb = _make_firebase_mock()
    fb.get_user_resume_analyses.side_effect = RuntimeError(LEAKY_MESSAGE)
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user

        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
        app.dependency_overrides.clear()


def test_unhandled_exception_returns_500_not_a_bare_crash(failing_client):
    resp = failing_client.get("/profile/resumes")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error. Please try again."}


def test_unhandled_exception_body_does_not_leak_exception_text(failing_client):
    """The whole point of the generic body — user content stays server-side."""
    resp = failing_client.get("/profile/resumes")
    body = resp.text
    assert LEAKY_MESSAGE not in body
    assert "Alice Smith" not in body
    assert "ACME-SECRET-PROJECT" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body


def test_unhandled_exception_is_logged_with_traceback(failing_client, caplog):
    """A silent 500 is the failure mode this handler exists to remove."""
    with caplog.at_level(logging.ERROR, logger="app.server"):
        failing_client.get("/profile/resumes")

    records = [r for r in caplog.records if "Unhandled exception" in r.getMessage()]
    assert records, "expected an ERROR log line for the unhandled exception"
    record = records[0]
    assert "/profile/resumes" in record.getMessage()
    assert record.exc_info is not None, "traceback must be attached for debugging"


def test_http_exception_still_passes_through_untouched(failing_client):
    """The catch-all must not swallow deliberate HTTP errors into 500s."""
    resp = failing_client.get("/interview/does-not-exist-xyz/report")
    assert resp.status_code != 500


def test_sentry_stays_disabled_without_a_dsn():
    """No DSN configured (the CI/dev case) ⇒ nothing initialised, nothing sent."""
    from app.core.config import settings
    import app.server as server

    assert settings.SENTRY_DSN == ""
    assert server._sentry_enabled is False
