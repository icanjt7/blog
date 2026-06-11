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
    if args.command == "build-site":
        posts_dir = settings.output_dir if not args.posts_dir else settings.output_dir.__class__(args.posts_dir)
        public_dir = settings.public_dir if not args.public_dir else settings.public_dir.__class__(args.public_dir)
        StaticSiteBuilder(
            posts_dir,
            public_dir,
            settings.site_title,
            settings.site_description,
            settings.custom_domain,
            settings.categories,
            ga_measurement_id=settings.ga_measurement_id,
            adsense_publisher_id=settings.adsense_publisher_id,
        ).build()
        print(json.dumps({"ok": True, "public_dir": str(public_dir)}, ensure_ascii=False, indent=2))
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
