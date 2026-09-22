from __future__ import annotations

import re


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
