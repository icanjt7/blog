"""Interleave press-release post dates by agency without changing content."""
from __future__ import annotations

import argparse
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import yaml


POSTS_DIR = Path(__file__).resolve().parents[1] / "output" / "posts"
AGENCY_ORDER = ("mois", "msit", "mofe", "mcst", "khs", "kh")


def split_post(raw: str) -> tuple[str, str] | None:
    if not raw.startswith("---"):
        return None
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def set_date(frontmatter: str, new_date: str) -> str:
    return re.sub(
        r'^date:\s*["\']?[^"\']*["\']?\s*$',
        f'date: "{new_date}"',
        frontmatter,
        flags=re.MULTILINE,
    )


def agency_prefix(path: Path) -> str:
    return path.name.split("-", 1)[0]


def is_press_post(meta: dict, path: Path) -> bool:
    tags = [str(tag) for tag in meta.get("tags") or []]
    return "보도기사" in tags and agency_prefix(path) in AGENCY_ORDER


def interleave(groups: dict[str, deque[Path]]) -> list[Path]:
    ordered: list[Path] = []
    while any(groups.values()):
        for agency in AGENCY_ORDER:
            if groups[agency]:
                ordered.append(groups[agency].popleft())
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-dir", type=Path, default=POSTS_DIR)
    parser.add_argument("--start", default=datetime.now().replace(second=0, microsecond=0).isoformat(timespec="minutes"))
    parser.add_argument("--spacing-minutes", type=int, default=17)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    groups: dict[str, list[tuple[datetime, Path]]] = defaultdict(list)
    for path in args.posts_dir.glob("*.md"):
        raw = path.read_text(encoding="utf-8")
        split = split_post(raw)
        if not split:
            continue
        frontmatter, _ = split
        meta = yaml.safe_load(frontmatter) or {}
        if not is_press_post(meta, path):
            continue
        groups[agency_prefix(path)].append((parse_date(str(meta.get("date") or "")), path))

    queues = {
        agency: deque(path for _, path in sorted(items, key=lambda item: item[0], reverse=True))
        for agency, items in groups.items()
    }
    for agency in AGENCY_ORDER:
        queues.setdefault(agency, deque())

    start = datetime.fromisoformat(args.start)
    changed = 0
    for index, path in enumerate(interleave(queues)):
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = split_post(raw) or ("", raw)
        new_date = (start - timedelta(minutes=index * args.spacing_minutes)).isoformat(timespec="minutes")
        updated_frontmatter = set_date(frontmatter, new_date)
        if updated_frontmatter == frontmatter:
            continue
        changed += 1
        print(f"{agency_prefix(path)} {new_date} {path.name}")
        if not args.dry_run:
            path.write_text(f"---{updated_frontmatter}---{body}", encoding="utf-8")

    print(f"\nrebalanced {changed} press post dates")


if __name__ == "__main__":
    main()
