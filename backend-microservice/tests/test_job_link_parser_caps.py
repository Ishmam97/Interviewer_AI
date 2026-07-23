"""
Regression test: scraped JD text must be capped before it's later embedded in
an LLM prompt (dream_job_analyzer_service). An oversized/hostile page
shouldn't translate into unbounded token cost downstream.
"""

from bs4 import BeautifulSoup

from app.services.job_link_parser import _visible_text, _MAX_JD_TEXT_CHARS


def test_visible_text_caps_oversized_page():
    huge_body = "word " * 20000  # far larger than _MAX_JD_TEXT_CHARS
    soup = BeautifulSoup(f"<html><body>{huge_body}</body></html>", "html.parser")

    text = _visible_text(soup)

    assert len(text) <= _MAX_JD_TEXT_CHARS


def test_visible_text_leaves_normal_page_untouched():
    soup = BeautifulSoup(
        "<html><body><p>Software Engineer role at Acme Corp.</p></body></html>",
        "html.parser",
    )

    text = _visible_text(soup)

    assert text == "Software Engineer role at Acme Corp."
