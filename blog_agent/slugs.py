from __future__ import annotations

import re
from datetime import date


class UnsafeSlugError(ValueError):
    """Raised instead of publishing a meaningless short/hash slug."""


_CATEGORY_EN = {
    "정책": "policy", "환경": "environment", "생활": "living", "기술": "technology",
    "정치": "politics", "스포츠": "sports", "핫이슈": "news",
}
_KEYWORD_EN = {
    "탄소중립": "carbon-neutral", "재난안전": "disaster-safety", "동향": "trends",
    "브리프": "brief", "소식지": "newsletter", "월간": "monthly", "정책": "policy",
    "지원금": "benefit", "복지": "welfare", "공모": "contest", "모집": "recruitment",
    "인공지능": "artificial-intelligence", "기술": "technology", "안전": "safety",
}
_MONTH_EN = {
    "01": "january", "02": "february", "03": "march", "04": "april",
    "05": "may", "06": "june", "07": "july", "08": "august",
    "09": "september", "10": "october", "11": "november", "12": "december",
}


def slugify_words(value: str, *, max_length: int = 64, fallback: str = "post") -> str:
    """URL 슬러그를 단어 경계에서 줄여 마지막 토큰이 잘리지 않게 만든다."""

    normalized = re.sub(r"[^\w가-힣]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        return fallback
    if len(normalized) <= max_length:
        return normalized

    kept: list[str] = []
    length = 0
    for token in normalized.split("-"):
        next_length = length + (1 if kept else 0) + len(token)
        if kept and next_length > max_length:
            break
        # 한 단어 자체가 제한보다 길면 잘라 깨뜨리지 않고 온전히 유지한다.
        kept.append(token)
        length = next_length
        if length >= max_length:
            break
    return "-".join(kept) or fallback


def _translated_tokens(value: str) -> list[str]:
    lowered = value.strip().lower()
    tokens: list[str] = []
    month = re.match(r"^\s*(0?[1-9]|1[0-2])월", lowered)
    if month:
        tokens.append(_MONTH_EN[f"{int(month.group(1)):02d}"])
    for korean, english in _KEYWORD_EN.items():
        if korean in lowered and english not in tokens:
            tokens.append(english)
    tokens.extend(re.findall(r"[a-z][a-z0-9]{1,}", lowered))
    return list(dict.fromkeys(tokens))


def source_integer_id(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return value if value >= 0 else None
    numbers = re.findall(r"\d+", str(value or ""))
    if not numbers:
        return None
    return int(max(numbers, key=len))


def build_seo_slug(
    title: str,
    *,
    category: str = "",
    agency: str = "",
    source_id: str | int | None = None,
    published_date: date | str | None = None,
    max_length: int = 80,
) -> str:
    """Build a stable readable slug; never append an opaque hash."""
    translated = _translated_tokens(title)
    agency_slug = re.sub(r"[^a-z0-9]+", "-", agency.lower()).strip("-")
    category_slug = _CATEGORY_EN.get(category, re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-"))
    parts = [part for part in (agency_slug, *translated) if part]
    identifier = source_integer_id(source_id)
    if published_date:
        try:
            date_text = date.fromisoformat(str(published_date)[:10]).strftime("%Y-%m-%d")
        except ValueError:
            date_text = ""
        if date_text:
            parts.append(date_text)
    if identifier is not None:
        parts.append(str(identifier))
    candidate = slugify_words("-".join(parts), max_length=max_length, fallback="") if parts else ""
    if len(re.sub(r"[^a-z0-9]", "", candidate)) >= 10:
        return candidate

    if identifier is not None and (agency_slug or category_slug):
        return f"{agency_slug or category_slug}-issue-{identifier}"

    native = slugify_words(title, max_length=max_length, fallback="")
    native_length = len(re.sub(r"[^가-힣a-z0-9]", "", native))
    if native_length >= 10:
        return native
    raise UnsafeSlugError(f"Skip: Unsafe short slug source ({title.strip()})")
