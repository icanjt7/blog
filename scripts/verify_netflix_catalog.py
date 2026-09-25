"""Verify factual JustWatch Netflix pages before production deployment."""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from blog_agent.netflix_pipeline import stream_json_items

REQUIRED_MARKERS = (
    '<article class="post movie-post netflix-post netflix-catalog-post">',
    'role="doc-abstract"',
    'loading="lazy"',
    'application/ld+json',
    'JustWatch에서 최신 제공 정보 확인',
    'class="toss-shopping-card product-recommendation"',
    '👉 [최저가 확인] 오늘 한정 특가 및 실구매자 후기 보기',
)
CATALOG_PAGE_SIZE = 100


def verify(input_path: Path, public_dir: Path, chunk_size: int) -> dict[str, int | bool]:
    expected = sum(1 for _ in stream_json_items(input_path))
    pages = list((public_dir / "netflix").glob("*/*/*.html"))
    if len(pages) != expected:
        raise SystemExit(f"expected {expected} Netflix catalog pages, found {len(pages)}")
    for path in pages:
        source = path.read_text(encoding="utf-8")
        missing = [marker for marker in REQUIRED_MARKERS if marker not in source]
        if missing:
            raise SystemExit(f"{path}: missing required markup {missing}")

    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    index_path = public_dir / "sitemap-netflix-index.xml"
    index = ET.parse(index_path).getroot()
    indexed = index.findall("s:sitemap/s:loc", namespace)
    expected_sitemaps = math.ceil(expected / chunk_size)
    if len(indexed) != expected_sitemaps:
        raise SystemExit(f"expected {expected_sitemaps} Netflix sitemaps, found {len(indexed)}")
    sitemap_urls = 0
    for number in range(1, expected_sitemaps + 1):
        root = ET.parse(public_dir / f"sitemap-netflix-{number}.xml").getroot()
        sitemap_urls += len(root.findall("s:url", namespace))
    if sitemap_urls != expected:
        raise SystemExit(f"expected {expected} sitemap URLs, found {sitemap_urls}")

    expected_catalog_pages = math.ceil(expected / CATALOG_PAGE_SIZE)
    catalog_pages = [public_dir / "netflix" / "index.html", *(
        public_dir / "netflix" / f"page-{number}.html"
        for number in range(2, expected_catalog_pages + 1)
    )]
    missing_catalog_pages = [str(path) for path in catalog_pages if not path.exists()]
    if missing_catalog_pages:
        raise SystemExit(f"missing Netflix catalog pages: {missing_catalog_pages[:3]}")
    home = (public_dir / "index.html").read_text(encoding="utf-8")
    if "지금 볼 수 있는 넷플릭스 작품" not in home or "./netflix/index.html" not in home:
        raise SystemExit("Netflix discovery section is missing from the home page")
    search_items = json.loads((public_dir / "search.json").read_text(encoding="utf-8"))
    search_netflix = [item for item in search_items if str(item.get("url", "")).startswith("./netflix/")]
    if len(search_netflix) != expected:
        raise SystemExit(f"expected {expected} Netflix search records, found {len(search_netflix)}")

    robots = (public_dir / "robots.txt").read_text(encoding="utf-8")
    if "Sitemap: https://briefwave.kr/sitemap-netflix-index.xml" not in robots:
        raise SystemExit("Netflix sitemap index is missing from robots.txt")
    result: dict[str, int | bool] = {
        "ok": True,
        "pages": expected,
        "sub_sitemaps": expected_sitemaps,
        "sitemap_urls": sitemap_urls,
        "catalog_pages": expected_catalog_pages,
        "search_records": len(search_netflix),
        "toss_widget": True,
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, default=Path("public"))
    parser.add_argument("--chunk-size", type=int, default=1000)
    args = parser.parse_args()
    verify(args.input, args.public_dir, args.chunk_size)


if __name__ == "__main__":
    main()
