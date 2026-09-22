"""
Regression tests for firebase_db.py report-storage and pagination fixes.

- #32a: get_report_by_session must find a report via a direct Firestore
  query instead of relying on the caller to linearly scan get_user_reports
  (which only returns the 50 most-recent reports).
- #32c: save_interview_report must key the interview_reports doc on
  session_id, so a re-save overwrites instead of racing a query-then-write
  and creating a duplicate.
- #32b: list methods accept a `start_after` cursor for pagination, forwarded
  from the API layer, without changing default (no-cursor) behavior.
"""

from unittest.mock import MagicMock

from app.database.firebase_db import FirebaseManager


def _make_fb_with_mock_db():
    """A FirebaseManager instance with a mocked Firestore client, bypassing
    __init__ (which would otherwise require real Firebase credentials)."""
    fb = object.__new__(FirebaseManager)
    fb.db = MagicMock()
    return fb


def _mock_doc(data, doc_id="doc-1"):
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.id = doc_id
    return doc


class TestSaveInterviewReportDocId:
    def test_uses_session_id_as_document_id(self):
        """A report save keyed on session_id must write to
        interview_reports/{session_id}, not an auto-generated ID."""
        fb = _make_fb_with_mock_db()
        doc_ref = MagicMock()
        fb.db.collection.return_value.document.return_value = doc_ref

        report_id = fb.save_interview_report(
            user_id="user-1",
            session_id="session-xyz",
            report_data={"report_content": "Some report text"},
        )

        assert report_id == "session-xyz"
        fb.db.collection.return_value.document.assert_any_call("session-xyz")
        doc_ref.set.assert_called_once()
        saved_data = doc_ref.set.call_args[0][0]
        assert saved_data["session_id"] == "session-xyz"
        assert saved_data["report_content"] == "Some report text"

    def test_resave_overwrites_rather_than_querying_for_existing(self):
        """The old implementation queried for an existing doc before deciding
        whether to update or insert (a query-then-write race). Keying on
        session_id means .set() is idempotent — no query needed at all."""
        fb = _make_fb_with_mock_db()

        fb.save_interview_report(
            user_id="user-1",
            session_id="session-xyz",
            report_data={"report_content": "v1"},
        )
        fb.save_interview_report(
            user_id="user-1",
            session_id="session-xyz",
            report_data={"report_content": "v2"},
        )

        fb.db.collection.return_value.where.assert_not_called()

    def test_without_session_id_falls_back_to_auto_id(self):
        fb = _make_fb_with_mock_db()
        added_doc_ref = MagicMock()
        added_doc_ref.id = "auto-generated-id"
        fb.db.collection.return_value.add.return_value = (MagicMock(), added_doc_ref)

        report_id = fb.save_interview_report(
            user_id="user-1",
            session_id=None,
            report_data={"report_content": "Some report text"},
        )

        assert report_id == "auto-generated-id"


class TestGetReportBySession:
    def test_found_via_direct_query(self):
        fb = _make_fb_with_mock_db()
        doc = _mock_doc(
            {"user_id": "user-1", "session_id": "session-xyz", "report_content": "Text"},
            doc_id="report-1",
        )
        (
            fb.db.collection.return_value.where.return_value.where.return_value
            .limit.return_value.stream
        ).return_value = [doc]

        result = fb.get_report_by_session("user-1", "session-xyz")

        assert result["id"] == "report-1"
        assert result["report_content"] == "Text"

    def test_not_found_returns_none(self):
        fb = _make_fb_with_mock_db()
        (
            fb.db.collection.return_value.where.return_value.where.return_value
            .limit.return_value.stream
        ).return_value = []

        result = fb.get_report_by_session("user-1", "missing-session")

        assert result is None

    def test_firestore_error_returns_none_not_raises(self):
        fb = _make_fb_with_mock_db()
        fb.db.collection.side_effect = RuntimeError("Firestore unavailable")

        result = fb.get_report_by_session("user-1", "session-xyz")

        assert result is None


class TestPaginationCursor:
    """#32b: each list method takes an optional start_after cursor and only
    calls query.start_after when one is given, so existing (no-cursor)
    behavior is unchanged."""

    def test_get_user_interview_sessions_forwards_cursor(self):
        fb = _make_fb_with_mock_db()
        query = fb.db.collection.return_value.where.return_value.order_by.return_value
        query.start_after.return_value.limit.return_value.stream.return_value = []

        fb.get_user_interview_sessions("user-1", limit=10, start_after="2026-01-01T00:00:00")

        query.start_after.assert_called_once_with({"created_at": "2026-01-01T00:00:00"})

    def test_get_user_interview_sessions_no_cursor_skips_start_after(self):
        fb = _make_fb_with_mock_db()
        query = fb.db.collection.return_value.where.return_value.order_by.return_value
        query.limit.return_value.stream.return_value = []

        fb.get_user_interview_sessions("user-1", limit=10)

        query.start_after.assert_not_called()

    def test_get_user_reports_forwards_cursor(self):
        fb = _make_fb_with_mock_db()
        query = fb.db.collection.return_value.where.return_value.order_by.return_value
        query.start_after.return_value.limit.return_value.stream.return_value = []

        fb.get_user_reports("user-1", limit=10, start_after="2026-01-01T00:00:00")

        query.start_after.assert_called_once_with({"created_at": "2026-01-01T00:00:00"})

    def test_get_user_resume_analyses_forwards_cursor(self):
        fb = _make_fb_with_mock_db()
        query = fb.db.collection.return_value.where.return_value.order_by.return_value
        query.start_after.return_value.limit.return_value.stream.return_value = []

        fb.get_user_resume_analyses("user-1", limit=10, start_after="2026-01-01T00:00:00")

        query.start_after.assert_called_once_with({"created_at": "2026-01-01T00:00:00"})

    def test_list_user_dream_jobs_forwards_cursor(self):
        fb = _make_fb_with_mock_db()
        query = fb.db.collection.return_value.where.return_value.order_by.return_value
        query.start_after.return_value.limit.return_value.stream.return_value = []

        fb.list_user_dream_jobs("uid-1", limit=10, start_after="2026-01-01T00:00:00")

        query.start_after.assert_called_once_with({"created_at": "2026-01-01T00:00:00"})
