"""Unit tests for the /interview/prepare endpoint and WebSocket flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.server import app, get_current_user

DUMMY_TOKEN = "test-token"
AUTH_HEADER = {"Authorization": f"Bearer {DUMMY_TOKEN}"}


@pytest.fixture
def mock_current_user():
    user = MagicMock()
    user.uid = "test-uid-123"
    user.email = "test@example.com"
    # FastAPI resolves Depends(get_current_user) by object reference captured at
    # route-definition time, so patching the module attribute does nothing.
    # dependency_overrides is the supported way to inject a fake user.
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_firebase():
    fb = MagicMock()
    fb.verify_id_token.return_value = {"uid": "test-uid-123", "email": "test@example.com"}
    return fb


class TestInterviewPrepare:
    @pytest.mark.asyncio
    async def test_prepare_missing_api_key(self, mock_current_user):
        """Should return 500 when GEMINI_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/interview/prepare",
                    headers=AUTH_HEADER,
                    files={
                        "resume": ("resume.txt", b"My resume content", "text/plain"),
                        "job_description": ("jd.txt", b"Job description content", "text/plain"),
                    },
                    data={"interview_type": "Initial Screening", "max_questions": "3"},
                )
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_prepare_invalid_file_type(self, mock_current_user):
        """Should return 400 for non-PDF/TXT files."""
        mock_svc = AsyncMock()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("app.services.gemini_file_service.GeminiFileService", return_value=mock_svc):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/interview/prepare",
                    headers=AUTH_HEADER,
                    files={
                        "resume": ("resume.exe", b"binary", "application/octet-stream"),
                        "job_description": ("jd.txt", b"Job description", "text/plain"),
                    },
                    data={"interview_type": "Initial Screening", "max_questions": "3"},
                )
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_prepare_success(self, mock_current_user):
        """Should return session_id and question_count on success."""
        mock_file = MagicMock()
        mock_file.uri = "gs://bucket/file"
        mock_file.mime_type = "text/plain"
        mock_file.name = "test_file"

        mock_svc = AsyncMock()
        mock_svc.upload_file.return_value = mock_file
        mock_svc.generate_question_plan.return_value = [
            {"question": "Tell me about yourself.", "category": "background"},
            {"question": "Why this role?", "category": "motivation"},
        ]

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("app.services.gemini_file_service.GeminiFileService", return_value=mock_svc):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/interview/prepare",
                    headers=AUTH_HEADER,
                    files={
                        "resume": ("resume.txt", b"My resume", "text/plain"),
                        "job_description": ("jd.txt", b"Job description", "text/plain"),
                    },
                    data={"interview_type": "Initial Screening", "max_questions": "2"},
                )
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["question_count"] == 2
            assert data["interview_type"] == "Initial Screening"


class TestInterviewTypes:
    """Validate that interview type values flow through the system."""

    VALID_TYPES = [
        "Initial Screening",
        "Technical Coding Interview",
        "Technical System Design",
        "Behavioral Interview",
        "HR Culture Fit",
        "Case Interview",
        "Product Manager Interview",
        "Internship Interview",
        "Graduate School Interview",
    ]

    @pytest.mark.parametrize("interview_type", VALID_TYPES)
    @pytest.mark.asyncio
    async def test_valid_interview_types_accepted(self, mock_current_user, interview_type):
        """All defined interview types should be accepted by the prepare endpoint."""
        mock_file = MagicMock()
        mock_file.uri = "gs://bucket/file"
        mock_file.mime_type = "text/plain"
        mock_file.name = "f"

        mock_svc = AsyncMock()
        mock_svc.upload_file.return_value = mock_file
        mock_svc.generate_question_plan.return_value = [
            {"question": "Q1", "category": "general"},
        ]

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("app.services.gemini_file_service.GeminiFileService", return_value=mock_svc):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/interview/prepare",
                    headers=AUTH_HEADER,
                    files={
                        "resume": ("resume.txt", b"resume", "text/plain"),
                        "job_description": ("jd.txt", b"jd", "text/plain"),
                    },
                    data={"interview_type": interview_type, "max_questions": "1"},
                )
            assert response.status_code == 200
            assert response.json()["interview_type"] == interview_type
