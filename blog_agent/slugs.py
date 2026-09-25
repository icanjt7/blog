from __future__ import annotations

import re
from datetime import date


class UnsafeSlugError(ValueError):
    """Raised instead of publishing a meaningless short/hash slug."""


_CATEGORY_EN = {
    "정책": "policy", "환경": "environment", "생활": "living", "기술": "technology",
    "정치": "politics", "스포츠": "sports", "핫이슈": "news",
}
_AGENCY_EN = {
    "국무조정실": "prime-minister-office", "고용노동부": "labor-ministry",
    "과학기술정보통신부": "science-ict-ministry", "교육부": "education-ministry",
    "국가데이터처": "national-data-office", "국가보훈부": "veterans-ministry",
    "국방부": "defense-ministry", "국토교통부": "land-transport-ministry",
    "기획예산처": "planning-budget-ministry", "기후에너지환경부": "climate-energy-ministry",
    "농림축산식품부": "agriculture-ministry", "문화체육관광부": "culture-ministry",
    "법무부": "justice-ministry", "법제처": "government-legislation-ministry",
    "보건복지부": "health-welfare-ministry", "산업통상부": "trade-industry-ministry",
    "성평등가족부": "gender-family-ministry", "식품의약품안전처": "food-drug-safety-ministry",
    "외교부": "foreign-affairs-ministry", "인사혁신처": "personnel-management-ministry",
    "재정경제부": "finance-economy-ministry", "중소벤처기업부": "sme-startup-ministry",
    "지식재산처": "intellectual-property-ministry", "통일부": "unification-ministry",
    "해양수산부": "oceans-fisheries-ministry", "행정안전부": "interior-safety-ministry",
    "경찰청": "national-police-agency", "소방청": "national-fire-agency",
    "질병관리청": "disease-control-agency", "국가유산청": "national-heritage-service",
    "공정거래위원회": "fair-trade-commission", "금융위원회": "financial-services-commission",
    "개인정보보호위원회": "privacy-commission", "원자력안전위원회": "nuclear-safety-commission",
}
_KEYWORD_EN = {
    "탄소중립": "carbon-neutral", "재난안전": "disaster-safety", "동향": "trends",
    "브리프": "brief", "소식지": "newsletter", "월간": "monthly", "정책": "policy",
    "지원금": "benefit", "복지": "welfare", "공모": "contest", "모집": "recruitment",
    "인공지능": "artificial-intelligence", "기술": "technology", "안전": "safety",
    "청년": "youth", "창업": "startup", "기업": "business", "일자리": "jobs",
    "교육": "education", "주거": "housing", "교통": "transport", "건강": "health",
    "문화": "culture", "관광": "tourism", "환경": "environment", "기후": "climate",
    "재난": "disaster", "협약": "agreement", "행사": "event", "결과": "results",
    "발표": "announcement", "개정": "revision", "건립": "construction", "지원": "support",
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
    translated = sorted(
        (lowered.find(korean), english)
        for korean, english in _KEYWORD_EN.items()
        if korean in lowered
    )
    for _, english in translated:
        if english not in tokens:
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
    agency_slug = _AGENCY_EN.get(
        agency,
        re.sub(r"[^a-z0-9]+", "-", agency.lower()).strip("-"),
    )
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
