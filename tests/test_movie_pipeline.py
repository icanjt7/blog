from __future__ import annotations

import json
from pathlib import Path

import pytest

from blog_agent.movie_pipeline import MOVIE_REVIEW_SYSTEM_PROMPT, load_movies, sanitize_review_text


def test_movie_review_prompt_forbids_hallucination_and_cliches() -> None:
    assert "제공된 관람객 리뷰 텍스트 데이터 내에서만" in MOVIE_REVIEW_SYSTEM_PROMPT
    assert "절대로 새로운 정보를 창작" in MOVIE_REVIEW_SYSTEM_PROMPT
    assert "AI가 분석한 바에 따르면" in MOVIE_REVIEW_SYSTEM_PROMPT
    assert "종합해 보면" in MOVIE_REVIEW_SYSTEM_PROMPT


@pytest.mark.parametrize("text", [
    "[스포일러] 마지막에 범인이 밝혀집니다.",
    "이 영화는 진짜 씨발 별로였어요.",
    "!!!!!!!!!!!!!!!!!",
    "ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ",
])
def test_review_filter_rejects_spoilers_profanity_and_spam(text: str) -> None:
    assert sanitize_review_text(text) is None


def test_canary_data_is_exactly_ten_valid_webp_movies() -> None:
    movies = load_movies(Path("data/movies-canary.json"), staging=True, limit=10)
    assert len(movies) == 10
    assert all(movie.poster_path.endswith(".webp") for movie in movies)
    assert all(movie.reviews for movie in movies)


def test_production_rejects_fixture_data(tmp_path: Path) -> None:
    raw = json.loads(Path("data/movies-canary.json").read_text(encoding="utf-8"))
    path = tmp_path / "movies.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture"):
        load_movies(path, staging=False)
