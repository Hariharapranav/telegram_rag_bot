"""
Telegram message formatting and safe sending utilities.
Ensures rich HTML rendering without markdown parsing errors or raw symbols.
"""
import html
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def markdown_to_telegram_html(text: str) -> str:
    """
    Convert Markdown formatting (**bold**, *italic*, `code`, ```block```)
    into Telegram-compliant HTML tags. Safely escapes <, >, & to avoid syntax errors.
    """
    if not text:
        return ""

    # 1. Protect code blocks: ```lang\ncode\n```
    blocks = []
    def save_block(m):
        code_content = m.group(1)
        blocks.append(code_content)
        return f"___CODE_BLOCK_{len(blocks)-1}___"

    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```", save_block, text, flags=re.DOTALL)

    # 2. Protect inline code: `code`
    inlines = []
    def save_inline(m):
        code_content = m.group(1)
        inlines.append(code_content)
        return f"___INLINE_CODE_{len(inlines)-1}___"

    text = re.sub(r"`([^`\n]+)`", save_inline, text)

    # 3. HTML-escape text to neutralize literal <, >, &
    text = html.escape(text, quote=False)

    # 4. Bold: **text** -> <b>text</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # 5. Italic / bold single asterisks: *text* -> <b>text</b>
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<b>\1</b>", text)

    # 6. Links: [title](url) -> <a href="\2">\1</a>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Restore inline code
    for i, code in enumerate(inlines):
        escaped_code = html.escape(code, quote=False)
        text = text.replace(f"___INLINE_CODE_{i}___", f"<code>{escaped_code}</code>")

    # 8. Restore code blocks
    for i, code in enumerate(blocks):
        escaped_block = html.escape(code, quote=False)
        text = text.replace(f"___CODE_BLOCK_{i}___", f"<pre>{escaped_block}</pre>")

    return text


def strip_markdown(text: str) -> str:
    """
    Strip all markdown annotations (**bold**, `code`, etc.) to produce clean plain text
    without any raw asterisks, backticks, or formatting artifacts.
    """
    if not text:
        return ""
    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"\1", text)
    return text


async def safe_reply(msg, text: str, parse_mode: Optional[str] = None, reply_markup=None):
    """
    Safely send a reply to Telegram.
    Converts markdown to Telegram HTML for robust styling.
    If parsing fails, falls back to clean plain text without raw symbols.
    """
    if not text:
        return None

    html_text = markdown_to_telegram_html(text)
    try:
        return await msg.reply_text(html_text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.warning("HTML reply failed (%s). Retrying with clean plain text.", e)
        clean_text = strip_markdown(text)
        try:
            return await msg.reply_text(clean_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as exc:
            logger.error("Failed to send message: %s", exc)
            return None


async def safe_edit(query, text: str, parse_mode: Optional[str] = None, reply_markup=None):
    """
    Safely edit a callback query message with HTML or clean plain text fallback.
    """
    if not text:
        return None

    html_text = markdown_to_telegram_html(text)
    try:
        return await query.edit_message_text(html_text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.warning("HTML edit failed (%s). Retrying with clean plain text.", e)
        clean_text = strip_markdown(text)
        try:
            return await query.edit_message_text(clean_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as exc:
            logger.error("Failed to edit message: %s", exc)
            return None
