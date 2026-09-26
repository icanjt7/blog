from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser


MIN_SOURCE_BODY_LENGTH = 500
ABSOLUTE_MIN_BODY_LENGTH = 200
SHORT_TITLE_LENGTH = 12
PERIODICAL_TITLE_RE = re.compile(
    r"^\s*\d{1,2}월.*(?:생활비|제철음식|동향|브리프|재난안전|탄소중립|소식지|월간|주간|신청방법|모집안내|결과발표)",
    re.IGNORECASE,
)
SPAMMY_TITLE_RE = re.compile(
    r"^\s*\d{1,2}월\s*(?:생활비|제철음식|동향|브리프|재난안전|탄소중립|소식지|월간|주간|신청방법|모집안내|결과발표)(?:\s|,|$)",
    re.IGNORECASE,
)
LEGACY_JUNK_SLUG_RE = re.compile(r"^\d{1,2}월-.+-[0-9a-f]{8}$", re.IGNORECASE)
BAD_KOREAN_HASH_SLUG_RE = re.compile(r"(?=.*[가-힣]).*-[0-9a-f]{8}$", re.IGNORECASE)
SAFE_GARBAGE_MONTH_HASH_RE = re.compile(
    r"^(?P<prefix>\d{1,2}월(?:-|$).*)-[0-9a-f]{8}$", re.IGNORECASE
)


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


def should_drop_post(post_data: dict[str, object]) -> tuple[bool, str]:
    """Apply the pre-render thin-content and unsafe-slug rules to a post payload.

    This API is intended for newly collected records. Existing published content
    uses :func:`is_legacy_junk_post`, which scopes the hash rule to recognizable
    monthly shells so a migration cannot remove valid legacy URLs in bulk.
    """
    title = visible_text(str(post_data.get("title") or ""))
    slug = str(post_data.get("slug") or "").strip().removesuffix(".html")
    raw_text = visible_text(str(post_data.get("body") or ""))
    text_length = len(raw_text)

    if text_length < ABSOLUTE_MIN_BODY_LENGTH:
        return True, f"Skip: 본문 텍스트 부족 (현재 {text_length}자)"

    is_spammy_title = bool(SPAMMY_TITLE_RE.search(title))
    is_short_title = len(title) < SHORT_TITLE_LENGTH
    if (is_spammy_title or is_short_title) and text_length < MIN_SOURCE_BODY_LENGTH:
        reason = "단답형 스팸 제목" if is_spammy_title else "제목 12자 미만"
        return True, f"Skip: {reason} + 본문 부실 (현재 {text_length}자)"

    if slug and BAD_KOREAN_HASH_SLUG_RE.fullmatch(slug):
        return True, f"Skip: 한글 슬러그 + 비정상 헥사 해시값 감지 ({slug})"

    return False, "Pass: 정상적인 고품질 데이터"


def is_safe_legacy_garbage_slug(slug: str) -> bool:
    """Match only short month-prefixed legacy slugs with an opaque hash."""
    normalized = slug.strip().removesuffix(".html")
    match = SAFE_GARBAGE_MONTH_HASH_RE.fullmatch(normalized)
    if not match:
        return False
    prefix = match.group("prefix")
    if re.fullmatch(r"[a-z0-9-]+", prefix, flags=re.IGNORECASE):
        return False
    compact_length = len(re.sub(r"[-_\s]", "", prefix))
    return compact_length < 10 and compact_length < 15


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
    if is_safe_legacy_garbage_slug(slug):
        return True
    clean_title = visible_text(title)
    is_periodical_shell = bool(SPAMMY_TITLE_RE.search(clean_title))
    if not is_periodical_shell:
        return False
    normalized_slug = slug.removesuffix(".html")
    return bool(
        LEGACY_JUNK_SLUG_RE.fullmatch(normalized_slug)
        or BAD_KOREAN_HASH_SLUG_RE.fullmatch(normalized_slug)
    )
