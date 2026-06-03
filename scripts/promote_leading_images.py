"""Promote a post's leading Markdown image into frontmatter cover fields.

Some older posts have a good stock image at the top of the Markdown body but
still keep a generic picsum cover image in frontmatter. The static site builder
strips the leading body image, so this script preserves that better image as
the actual cover.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


POSTS_DIR = Path(__file__).resolve().parents[1] / "output" / "posts"


def _quote_yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _set_frontmatter_field(frontmatter: str, key: str, value: str) -> str:
    line = f"{key}: {_quote_yaml(value)}"
    pattern = rf"^{re.escape(key)}:\s*.*$"
    if re.search(pattern, frontmatter, flags=re.MULTILINE):
        return re.sub(pattern, line, frontmatter, flags=re.MULTILINE)
    return frontmatter.rstrip() + "\n" + line + "\n"


def promote_post(path: Path, dry_run: bool = False) -> bool:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return False
    parts = raw.split("---", 2)
    if len(parts) != 3:
        return False
    _, frontmatter, body = parts

    cover_match = re.search(r'^cover_image:\s*"?([^"\n]+)"?', frontmatter, flags=re.MULTILINE)
    cover_url = cover_match.group(1).strip() if cover_match else ""
    leading_match = re.match(r"\s*!\[([^\]]*)\]\(([^)]+)\)", body)
    if not leading_match:
        return False

    alt, image_url = leading_match.groups()
    image_url = image_url.strip()
    alt = alt.strip()
    if "picsum.photos" in image_url:
        return False
    if cover_url and "picsum.photos" not in cover_url:
        return False

    if dry_run:
        return True

    updated = _set_frontmatter_field(frontmatter, "cover_image", image_url)
    if alt:
        updated = _set_frontmatter_field(updated, "cover_image_alt", alt)
    path.write_text(f"---\n{updated.strip()}\n---{body}", encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        if promote_post(path, dry_run=args.dry_run):
            changed.append(path)

    verb = "would promote" if args.dry_run else "promoted"
    print(f"{verb} {len(changed)} posts")
    for path in changed:
        print(path.relative_to(POSTS_DIR.parent.parent))


if __name__ == "__main__":
    main()
