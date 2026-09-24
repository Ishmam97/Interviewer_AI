"""
Route-level tests for monthly usage gating (#26).

The unit rules live in test_usage_service.py; these prove the routes actually
apply them, and — importantly — *when* they apply them relative to the work
being paid for.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import usage_service as usage
from app.services.usage_service import usage_defaults
from tests.conftest import FAKE_USER, _make_firebase_mock

RESUME_FILE = {"resume": ("resume.txt", b"Alice Smith. Python engineer.", "text/plain")}


@contextmanager
def authed_client(fb):
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user

        app.dependency_overrides[get_current_user] = lambda: FAKE_USER
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()


def fb_with_settings(**settings_overrides):
    fb = _make_firebase_mock()
    doc = {
        "user_id": "test-uid-123",
        "api_provider": "openai",
        "user_api_key": "",
        "base_url": "",
        **usage_defaults(),
    }
    doc.update(settings_overrides)
    fb.get_user_settings.return_value = doc
    return fb


def exhausted(action):
    return fb_with_settings(
        **{usage.counter_field(action): usage.limit_for("free", action, settings)}
    )


class TestQuotaBlocksTheSpend:
    def test_exhausted_resume_quota_returns_402(self):
        fb = exhausted(usage.RESUME_ANALYSES)
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code == 402

    def test_402_body_tells_the_ui_what_to_render(self):
        fb = exhausted(usage.RESUME_ANALYSES)
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        detail = r.json()["detail"]
        assert detail["error"] == "quota_exceeded"
        assert detail["action"] == usage.RESUME_ANALYSES
        assert detail["limit"] == settings.FREE_RESUME_ANALYSES_PER_MONTH
        assert detail["plan"] == "free"
        assert detail["reset_at"]

    def test_402_not_429_so_a_paywall_is_distinguishable_from_rate_limiting(self):
        fb = exhausted(usage.RESUME_ANALYSES)
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code != 429

    def test_blocked_request_does_no_work(self):
        """A 402 must stop before the background task is queued, not after."""
        fb = exhausted(usage.RESUME_ANALYSES)
        with authed_client(fb) as c:
            c.post("/profile/resume", files=RESUME_FILE)
        fb.increment_usage.assert_not_called()


class TestQuotaConsumption:
    def test_allowed_request_consumes_exactly_one_unit(self):
        fb = fb_with_settings()
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code == 200
        fb.increment_usage.assert_called_once_with("test-uid-123", usage.RESUME_ANALYSES)

    def test_a_request_that_fails_validation_does_not_burn_quota(self):
        """Quota is charged after validation, so a 400 costs the user nothing."""
        fb = fb_with_settings()
        with authed_client(fb) as c:
            r = c.post(
                "/profile/resume",
                files={"resume": ("resume.exe", b"x", "application/octet-stream")},
            )
        assert r.status_code == 400
        fb.increment_usage.assert_not_called()


class TestByokExemption:
    def test_byok_user_is_never_blocked(self):
        fb = fb_with_settings(
            user_api_key="sk-users-own-key",
            **{usage.counter_field(usage.RESUME_ANALYSES): 9999},
        )
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code == 200

    def test_byok_user_is_not_metered_at_all(self):
        """They pay the provider directly — counting them would charge twice."""
        fb = fb_with_settings(user_api_key="sk-users-own-key")
        with authed_client(fb) as c:
            c.post("/profile/resume", files=RESUME_FILE)
        fb.increment_usage.assert_not_called()


class TestWindowRollover:
    def test_expired_window_is_reset_and_the_request_proceeds(self):
        fb = fb_with_settings(
            usage_reset_at=datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),
            **{usage.counter_field(usage.RESUME_ANALYSES): 9999},
        )
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code == 200
        fb.reset_usage_window.assert_called_once()

    def test_live_window_is_not_reset(self):
        fb = fb_with_settings()
        with authed_client(fb) as c:
            c.post("/profile/resume", files=RESUME_FILE)
        fb.reset_usage_window.assert_not_called()

    def test_a_user_predating_metering_is_not_locked_out(self):
        """No usage fields at all — the pre-#26 shape. Must not 402."""
        fb = _make_firebase_mock()
        fb.get_user_settings.return_value = {
            "user_id": "test-uid-123",
            "user_api_key": "",
            "api_provider": "openai",
        }
        with authed_client(fb) as c:
            r = c.post("/profile/resume", files=RESUME_FILE)
        assert r.status_code == 200


class TestFreeActionsStayFree:
    def test_rejecting_a_suggestion_costs_nothing(self):
        """Only 'accept' reaches an LLM."""
        fb = exhausted(usage.SUGGESTION_APPLIES)
        fb.get_resume_data.return_value = {"current_analysis_id": "analysis-1"}
        fb.get_resume_analysis_by_id.return_value = {
            "id": "analysis-1",
            "user_id": "test-uid-123",
            "status": "completed",
            "overall": {"suggestions": [{"id": "s1", "status": "pending"}]},
            "sections": [],
        }
        with authed_client(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/s1", json={"action": "reject"}
            )
        assert r.status_code != 402
        fb.increment_usage.assert_not_called()
