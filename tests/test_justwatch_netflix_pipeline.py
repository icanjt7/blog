from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_netflix import build, normalize_record
from fetch_netflix_data import normalize_entry


def _raw(index: int) -> dict:
    return {
        "id": f"tm{index}",
        "object_id": index,
        "title": f"넷플릭스 검증작 {index}",
        "release_year": 2026,
        "release_date": "2026-09-25",
        "genre_ids": ["drm"],
        "genres": ["드라마"],
        "genre_slugs": ["drama"],
        "synopsis": "JustWatch 원시 데이터에 포함된 검증용 시놉시스입니다.",
        "poster_url": "https://images.justwatch.com/poster/test/s718/poster.jpg",
        "backdrop_urls": [],
        "content_type": "movie",
        "runtime_minutes": 101,
        "season_count": 0,
        "episode_count": 0,
        "age_certification": "12",
        "imdb_id": "",
        "tmdb_id": str(index),
        "scoring": {"imdb_score": 7.1, "imdb_votes": 100},
        "source_url": f"https://www.justwatch.com/kr/movie/test-{index}",
        "provider": "nfx",
        "locale": "ko_KR",
        "collected_at": "2026-09-25T00:00:00+00:00",
    }


def test_justwatch_entry_maps_required_fields_and_genres() -> None:
    entry = SimpleNamespace(
        entry_id="tm123",
        object_id=123,
        object_type="MOVIE",
        title="테스트 영화",
        release_year=2026,
        release_date="2026-09-25",
        genres=["drm", "trl"],
        short_description="공식 시놉시스",
        poster="https://images.justwatch.com/poster/test.jpg",
        backdrops=[],
        runtime_minutes=110,
        total_season_count=None,
        total_episode_count=None,
        age_certification="12",
        imdb_id="tt123",
        tmdb_id="123",
        scoring=SimpleNamespace(imdb_score=7.5, imdb_votes=1000),
        url="/kr/movie/test",
    )
    record = normalize_entry(entry, collected_at="2026-09-25T00:00:00+00:00")
    assert record["id"] == "tm123"
    assert record["genres"] == ["드라마", "스릴러"]
    assert record["genre_slugs"] == ["drama", "thriller"]
    assert record["content_type"] == "movie"
    assert record["locale"] == "ko_KR"
    assert record["provider"] == "nfx"


def test_normalize_record_uses_partitioned_ascii_path() -> None:
    record = normalize_record(_raw(7))
    assert record["genre_slug"] == "drama"
    assert record["slug"] == "netflix-movie-tm7"


def test_multiprocess_builder_writes_pages_toss_widget_and_split_sitemaps(tmp_path: Path) -> None:
    source = tmp_path / "netflix_raw_data.json"
    source.write_text(json.dumps([_raw(index) for index in range(1, 4)], ensure_ascii=False), encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body><main>홈</main></body></html>", encoding="utf-8")
    (dist / "search.json").write_text("[]", encoding="utf-8")
    report = build(argparse.Namespace(
        input=source,
        dist_dir=dist,
        posts_dir=tmp_path / "posts",
        chunk_size=2,
        workers=2,
        limit=0,
        domain="briefwave.kr",
    ))

    assert report["records"] == 3
    assert report["chunks"] == 2
    assert report["catalog_pages"] == 1
    assert report["home_discovery"] == 1
    pages = sorted(dist.glob("netflix/drama/2026/*.html"))
    assert len(pages) == 3
    source_html = pages[0].read_text(encoding="utf-8")
    assert 'class="toss-shopping-card product-recommendation"' in source_html
    assert 'role="doc-abstract"' in source_html
    assert 'loading="lazy"' in source_html
    assert '"@type": "Movie"' in source_html
    assert "🍿 <time" in source_html
    assert "기준 한국 넷플릭스에서 서비스 중인 것으로 확인했습니다" in source_html
    assert "수집 시점" not in source_html
    assert '<a href="../../../category-정책.html" class="">정책</a>' in source_html
    assert '<a href="../../../netflix/index.html" class="active">영화</a>' in source_html
    assert source_html.count("googletagmanager.com/gtm.js?id=") == 1
    assert source_html.count("googletagmanager.com/ns.html?id=GTM-PRH78BZK") == 1
    assert source_html.index("<!-- Google Tag Manager -->") < source_html.index('<meta charset="utf-8">')
    assert source_html.index("<body>") < source_html.index("<!-- Google Tag Manager (noscript) -->") < source_html.index('<header class="site-header">')
    catalog_html = (dist / "netflix" / "index.html").read_text(encoding="utf-8")
    assert "한국 넷플릭스 작품 전체 목록" in catalog_html
    assert "🍿 2026-09-25 기준 한국 넷플릭스에서 확인된" in catalog_html
    assert "수집 시점 기준" not in catalog_html
    assert '<a href="../category-정책.html" class="">정책</a>' in catalog_html
    assert '<a href="../netflix/index.html" class="active">영화</a>' in catalog_html
    assert "넷플릭스 검증작 1" in catalog_html
    home_html = (dist / "index.html").read_text(encoding="utf-8")
    assert "지금 볼 수 있는 넷플릭스 작품" in home_html
    assert "./netflix/drama/2026/netflix-movie-tm1.html" in home_html
    search_items = json.loads((dist / "search.json").read_text(encoding="utf-8"))
    assert len(search_items) == 3
    assert search_items[0]["url"] == "./netflix/drama/2026/netflix-movie-tm1.html"

    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    index = ET.parse(dist / "sitemap-netflix-index.xml").getroot()
    submaps = index.findall("s:sitemap/s:loc", namespace)
    assert [item.text for item in submaps] == [
        "https://briefwave.kr/sitemap-netflix-1.xml",
        "https://briefwave.kr/sitemap-netflix-2.xml",
    ]
    counts = [
        len(ET.parse(dist / f"sitemap-netflix-{index}.xml").getroot().findall("s:url", namespace))
        for index in (1, 2)
    ]
    assert counts == [2, 1]
    robots = (dist / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://briefwave.kr/sitemap-netflix-index.xml" in robots
