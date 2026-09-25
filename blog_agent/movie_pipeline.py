from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


MOVIE_REVIEW_SYSTEM_PROMPT = """당신은 영화 관람객 리뷰 편집자다.
반드시 제공된 관람객 리뷰 텍스트 데이터 내에서만 장/단점을 추출하라. 절대로 새로운 정보를 창작하거나, 'AI가 분석한 바에 따르면' 같은 기계적인 서두를 쓰지 말 것. 사람이 직접 작성한 듯한 자연스럽고 간결한 블로그 문체를 유지할 것.
절대로 '결론적으로', '요약하자면', '이 영화가 주는 메시지는', '종합해 보면' 같은 기계적이고 상투적인 서두/맺음말을 사용하지 마라. 전문적이고 건조한 블로거 문체로 첫 문장부터 리뷰에 나타난 구체적 장점이나 단점을 제시하라.
고유명사, 평점, 사건, 인물 관계를 추론하지 말고 입력에 없는 사실은 출력하지 마라.
스포일러가 의심되는 문장은 사용하지 말고, 장점과 아쉬운 점에 인용 근거가 없으면 해당 항목을 빈 배열로 반환하라.
JSON 형식으로만 답하라: {"strengths": [{"summary": "...", "evidence": "입력 문장의 짧은 인용"}], "weaknesses": [...]}
"""

_SPOILER_RE = re.compile(
    r"(?:스포(?:일러)?|spoiler|반전|범인(?:은|이|가)|결말(?:은|이|에서)|죽(?:는다|었)|정체(?:는|가))",
    re.IGNORECASE,
)
_PROFANITY_RE = re.compile(r"(?:씨발|시발|ㅅㅂ|개새끼|병신|좆|fuck|shit)", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_SPECIAL_SPAM_RE = re.compile(r"(?:[^\w\s가-힣.,!?~'\-]){4,}")
_REPEAT_RE = re.compile(r"(.)\1{5,}")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class MovieRecord:
    movie_id: str
    title: str
    slug: str
    release_date: str
    genres: tuple[str, ...]
    director: str
    cast: tuple[str, ...]
    synopsis: str
    spoiler_summary: str
    poster_path: str
    poster_alt: str
    image_license: str
    image_source_url: str
    reviews: tuple[str, ...]
    runtime_minutes: int | None = None
    is_fixture: bool = False

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.__dict__, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sanitize_review_text(value: str) -> str | None:
    """Remove unsafe/noisy review text before it can reach an LLM."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _HTML_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 12 or _SPOILER_RE.search(text) or _PROFANITY_RE.search(text):
        return None
    if _SPECIAL_SPAM_RE.search(text) or _REPEAT_RE.search(text):
        return None
    return text[:600].rstrip()


def preprocess_reviews(values: list[Any]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = sanitize_review_text(str(value))
        key = text.casefold() if text else ""
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return tuple(cleaned[:30])


def review_prompt(reviews: tuple[str, ...]) -> str:
    numbered = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(reviews))
    return f"{MOVIE_REVIEW_SYSTEM_PROMPT}\n\n관람객 리뷰:\n{numbered}"


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"movie field '{key}' is required")
    return value


def parse_movie(raw: dict[str, Any], *, staging: bool) -> MovieRecord:
    slug = _required_text(raw, "slug")
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"movie slug must be lowercase ASCII words: {slug}")
    release_date = _required_text(raw, "release_date")
    date.fromisoformat(release_date)
    poster = raw.get("poster")
    if not isinstance(poster, dict):
        raise ValueError(f"movie '{slug}' needs poster metadata")
    poster_path = _required_text(poster, "path")
    if Path(poster_path).suffix.lower() != ".webp":
        raise ValueError(f"movie '{slug}' poster must be WebP")
    image_license = _required_text(poster, "license")
    image_source_url = _required_text(poster, "source_url")
    if not staging and raw.get("is_fixture"):
        raise ValueError("fixture movie data cannot be used for production")
    reviews = preprocess_reviews(raw.get("reviews") if isinstance(raw.get("reviews"), list) else [])
    if not reviews:
        raise ValueError(f"movie '{slug}' has no usable non-spoiler reviews")
    runtime = raw.get("runtime_minutes")
    runtime_minutes = int(runtime) if runtime not in (None, "") else None
    return MovieRecord(
        movie_id=_required_text(raw, "id"),
        title=_required_text(raw, "title"),
        slug=slug,
        release_date=release_date,
        genres=tuple(str(item).strip() for item in raw.get("genres", []) if str(item).strip()),
        director=_required_text(raw, "director"),
        cast=tuple(str(item).strip() for item in raw.get("cast", []) if str(item).strip()),
        synopsis=_required_text(raw, "synopsis"),
        spoiler_summary=_required_text(raw, "spoiler_summary"),
        poster_path=poster_path,
        poster_alt=_required_text(poster, "alt"),
        image_license=image_license,
        image_source_url=image_source_url,
        reviews=reviews,
        runtime_minutes=runtime_minutes,
        is_fixture=bool(raw.get("is_fixture")),
    )


def load_movies(path: Path, *, staging: bool, limit: int | None = None) -> list[MovieRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("movie data must be a JSON array")
    movies = [parse_movie(item, staging=staging) for item in payload if isinstance(item, dict)]
    slugs = [movie.slug for movie in movies]
    if len(slugs) != len(set(slugs)):
        raise ValueError("movie slugs must be unique")
    return movies[:limit] if limit is not None else movies
