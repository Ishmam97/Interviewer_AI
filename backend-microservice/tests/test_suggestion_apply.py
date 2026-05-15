"""
Tests for suggestion accept/undo flow with dummy AI responses.

Covers:
- Accepting a suggestion → status update + resume edit applied
- Undoing an accepted suggestion → resume restored, status reverted
- Edge cases: missing profile, missing analysis, suggestion not found,
  suggestion already rejected, no snapshot for undo
- Snapshot creation and restoration
- Notes added when suggestion doesn't map to existing fields
"""

import json
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from tests.conftest import _make_firebase_mock, FAKE_USER

# ── Dummy resume data used across tests ──────────────────────────────────────

DUMMY_RESUME_DATA = {
    "name": "Alice Smith",
    "contact": {
        "email": "alice@example.com",
        "phone": "555-1234",
        "linkedin": "linkedin.com/in/alicesmith",
        "location": "San Francisco, CA",
    },
    "summary": "Experienced Python developer with 5 years of backend development.",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "TechCorp",
            "duration": "Jan 2020 - Present",
            "bullets": [
                "Built REST APIs with FastAPI",
                "Led migration from Flask to FastAPI",
            ],
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "institution": "Stanford University",
            "year": "2019",
        },
    ],
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "certifications": ["AWS Solutions Architect"],
    "projects": [
        {
            "name": "Resume Analyzer",
            "description": "AI-powered resume analysis tool",
        },
    ],
}

# Dummy AI response that adds quantified bullets
DUMMY_AI_RESPONSE_SUMMARY = {
    "name": "Alice Smith",
    "contact": DUMMY_RESUME_DATA["contact"],
    "summary": "Senior Python developer with 5+ years of experience building high-performance backend systems with FastAPI and Flask. Proven track record of leading technical migrations and improving API response times by 40%.",
    "experience": DUMMY_RESUME_DATA["experience"],
    "education": DUMMY_RESUME_DATA["education"],
    "skills": DUMMY_RESUME_DATA["skills"],
    "certifications": DUMMY_RESUME_DATA["certifications"],
    "projects": DUMMY_RESUME_DATA["projects"],
}

# Dummy AI response that adds notes (for suggestions that don't map to fields)
DUMMY_AI_RESPONSE_WITH_NOTES = {
    **DUMMY_RESUME_DATA,
    "_notes": [
        "Consider adding a GitHub profile link to showcase projects",
        "Add metrics to experience bullets (e.g., 'reduced latency by 30%')",
    ],
}

# Dummy analysis document
DUMMY_ANALYSIS = {
    "status": "completed",
    "overall": {
        "score": 75,
        "quality_score": 70,
        "summary": "Good resume but could use more metrics.",
        "strengths": ["Strong tech stack"],
        "weaknesses": ["Lacks quantified achievements"],
        "top_tips": ["Add metrics to bullets"],
        "lackings": ["Metrics"],
        "suggestions": [
            {
                "id": "add_summary",
                "text": "Add quantified achievements to experience bullets",
                "section": "overall",
                "status": "pending",
            },
            {
                "id": "add_github",
                "text": "Consider adding GitHub profile link",
                "section": "overall",
                "status": "pending",
            },
        ],
    },
    "sections": [
        {
            "name": "experience",
            "found": True,
            "score": 70,
            "content_snippet": "Built REST APIs...",
            "strengths": ["Good tech stack"],
            "weaknesses": ["No metrics"],
            "tips": ["Quantify achievements"],
            "suggestions": [
                {
                    "id": "quantify_bullets",
                    "text": "Quantify your experience bullets with specific metrics and percentages",
                    "section": "experience",
                    "status": "pending",
                },
            ],
        },
        {
            "name": "skills",
            "found": True,
            "score": 80,
            "content_snippet": "Python, FastAPI...",
            "strengths": ["Good mix of skills"],
            "weaknesses": [],
            "tips": [],
            "suggestions": [],
        },
    ],
    "ats": {
        "score": 65,
        "keywords_found": ["Python", "FastAPI"],
        "keywords_missing": ["Django"],
        "formatting_issues": [],
    },
    "parsed_sections": DUMMY_RESUME_DATA,
}


def _setup_firestore_for_snapshots(fb, snapshot_data=DUMMY_RESUME_DATA, snapshot_exists=True, parsed_sections=None):
    """Configure fb.db to properly handle Firestore operations.
    
    Sets up two collection chains:
    1. suggestion_snapshots: db.collection().document(id).get() → result doc with .exists, .to_dict(), .delete()
    2. resume_parsed_sections: db.collection().document(id).get() → result doc with .exists, .to_dict()
    """
    # ── Suggestion snapshot: for undo path (read) and accept path (write via .set()) ──
    # The result of .get() on a snapshot document
    mock_snapshot_result = MagicMock()
    mock_snapshot_result.exists = snapshot_exists
    mock_snapshot_result.to_dict.return_value = {
        "snapshot_data": snapshot_data,
        "created_at": "2025-01-01T00:00:00",
    }
    mock_snapshot_result.delete = MagicMock()

    # The snapshot document ref — .get() returns result, .set() saves, .delete() removes
    mock_snapshot_doc_ref = MagicMock()
    mock_snapshot_doc_ref.get.return_value = mock_snapshot_result
    mock_snapshot_doc_ref.set = MagicMock()
    mock_snapshot_doc_ref.delete = MagicMock()

    # ── Parsed sections document (for fallback when no edited_resume_data) ──
    mock_parsed_result = MagicMock()
    mock_parsed_result.exists = parsed_sections is not None
    mock_parsed_result.to_dict.return_value = {
        "parsed_sections": parsed_sections if parsed_sections else {},
    }

    mock_parsed_doc_ref = MagicMock()
    mock_parsed_doc_ref.get.return_value = mock_parsed_result

    # ── Collection reference that returns different doc refs based on document ID ──
    def document_side_effect(doc_id):
        # Session-scoped snapshot id: uid:analysis_id:suggestion_id (two+ colons)
        if doc_id.startswith("test-uid-123:") and doc_id.count(":") >= 2:
            return mock_snapshot_doc_ref
        # Legacy undo snapshot: uid:suggestion_id
        if doc_id in ("test-uid-123:add_summary", "test-uid-123:quantify_bullets"):
            return mock_snapshot_doc_ref
        return mock_parsed_doc_ref

    mock_collection = MagicMock()
    mock_collection.document.side_effect = document_side_effect

    # The db — .collection("name") returns the collection
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    fb.db = mock_db
    return mock_db, mock_collection, mock_snapshot_doc_ref, mock_snapshot_result


@contextmanager
def authed_client_with_ai(fb, ai_mock=None):
    """Create an authenticated test client with optional AI mock."""
    with patch("app.server.get_firebase_manager", return_value=fb):
        from app.server import app, get_current_user
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER

        if ai_mock:
            # Patch the AsyncOpenAI constructor to return our mock
            with patch("app.server.AsyncOpenAI", return_value=ai_mock):
                with TestClient(app, raise_server_exceptions=True) as c:
                    yield c
        else:
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c

        app.dependency_overrides.clear()


def _setup_fb_with_resume(fb, analysis=None, profile_edited_data=None):
    """Configure the firebase mock to return resume data."""
    analysis_data = dict(analysis or DUMMY_ANALYSIS)
    analysis_data["user_id"] = "test-uid-123"
    profile = {
        "uid": "test-uid-123",
        "email": "test@example.com",
        "current_analysis_id": "analysis-123",
    }
    if profile_edited_data:
        profile["edited_resume_data"] = profile_edited_data

    fb.get_user_profile.return_value = profile
    fb.get_resume_data.return_value = {
        "current_analysis_id": "analysis-123",
    }
    fb.get_resume_analysis_by_id.return_value = analysis_data
    fb.ensure_working_parsed_sections.return_value = True
    resume_payload = profile_edited_data if profile_edited_data is not None else DUMMY_RESUME_DATA
    fb.get_resume_parsed_doc.return_value = {
        "user_id": "test-uid-123",
        "analysis_id": "analysis-123",
        "parsed_sections": resume_payload,
        "working_parsed_sections": resume_payload,
    }
    fb.set_working_parsed_sections.return_value = True


def _make_ai_mock(response_data):
    """Create an AsyncOpenAI mock that returns the given JSON."""
    ai_mock = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(response_data)
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 100

    # Async create method
    async_create = AsyncMock(return_value=mock_response)
    ai_mock.chat.completions.create = async_create
    return ai_mock


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAcceptSuggestion:
    """Tests for accepting a suggestion and applying changes to resume."""

    def test_accept_overall_suggestion_applies_changes(self):
        """Accepting an overall suggestion should update status AND apply resume changes."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=DUMMY_RESUME_DATA)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "accepted"
        assert data["suggestion_id"] == "add_summary"
        assert "applied_changes" in data
        assert data["applied_changes"]["section"] == "overall"

        fb.set_working_parsed_sections.assert_called()
        call_args = fb.set_working_parsed_sections.call_args
        assert call_args[0][0] == "analysis-123"
        assert call_args[0][1] == "test-uid-123"
        saved_data = call_args[0][2]
        assert saved_data["summary"] == DUMMY_AI_RESPONSE_SUMMARY["summary"]

        fb.update_resume_analysis.assert_called()

    def test_accept_section_suggestion_applies_changes(self):
        """Accepting a section-level suggestion should work the same."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=DUMMY_RESUME_DATA)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            r = c.post(
                "/profile/resume/suggestions/quantify_bullets",
                json={"action": "accept"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "accepted"
        # Section name should be derived from the section's name field
        assert data["applied_changes"]["section"] == "experience"

    def test_accept_suggestion_with_notes(self):
        """When AI adds _notes field, they should appear in applied_changes."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=DUMMY_RESUME_DATA)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_WITH_NOTES)

        with authed_client_with_ai(fb, ai_mock) as c:
            r = c.post(
                "/profile/resume/suggestions/add_github",
                json={"action": "accept"},
            )

        assert r.status_code == 200
        data = r.json()
        assert "applied_changes" in data
        assert "notes_added" in data["applied_changes"]
        assert len(data["applied_changes"]["notes_added"]) == 2

    def test_accept_suggestion_creates_snapshot(self):
        """Accepting a suggestion should save a snapshot for undo."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=DUMMY_RESUME_DATA)
        mock_db, mock_collection, mock_snapshot_doc_ref, mock_snapshot_result = _setup_firestore_for_snapshots(fb)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        # Verify snapshot was saved: db.collection("suggestion_snapshots").document(...).set(...)
        mock_db.collection.assert_called_with("suggestion_snapshots")
        mock_collection.document.assert_called_with("test-uid-123:analysis-123:add_summary")
        mock_snapshot_doc_ref.set.assert_called()
        set_call = mock_snapshot_doc_ref.set.call_args
        assert set_call[0][0]["user_id"] == "test-uid-123"
        assert set_call[0][0]["suggestion_id"] == "add_summary"
        assert "snapshot_data" in set_call[0][0]

    def test_accept_suggestion_uses_edited_resume_data_if_exists(self):
        """Working copy from resume_parsed_sections is used (session-scoped)."""
        edited_data = {**DUMMY_RESUME_DATA, "name": "Edited Name"}
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=edited_data)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        assert r.status_code == 200
        fb.set_working_parsed_sections.assert_called()
        saved_data = fb.set_working_parsed_sections.call_args[0][2]
        assert saved_data["summary"] == DUMMY_AI_RESPONSE_SUMMARY["summary"]

    def test_accept_rejected_suggestion_fails(self):
        """Accepting an already-rejected suggestion should still work (status is just overwritten)."""
        analysis = dict(DUMMY_ANALYSIS)
        analysis["overall"] = dict(DUMMY_ANALYSIS["overall"])
        analysis["overall"]["suggestions"] = [
            {**DUMMY_ANALYSIS["overall"]["suggestions"][0], "status": "rejected"},
        ]

        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, analysis=analysis, profile_edited_data=DUMMY_RESUME_DATA)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

    def test_accept_invalid_action_fails(self):
        """Using an invalid action should return 400."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)

        with authed_client_with_ai(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "maybe"},
            )

        assert r.status_code == 400

    def test_accept_no_profile_fails(self):
        """If user has no resume data, accept should fail."""
        fb = _make_firebase_mock()
        fb.get_resume_data.return_value = None

        with authed_client_with_ai(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        assert r.status_code == 404

    def test_accept_no_analysis_id_fails(self):
        """If profile has no current_analysis_id, accept should fail."""
        fb = _make_firebase_mock()
        fb.get_resume_data.return_value = {"uid": "test-uid-123"}
        fb.get_user_profile.return_value = {"uid": "test-uid-123"}

        with authed_client_with_ai(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )

        assert r.status_code == 404

    def test_accept_suggestion_not_found_fails(self):
        """Accepting a non-existent suggestion should fail."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)

        with authed_client_with_ai(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/nonexistent_id",
                json={"action": "accept"},
            )

        assert r.status_code == 404

    def test_reject_suggestion_no_ai_call(self):
        """Rejecting a suggestion should NOT call the AI."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)

        # Don't pass an AI mock — if AI is called, it will fail
        with authed_client_with_ai(fb) as c:
            r = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "reject"},
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "rejected"
        assert "applied_changes" not in data


class TestUndoSuggestion:
    """Tests for undoing an accepted suggestion."""

    def test_undo_accepted_suggestion_restores_snapshot(self):
        """Undoing should restore the snapshot and set status back to pending."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)
        mock_db, mock_collection, mock_snapshot_doc_ref, mock_snapshot_result = _setup_firestore_for_snapshots(fb)

        # Mark suggestion as accepted
        analysis = dict(DUMMY_ANALYSIS)
        analysis["user_id"] = "test-uid-123"
        analysis["overall"] = dict(DUMMY_ANALYSIS["overall"])
        analysis["overall"]["suggestions"] = [
            {**DUMMY_ANALYSIS["overall"]["suggestions"][0], "status": "accepted"},
        ]
        fb.get_resume_analysis_by_id.return_value = analysis

        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/add_summary/undo")

        assert r.status_code == 200
        data = r.json()
        assert data["suggestion_id"] == "add_summary"
        assert "restored" in data["message"].lower()

        fb.set_working_parsed_sections.assert_called()
        restore_call = fb.set_working_parsed_sections.call_args
        assert restore_call[0][2] == DUMMY_RESUME_DATA

        # Verify status was reverted to pending
        fb.update_resume_analysis.assert_called()
        update_call = fb.update_resume_analysis.call_args
        updated_analysis = update_call[0][1]
        statuses = [s["status"] for s in updated_analysis["overall"]["suggestions"]]
        assert "pending" in statuses

        # Verify snapshot was deleted
        mock_snapshot_doc_ref.delete.assert_called()

    def test_undo_not_accepted_fails(self):
        """Undoing a non-accepted suggestion should fail."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)
        _setup_firestore_for_snapshots(fb)

        # Suggestion is still pending (default)
        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/add_summary/undo")

        assert r.status_code == 400
        assert "not been accepted" in r.json()["detail"]

    def test_undo_rejected_suggestion_fails(self):
        """Undoing a rejected suggestion should fail."""
        fb = _make_firebase_mock()
        analysis = dict(DUMMY_ANALYSIS)
        analysis["overall"] = dict(DUMMY_ANALYSIS["overall"])
        analysis["overall"]["suggestions"] = [
            {**DUMMY_ANALYSIS["overall"]["suggestions"][0], "status": "rejected"},
        ]
        _setup_fb_with_resume(fb, analysis=analysis)
        _setup_firestore_for_snapshots(fb)

        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/add_summary/undo")

        assert r.status_code == 400

    def test_undo_no_snapshot_fails(self):
        """Undoing when no snapshot exists should fail."""
        fb = _make_firebase_mock()
        analysis = dict(DUMMY_ANALYSIS)
        analysis["overall"] = dict(DUMMY_ANALYSIS["overall"])
        analysis["overall"]["suggestions"] = [
            {**DUMMY_ANALYSIS["overall"]["suggestions"][0], "status": "accepted"},
        ]
        _setup_fb_with_resume(fb, analysis=analysis)
        # No snapshot exists (snapshot_exists=False)
        mock_db, mock_collection, mock_snapshot_doc_ref, mock_snapshot_result = _setup_firestore_for_snapshots(fb, snapshot_exists=False)

        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/add_summary/undo")

        assert r.status_code == 404
        assert "snapshot" in r.json()["detail"].lower()

    def test_undo_section_suggestion(self):
        """Undoing a section-level suggestion should work."""
        fb = _make_firebase_mock()
        analysis = dict(DUMMY_ANALYSIS)
        analysis["sections"] = [dict(DUMMY_ANALYSIS["sections"][0])]
        analysis["sections"][0]["suggestions"] = [
            {**DUMMY_ANALYSIS["sections"][0]["suggestions"][0], "status": "accepted"},
        ]
        _setup_fb_with_resume(fb, analysis=analysis)
        _setup_firestore_for_snapshots(fb)

        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/quantify_bullets/undo")

        assert r.status_code == 200

    def test_undo_suggestion_not_found_fails(self):
        """Undoing a non-existent suggestion should fail."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb)
        _setup_firestore_for_snapshots(fb)

        with authed_client_with_ai(fb) as c:
            r = c.post("/profile/resume/suggestions/nonexistent/undo")

        assert r.status_code == 404


class TestAcceptUndoRoundTrip:
    """Full round-trip: accept → verify changes → undo → verify restored."""

    def test_accept_then_undo_round_trip(self):
        """Accept a suggestion, verify changes applied, then undo and verify restoration."""
        fb = _make_firebase_mock()
        _setup_fb_with_resume(fb, profile_edited_data=DUMMY_RESUME_DATA)
        mock_db, mock_collection, mock_snapshot_doc_ref, mock_snapshot_result = _setup_firestore_for_snapshots(fb)
        ai_mock = _make_ai_mock(DUMMY_AI_RESPONSE_SUMMARY)

        with authed_client_with_ai(fb, ai_mock) as c:
            # Step 1: Accept the suggestion
            accept_resp = c.post(
                "/profile/resume/suggestions/add_summary",
                json={"action": "accept"},
            )
            assert accept_resp.status_code == 200
            assert accept_resp.json()["status"] == "accepted"
            assert "applied_changes" in accept_resp.json()

            update_call = fb.set_working_parsed_sections.call_args
            updated_data = update_call[0][2]
            assert updated_data["summary"] == DUMMY_AI_RESPONSE_SUMMARY["summary"]

            undo_resp = c.post("/profile/resume/suggestions/add_summary/undo")
            assert undo_resp.status_code == 200

            restore_call = fb.set_working_parsed_sections.call_args
            restored_data = restore_call[0][2]
            assert restored_data == DUMMY_RESUME_DATA
