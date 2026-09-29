import pytest
from app.telegram.formatting import markdown_to_telegram_html, strip_markdown


def test_markdown_to_telegram_html_headings_and_bold():
    raw = "📁 **Organization Knowledge Base**\n🏢 **Organization:** Slidio Inc"
    converted = markdown_to_telegram_html(raw)
    assert "<b>Organization Knowledge Base</b>" in converted
    assert "<b>Organization:</b>" in converted
    assert "**" not in converted


def test_markdown_to_telegram_html_code_and_filenames():
    raw = "📄 **slidio_technology_policy_2026.pdf**\n• ID: `2810c2d9-e7c9`\n• Delete: `/delete_doc <id>`"
    converted = markdown_to_telegram_html(raw)
    assert "<b>slidio_technology_policy_2026.pdf</b>" in converted
    assert "<code>2810c2d9-e7c9</code>" in converted
    assert "<code>/delete_doc &lt;id&gt;</code>" in converted
    assert "`" not in converted
    assert "**" not in converted


def test_markdown_to_telegram_html_escapes_special_chars():
    raw = "Formula: 5 < 10 & 20 > 15"
    converted = markdown_to_telegram_html(raw)
    assert "5 &lt; 10 &amp; 20 &gt; 15" in converted


def test_strip_markdown():
    raw = "📁 **Knowledge Base** with `code` and *notes*"
    stripped = strip_markdown(raw)
    assert stripped == "📁 Knowledge Base with code and notes"
