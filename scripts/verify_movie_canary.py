from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_SNIPPETS = (
    '<article class="post movie-post">',
    'aria-label="탐색 경로"',
    '<link rel="canonical"',
    'hreflang="ko"',
    'hreflang="x-default"',
    'property="og:image"',
    '"@type": "Movie"',
    'class="movie-poster"',
    'loading="eager"',
    'class="movie-review-card"',
    '<details class="movie-spoiler">',
    'class="toss-shopping-card product-recommendation"',
    'rel="sponsored nofollow noopener noreferrer"',
    'data-product-catalog="../../product-catalog.json"',
)


def verify(public_dir: Path, expected_count: int) -> None:
    movie_dir = public_dir / "staging" / "movies"
    pages = sorted(path for path in movie_dir.glob("*.html") if path.name != "index.html")
    if len(pages) != expected_count:
        raise SystemExit(f"expected {expected_count} canary movie pages, found {len(pages)}")
    for page in pages:
        source = page.read_text(encoding="utf-8")
        missing = [snippet for snippet in REQUIRED_SNIPPETS if snippet not in source]
        if missing:
            raise SystemExit(f"{page}: missing {missing}")
        if 'name="robots" content="noindex,follow"' not in source:
            raise SystemExit(f"{page}: staging page must be noindex")
        poster_match = re.search(r'class="movie-poster" src="([^"]+\.webp)"', source)
        if not poster_match:
            raise SystemExit(f"{page}: WebP poster missing")
        poster_path = (page.parent / poster_match.group(1)).resolve()
        if not poster_path.exists():
            raise SystemExit(f"{page}: poster target does not exist: {poster_path}")
        json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', source)
        if not any(json.loads(item).get("@type") == "Movie" for item in json_ld):
            raise SystemExit(f"{page}: valid Movie JSON-LD missing")
    print(json.dumps({"ok": True, "movie_pages": len(pages), "toss_widget": True, "posters": True}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-dir", type=Path, default=Path("public"))
    parser.add_argument("--expected-count", type=int, default=10)
    args = parser.parse_args()
    verify(args.public_dir, args.expected_count)


if __name__ == "__main__":
    main()
