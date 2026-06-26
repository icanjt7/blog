from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blog_agent.narabid import OPERATIONS, NaraBidClient, write_bid_digest, write_service_digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a test post from Nara Bid public notices.")
    parser.add_argument("--limit", type=int, default=50, help="number of notices to include")
    parser.add_argument("--days", type=int, default=1, help="lookback window in days")
    parser.add_argument(
        "--work-types",
        nargs="+",
        default=None,
        choices=sorted(OPERATIONS),
        help="notice categories to fetch",
    )
    parser.add_argument(
        "--format",
        choices=["table", "service-summary"],
        default="table",
        help="markdown post format",
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
    work_types = args.work_types or (["service"] if args.format == "service-summary" else ["goods", "service", "construction"])
    filename_base = "나라장터-용역입찰공고" if args.format == "service-summary" else "나라장터-입찰공고"
    filename = f"{_slug(filename_base)}-{generated_at:%Y-%m-%d}.md"
    path = output_dir / filename
    if path.exists() and not args.overwrite:
        print(f"이미 파일이 있습니다: {path}. 덮어쓰려면 --overwrite를 사용하세요.", file=sys.stderr)
        return 3

    client = NaraBidClient(service_key)
    target_limit = max(1, args.limit)
    fetch_limit = max(target_limit * 4, 80) if args.format == "service-summary" else target_limit
    notices = client.fetch_recent(
        work_types,
        limit=fetch_limit,
        days=max(1, args.days),
        keywords=args.keyword or None,
    )
    if args.format == "service-summary":
        notices = _active_service_notices(_dedupe_service_notices(notices), limit=target_limit)
        write_service_digest(path, notices, generated_at=generated_at)
    else:
        notices = notices[:target_limit]
        write_bid_digest(path, notices, generated_at=generated_at)
    print(f"generated={path}")
    print(f"notices={len(notices)}")
    print(f"work_types={','.join(work_types)}")
    print(f"format={args.format}")
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


def _dedupe_service_notices(notices):
    unique = {}
    for notice in notices:
        key = (notice.title, notice.demand_inst or notice.notice_inst, notice.bid_close_at)
        unique.setdefault(key, notice)
    return list(unique.values())


def _active_service_notices(notices, *, limit: int):
    now_kst = datetime.utcnow() + timedelta(hours=9)
    active = [notice for notice in notices if _notice_close_dt(notice.bid_close_at) >= now_kst]
    return active[:limit]


def _notice_close_dt(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.max


if __name__ == "__main__":
    raise SystemExit(main())
