#!/usr/bin/env python3
"""Remove only unmistakable short monthly/hash HTML shells from a build tree.

The command is dry-run by default. Pass ``--execute`` after reviewing the
candidate list. Source Markdown and long legacy articles are never touched.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote


HASH_HTML_RE = re.compile(r"-[a-f0-9]{8}\.html$", re.IGNORECASE)
MONTH_PREFIX_RE = re.compile(r"^\d{1,2}월(?:-|$)")
ENGLISH_CLEAN_SLUG_RE = re.compile(r"^[a-z0-9-]+$", re.IGNORECASE)
MAX_SHORT_SLUG_LENGTH = 9


def is_safe_garbage_candidate(path: Path) -> bool:
    """Return True only when every conservative garbage condition matches."""
    filename = unquote(path.name)

    # Condition 1: the filename must end in an opaque eight-character hash.
    hash_match = HASH_HTML_RE.search(filename)
    if not hash_match:
        return False

    prefix = filename[: hash_match.start()]

    # Condition 3: protect clean English slugs before evaluating deletion.
    if ENGLISH_CLEAN_SLUG_RE.fullmatch(prefix):
        return False

    # Condition 2: only very short slugs beginning with a numeric month qualify.
    if not MONTH_PREFIX_RE.match(prefix):
        return False
    compact_length = len(re.sub(r"[-_\s]", "", prefix))
    if compact_length > MAX_SHORT_SLUG_LENGTH:
        return False

    # Condition 3: explicit belt-and-suspenders protection for long mixed slugs.
    if compact_length >= 15:
        return False

    return True


def cleanup_build(root: Path, *, execute: bool = False) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Build directory does not exist: {root}")

    candidates: list[Path] = []
    for path in sorted(root.rglob("*.html")):
        if path.is_symlink() or not path.is_file():
            continue
        if is_safe_garbage_candidate(path):
            candidates.append(path)

    action = "DELETE" if execute else "DRY-RUN"
    for path in candidates:
        print(f"[{action}] {path.relative_to(root)}")
        if execute:
            path.unlink()

    print(f"{action}: {len(candidates)} safe garbage file(s)")
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("dist"))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete matched files. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    cleanup_build(args.root, execute=args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
