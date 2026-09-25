from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = (
    '<article class="post movie-post netflix-post">',
    '<dl class="netflix-summary-box"',
    '시놉시스 및 주요 등장인물</h2>',
    '놓치면 안 될 핵심 관전 포인트 3가지</h2>',
    '결말 해석 및 시즌 후속작 떡밥</h2>',
    '국내외 관람객 호불호 평점 요약</h2>',
    '<details class="movie-spoiler netflix-spoiler">',
    '🚨 스포일러 주의! [결말 해석 보기] 클릭하여 펼치기',
    '📺 [정주행 필수템] 넷플릭스 몰아보기를 위한 실속 가성비 핫딜',
    'class="toss-shopping-card product-recommendation"',
    'class="toss-cta-button product-recommendation-link"',
    '👉 [최저가 확인] 오늘 한정 특가 및 실구매자 후기 보기',
)


def verify(
    public_dir: Path,
    expected: int,
    *,
    dry_run: bool,
    stats_path: Path | None = None,
    expected_sitemaps: int | None = None,
) -> None:
    root = public_dir / ("staging/netflix" if dry_run else "netflix")
    pages = sorted(root.glob("*/*/*.html"))
    if len(pages) != expected:
        raise SystemExit(f"expected {expected} Netflix pages, found {len(pages)}")
    for page in pages:
        source = page.read_text(encoding="utf-8")
        missing = [value for value in REQUIRED if value not in source]
        if missing:
            raise SystemExit(f"{page}: missing {missing}")
        if dry_run and 'name="robots" content="noindex,follow"' not in source:
            raise SystemExit(f"{page}: dry-run page must be noindex")
        schemas = re.findall(r'<script type="application/ld\+json">(.*?)</script>', source)
        if not any(json.loads(item).get("@type") in {"TVSeries", "Movie"} for item in schemas):
            raise SystemExit(f"{page}: TVSeries/Movie JSON-LD missing")
    prefix = "sitemap-netflix-canary" if dry_run else "sitemap-netflix"
    submaps = sorted(public_dir.glob(f"{prefix}-[0-9]*.xml"))
    if not submaps or not (public_dir / f"{prefix}.xml").exists():
        raise SystemExit("Netflix sitemap index/sub-sitemaps missing")
    if expected_sitemaps is not None and len(submaps) != expected_sitemaps:
        raise SystemExit(f"expected {expected_sitemaps} sub-sitemaps, found {len(submaps)}")
    if stats_path:
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        if stats.get("records") != expected:
            raise SystemExit("build stats record count mismatch")
        if int(stats.get("max_worker_rss_kb") or 0) > 512 * 1024:
            raise SystemExit("worker memory exceeded 512 MiB guard")
    print(json.dumps({"ok": True, "pages": len(pages), "sub_sitemaps": len(submaps), "toss_widget": True}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-dir", type=Path, default=Path("public"))
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", type=Path)
    parser.add_argument("--expected-sitemaps", type=int)
    args = parser.parse_args()
    verify(
        args.public_dir,
        args.expected,
        dry_run=args.dry_run,
        stats_path=args.stats,
        expected_sitemaps=args.expected_sitemaps,
    )


if __name__ == "__main__":
    main()
