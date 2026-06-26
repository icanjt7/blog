from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blog_agent.narabid import OPERATIONS, NaraBidClient, write_bid_digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a test post from Nara Bid public notices.")
    parser.add_argument("--limit", type=int, default=50, help="number of notices to include")
    parser.add_argument("--days", type=int, default=1, help="lookback window in days")
    parser.add_argument(
        "--work-types",
        nargs="+",
        default=["goods", "service", "construction"],
        choices=sorted(OPERATIONS),
        help="notice categories to fetch",
    )
    parser.add_argument("--keyword", action="append", default=[], help="optional title keyword filter")
    parser.add_argument("--output-dir", default="output/posts", help="directory for generated markdown")
    parser.add_argument("--date", help="post date/time in YYYY-MM-DD or YYYY-MM-DDTHH:MM format")
    parser.add_argument("--overwrite", action="store_true", help="overwrite an existing post for the same date")
    args = parser.parse_args()

    service_key = os.getenv("BIDPUBLICINFOSERVICE")
    if not service_key:
        print("BIDPUBLICINFOSERVICE 환경변수가 없습니다. GitHub Secret 또는 로컬 환경변수로 설정해 주세요.", file=sys.stderr)
        return 2

    try:
        generated_at = _parse_datetime(args.date) if args.date else datetime.now()
    except ValueError as exc:
        parser.error(str(exc))
    output_dir = Path(args.output_dir)
    filename = f"{_slug('나라장터-입찰공고')}-{generated_at:%Y-%m-%d}.md"
    path = output_dir / filename
    if path.exists() and not args.overwrite:
        print(f"이미 파일이 있습니다: {path}. 덮어쓰려면 --overwrite를 사용하세요.", file=sys.stderr)
        return 3

    client = NaraBidClient(service_key)
    notices = client.fetch_recent(
        args.work_types,
        limit=max(1, args.limit),
        days=max(1, args.days),
        keywords=args.keyword or None,
    )
    write_bid_digest(path, notices, generated_at=generated_at)
    print(f"generated={path}")
    print(f"notices={len(notices)}")
    print(f"work_types={','.join(args.work_types)}")
    return 0


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError("--date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM")


def _slug(value: str) -> str:
    slug = re.sub(r"\s+", "-", value.strip())
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "", slug).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
