from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser


MIN_SOURCE_BODY_LENGTH = 500
PERIODICAL_TITLE_RE = re.compile(
    r"^\s*\d{1,2}월.*(?:동향|브리프|재난안전|탄소중립|소식지|월간)",
    re.IGNORECASE,
)
LEGACY_JUNK_SLUG_RE = re.compile(r"^\d{1,2}월-.+-[0-9a-f]{8}$", re.IGNORECASE)


class InvalidContentData(ValueError):
    """Raised when source or model output must never become a post."""


class _VisibleTextParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


@dataclass(frozen=True)
class ContentDecision:
    accepted: bool
    raw_text: str
    reason: str = ""


def visible_text(value: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(str(value or ""))
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def evaluate_source_content(
    title: str,
    body: str,
    *,
    min_length: int = MIN_SOURCE_BODY_LENGTH,
) -> ContentDecision:
    raw_text = visible_text(body)
    if len(raw_text) >= min_length:
        return ContentDecision(True, raw_text)
    if PERIODICAL_TITLE_RE.search(visible_text(title)):
        reason = "Skip: Insufficient body length (월간 동향)"
    else:
        reason = f"Skip: Insufficient body length ({len(raw_text)} chars)"
    return ContentDecision(False, raw_text, reason)


def require_source_content(
    title: str,
    body: str,
    *,
    logger: logging.Logger | None = None,
    min_length: int = MIN_SOURCE_BODY_LENGTH,
) -> str:
    decision = evaluate_source_content(title, body, min_length=min_length)
    if decision.accepted:
        return decision.raw_text
    (logger or logging.getLogger(__name__)).warning(decision.reason)
    raise InvalidContentData(decision.reason)


def is_legacy_junk_post(title: str, slug: str, body: str) -> bool:
    """Reject known monthly-keyword/hash shells that predate the source filter."""
    if not PERIODICAL_TITLE_RE.search(visible_text(title)):
        return False
    if not LEGACY_JUNK_SLUG_RE.fullmatch(slug):
        return False
    markers = (
        "월별 반복 검색 수요가 있는 evergreen 키워드",
        "공식 포털",
        "원문에서 확인할 내용",
    )
    return sum(marker in body for marker in markers) >= 2
