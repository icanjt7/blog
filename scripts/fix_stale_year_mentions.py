from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


RECENT_FROM = datetime(2026, 6, 1)
TARGET_YEAR = "2026"
TARGET_MONTH = "6월"

EXCLUDE_TITLE_PATTERNS = (
    r"2024년",
    r"2024\s*결과",
    r"2024\s*통계",
    r"2024\s*실태조사",
)

REPLACEMENTS = (
    (re.compile(r"2024년\s*0?6월\s*기준"), f"{TARGET_YEAR}년 {TARGET_MONTH} 기준"),
    (re.compile(r"2024년\s*0?6월\s*현재"), f"{TARGET_YEAR}년 {TARGET_MONTH} 현재"),
    (re.compile(r"2024년\s*0?6월\s*최신"), f"{TARGET_YEAR}년 {TARGET_MONTH} 최신"),
    (re.compile(r"2024년\s*0?6월\s*공식 자료"), f"{TARGET_YEAR}년 {TARGET_MONTH} 공식 자료"),
    (re.compile(r"2024년\s*0?6월\s*공식 안내"), f"{TARGET_YEAR}년 {TARGET_MONTH} 공식 안내"),
    (re.compile(r"2024년\s*0?6월\s*신청 전"), f"{TARGET_YEAR}년 {TARGET_MONTH} 신청 전"),
    (re.compile(r"2024년\s*0?6월\s*적용"), f"{TARGET_YEAR}년 {TARGET_MONTH} 적용"),
    (re.compile(r"2024년\s*0?6월\s*확대 적용"), f"{TARGET_YEAR}년 {TARGET_MONTH} 기준 적용"),
    (re.compile(r"2024년\s*0?6월\s*운영"), f"{TARGET_YEAR}년 {TARGET_MONTH} 운영"),
    (re.compile(r"2024년\s*0?6월\s*특별 체험"), f"{TARGET_YEAR}년 {TARGET_MONTH} 특별 체험"),
    (re.compile(r"2024년\s*0?6월\s*특례"), f"{TARGET_YEAR}년 {TARGET_MONTH} 특례"),
    (re.compile(r"2024년\s*0?6월\s*부터"), f"{TARGET_YEAR}년 {TARGET_MONTH} 현재"),
    (re.compile(r"2024년\s*0?6월\s*이후"), f"{TARGET_YEAR}년 {TARGET_MONTH} 현재"),
    (re.compile(r"2024년\s*0?6월\s*체결"), f"{TARGET_YEAR}년 {TARGET_MONTH} 체결"),
    (re.compile(r"2024년\s*0?6월\s*개최"), f"{TARGET_YEAR}년 {TARGET_MONTH} 개최"),
    (re.compile(r"2024년\s*0?6월(?=\s*\d{1,2}일)"), f"{TARGET_YEAR}년 {TARGET_MONTH}"),
    (re.compile(r"2024년\s*0?6월(?=에도)"), f"{TARGET_YEAR}년 {TARGET_MONTH}"),
    (re.compile(r"2024년\s*0?6월(?=~)"), f"{TARGET_YEAR}년 {TARGET_MONTH}"),
    (re.compile(r"2024년\s*0?6월(?=,)"), f"{TARGET_YEAR}년 {TARGET_MONTH}"),
    (re.compile(r"2024년\s*0?6월(?=\s*(?:\)|$))"), f"{TARGET_YEAR}년 {TARGET_MONTH}"),
    (re.compile(r"2024\.6\.15"), f"{TARGET_YEAR}.6.15"),
)


def frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---\n"):
        return {}
    end = markdown.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    for line in markdown[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("'\"")
    return data


def is_recent_post(markdown: str) -> bool:
    raw_date = frontmatter(markdown).get("date", "")
    if not raw_date:
        return False
    try:
        date = datetime.fromisoformat(raw_date)
    except ValueError:
        return False
    return date >= RECENT_FROM


def should_skip(markdown: str) -> bool:
    title = frontmatter(markdown).get("title", "")
    return any(re.search(pattern, title) for pattern in EXCLUDE_TITLE_PATTERNS)


def repair(markdown: str) -> tuple[str, int]:
    updated = markdown
    changes = 0
    for pattern, replacement in REPLACEMENTS:
        updated, count = pattern.subn(replacement, updated)
        changes += count
    return updated, changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-dir", default="output/posts")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed: list[tuple[Path, int]] = []
    for path in sorted(Path(args.posts_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not is_recent_post(text) or should_skip(text):
            continue
        updated, changes = repair(text)
        if not changes:
            continue
        changed.append((path, changes))
        if not args.dry_run:
            path.write_text(updated, encoding="utf-8")

    for path, changes in changed:
        print(f"{path}: {changes}")
    print(f"changed_files={len(changed)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
