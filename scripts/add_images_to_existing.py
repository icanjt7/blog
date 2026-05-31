"""기존 포스트 frontmatter에 Picsum 커버 이미지를 소급 추가."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


def picsum_url(slug: str) -> str:
    seed = int(hashlib.md5(slug.encode()).hexdigest()[:8], 16) % 1000
    return f"https://picsum.photos/seed/{seed}/1200/630"


def patch_post(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return False
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return False
    _, frontmatter, body = parts
    if "cover_image:" in frontmatter:
        return False  # already has image
    slug = path.stem
    url = picsum_url(slug)
    frontmatter = frontmatter.rstrip("\n") + f'\ncover_image: "{url}"\n'
    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")
    return True


def main() -> None:
    posts_dir = Path(__file__).parent.parent / "output" / "posts"
    patched = 0
    for md in sorted(posts_dir.glob("*.md")):
        if patch_post(md):
            print(f"  + {md.name}")
            patched += 1
    print(f"\n{patched}개 포스트에 커버 이미지 추가 완료.")


if __name__ == "__main__":
    main()
