"""
Unit tests for the monthly quota rules (#26).

These encode product decisions, not just behaviour:
  - BYOK users are never metered (they pay the provider directly; metering them
    would charge twice for one call).
  - A user who predates metering gets a clean window, never a lockout.
  - Windows roll on a calendar-month boundary in UTC.
"""

from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.services import usage_service as usage
from app.services.usage_service import (
    DREAM_JOBS,
    INTERVIEWS,
    PLAN_FREE,
    PLAN_PRO,
    RESUME_ANALYSES,
    SUGGESTION_APPLIES,
    UNLIMITED,
)

JAN = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 2, 9, 0, tzinfo=timezone.utc)


def free_user(**overrides):
    doc = {
        "plan": PLAN_FREE,
        "user_api_key": "",
        "usage_reset_at": datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat(),
    }
    for action in usage.ALL_ACTIONS:
        doc[usage.counter_field(action)] = 0
    doc.update(overrides)
    return doc


class TestWindowBoundary:
    def test_next_reset_is_first_of_next_month(self):
        assert usage.next_reset_at(JAN) == datetime(2026, 2, 1, tzinfo=timezone.utc)

    def test_december_rolls_into_january_of_the_next_year(self):
        dec = datetime(2026, 12, 20, tzinfo=timezone.utc)
        assert usage.next_reset_at(dec) == datetime(2027, 1, 1, tzinfo=timezone.utc)

    def test_window_is_live_before_the_reset_instant(self):
        assert usage.window_expired(free_user(), JAN) is False

    def test_window_expires_at_the_reset_instant(self):
        assert usage.window_expired(free_user(), FEB) is True

    def test_missing_reset_at_counts_as_expired(self):
        """Users predating metering must get a fresh window, not a lockout."""
        assert usage.window_expired({}, JAN) is True

    def test_unparseable_reset_at_counts_as_expired(self):
        assert usage.window_expired({"usage_reset_at": "garbage"}, JAN) is True


class TestFreePlanCeiling:
    def test_under_the_limit_is_allowed(self):
        doc = free_user(interviews_this_month=settings.FREE_INTERVIEWS_PER_MONTH - 1)
        state = usage.evaluate(doc, INTERVIEWS, settings, JAN)
        assert state.allowed is True
        assert state.limit == settings.FREE_INTERVIEWS_PER_MONTH

    def test_at_the_limit_is_blocked(self):
        doc = free_user(interviews_this_month=settings.FREE_INTERVIEWS_PER_MONTH)
        state = usage.evaluate(doc, INTERVIEWS, settings, JAN)
        assert state.allowed is False
        assert state.exempt is False

    def test_over_the_limit_is_blocked(self):
        doc = free_user(interviews_this_month=settings.FREE_INTERVIEWS_PER_MONTH + 3)
        assert usage.evaluate(doc, INTERVIEWS, settings, JAN).allowed is False

    @pytest.mark.parametrize(
        "action", [INTERVIEWS, RESUME_ANALYSES, DREAM_JOBS, SUGGESTION_APPLIES]
    )
    def test_every_metered_action_has_its_own_ceiling(self, action):
        limit = usage.limit_for(PLAN_FREE, action, settings)
        doc = free_user(**{usage.counter_field(action): limit})
        assert usage.evaluate(doc, action, settings, JAN).allowed is False
        # ...and exhausting one action does not block the others
        for other in usage.ALL_ACTIONS:
            if other != action:
                assert usage.evaluate(doc, other, settings, JAN).allowed is True

    def test_counters_are_independent_not_shared(self):
        doc = free_user(interviews_this_month=999)
        assert usage.evaluate(doc, DREAM_JOBS, settings, JAN).allowed is True


class TestRollover:
    def test_expired_window_frees_an_exhausted_user(self):
        doc = free_user(interviews_this_month=9999)
        state = usage.evaluate(doc, INTERVIEWS, settings, FEB)
        assert state.allowed is True
        assert state.used == 0
        assert state.window_rolled is True

    def test_rolled_state_reports_the_new_window_end(self):
        doc = free_user(interviews_this_month=9999)
        state = usage.evaluate(doc, INTERVIEWS, settings, FEB)
        assert state.reset_at == datetime(2026, 3, 1, tzinfo=timezone.utc).isoformat()

    def test_live_window_is_not_rolled(self):
        state = usage.evaluate(free_user(), INTERVIEWS, settings, JAN)
        assert state.window_rolled is False


class TestByokExemption:
    def test_byok_user_is_never_metered(self):
        doc = free_user(user_api_key="sk-user-own-key", interviews_this_month=9999)
        state = usage.evaluate(doc, INTERVIEWS, settings, JAN)
        assert state.allowed is True
        assert state.exempt is True
        assert state.limit == UNLIMITED

    def test_empty_key_is_not_byok(self):
        doc = free_user(user_api_key="", interviews_this_month=9999)
        assert usage.evaluate(doc, INTERVIEWS, settings, JAN).allowed is False


class TestProPlan:
    def test_pro_is_unlimited_on_every_action(self):
        for action in usage.ALL_ACTIONS:
            doc = free_user(plan=PLAN_PRO, **{usage.counter_field(action): 100_000})
            state = usage.evaluate(doc, action, settings, JAN)
            assert state.allowed is True
            assert state.limit == UNLIMITED


class TestDefaultsAndErrors:
    def test_usage_defaults_cover_every_action(self):
        doc = usage.usage_defaults(JAN)
        assert doc["plan"] == PLAN_FREE
        for action in usage.ALL_ACTIONS:
            assert doc[usage.counter_field(action)] == 0
        assert doc["usage_reset_at"] == datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat()

    def test_missing_plan_defaults_to_free_not_unlimited(self):
        """A settings doc without `plan` must not accidentally grant PRO."""
        doc = free_user(interviews_this_month=settings.FREE_INTERVIEWS_PER_MONTH)
        doc.pop("plan")
        assert usage.evaluate(doc, INTERVIEWS, settings, JAN).allowed is False

    def test_unknown_action_is_a_programming_error(self):
        with pytest.raises(ValueError):
            usage.evaluate(free_user(), "teleportation", settings, JAN)

    def test_402_detail_carries_what_the_paywall_needs(self):
        doc = free_user(interviews_this_month=settings.FREE_INTERVIEWS_PER_MONTH)
        detail = usage.evaluate(doc, INTERVIEWS, settings, JAN).as_detail()
        assert detail["error"] == "quota_exceeded"
        assert detail["action"] == INTERVIEWS
        assert detail["limit"] == settings.FREE_INTERVIEWS_PER_MONTH
        assert detail["plan"] == PLAN_FREE
        assert "reset_at" in detail
        assert "API key" in detail["message"]   # BYOK is offered as an escape
