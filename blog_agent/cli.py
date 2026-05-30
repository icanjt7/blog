from __future__ import annotations

import argparse
import json

from .config import load_settings
from .pipeline import BlogPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily blog automation agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="plan, write, review, and publish posts")
    run.add_argument("--count", type=int, default=5)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--min-quality", type=float, default=65)
    run.add_argument("--publisher", choices=["markdown", "wordpress"])
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()
    if args.publisher:
        settings.publisher = args.publisher
    pipeline = BlogPipeline(settings)
    result = pipeline.run(count=args.count, dry_run=args.dry_run, min_quality=args.min_quality)
    print(
        json.dumps(
            {
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


if __name__ == "__main__":
    main()
