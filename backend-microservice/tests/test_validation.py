"""
Tests for file upload validation (_validate_upload helper).
Pure unit tests — no HTTP client, no Firebase mocks needed.
"""

import io
import pytest
from fastapi import HTTPException, UploadFile
from unittest.mock import AsyncMock


def _make_upload(filename: str, content: bytes) -> UploadFile:
    f = UploadFile(filename=filename, file=io.BytesIO(content))
    f.read = AsyncMock(return_value=content)
    return f


async def test_valid_txt_file():
    from app.server import _validate_upload
    content = b"some resume content"
    result = await _validate_upload(_make_upload("resume.txt", content), "resume")
    assert result == content


async def test_valid_pdf_file():
    from app.server import _validate_upload
    content = b"%PDF-1.4 fake pdf content"
    result = await _validate_upload(_make_upload("resume.pdf", content), "resume")
    assert result == content


async def test_invalid_extension_raises_400():
    from app.server import _validate_upload
    with pytest.raises(HTTPException) as exc:
        await _validate_upload(_make_upload("resume.docx", b"data"), "resume")
    assert exc.value.status_code == 400
    assert "PDF or TXT" in exc.value.detail


async def test_empty_file_raises_400():
    from app.server import _validate_upload
    with pytest.raises(HTTPException) as exc:
        await _validate_upload(_make_upload("resume.txt", b""), "resume")
    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail.lower()


async def test_oversized_file_raises_413():
    from app.server import _validate_upload
    big = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc:
        await _validate_upload(_make_upload("resume.txt", big), "resume")
    assert exc.value.status_code == 413
    assert "10 mb" in exc.value.detail.lower()
