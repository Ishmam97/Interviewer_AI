"""
Regression tests for the stale-analysis sweep (background-task durability).

Business rule: FastAPI BackgroundTasks run in-process. If the process is
killed or restarted mid-analysis, the Firestore doc is left in a non-terminal
status (`processing` / `normalizing` / `analyzing`) forever — the client polls
a status that will never change. sweep_stale_resume_analyses /
sweep_stale_dream_jobs fail those docs out once they've been stuck longer than
max_age_seconds, based on the `updated_at` heartbeat every step already writes.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.database.firebase_db import FirebaseManager


def _make_fb_with_mock_db():
    """A FirebaseManager instance with a mocked Firestore client, bypassing
    __init__ (which would otherwise require real Firebase credentials)."""
    fb = object.__new__(FirebaseManager)
    fb.db = MagicMock()
    return fb


def _mock_doc(data):
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


class TestSweepStaleResumeAnalyses:
    def test_sweeps_doc_stuck_past_threshold(self):
        fb = _make_fb_with_mock_db()
        stale_ts = (datetime.now() - timedelta(seconds=700)).isoformat()
        doc = _mock_doc({"status": "processing", "updated_at": stale_ts})
        fb.db.collection.return_value.where.return_value.stream.return_value = [doc]

        swept = fb.sweep_stale_resume_analyses(max_age_seconds=600)

        assert swept == 1
        doc.reference.update.assert_called_once()
        update_data = doc.reference.update.call_args[0][0]
        assert update_data["status"] == "failed"
        assert update_data["error"]

    def test_does_not_sweep_doc_within_threshold(self):
        """A doc that's still legitimately mid-analysis must not be failed out."""
        fb = _make_fb_with_mock_db()
        recent_ts = (datetime.now() - timedelta(seconds=30)).isoformat()
        doc = _mock_doc({"status": "processing", "updated_at": recent_ts})
        fb.db.collection.return_value.where.return_value.stream.return_value = [doc]

        swept = fb.sweep_stale_resume_analyses(max_age_seconds=600)

        assert swept == 0
        doc.reference.update.assert_not_called()

    def test_sweeps_doc_with_missing_timestamp(self):
        """A doc with no updated_at/created_at is treated as unrecoverable, not skipped."""
        fb = _make_fb_with_mock_db()
        doc = _mock_doc({"status": "processing"})
        fb.db.collection.return_value.where.return_value.stream.return_value = [doc]

        swept = fb.sweep_stale_resume_analyses(max_age_seconds=600)

        assert swept == 1

    def test_firestore_error_returns_zero_not_raises(self):
        """A sweep is best-effort infrastructure — it must never crash the caller."""
        fb = _make_fb_with_mock_db()
        fb.db.collection.side_effect = RuntimeError("Firestore unavailable")

        swept = fb.sweep_stale_resume_analyses(max_age_seconds=600)

        assert swept == 0


class TestSweepStaleDreamJobs:
    def test_sweeps_doc_stuck_past_threshold(self):
        fb = _make_fb_with_mock_db()
        stale_ts = (datetime.now() - timedelta(seconds=700)).isoformat()
        doc = _mock_doc({"status": "normalizing", "updated_at": stale_ts})
        fb.db.collection.return_value.where.return_value.stream.return_value = [doc]

        swept = fb.sweep_stale_dream_jobs(max_age_seconds=600)

        assert swept == 1
        doc.reference.update.assert_called_once()
        update_data = doc.reference.update.call_args[0][0]
        assert update_data["status"] == "failed"

    def test_does_not_sweep_doc_within_threshold(self):
        fb = _make_fb_with_mock_db()
        recent_ts = datetime.now().isoformat()
        doc = _mock_doc({"status": "analyzing", "updated_at": recent_ts})
        fb.db.collection.return_value.where.return_value.stream.return_value = [doc]

        swept = fb.sweep_stale_dream_jobs(max_age_seconds=600)

        assert swept == 0
        doc.reference.update.assert_not_called()
