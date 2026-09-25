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

    robots = (public_dir / "robots.txt").read_text(encoding="utf-8")
    if "Sitemap: https://briefwave.kr/sitemap-netflix-index.xml" not in robots:
        raise SystemExit("Netflix sitemap index is missing from robots.txt")
    result: dict[str, int | bool] = {
        "ok": True,
        "pages": expected,
        "sub_sitemaps": expected_sitemaps,
        "sitemap_urls": sitemap_urls,
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
