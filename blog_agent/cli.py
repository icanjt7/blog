from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from .config import load_settings
from .images import ImageAgent
from .models import Draft, Topic
from .netflix_pipeline import build_netflix_site
from .pipeline import BlogPipeline
from .site import StaticSiteBuilder
from .storage import RunStore

_CAT_MAP = {"tech": "기술", "living": "생활", "finance": "정책", "local": "핫이슈"}
_VALID_CATS = {"핫이슈", "기술", "정책", "생활", "정치"}


def _reimage_posts(
    posts_dir: Path,
    settings,
    category_filter: str | None = None,
    force: bool = False,
) -> int:
    """Re-fetch cover images for posts.

    force=True: 기존 URL이 있어도 새 쿼리로 재요청 (소급 적용 시 사용).
    force=False: 빈 이미지 / picsum URL 포스트만 처리 (평소 운영).
    """
    agent = ImageAgent(settings)
    updated = 0
    for md_path in sorted(posts_dir.glob("*.md")):
        raw = md_path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        _, fm, body = raw.split("---", 2)
        try:
            meta = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            print(f"skip invalid frontmatter: {md_path}")
            continue

        raw_cat = str(meta.get("category") or "생활")
        cat = _CAT_MAP.get(raw_cat, raw_cat)
        if cat not in _VALID_CATS:
            cat = "생활"
        if category_filter and cat != category_filter:
            continue

        cover = str(meta.get("cover_image") or "")
        if not force and cover and "picsum.photos" not in cover:
            continue  # 평소엔 유효한 이미지 건너뜀

        title = str(meta.get("title") or md_path.stem)
        tags = [str(t) for t in (meta.get("tags") or [])]
        keyword = " ".join(tags[:5]) or title

        topic = Topic(keyword=keyword, title_hint=title, category=cat)  # type: ignore[arg-type]
        draft = Draft(topic=topic, title=title, slug=md_path.stem, excerpt="", body_markdown="", tags=tags)
        draft = agent.attach_cover(draft)

        new_url = draft.cover_image_path or ""
        # picsum 폴백이면 저장하지 않음 (build-time loremflickr 폴백이 더 나음)
        if not new_url or "picsum.photos" in new_url:
            continue

        new_fm = re.sub(r'^cover_image:.*$', f'cover_image: "{new_url}"', fm, flags=re.MULTILINE)
        if "cover_image:" not in new_fm:
            new_fm = new_fm.rstrip("\n") + f'\ncover_image: "{new_url}"\n'
        md_path.write_text(f"---{new_fm}---{body}", encoding="utf-8")
        updated += 1

    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily blog automation agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="plan, write, review, and publish posts")
    run.add_argument("--count", type=int)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--min-quality", type=float, default=65)
    run.add_argument("--publisher", choices=["markdown", "wordpress", "both"])
    run.add_argument("--require-publish-success", action="store_true")
    build = sub.add_parser("build-site", help="render generated Markdown posts into a static site")
    build.add_argument("--posts-dir")
    build.add_argument("--public-dir")
    build.add_argument("--movie-data", help="validated movie JSON array")
    build.add_argument("--movie-limit", type=int)
    build.add_argument("--movie-mode", choices=["staging", "production"], default="production")
    build.add_argument("--movie-cache-dir", default=".cache/movie-pages")
    build.add_argument("--movie-release-approval", help="manual canary approval JSON required for production movies")
    netflix = sub.add_parser("build-netflix", help="stream and render large Netflix JSON/JSONL datasets")
    netflix.add_argument("--input", required=True)
    netflix.add_argument("--posts-dir")
    netflix.add_argument("--public-dir")
    netflix.add_argument("--cache-dir", default=".cache/netflix-pages")
    netflix.add_argument("--chunk-size", type=int, default=1000)
    netflix.add_argument("--limit", type=int)
    netflix.add_argument("--workers", type=int)
    netflix.add_argument("--dry-run", action="store_true")
    netflix.add_argument("--expected-count", type=int, default=20000)
    netflix.add_argument("--release-approval", help="manual 50-page approval JSON required for production")
    reimage = sub.add_parser("re-image", help="re-fetch cover images for posts with missing/picsum images")
    reimage.add_argument("--category", help="only re-image posts in this category (e.g. 기술)")
    reimage.add_argument("--force", action="store_true", help="기존 URL이 있어도 재요청 (소급 적용)")
    reimage.add_argument("--posts-dir")
    status = sub.add_parser("status", help="show recent pipeline runs")
    status.add_argument("--limit", type=int, default=10)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "status":
        store = RunStore(settings.state_dir)
        print(json.dumps(store.latest_runs(args.limit), ensure_ascii=False, indent=2))
        return
    if args.command == "build-netflix":
        if not args.dry_run:
            approval_path = Path(args.release_approval) if args.release_approval else None
            try:
                approval = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path else {}
            except (OSError, json.JSONDecodeError):
                approval = {}
            if approval.get("approved") is not True or approval.get("verified_pages") != 50:
                parser.error(
                    "production Netflix build requires --release-approval JSON "
                    "with approved=true and verified_pages=50"
                )
        posts_dir = settings.output_dir if not args.posts_dir else Path(args.posts_dir)
        public_dir = settings.public_dir if not args.public_dir else Path(args.public_dir)
        stats = build_netflix_site(
            Path(args.input),
            public_dir=public_dir,
            posts_dir=posts_dir,
            site_title=settings.site_title,
            site_description=settings.site_description,
            custom_domain=settings.custom_domain,
            categories=settings.categories,
            ga_measurement_id=settings.ga_measurement_id,
            adsense_publisher_id=settings.adsense_publisher_id,
            cache_dir=Path(args.cache_dir),
            chunk_size=args.chunk_size,
            limit=args.limit,
            dry_run=args.dry_run,
            workers=args.workers,
        )
        expected = args.limit if args.dry_run and args.limit is not None else args.expected_count
        if stats["records"] != expected:
            raise SystemExit(f"expected {expected} Netflix records, rendered {stats['records']}")
        print(json.dumps({"ok": True, "dry_run": args.dry_run, **stats}, ensure_ascii=False, indent=2))
        return
    if args.command == "build-site":
        if args.movie_data and args.movie_mode == "production":
            approval_path = Path(args.movie_release_approval) if args.movie_release_approval else None
            try:
                approval = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path else {}
            except (OSError, json.JSONDecodeError):
                approval = {}
            if approval.get("approved") is not True or approval.get("verified_pages") != 10:
                parser.error(
                    "production movie build requires --movie-release-approval JSON "
                    "with approved=true and verified_pages=10"
                )
        posts_dir = settings.output_dir if not args.posts_dir else settings.output_dir.__class__(args.posts_dir)
        public_dir = settings.public_dir if not args.public_dir else settings.public_dir.__class__(args.public_dir)
        builder = StaticSiteBuilder(
            posts_dir,
            public_dir,
            settings.site_title,
            settings.site_description,
            settings.custom_domain,
            settings.categories,
            ga_measurement_id=settings.ga_measurement_id,
            adsense_publisher_id=settings.adsense_publisher_id,
            movie_data_path=Path(args.movie_data) if args.movie_data else None,
            movie_limit=args.movie_limit,
            movie_staging=args.movie_mode == "staging",
            movie_cache_dir=Path(args.movie_cache_dir),
        )
        builder.build()
        print(json.dumps({
            "ok": True,
            "public_dir": str(public_dir),
            "movie_build": builder.movie_build_stats,
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "re-image":
        posts_dir = settings.output_dir if not args.posts_dir else Path(args.posts_dir)
        count = _reimage_posts(posts_dir, settings, category_filter=args.category, force=args.force)
        print(json.dumps({"ok": True, "updated": count}, ensure_ascii=False, indent=2))
        return
    if args.command == "run":
        if args.publisher:
            settings.publisher = args.publisher
        pipeline = BlogPipeline(settings)
        count = args.count if args.count is not None else settings.post_count
        result = pipeline.run(count=count, dry_run=args.dry_run, min_quality=args.min_quality)
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "manifest_path": result.manifest_path,
                    "report_path": result.report_path,
                    "drafts": [
                        {
                            "title": draft.title,
                            "keyword": draft.topic.keyword,
                            "category": draft.topic.category,
                            "quality_score": draft.quality_score,
                            "notes": draft.review_notes,
                        }
                        for draft in result.drafts
                    ],
                    "publish_results": [item.model_dump() for item in result.publish_results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        published = sum(1 for item in result.publish_results if item.ok)
        if args.require_publish_success and published < count and not args.dry_run:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "published": published,
                        "required": count,
                        "message": "not enough posts passed quality gate and were published",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
