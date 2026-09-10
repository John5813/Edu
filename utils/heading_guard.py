"""Keep AI body text from repeating the heading the document builder prints.

The builders (`services/document_service.py`) write every section heading
themselves and then drop the model's text underneath it. When the model also
opens with that heading the reader sees it twice.

Cutting any prefix that matches the title is what made the output *wrong*
rather than merely repetitive: a normal opening sentence usually starts with
the section subject ("Mehnat iqtisodiyoti fanining asosiy vazifasi ..."), and
cutting the matching words leaves a headless fragment. So a leading span is
removed only when it stands alone as a heading — its own line, or its own
sentence — never when it continues into the sentence.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

_LABEL = r"bob|bo['ʻ’`]?lim|qism|mavzu|chapter|section|part|глава|раздел|часть"
# "BOB 1.", "Chapter 2)", "Глава 3"
_LABEL_PREFIX = re.compile(rf"^\s*(?:{_LABEL})\s+[\dIVXLCDM]+\s*[.)]?\s*", re.IGNORECASE)
# "1-BOB.", "II bob", "1-bo'lim" — the form Uzbek documents actually use
_NUMBERED_LABEL_PREFIX = re.compile(
    rf"^\s*[\dIVXLCDM]+\s*[-–—]?\s*(?:{_LABEL})\s*[.)]?\s*", re.IGNORECASE
)
_NUMBER_PREFIX = re.compile(r"^\s*(?:\d+|[IVXLCDM]+)(?:\s*[.)]\s*\d+)*\s*[.)]?\s+")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"[.!?]")

# Below this length a "title" is too generic to match on safely.
_MIN_TITLE_CHARS = 6
# A strip that leaves less than this much text means we cut real content.
_MIN_REMAINDER_CHARS = 40

_HEADING_RULE = {
    "uz": (
        "- Sarlavha hujjatda ALLAQACHON chop etilgan — siz faqat uning ostidagi "
        "matnni yozasiz. Sarlavhani alohida satr yoki alohida gap sifatida "
        "qaytarmang, birinchi jumlani to'liq, kesimi bor gap bilan boshlang"
    ),
    "ru": (
        "- Заголовок УЖЕ напечатан в документе — вы пишете только текст под ним. "
        "Не повторяйте заголовок отдельной строкой или отдельным предложением; "
        "первое предложение должно быть полным, со сказуемым"
    ),
    "en": (
        "- The heading is ALREADY printed in the document — you write only the body "
        "text below it. Do not repeat the heading as its own line or its own "
        "sentence; start with a complete first sentence that has a verb"
    ),
}


def heading_rule(language: str) -> str:
    """The prompt line that tells the model the heading is already on the page."""
    return _HEADING_RULE.get(language, _HEADING_RULE["uz"])


def _normalize(value: str) -> str:
    value = _LABEL_PREFIX.sub("", value.strip())
    value = _NUMBERED_LABEL_PREFIX.sub("", value)
    value = _NUMBER_PREFIX.sub("", value)
    value = value.lower()
    for apostrophe in ("ʻ", "’", "`", "‘"):
        value = value.replace(apostrophe, "'")
    value = _PUNCTUATION.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()


def _heading_span(text: str, titles: set) -> Optional[int]:
    """End index of a leading standalone heading, or None if there isn't one."""
    newline = text.find("\n")
    if newline != -1 and _normalize(text[:newline]) in titles:
        return newline

    sentence_end = _SENTENCE_END.search(text)
    if sentence_end:
        head = text[: sentence_end.start()]
        if "\n" not in head and _normalize(head) in titles:
            return sentence_end.end()

    return None


def strip_echoed_heading(text: str, titles: Iterable[str], max_passes: int = 4) -> str:
    """Drop heading echoes from the front of `text`.

    Call this *before* collapsing newlines — a heading on its own line is the
    clearest signal there is, and flattening the text destroys it.
    """
    if not text:
        return text

    normalized = {
        candidate
        for candidate in (_normalize(title) for title in titles if title)
        if len(candidate) >= _MIN_TITLE_CHARS
    }
    if not normalized:
        return text.strip()

    result = text.strip()
    for _ in range(max_passes):
        span = _heading_span(result, normalized)
        if span is None:
            break
        remainder = result[span:].lstrip(" \t\r\n.:;—–-")
        if len(remainder) < _MIN_REMAINDER_CHARS:
            break
        result = remainder

    return result.strip()
