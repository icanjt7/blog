from __future__ import annotations

import json
import gzip
from pathlib import Path

import pytest

from blog_agent.netflix_pipeline import (
    NETFLIX_CONTENT_SYSTEM_PROMPT,
    NETFLIX_OUTPUT_SCHEMA,
    chunked_records,
    parse_netflix_record,
    stream_json_items,
)


def _record(index: int = 1) -> dict:
    return {
        "post_type": "ENTERTAINMENT_NETFLIX",
        "id": str(index), "content_type": "tv", "title": f"검증 {index}",
        "slug": f"test-{index}", "genre": "드라마", "genre_slug": "drama", "year": 2026,
        "summary_box": {"genre_rating": "드라마 · 12세", "episodes_runtime": "8부작", "casting_direction": "배우 · 감독"},
        "director": "감독", "cast": ["배우"], "synopsis": "입력 데이터에 포함된 검증용 줄거리입니다.",
        "characters": [{"name": "인물", "relationship": "갈등을 조율하는 관계"}],
        "viewing_points": ["포인트 1", "포인트 2", "포인트 3"],
        "ending_analysis": "입력에 포함된 결말 설명",
        "review_summary": {"strengths": ["장점 1", "장점 2", "장점 3"], "weaknesses": ["단점 1", "단점 2"]},
        "poster_url": "https://example.com/poster.webp", "poster_alt": "검증 포스터",
        "source_url": "https://example.com/title", "reviews_source_url": "https://example.com/reviews",
        "updated_at": "2026-09-25T00:00:00+09:00", "is_fixture": True,
    }


def test_prompt_and_schema_lock_post_type_and_four_sections() -> None:
    assert NETFLIX_OUTPUT_SCHEMA["properties"]["post_type"]["const"] == "ENTERTAINMENT_NETFLIX"
    for phrase in ("시놉시스 및 주요 등장인물", "핵심 관전 포인트 3가지", "결말 해석", "관람객 호불호"):
        assert phrase in NETFLIX_CONTENT_SYSTEM_PROMPT
    assert "입력에 없는" in NETFLIX_CONTENT_SYSTEM_PROMPT
    assert "종합해 보면" in NETFLIX_CONTENT_SYSTEM_PROMPT
    assert "H1 바로 아래" in NETFLIX_CONTENT_SYSTEM_PROMPT


def test_streams_json_array_with_tiny_read_buffer(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps([_record(1), _record(2)], ensure_ascii=False), encoding="utf-8")
    assert [item["id"] for item in stream_json_items(path, read_size=17)] == ["1", "2"]


def test_streams_gzip_json_array_without_loading_it_all(tmp_path: Path) -> None:
    path = tmp_path / "records.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump([_record(1), _record(2)], handle, ensure_ascii=False)
    assert [item["id"] for item in stream_json_items(path, read_size=19)] == ["1", "2"]


def test_chunk_generator_never_exceeds_requested_size(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text("".join(json.dumps(_record(i), ensure_ascii=False) + "\n" for i in range(1, 8)), encoding="utf-8")
    chunks = list(chunked_records(path, chunk_size=3))
    assert [len(chunk) for chunk in chunks] == [3, 3, 1]


def test_fixture_is_rejected_for_production() -> None:
    with pytest.raises(ValueError, match="fixture"):
        parse_netflix_record(_record(), dry_run=False)


def test_hierarchical_output_path() -> None:
    record = parse_netflix_record(_record(), dry_run=True)
    assert record.output_path(dry_run=False) == "netflix/drama/2026/test-1.html"
    assert record.output_path(dry_run=True) == "staging/netflix/drama/2026/test-1.html"
