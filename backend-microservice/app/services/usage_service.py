"""
Per-user monthly usage quotas for the LLM-cost routes (Phase C, #26).

Design notes:

* State lives on the existing `user_settings` document, not a new collection.
  That doc is already fetched on the hot path for BYOK resolution, so metering
  costs no extra read.
* Counters are per calendar month in UTC. `usage_reset_at` holds the instant
  the current window ends; the first request after that rolls the window over
  lazily, so no scheduled job is needed.
* **BYOK users are exempt.** A user with their own API key pays the provider
  directly — metering them would be charging twice for one call. This is a
  deliberate product decision (roadmap §5), not an oversight.
* This module is pure: it reads a settings dict and returns a decision. All
  persistence lives in FirebaseManager, which keeps the rules unit-testable
  without Firestore.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

UNLIMITED = -1

# Metered actions. The value is also the counter's field-name stem on the
# user_settings doc, so adding an action needs no mapping table.
INTERVIEWS = "interviews"
RESUME_ANALYSES = "resume_analyses"
DREAM_JOBS = "dream_jobs"
SUGGESTION_APPLIES = "suggestion_applies"

ALL_ACTIONS = (INTERVIEWS, RESUME_ANALYSES, DREAM_JOBS, SUGGESTION_APPLIES)

PLAN_FREE = "free"
PLAN_PRO = "pro"


def counter_field(action: str) -> str:
    """Firestore field holding this action's count for the current window."""
    return f"{action}_this_month"


def usage_defaults(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fields a freshly-created user_settings doc needs for metering."""
    doc: Dict[str, Any] = {
        "plan": PLAN_FREE,
        "subscription_status": "none",
        "usage_reset_at": next_reset_at(now).isoformat(),
    }
    for action in ALL_ACTIONS:
        doc[counter_field(action)] = 0
    return doc


def next_reset_at(now: Optional[datetime] = None) -> datetime:
    """Start of the next calendar month, UTC.

    A fixed month boundary (rather than 30 days from signup) means every user's
    window rolls at the same moment, which makes support questions answerable
    without per-user arithmetic.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)


def _parse_reset_at(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def window_expired(user_settings: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True when the stored window has ended and counters should roll over.

    A missing or unparseable `usage_reset_at` counts as expired: existing users
    predate metering and must get a clean window rather than being locked out.
    """
    now = now or datetime.now(timezone.utc)
    reset_at = _parse_reset_at(user_settings.get("usage_reset_at"))
    if reset_at is None:
        return True
    return now >= reset_at


def limit_for(plan: str, action: str, settings_obj: Any) -> int:
    """Monthly allowance for a plan/action. PRO is unlimited on every action."""
    if plan == PLAN_PRO:
        return UNLIMITED
    return {
        INTERVIEWS: settings_obj.FREE_INTERVIEWS_PER_MONTH,
        RESUME_ANALYSES: settings_obj.FREE_RESUME_ANALYSES_PER_MONTH,
        DREAM_JOBS: settings_obj.FREE_DREAM_JOBS_PER_MONTH,
        SUGGESTION_APPLIES: settings_obj.FREE_SUGGESTION_APPLIES_PER_MONTH,
    }[action]


@dataclass(frozen=True)
class QuotaState:
    action: str
    allowed: bool
    used: int
    limit: int          # UNLIMITED (-1) means no ceiling
    plan: str
    reset_at: str
    exempt: bool        # True when BYOK bypassed metering
    window_rolled: bool # True when this evaluation rolled the window over

    def as_detail(self) -> Dict[str, Any]:
        """Body for the 402 — everything the UI needs to render a paywall."""
        return {
            "error": "quota_exceeded",
            "action": self.action,
            "used": self.used,
            "limit": self.limit,
            "plan": self.plan,
            "reset_at": self.reset_at,
            "message": (
                f"You've used all {self.limit} of this month's "
                f"{self.action.replace('_', ' ')} on the free plan. "
                "Upgrade, or add your own API key in Settings, to continue."
            ),
        }


def evaluate(
    user_settings: Dict[str, Any],
    action: str,
    settings_obj: Any,
    now: Optional[datetime] = None,
) -> QuotaState:
    """Decide whether `action` may proceed for this user, right now."""
    if action not in ALL_ACTIONS:
        raise ValueError(f"unknown metered action: {action}")

    now = now or datetime.now(timezone.utc)
    plan = user_settings.get("plan") or PLAN_FREE
    rolled = window_expired(user_settings, now)
    reset_at = (
        next_reset_at(now) if rolled else _parse_reset_at(user_settings["usage_reset_at"])
    )
    used = 0 if rolled else int(user_settings.get(counter_field(action)) or 0)

    # BYOK: the user is paying the provider themselves.
    if user_settings.get("user_api_key"):
        return QuotaState(
            action=action, allowed=True, used=used, limit=UNLIMITED, plan=plan,
            reset_at=reset_at.isoformat(), exempt=True, window_rolled=rolled,
        )

    limit = limit_for(plan, action, settings_obj)
    allowed = limit == UNLIMITED or used < limit

    return QuotaState(
        action=action, allowed=allowed, used=used, limit=limit, plan=plan,
        reset_at=reset_at.isoformat(), exempt=False, window_rolled=rolled,
    )
